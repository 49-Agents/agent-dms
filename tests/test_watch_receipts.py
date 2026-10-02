import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from agent_dms.errors import DomainError
from agent_dms.notification_receipts import ReceiptLedger
from agent_dms.watch import CodexSink, FIXED_NUDGE, StdoutSink, dispatch_hint, exact_uuid
from conftest import Clock, error


class Sink:
    def __init__(self, state="emitted"):
        self.calls = 0
        self.state = state

    def dispatch(self):
        self.calls += 1
        return self.state


def test_empty_unchanged_many_pending_captured_revision(tmp_path):
    sink = Sink()
    with ReceiptLedger(tmp_path / "ledger" / "receipts.sqlite3") as ledger:
        error("CAPACITY_LIMIT", lambda: ReceiptLedger(ledger.path).__enter__())
        for hint in [{"notification_revision": 0, "available": 0}, {"notification_revision": 1, "available": 0}]:
            assert dispatch_hint(ledger, "target", "agent", "session", None, hint, sink) is None
        assert ledger.list() == [] and sink.calls == 0
        first = dispatch_hint(ledger, "target", "agent", "session", None, {"notification_revision": 101, "available": 101}, sink)
        assert first["state"] == "emitted" and sink.calls == 1
        assert dispatch_hint(ledger, "target", "agent", "session", None, {"notification_revision": 101, "available": 101}, sink) is None
        assert ledger.accepted_revision("target") == 101
        # Arrival while a sink is dispatching must not be absorbed into the captured receipt.
        receipt = ledger.next_receipt("target", "agent", "session", None, 102, 102)
        ledger.dispatching(receipt["id"])
        ledger.finish(receipt["id"], "accepted")
        assert ledger.accepted_revision("target") == 102
        later = dispatch_hint(ledger, "target", "agent", "session", None, {"notification_revision": 103, "available": 103}, sink)
        assert later["revision"] == 103 and sink.calls == 2


def test_pre_spawn_retry_uncertain_restart_resolution(tmp_path):
    clock = Clock()
    path = tmp_path / "ledger" / "receipts.sqlite3"
    with ReceiptLedger(path, clock) as ledger:
        no_start = Sink("not_started")
        receipt = dispatch_hint(ledger, "t", "a", "s", None, {"notification_revision": 1, "available": 1}, no_start)
        assert receipt["state"] == "not_started"
        assert ledger.next_receipt("t", "a", "s", None, 2, 2) is None
        clock.advance(60_000)
        retry = ledger.next_receipt("t", "a", "s", None, 2, 2)
        assert retry["id"] == receipt["id"] and retry["revision"] == 1
        ledger.dispatching(retry["id"])
        # Simulate process death after persisted dispatching.
    with ReceiptLedger(path, clock) as ledger:
        assert ledger.get(receipt["id"])["state"] == "uncertain"
        assert ledger.next_receipt("t", "a", "s", None, 3, 3) is None
        ledger.resolve(receipt["id"], False, "Operator established no external effect")
        retry = ledger.next_receipt("t", "a", "s", None, 3, 3)
        assert retry["id"] == receipt["id"]
        ledger.dispatching(retry["id"])
        ledger.finish(retry["id"], "uncertain")
        ledger.resolve(retry["id"], True, "Operator confirmed delivery")
        assert ledger.accepted_revision("t") == 1
        assert ledger.next_receipt("t", "a", "s", None, 3, 3)["revision"] == 3


