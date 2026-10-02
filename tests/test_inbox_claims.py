from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_dms.service import Service
from agent_dms.storage import Store
from conftest import error


def test_reads_fifo_concurrent_exact_claims(h, peers):
    a, b, c = peers
    sent = [h.send(a, b) for _ in range(6)]
    h.call(b, "thread_read", thread_id=sent[0]["thread_id"])
    h.call(b, "inbox_hint", after_revision=0)
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 6
    with ThreadPoolExecutor(2) as pool:
        batches = list(pool.map(lambda i: h.call(b, "inbox_next", limit=3, idempotency_key=f"claim-{i}"), (1, 2)))
    ids = [{m["message_id"] for m in batch["items"]} for batch in batches]
    assert not ids[0] & ids[1]
    assert ids[0] | ids[1] == {m["message_id"] for m in sent}
    assert sorted(sorted(m["seq"] for m in batch["items"]) for batch in batches) == [[1, 2, 3], [4, 5, 6]]
    assert h.call(b, "inbox_next")["claim_token"] is None
    assert h.call(b, "inbox_peek")["counts"] == {"pending": 6, "available": 0, "claimed": 6}


def test_ack_atomic_partial_first_outcome_release_renew_restart(h, peers):
    a, b, c = peers
    sent = [h.send(a, b) for _ in range(3)]
    foreign = h.send(a, c)
    batch = h.call(b, "inbox_next", idempotency_key="batch")
    token = batch["claim_token"]
    error("CLAIM_INVALID", lambda: h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[0]["message_id"], foreign["message_id"]]))
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 3
    ack = h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[0]["message_id"]], outcome="Handled", idempotency_key="ack")
    h.clock.advance(1000)
    assert h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[0]["message_id"]], outcome="Handled", idempotency_key="ack") == ack
    assert h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[0]["message_id"]], outcome="Handled") == ack
    error("CLAIM_INVALID", lambda: h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[0]["message_id"]], outcome="Changed"))
    h.call(b, "inbox_renew", claim_token=token)
    released = h.call(b, "inbox_release", claim_token=token, message_ids=[sent[1]["message_id"]])
    assert released["counts"] == {"pending": 2, "available": 1, "claimed": 1}
    h.service = Service(Store(h.data_dir, h.clock))
    h.clock.advance(900_001)
    replay = h.call(b, "inbox_next", idempotency_key="batch")
    assert not replay["claim_active"] and replay["claim_token"] == token
    error("CLAIM_EXPIRED", lambda: h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[2]["message_id"]]))
    next_batch = h.call(b, "inbox_next")
    assert [m["message_id"] for m in next_batch["items"]] == [s["message_id"] for s in sent[1:]]
    assert h.call(b, "inbox_ack", claim_token=token, message_ids=[sent[0]["message_id"]], outcome="Handled") == ack


def test_reply_ack_rollback_retry_takeover(h, peers, monkeypatch):
    a, b, _ = peers
    sent = h.send(a, b)
    batch = h.call(b, "inbox_next")
    args = dict(message_id=sent["message_id"], body="done", acknowledge_parent=True, claim_token=batch["claim_token"], idempotency_key="reply")
    original = h.service.emit_message
    def fault(*args, **kwargs):
        raise RuntimeError("send after ACK fails")
    monkeypatch.setattr(h.service, "emit_message", fault)
    with pytest.raises(RuntimeError):
        h.call(b, "dm_reply", **args)
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 1
    monkeypatch.setattr(h.service, "emit_message", original)
    result = h.call(b, "dm_reply", **args)
    assert h.call(b, "dm_reply", **args) == result
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 0
    assert h.call(a, "inbox_peek")["counts"]["pending"] == 1
    new_message = h.send(a, b)
    claim = h.call(b, "inbox_next")
    old = h.sessions[b]
    h.open(b, "takeover", takeover=True)
    error("SESSION_SUPERSEDED", lambda: h.call(b, "inbox_ack", session_id=old, claim_token=claim["claim_token"], message_ids=[new_message["message_id"]]))
    assert h.call(b, "inbox_next")["items"][0]["message_id"] == new_message["message_id"]


def test_ack_transaction_fault(h, peers):
    a, b, _ = peers
    sent = [h.send(a, b) for _ in range(2)]
    claim = h.call(b, "inbox_next")
    with h.service.store.transaction() as conn:
        conn.execute("CREATE TRIGGER ack_fault BEFORE INSERT ON ack_receipts BEGIN SELECT RAISE(ABORT,'fault'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        h.call(b, "inbox_ack", claim_token=claim["claim_token"], message_ids=[m["message_id"] for m in sent])
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 2
    with h.service.store.transaction() as conn:
        conn.execute("DROP TRIGGER ack_fault")
    h.call(b, "inbox_ack", claim_token=claim["claim_token"], message_ids=[m["message_id"] for m in sent])
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 0
