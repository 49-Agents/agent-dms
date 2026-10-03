import pytest

from conftest import error


def test_full_role_revision_loop(h, peers):
    a, b, c = peers
    started = h.call(a, "workstream_start", worker_agent_id=b, goal="Implement", plan="Full approved plan", idempotency_key="start")
    assert h.call(a, "workstream_start", worker_agent_id=b, goal="Implement", plan="Full approved plan", idempotency_key="start") == started
    workstream_id = started["workstream"]["workstream_id"]
    sequence = [(b, "question", "blocked", 1), (a, "answer", "working", 1), (b, "complete", "awaiting_review", 1), (a, "revise", "working", 2), (b, "complete", "awaiting_review", 2), (a, "approve", "approved", 2)]
    revision = 1
    for actor, action, state, round in sequence:
        batch = h.call(actor, "inbox_next")
        parent = batch["items"][-1]["message_id"]
        args = dict(workstream_id=workstream_id, action=action, text=f"Full {action} text", expected_revision=revision, ack_message_id=parent, claim_token=batch["claim_token"], idempotency_key=f"step-{revision}")
        result = h.call(actor, "workstream_transition", **args)
        assert h.call(actor, "workstream_transition", **args) == result
        revision += 1
        assert result["workstream"]["state"] == state
        assert result["workstream"]["round"] == round
        assert result["workstream"]["revision"] == revision
    assert len(h.call(a, "thread_read", thread_id=started["workstream"]["thread_id"])["items"]) == 7
    events = h.call(a, "workstream_get", workstream_id=workstream_id)["items"]
    assert len(events) == 7
    error("INVALID_TRANSITION", lambda: h.call(b, "workstream_transition", workstream_id=workstream_id, action="complete", text="late", expected_revision=7))
    error("NOT_FOUND", lambda: h.call(c, "workstream_get", workstream_id=workstream_id))


def test_invalid_transitions_and_combined_limit(h, peers, monkeypatch):
    a, b, c = peers
    error("VALIDATION_ERROR", lambda: h.call(a, "workstream_start", worker_agent_id=b, goal="g" * 1000, plan="p" * 16000))
    started = h.call(a, "workstream_start", worker_agent_id=b, goal="goal", plan="plan")
    ws = started["workstream"]["workstream_id"]
    error("INVALID_TRANSITION", lambda: h.call(a, "workstream_transition", workstream_id=ws, action="complete", text="bad", expected_revision=1))
    error("REVISION_CONFLICT", lambda: h.call(b, "workstream_transition", workstream_id=ws, action="complete", text="bad", expected_revision=0))
    h.send(b, a, "ordinary completion metadata", thread_id=started["workstream"]["thread_id"], kind="completion")
    assert h.call(a, "workstream_get", workstream_id=ws)["workstream"]["state"] == "working"
    claim = h.call(b, "inbox_next")
    original = h.service.emit_message
    def fault(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected workstream failure")
    monkeypatch.setattr(h.service, "emit_message", fault)
    args = dict(workstream_id=ws, action="question", text="blocker", expected_revision=1, ack_message_id=started["message"]["message_id"], claim_token=claim["claim_token"], idempotency_key="question")
    with pytest.raises(RuntimeError):
        h.call(b, "workstream_transition", **args)
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 1
    assert h.call(a, "workstream_get", workstream_id=ws)["workstream"]["revision"] == 1
    monkeypatch.setattr(h.service, "emit_message", original)
    h.call(b, "workstream_transition", **args)
    error("INVALID_TRANSITION", lambda: h.call(b, "workstream_transition", workstream_id=ws, action="complete", text="blocked", expected_revision=2))
