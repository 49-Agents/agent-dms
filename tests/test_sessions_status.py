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
