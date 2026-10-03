import asyncio
import json

import httpx
import pytest

from agent_dms.client import call, connect, service_url
from agent_dms.errors import DomainError
from agent_dms.mcp_server import INPUT_MODELS, TOOL_NAMES, configure_safe_logging, validate_bind
from conftest import error


async def test_real_two_clients_surface_workstream(h, peers, live):
    a, b, c = peers
    url, app = live
    async with connect(url, h.tokens[a]) as manager, connect(url, h.tokens[b]) as worker:
        tools = await manager.list_tools()
        assert {t.name for t in tools.tools} == set(TOOL_NAMES)
        assert all(t.annotations.idempotent_hint for t in tools.tools)
        assert len((await worker.list_prompts()).prompts) == 2
        assert (await worker.get_prompt("agent-dms-acla")).messages
        assert (await manager.list_resources()).resources[0].uri == "agent-dms://protocol"
        assert "untrusted" in (await manager.read_resource("agent-dms://protocol")).contents[0].text
        invalid = await manager.call_tool("dm_send", {"sender_id": c})
        assert invalid.is_error and invalid.structured_content["error"]["code"] == "VALIDATION_ERROR"
        roster = await call(manager, "agents_list", {"session_id": h.sessions[a]})
        assert {v["agent_id"] for v in roster["items"]} == {a, b, c}
        started = await call(manager, "workstream_start", {"session_id": h.sessions[a], "worker_agent_id": b, "goal": "Verify wire flow", "plan": "Run full revision loop", "idempotency_key": "wire-start"})
        ws = started["workstream"]["workstream_id"]
        steps = [(worker, b, "question"), (manager, a, "answer"), (worker, b, "complete"), (manager, a, "revise"), (worker, b, "complete"), (manager, a, "approve")]
        for revision, (session, actor, action) in enumerate(steps, 1):
            claim = await call(session, "inbox_next", {"session_id": h.sessions[actor], "idempotency_key": f"claim-{revision}"})
            result = await call(session, "workstream_transition", {"session_id": h.sessions[actor], "workstream_id": ws, "action": action, "text": f"Full report {action}", "expected_revision": revision, "claim_token": claim["claim_token"], "ack_message_id": claim["items"][-1]["message_id"], "idempotency_key": f"transition-{revision}"})
        assert result["workstream"]["state"] == "approved"
        assert result["workstream"]["round"] == 2
        stolen = await manager.call_tool("inbox_peek", {"session_id": h.sessions[b]})
        assert stolen.is_error and stolen.structured_content["error"]["code"] == "SESSION_REQUIRED"


