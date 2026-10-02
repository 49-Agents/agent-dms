from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_dms.errors import DomainError
from agent_dms.models import status_text
from conftest import error


@pytest.mark.parametrize("value,normalized,words", [("one", "one", 1), (" ".join(["word"] * 30), " ".join(["word"] * 30), 30), ("  Cafe\u0301\u2003work\nnow ", "Café work now", 3), ("x" * 500, "x" * 500, 1)])
def test_status_accept(value, normalized, words):
    assert status_text(value) == (normalized, words)


@pytest.mark.parametrize("value", ["", " \t\n", " ".join(["w"] * 31), "x" * 501, "bad\x00text", "bad\u200btext"])
def test_status_reject(value):
    error("VALIDATION_ERROR", lambda: status_text(value))


def test_revision_concurrency_age_heartbeat(h, peers):
    a, b, _ = peers
    def update(i):
        try:
            return h.call(a, "status_set", status=f"Work {i}", availability="working", expected_revision=1)["status_revision"]
        except DomainError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(update, (1, 2)))
    assert sorted(map(str, results)) == ["2", "REVISION_CONFLICT"]
    before = h.call(b, "agent_get", agent_id=a)
    h.clock.advance(900_000)
    h.call(a, "session_heartbeat")
    view = h.call(b, "agent_get", agent_id=a)
    assert view["presence"] == "online" and not view["status_fresh"]
    assert view["status_updated_at"] == before["status_updated_at"]
    error("STATUS_STALE", lambda: h.send(a, b))
    h.call(a, "status_set", status=view["status"], availability="blocked", expected_revision=2)
    assert h.call(b, "agent_get", agent_id=a)["status_fresh"]
    assert h.call(b, "agents_list")["filters"] == {"include_offline": False, "query": None}


def test_takeover_tombstones_reconnect_close(h, peers):
    a, b, _ = peers
    first = h.sessions[a]
    error("SESSION_CONFLICT", lambda: h.open(a, "other"))
    second = h.open(a, "other", takeover=True)["session_id"]
    error("SESSION_SUPERSEDED", lambda: h.call(a, "session_close", session_id=first))
    error("SESSION_SUPERSEDED", lambda: h.open(a, a, takeover=True))
    h.clock.advance(900_001)
    assert h.open(a, "other")["session_id"] == second
    h.call(a, "status_set", status="Changed work", availability="idle", expected_revision=2)
    assert h.open(a, "other")["session_id"] == second
    assert h.call(a, "agent_get", agent_id=a)["status"] == "Changed work"
    h.call(a, "session_close")
    h.call(a, "session_close")
    error("SESSION_SUPERSEDED", lambda: h.open(a, "other"))
    assert h.open(a, "third")["generation"] == 3


def test_open_retry_authority_and_offline_directory(h, peers):
    a, b, c = peers
    args = dict(client_session_key="new", status="Working", availability="working", takeover=True, idempotency_key="saved-open")
    opened = h.service.call(h.tokens[a], "session_open", args)
    assert h.service.call(h.tokens[a], "session_open", args) == opened
    h.open(a, "newer", takeover=True)
    error("SESSION_SUPERSEDED", lambda: h.service.call(h.tokens[a], "session_open", args))
    h.clock.advance(90_000)
    online = h.call(b, "agents_list")["items"]
    assert [v["agent_id"] for v in online] == [b]
    assert len(h.call(b, "agents_list", include_offline=True)["items"]) == 3
    assert h.call(b, "agent_get", agent_id=a)["presence"] == "offline"


def test_saved_session_open_replay_renews_contact_without_changing_receipt_or_status(h, peers):
    a, b, _ = peers
    args = dict(client_session_key='saved-conversation', status='Initial assertion', availability='working',
                takeover=True, idempotency_key='saved-contact')
    opened = h.service.call(h.tokens[a], 'session_open', args)
    h.sessions[a] = opened['session_id']
    h.call(a, 'status_set', status='Newer assertion must remain', availability='blocked', expected_revision=2)
    with h.service.store.transaction() as conn:
        status = dict(conn.execute('SELECT * FROM statuses WHERE agent_id=?', (a,)).fetchone())
        receipt = dict(conn.execute("SELECT * FROM idempotency WHERE principal_id=? AND operation='session_open' AND key='saved-contact'", (a,)).fetchone())
    h.clock.advance(900_001)
    assert h.call(b, 'agent_get', agent_id=a)['presence'] == 'offline'
    assert h.service.call(h.tokens[a], 'session_open', args) == opened
    with h.service.store.transaction() as conn:
        session = dict(conn.execute('SELECT * FROM sessions WHERE id=?', (opened['session_id'],)).fetchone())
        assert dict(conn.execute('SELECT * FROM statuses WHERE agent_id=?', (a,)).fetchone()) == status
        assert dict(conn.execute("SELECT * FROM idempotency WHERE principal_id=? AND operation='session_open' AND key='saved-contact'", (a,)).fetchone()) == receipt
    assert session['last_seen_at'] == h.clock()
    assert session['lease_until'] == h.clock() + 900_000
    view = h.call(b, 'agent_get', agent_id=a)
    assert view['presence'] == 'online' and not view['status_fresh']
    assert view['status'] == 'Newer assertion must remain'


@pytest.mark.parametrize('invalid,code', [('conflicting', 'IDEMPOTENCY_CONFLICT'), ('closed', 'SESSION_REQUIRED'),
                                        ('superseded', 'SESSION_SUPERSEDED'), ('revoked', 'UNAUTHENTICATED')])
def test_failed_saved_session_open_replay_never_touches_sessions(h, invalid, code):
    a = h.add('agent')
    args = dict(client_session_key='stable', status='Original status', availability='working', idempotency_key='saved')
    h.sessions[a] = h.service.call(h.tokens[a], 'session_open', args)['session_id']
    if invalid == 'conflicting':
        args = {**args, 'status': 'Different input'}
    elif invalid == 'closed':
        h.call(a, 'session_close')
    elif invalid == 'superseded':
        h.open(a, 'replacement', takeover=True)
    elif invalid == 'revoked':
        h.service.revoke(a)
    with h.service.store.transaction() as conn:
        before = [dict(row) for row in conn.execute('SELECT * FROM sessions ORDER BY generation')]
    h.clock.advance(900_001)
    error(code, lambda: h.service.call(h.tokens[a], 'session_open', args))
    with h.service.store.transaction() as conn:
        assert [dict(row) for row in conn.execute('SELECT * FROM sessions ORDER BY generation')] == before