@pytest.mark.parametrize("behavior,expected", [("success", "accepted"), ("nonzero", "uncertain"), ("timeout", "uncertain")])
def test_actual_queue_subprocess_fixed_argv(tmp_path, monkeypatch, behavior, expected):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "argv.json"
    fake = bindir / "codex"
    fake.write_text('''#!/usr/bin/python3
import json,os,sys,time
if sys.argv[1:] == ['queue','--help']:
    print('--thread --message')
    raise SystemExit(0)
open(os.environ['QUEUE_TEST_LOG'],'w').write(json.dumps({'argv':sys.argv[1:],'cwd':os.getcwd()}))
if os.environ['QUEUE_TEST_BEHAVIOR']=='timeout': time.sleep(10)
raise SystemExit(1 if os.environ['QUEUE_TEST_BEHAVIOR']=='nonzero' else 0)
''')
    fake.chmod(0o700)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("QUEUE_TEST_LOG", str(log))
    monkeypatch.setenv("QUEUE_TEST_BEHAVIOR", behavior)
    thread = str(uuid4())
    with ReceiptLedger(tmp_path / "ledger" / "receipts.sqlite3") as ledger:
        receipt = dispatch_hint(ledger, "t", "a", "s", thread, {"notification_revision": 1, "available": 1}, CodexSink(thread, tmp_path, timeout=0.1))
        assert receipt["state"] == expected
        logged = json.loads(log.read_text())
        assert logged == {"argv": ["queue", "--thread", thread, "--message", FIXED_NUDGE], "cwd": str(tmp_path)}
        if expected == "uncertain":
            assert ledger.next_receipt("t", "a", "s", thread, 2, 2) is None


def test_missing_sink_uuid_stdout_broken_pipe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert CodexSink(str(uuid4()), tmp_path).dispatch() == "not_started"
    for value in ("--last", "latest", "not-a-uuid", str(uuid4()).upper()):
        error("VALIDATION_ERROR", lambda value=value: exact_uuid(value))
    assert StdoutSink().dispatch() == "emitted"
    assert capsys.readouterr().out == FIXED_NUDGE + "\n"
    class Broken:
        def write(self, value):
            raise BrokenPipeError
    monkeypatch.setattr(sys, "stdout", Broken())
    assert StdoutSink().dispatch() == "uncertain"