async def test_wait_arrival_stale_recovery_revocation_cancellation(h, peers, live):
    a, b, _ = peers
    url, app = live
    async with connect(url, h.tokens[b]) as worker, connect(url, h.tokens[a]) as manager:
        empty = await call(worker, "inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 0})
        assert empty == {"notification_revision": 0, "available": 0, "changed": False}
        waiting = asyncio.create_task(call(worker, "inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 2}))
        await asyncio.sleep(0.1)
        sent = await call(manager, "dm_send", {"session_id": h.sessions[a], "to_agent_id": b, "body": "wire arrival", "idempotency_key": "wire-send"})
        assert (await waiting)["available"] == 1
        h.clock.advance(900_000)
        failed = await manager.call_tool("dm_send", {"session_id": h.sessions[a], "to_agent_id": b, "body": "stale", "idempotency_key": "stale"})
        assert failed.is_error and failed.structured_content["error"]["code"] == "STATUS_STALE"
        assert (await call(worker, "inbox_peek", {"session_id": h.sessions[b]}))["items"][0]["message_id"] == sent["message_id"]
        waiting = asyncio.create_task(call(worker, "inbox_wait", {"session_id": h.sessions[b], "after_revision": 1, "timeout_seconds": 25}))
        await asyncio.sleep(0.1)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        for _ in range(30):
            if not app.service.waiters:
                break
            await asyncio.sleep(0.02)
        assert not app.service.waiters
        waiting = asyncio.create_task(call(worker, "inbox_wait", {"session_id": h.sessions[b], "after_revision": 1, "timeout_seconds": 2}))
        await asyncio.sleep(0.1)
        h.service.revoke(b)
        with pytest.raises(DomainError) as exc:
            await waiting
        assert exc.value.code == "UNAUTHENTICATED"
        async with httpx.AsyncClient() as http:
            response = await http.post(url, headers={"Authorization": "Bearer " + h.tokens[b]}, json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
        assert response.status_code == 401


async def test_http_boundaries_and_capacity(h, peers, live):
    a, b, _ = peers
    url, app = live
    auth = {"Authorization": "Bearer " + h.tokens[a]}
    async with httpx.AsyncClient() as http:
        assert (await http.get(url.replace("/mcp", "/health/live"))).json() == {"ok": True}
        assert (await http.get(url.replace("/mcp", "/health/ready"))).json() == {"ok": True}
        for method in ("get", "post", "delete"):
            assert (await getattr(http, method)(url)).status_code == 401
        assert (await http.post(url, headers={**auth, "Host": "evil.example"}, json={})).status_code == 403
        assert (await http.post(url, headers={**auth, "Origin": "https://evil.example"}, json={})).status_code == 403
        oversized = await http.post(url, headers=auth, content=b"x" * (256 * 1024 + 1))
        assert oversized.status_code == 413
        app.capacity = 0
        limited = await http.post(url, headers=auth, json={})
        assert limited.status_code == 429 and limited.json()["error"]["retryable"]
        app.capacity = 64
        sentinel = "PRIVATE-BODY-SENTINEL"
        invalid = await http.post(url, headers={**auth, "Content-Type": "application/json", "Accept": "application/json,text/event-stream"}, json={"jsonrpc": "bad", "id": sentinel})
        assert invalid.status_code == 400 and sentinel not in invalid.text
    async with connect(url, h.tokens[b]) as worker:
        waits = [asyncio.create_task(call(worker, "inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 0.5})) for _ in range(2)]
        await asyncio.sleep(0.1)
        third = await worker.call_tool("inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 0.5})
        assert third.is_error and third.structured_content["error"]["code"] == "CAPACITY_LIMIT"
        await asyncio.gather(*waits)
    error("VALIDATION_ERROR", lambda: validate_bind("0.0.0.0", False, None))
    error("VALIDATION_ERROR", lambda: validate_bind("0.0.0.0", True, None))
    validate_bind("0.0.0.0", True, ["service.example"])
    error("VALIDATION_ERROR", lambda: service_url("http://user:secret@localhost/mcp"))


async def test_sanitized_unexpected_tool_exception(h, peers, live, monkeypatch, capsys):
    a, _, _ = peers
    url, app = live
    configure_safe_logging()
    secret = h.tokens[a]
    body = "PRIVATE-EXCEPTION-BODY"
    original = app.service.call
    def fault(*args):
        raise RuntimeError(secret + body)
    monkeypatch.setattr(app.service, "call", fault)
    async with connect(url, secret) as session:
        result = await session.call_tool("agent_whoami", {})
        rendered = json.dumps(result.model_dump())
        assert result.is_error and "INTERNAL_ERROR" in rendered
        assert secret not in rendered and body not in rendered
    assert secret not in capsys.readouterr().err
    monkeypatch.setattr(app.service, "call", original)

async def _wait_for_registry(app, count, timeout=2):
    deadline = asyncio.get_running_loop().time() + timeout
    while len(app.registry.entries) != count:
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.01)


async def test_m01_wire_cancel_collision_isolation_and_capacity(h, peers, live):
    from mcp import types
    a, b, _ = peers
    url, app = live
    async with connect(url, h.tokens[b]) as original, connect(url, h.tokens[b]) as duplicate, connect(url, h.tokens[a]) as foreign:
        wait_args = {"session_id": h.sessions[b], "timeout_seconds": 25}
        waiting = asyncio.create_task(call(original, "inbox_wait", wait_args))
        await _wait_for_registry(app, 1)
        request_id = next(iter(app.registry.entries))[3]
        cancelled = types.CancelledNotification(params=types.CancelledNotificationParams(request_id=request_id))
        await foreign.send_notification(cancelled)
        await asyncio.sleep(0.1)
        assert len(app.registry.entries) == 1 and not waiting.done()
        newer = await duplicate.call_tool("inbox_wait", wait_args)
        assert newer.is_error and newer.structured_content["error"]["code"] == "CAPACITY_LIMIT"
        assert newer.structured_content["error"]["retryable"]
        assert len(app.registry.entries) == 1
        started = asyncio.get_running_loop().time()
        waiting.cancel()  # Official SDK courtesy notifications/cancelled, over a separate POST.
        with pytest.raises(asyncio.CancelledError):
            await waiting
        await _wait_for_registry(app, 0)
        assert not app.service.waiters and asyncio.get_running_loop().time() - started < 2
        await original.send_notification(cancelled)
        await original.send_notification(cancelled)  # Exact no-op after cleanup.
        assert (await call(original, "inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 0}))["available"] == 0
        sent = await call(foreign, "dm_send", {"session_id": h.sessions[a], "to_agent_id": b, "body": "survives cancelled wait", "idempotency_key": "cancel-arrival"})
        claim = await call(original, "inbox_next", {"session_id": h.sessions[b], "idempotency_key": "after-cancel"})
        assert claim["items"][0]["message_id"] == sent["message_id"]


async def test_m01_typed_id_timeout_error_takeover_and_disconnect(h, peers, live, monkeypatch):
    from mcp import types
    a, b, _ = peers
    url, app = live
    auth = {"Authorization": "Bearer " + h.tokens[b], "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    # Build wire messages with official SDK types, preserving the exact ID type.
    request = types.JSONRPCRequest(jsonrpc="2.0", id=7, method="tools/call", params=types.CallToolRequestParams(name="inbox_wait", arguments={"session_id": h.sessions[b], "timeout_seconds": 0.4}).model_dump(by_alias=True))
    async with httpx.AsyncClient() as http:
        pending = asyncio.create_task(http.post(url, headers=auth, content=request.model_dump_json(by_alias=True)))
        await _wait_for_registry(app, 1)
        notification = types.JSONRPCNotification(jsonrpc="2.0", method="notifications/cancelled", params=types.CancelledNotificationParams(request_id="7").model_dump(by_alias=True))
        assert (await http.post(url, headers=auth, content=notification.model_dump_json(by_alias=True))).status_code == 202
        await asyncio.sleep(0.1)
        assert len(app.registry.entries) == 1
        assert (await pending).status_code == 200
        await _wait_for_registry(app, 0)
        assert not app.service.waiters
    async with connect(url, h.tokens[b]) as worker:
        original_wait = app.service.wait
        async def fault(*args, **kwargs):
            raise RuntimeError("private body must not leak")
        monkeypatch.setattr(app.service, "wait", fault)
        result = await worker.call_tool("inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 1})
        assert result.is_error and result.structured_content["error"]["code"] == "INTERNAL_ERROR"
        assert not app.registry.entries
        monkeypatch.setattr(app.service, "wait", original_wait)
        waiting = asyncio.create_task(call(worker, "inbox_wait", {"session_id": h.sessions[b], "timeout_seconds": 25}))
        await _wait_for_registry(app, 1)
        h.open(b, "replacement", takeover=True)
        with pytest.raises(DomainError) as exc:
            await waiting
        assert exc.value.code == "SESSION_SUPERSEDED"
        await _wait_for_registry(app, 0)
        assert not app.service.waiters
    # A raw HTTP client's disconnect cancels its exact SDK handler and releases capacity.
    http = httpx.AsyncClient()
    request.params["arguments"]["session_id"] = h.sessions[b]
    request.params["arguments"]["timeout_seconds"] = 25
    pending = asyncio.create_task(http.post(url, headers=auth, content=request.model_dump_json(by_alias=True)))
    await _wait_for_registry(app, 1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await http.aclose()
    await _wait_for_registry(app, 0)
    assert not app.service.waiters

async def test_two_process_restart_e2e(h):
    import socket
    import sys
    from pathlib import Path
    from agent_dms.config import private_write
    a, b = h.add("Process Manager"), h.add("Process Worker")
    socket_probe = socket.socket()
    socket_probe.bind(("127.0.0.1", 0))
    port = socket_probe.getsockname()[1]
    socket_probe.close()
    url = f"http://127.0.0.1:{port}/mcp"
    async def start_daemon():
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "agent_dms", "serve", "--data-dir", str(h.data_dir), "--port", str(port), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        async with httpx.AsyncClient() as http:
            for _ in range(200):
                assert process.returncode is None
                try:
                    if (await http.get(url.replace("/mcp", "/health/ready"))).status_code == 200:
                        return process
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.02)
        raise AssertionError("isolated daemon did not become ready")
    daemon = await start_daemon()
    clients = {}
    session_ids = {}
    counters = {a: 0, b: 0}
    try:
        for actor in (a, b):
            token_file = h.data_dir / f"process-{actor}.token"
            private_write(token_file, h.tokens[actor])
            clients[actor] = await asyncio.create_subprocess_exec(sys.executable, "tests/process_client.py", url, str(token_file), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        async def run(actor, tool, **args):
            if tool not in {"agent_whoami", "session_open"}:
                args.setdefault("session_id", session_ids[actor])
            from agent_dms.service import MUTATING
            if tool in MUTATING:
                counters[actor] += 1
                args.setdefault("idempotency_key", f"process-{counters[actor]}")
            client = clients[actor]
            client.stdin.write((json.dumps({"tool": tool, "arguments": args}) + "\n").encode())
            await client.stdin.drain()
            envelope = json.loads(await asyncio.wait_for(client.stdout.readline(), 8))
            assert envelope["ok"], envelope.get("error")
            return envelope["data"]
        for actor in (a, b):
            opened = await run(actor, "session_open", client_session_key=f"process-conversation-{actor}", status="Checking durable messages through restart", availability="working")
            session_ids[actor] = opened["session_id"]
        assert len((await run(a, "agents_list"))["items"]) == 2
        sent = await run(a, "dm_send", to_agent_id=b, body="Offline delivery survives restart", idempotency_key="restart-send")
        await run(b, "inbox_peek")  # Read does not handle.
        daemon.terminate()
        await asyncio.wait_for(daemon.wait(), 5)
        daemon = await start_daemon()
        assert (await run(a, "dm_send", to_agent_id=b, body="Offline delivery survives restart", idempotency_key="restart-send"))["message_id"] == sent["message_id"]
        claim = await run(b, "inbox_next")
        reply = await run(b, "dm_reply", message_id=sent["message_id"], body="Received after reconnect", acknowledge_parent=True, claim_token=claim["claim_token"])
        claim = await run(a, "inbox_next")
        assert claim["items"][0]["message_id"] == reply["message_id"]
        await run(a, "inbox_ack", claim_token=claim["claim_token"], message_ids=[reply["message_id"]])
        started = await run(a, "workstream_start", worker_agent_id=b, goal="Complete full workflow", plan="Approved implementation plan")
        ws = started["workstream"]["workstream_id"]
        for revision, (actor, action) in enumerate([(b, "question"), (a, "answer"), (b, "complete"), (a, "revise"), (b, "complete"), (a, "approve")], 1):
            claim = await run(actor, "inbox_next")
            result = await run(actor, "workstream_transition", workstream_id=ws, action=action, text=f"Complete {action} content", expected_revision=revision, ack_message_id=claim["items"][-1]["message_id"], claim_token=claim["claim_token"])
            if action == "revise":
                daemon.terminate()
                await asyncio.wait_for(daemon.wait(), 5)
                daemon = await start_daemon()
        assert result["workstream"]["state"] == "approved" and result["workstream"]["round"] == 2
        assert len((await run(a, "thread_read", thread_id=started["workstream"]["thread_id"]))["items"]) == 7
        assert (await run(b, "inbox_peek"))["counts"]["pending"] == 1  # Approval remains until explicit handling.
    finally:
        for client in clients.values():
            client.stdin.close()
            await asyncio.wait_for(client.wait(), 5)
        if daemon.returncode is None:
            daemon.terminate()
            await asyncio.wait_for(daemon.wait(), 5)


async def test_actual_64_request_capacity(h, live):
    from mcp import types
    url, app = live
    agents = [h.add(f"Capacity {i}") for i in range(32)]
    for agent in agents:
        h.open(agent)
    http = httpx.AsyncClient(limits=httpx.Limits(max_connections=70, max_keepalive_connections=70))
    pending = []
    try:
        for actor in agents:
            for request_id in (1, 2):
                request = types.JSONRPCRequest(jsonrpc="2.0", id=request_id, method="tools/call", params=types.CallToolRequestParams(name="inbox_wait", arguments={"session_id": h.sessions[actor], "timeout_seconds": 25}).model_dump(by_alias=True))
                pending.append(asyncio.create_task(http.post(url, headers={"Authorization": "Bearer " + h.tokens[actor], "Accept": "application/json,text/event-stream", "Content-Type": "application/json"}, content=request.model_dump_json(by_alias=True))))
        await _wait_for_registry(app, 64, timeout=4)
        response = await http.post(url, headers={"Authorization": "Bearer " + h.tokens[agents[0]]}, json={})
        assert response.status_code == 429 and response.json()["error"]["code"] == "CAPACITY_LIMIT"
        assert app.active == 64 and len(app.registry.entries) == 64
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await http.aclose()
    await _wait_for_registry(app, 0)
    assert not app.service.waiters
