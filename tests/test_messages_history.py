import sqlite3

import pytest

from agent_dms.service import Service
from agent_dms.storage import Store
from conftest import error


def test_send_reply_retry_offline_persistence(h, peers):
    a, b, c = peers
    h.call(b, "session_close")
    sent = h.send(a, b, "  preserve original\ntext  ", idempotency_key="send")
    h.clock.advance(900_001)
    assert h.send(a, b, "  preserve original\ntext  ", idempotency_key="send") == sent
    error("IDEMPOTENCY_CONFLICT", lambda: h.send(a, b, "different", idempotency_key="send"))
    h.open(b, "reconnect")
    assert h.call(b, "inbox_peek")["items"][0]["body"] == "  preserve original\ntext  "
    replied = h.call(b, "dm_reply", message_id=sent["message_id"], body="Reply")
    assert replied["reply_to"] == sent["message_id"]
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 1
    h.service = Service(Store(h.data_dir, h.clock))
    history = h.call(b, "thread_read", thread_id=sent["thread_id"])["items"]
    assert [m["message_id"] for m in history] == [sent["message_id"], replied["message_id"]]
    assert history[0]["created_at"] == sent["created_at"]


def test_authorization_cursors_stable_pass(h, peers):
    a, b, c = peers
    first = h.send(a, b)
    for i in range(5):
        h.send(a, b, str(i), thread_id=first["thread_id"])
    for op, args in [("thread_read", {"thread_id": first["thread_id"]}), ("dm_reply", {"message_id": first["message_id"], "body": "leak"}), ("dm_send", {"to_agent_id": a, "thread_id": first["thread_id"], "body": "leak"})]:
        error("NOT_FOUND", lambda op=op, args=args: h.call(c, op, **args))
    page = h.call(b, "thread_read", thread_id=first["thread_id"], limit=2)
    cursor = page["cursor"]
    error("VALIDATION_ERROR", lambda: h.call(b, "thread_read", thread_id=first["thread_id"], cursor=cursor[:-5] + "abcde"))
    error("VALIDATION_ERROR", lambda: h.call(a, "thread_read", thread_id=first["thread_id"], cursor=cursor))
    other = h.send(a, b)
    error("VALIDATION_ERROR", lambda: h.call(b, "thread_read", thread_id=other["thread_id"], cursor=cursor))
    later = h.send(a, b, "arrival", thread_id=first["thread_id"])
    seen = page["items"]
    while page["cursor"]:
        page = h.call(b, "thread_read", thread_id=first["thread_id"], limit=2, cursor=page["cursor"])
        seen += page["items"]
    assert len(seen) == len({m["message_id"] for m in seen}) == 6
    assert later["message_id"] not in {m["message_id"] for m in seen}
    assert len(h.call(b, "thread_read", thread_id=first["thread_id"])["items"]) == 7
    roster = h.call(a, "agents_list", include_offline=True, limit=1)
    error("VALIDATION_ERROR", lambda: h.call(a, "agents_list", cursor=roster["cursor"], query="declared"))


def test_send_transaction_rollback_and_lost_response(h, peers, monkeypatch):
    a, b, _ = peers
    original = h.service.emit_message
    def injected(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("response fault before commit")
    monkeypatch.setattr(h.service, "emit_message", injected)
    with pytest.raises(RuntimeError):
        h.send(a, b, idempotency_key="fault")
    with h.service.store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM deliveries").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM threads").fetchone()[0] == 0
    monkeypatch.setattr(h.service, "emit_message", original)
    intended = h.send(a, b, idempotency_key="fault")
    # Simulate a response discarded after a committed transaction; retry the exact key.
    replay = h.send(a, b, idempotency_key="fault")
    assert replay == intended
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 1