async def test_watcher_quiet_authority_and_transport_redaction(tmp_path, monkeypatch, capsys):
    import agent_dms.watch as module
    from agent_dms.config import private_write
    token_file = tmp_path / "token"
    private_write(token_file, "TOKEN-SENTINEL")
    seen, sink = [], Sink()
    session_id = str(uuid4())
    monkeypatch.setattr(module, "StdoutSink", lambda: sink)
    @asynccontextmanager
    async def fake_connect(*args):
        yield object()
    monkeypatch.setattr(module, "connect", fake_connect)
    waits = 0
    async def fake_call(client, name, args):
        nonlocal waits
        seen.append(name)
        if name == "agent_whoami":
            return {"agent_id": "a"}
        if name == "session_heartbeat":
            return {}
        if name == "inbox_wait":
            waits += 1
            if waits == 1:
                return {"notification_revision": 0, "available": 0}
            raise DomainError("SESSION_SUPERSEDED", "Stop")
        raise AssertionError(name)
    monkeypatch.setattr(module, "call", fake_call)
    with pytest.raises(DomainError):
        await module.watch("http://127.0.0.1:1/mcp", token_file, session_id, tmp_path / "ledger" / "receipts.sqlite3")
    assert sink.calls == 0 and set(seen) == {"agent_whoami", "session_heartbeat", "inbox_wait"}
    assert not capsys.readouterr().err
    @asynccontextmanager
    async def failed_connect(*args):
        raise RuntimeError("TOKEN-SENTINEL PRIVATE-MESSAGE-SENTINEL")
        yield
    monkeypatch.setattr(module, "connect", failed_connect)
    task = asyncio.create_task(module.watch("http://127.0.0.1:1/mcp", token_file, session_id, tmp_path / "ledger2" / "receipts.sqlite3"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    diagnostic = capsys.readouterr().err
    assert "connection unavailable" in diagnostic
    assert "SENTINEL" not in diagnostic


async def test_wait_counts_over_100(h, peers):
    a, b, _ = peers
    for _ in range(105):
        h.send(a, b)
    result = await h.service.wait(h.tokens[b], h.sessions[b], 0, 0)
    assert result["available"] == 105
    batch = h.call(b, "inbox_next", limit=100)
    assert (await h.service.wait(h.tokens[b], h.sessions[b], 0, 0))["available"] == 5
    h.call(b, "inbox_release", claim_token=batch["claim_token"])
    assert (await h.service.wait(h.tokens[b], h.sessions[b], 105, 0))["available"] == 105


def test_unexpected_dispatch_failure_is_quarantined(tmp_path):
    class Fault:
        def dispatch(self):
            raise RuntimeError("unconfirmed external write")
    with ReceiptLedger(tmp_path / "ledger" / "receipts.sqlite3") as ledger:
        receipt = dispatch_hint(ledger, "t", "a", "s", None, {"notification_revision": 1, "available": 1}, Fault())
        assert receipt["state"] == "uncertain"
        assert ledger.next_receipt("t", "a", "s", None, 2, 2) is None


def test_actual_parent_crash_after_child_spawn_is_quarantined(tmp_path, monkeypatch):
    import signal
    import subprocess
    import time
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "child.json"
    executable = bindir / "codex"
    executable.write_text('''#!/usr/bin/python3
import json,os,sys,time
if sys.argv[1:] == ['queue','--help']:
 print('--thread --message'); raise SystemExit(0)
open(os.environ['QUEUE_CRASH_MARKER'],'w').write(json.dumps({'pid':os.getpid(),'argv':sys.argv[1:]}))
time.sleep(10)
''')
    executable.chmod(0o700)
    environment = dict(os.environ, PATH=str(bindir), QUEUE_CRASH_MARKER=str(marker))
    path = tmp_path / "ledger" / "receipts.sqlite3"
    thread = str(uuid4())
    program = """import sys
from agent_dms.notification_receipts import ReceiptLedger
from agent_dms.watch import CodexSink,dispatch_hint
with ReceiptLedger(sys.argv[1]) as ledger:
 dispatch_hint(ledger,'target','agent','session',sys.argv[2],{'notification_revision':1,'available':1},CodexSink(sys.argv[2],sys.argv[3],timeout=20))
"""
    parent = subprocess.Popen([sys.executable, "-c", program, str(path), thread, str(tmp_path)], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child_pid = None
    try:
        deadline = time.monotonic() + 3
        while not marker.exists():
            assert parent.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        child = json.loads(marker.read_text())
        child_pid = child["pid"]
        assert child["argv"] == ["queue", "--thread", thread, "--message", FIXED_NUDGE]
        parent.kill()
        parent.wait(timeout=2)
        with ReceiptLedger(path) as ledger:
            receipt = ledger.list()[0]
            assert receipt["state"] == "uncertain"
            assert ledger.next_receipt("target", "agent", "session", thread, 2, 2) is None
            assert ledger.accepted_revision("target") == 0
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=2)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


async def test_arrival_during_sink_preserves_next_revision(h, peers, tmp_path):
    a, b, _ = peers
    h.send(a, b)
    hint = await h.service.wait(h.tokens[b], h.sessions[b], 0, 0)
    class ArrivalSink:
        def dispatch(self):
            h.send(a, b, "arrived during dispatch")
            return "accepted"
    with ReceiptLedger(tmp_path / "ledger" / "receipts.sqlite3") as ledger:
        first = dispatch_hint(ledger, "target", b, h.sessions[b], None, hint, ArrivalSink())
        assert first["revision"] == ledger.accepted_revision("target") == 1
        next_hint = await h.service.wait(h.tokens[b], h.sessions[b], 1, 0)
        assert next_hint["notification_revision"] == 2 and next_hint["available"] == 2
        assert dispatch_hint(ledger, "target", b, h.sessions[b], None, next_hint, Sink())["revision"] == 2


async def test_real_watcher_stops_on_session_takeover(h, peers, live, tmp_path, monkeypatch):
    import agent_dms.watch as module
    from agent_dms.config import private_write
    a, b, _ = peers
    url, app = live
    path = tmp_path / "watch.token"
    private_write(path, h.tokens[b])
    sink = Sink()
    monkeypatch.setattr(module, "StdoutSink", lambda: sink)
    task = asyncio.create_task(module.watch(url, path, h.sessions[b], tmp_path / "ledger" / "receipts.sqlite3"))
    deadline = asyncio.get_running_loop().time() + 3
    while not app.registry.entries:
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.01)
    h.open(b, "watcher-replaced", takeover=True)
    with pytest.raises(DomainError):
        await asyncio.wait_for(task, 2)
    assert sink.calls == 0
    with ReceiptLedger(tmp_path / "ledger" / "receipts.sqlite3") as ledger:
        assert ledger.list() == []
