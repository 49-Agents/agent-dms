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
        assert ledger.accepted_revision("target", "session") == 101
        # Arrival while a sink is dispatching must not be absorbed into the captured receipt.
        receipt = ledger.next_receipt("target", "agent", "session", None, 102, 102)
        ledger.dispatching(receipt["id"])
        ledger.finish(receipt["id"], "accepted")
        assert ledger.accepted_revision("target", "session") == 102
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
        assert ledger.accepted_revision("t", "s") == 1
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
            assert ledger.accepted_revision("target", "session") == 0
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
        assert first["revision"] == ledger.accepted_revision("target", h.sessions[b]) == 1
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


def test_ledger_parent_modes_files_nesting_and_symlink_refusal(tmp_path):
    parent = tmp_path / 'shared'
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    path = parent / 'receipts.sqlite3'
    with ReceiptLedger(path) as ledger:
        assert parent.stat().st_mode & 0o777 == 0o755
        assert path.stat().st_mode & 0o777 == 0o600
        assert ledger.lock.path.stat().st_mode & 0o777 == 0o600
    with ReceiptLedger(parent / 'nested/private/receipts.sqlite3'):
        assert (parent / 'nested').stat().st_mode & 0o777 == 0o700
        assert (parent / 'nested/private').stat().st_mode & 0o777 == 0o700
    alias = parent / 'alias'
    alias.symlink_to(path)
    error('VALIDATION_ERROR', lambda: ReceiptLedger(alias))
    path.chmod(0o644)
    before = path.read_bytes()
    error('VALIDATION_ERROR', lambda: ReceiptLedger(path))
    assert path.stat().st_mode & 0o777 == 0o644 and path.read_bytes() == before
    path.chmod(0o600)
    lock = path.with_suffix(path.suffix + '.lock')
    lock.chmod(0o644)
    error('VALIDATION_ERROR', lambda: ReceiptLedger(path).__enter__())
    assert lock.stat().st_mode & 0o777 == 0o644
    assert parent.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize('state', ['pending', 'not_started'])
def test_old_unstarted_session_intent_superseded_without_dispatch(tmp_path, state):
    clock = Clock()
    with ReceiptLedger(tmp_path / 'ledger.sqlite3', clock) as ledger:
        old = ledger.next_receipt('target', 'agent', 'old', 'native', 1, 1)
        if state == 'not_started':
            ledger.dispatching(old['id'])
            ledger.finish(old['id'], 'not_started')
        old = ledger.get(old['id'])
        clock.advance(1)
        current = ledger.next_receipt('target', 'agent', 'new', 'native', 1, 1)
        assert current['id'] != old['id'] and current['session_id'] == 'new' and current['revision'] == 1
        retired = ledger.get(old['id'])
        assert retired['state'] == 'superseded' and retired['superseded_at'] == clock()
        assert retired['superseded_reason']
        for field in ('id', 'target', 'agent_id', 'session_id', 'native_thread', 'revision', 'attempts', 'retry_at', 'reason', 'created_at', 'updated_at'):
            assert retired[field] == old[field]
        error('INVALID_TRANSITION', lambda: ledger.dispatching(old['id']))
        ledger.dispatching(current['id'])
        ledger.finish(current['id'], 'emitted')
        assert ledger.accepted_revision('target', 'new') == 1
        assert ledger.accepted_revision('target', 'old') == 0
        assert ledger.next_receipt('target', 'agent', 'new', 'native', 1, 1) is None


def test_session_watermarks_no_work_and_capped_same_intent_retry(tmp_path):
    clock = Clock()
    path = tmp_path / 'ledger.sqlite3'
    with ReceiptLedger(path, clock) as ledger:
        first = dispatch_hint(ledger, 'target', 'agent', 'old', None, {'notification_revision': 7, 'available': 1}, Sink())
        assert ledger.accepted_revision('target', 'old') == 7
        assert ledger.next_receipt('target', 'agent', 'new', None, 7, 0) is None
        current = ledger.next_receipt('target', 'agent', 'new', None, 7, 1)
        assert current['id'] != first['id']
        for attempt in range(1, 10):
            ledger.dispatching(current['id'])
            failed = ledger.finish(current['id'], 'not_started')
            delay = min(60_000, 1000 * 2 ** min(attempt, 6))
            assert failed['retry_at'] == clock() + delay and failed['attempts'] == attempt
            assert ledger.next_receipt('target', 'agent', 'new', None, 8, 1) is None
            clock.advance(delay)
            current = ledger.next_receipt('target', 'agent', 'new', None, 8, 1)
            assert current['id'] == failed['id'] and current['revision'] == 7
        ledger.dispatching(current['id'])
        ledger.finish(current['id'], 'accepted')
    with ReceiptLedger(path, clock) as ledger:
        assert ledger.accepted_revision('target', 'new') == 7
        assert ledger.next_receipt('target', 'agent', 'new', None, 7, 1) is None
        assert ledger.next_receipt('target', 'agent', 'new', None, 8, 1)['revision'] == 8


@pytest.mark.parametrize('delivered', [True, False])
def test_cross_session_uncertainty_quarantine_and_exact_resolution(tmp_path, delivered):
    path = tmp_path / 'ledger.sqlite3'
    with ReceiptLedger(path) as ledger:
        old = ledger.next_receipt('target', 'agent', 'old', None, 5, 1)
        ledger.dispatching(old['id'])
        # An unresolved dispatch also prevents retiring other old pending work.
        ledger.conn.execute("INSERT INTO receipts(id,target,agent_id,session_id,revision,state,created_at,updated_at) VALUES('pending-other','target','agent','older',4,'pending',1,1)")
        assert ledger.next_receipt('target', 'agent', 'new', None, 5, 1) is None
        assert ledger.get('pending-other')['state'] == 'pending'
    with ReceiptLedger(path) as ledger:
        assert ledger.get(old['id'])['state'] == 'uncertain'
        assert ledger.next_receipt('target', 'agent', 'new', None, 5, 1) is None
        assert ledger.get('pending-other')['state'] == 'pending'
        error('INVALID_TRANSITION', lambda: ledger.resolve('pending-other', True, 'wrong receipt'))
        ledger.resolve(old['id'], delivered, 'Operator reconciled exact intent')
        assert ledger.accepted_revision('target', 'old') == (5 if delivered else 0)
        assert ledger.accepted_revision('target', 'new') == 0
        current = ledger.next_receipt('target', 'agent', 'new', None, 5, 1)
        assert current['session_id'] == 'new' and current['id'] != old['id']
        assert ledger.get(old['id'])['state'] == ('accepted' if delivered else 'superseded')
        assert ledger.get('pending-other')['state'] == 'superseded'
        ledger.dispatching(current['id'])
        ledger.finish(current['id'], 'accepted')
        assert ledger.accepted_revision('target', 'new') == 5


def legacy_ledger(path):
    import sqlite3
    from agent_dms.config import private_write
    private_write(path, b'')
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE targets(target TEXT PRIMARY KEY,accepted_revision INTEGER NOT NULL DEFAULT 0)')
    conn.execute('''CREATE TABLE receipts(id TEXT PRIMARY KEY,target TEXT NOT NULL REFERENCES targets(target),
        agent_id TEXT NOT NULL,session_id TEXT NOT NULL,native_thread TEXT,revision INTEGER NOT NULL,
        state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,retry_at INTEGER NOT NULL DEFAULT 0,
        reason TEXT,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,UNIQUE(target,revision))''')
    conn.execute("INSERT INTO targets VALUES('target',99)")
    conn.execute("INSERT INTO targets VALUES('historical-only',123)")
    states = [('one', 'emitted'), ('two', 'accepted'), ('one', 'pending'), ('two', 'not_started'),
              ('three', 'uncertain'), ('four', 'dispatching'), ('one', 'accepted')]
    for revision, (session, state) in enumerate(states, 1):
        conn.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                     (f'legacy-{revision}', 'target', 'agent', session, 'native', revision, state,
                      revision + 10, revision + 100, f'reason-{revision}', revision + 1000, revision + 2000))
    conn.commit()
    rows = [dict(r) for r in conn.execute('SELECT * FROM receipts ORDER BY revision')]
    conn.close()
    return rows


def test_atomic_legacy_migration_preserves_history_and_rebuilds_session_acceptance(tmp_path):
    from agent_dms.notification_receipts import LEDGER_SCHEMA_VERSION
    path = tmp_path / 'legacy.sqlite3'
    rows = legacy_ledger(path)
    clock = Clock()
    with ReceiptLedger(path, clock) as ledger:
        assert ledger.conn.execute('PRAGMA user_version').fetchone()[0] == LEDGER_SCHEMA_VERSION
        assert [tuple(r) for r in ledger.conn.execute('SELECT * FROM targets ORDER BY target')] == [('historical-only', 123), ('target', 99)]
        for row in rows:
            actual = ledger.get(row['id'])
            if row['state'] == 'dispatching':
                row = {**row, 'state': 'uncertain', 'reason': 'Interrupted while dispatching', 'updated_at': clock()}
            assert {key: actual[key] for key in row} == row
            assert actual['superseded_at'] is None and actual['superseded_reason'] is None
        assert ledger.accepted_revision('target', 'one') == 7
        assert ledger.accepted_revision('target', 'two') == 2
        assert ledger.accepted_revision('target', 'new') == ledger.accepted_revision('historical-only', 'one') == 0
        assert ledger.next_receipt('target', 'agent', 'new', 'native', 7, 7) is None
        ledger.resolve('legacy-5', True, 'Exact old receipt confirmed')
        assert ledger.accepted_revision('target', 'three') == 5
        assert ledger.next_receipt('target', 'agent', 'new', 'native', 7, 7) is None  # legacy-6 still uncertain
        ledger.resolve('legacy-6', False, 'Exact interrupted receipt had no effect')
        new = ledger.next_receipt('target', 'agent', 'new', 'native', 7, 7)
        assert new['revision'] == 7 and new['session_id'] == 'new'
        assert all(ledger.get(f'legacy-{i}')['state'] == 'superseded' for i in (3, 4, 6))
        assert len(ledger.list()) == len(rows) + 1


def test_legacy_migration_failure_rolls_back_all_ddl_and_rows(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / 'legacy.sqlite3'
    rows = legacy_ledger(path)
    before = path.read_bytes()
    migrate = ReceiptLedger.migrate_legacy
    def fault(self):
        migrate(self)
        raise RuntimeError('injected failure after table replacement and watermark reconstruction')
    with monkeypatch.context() as scoped:
        scoped.setattr(ReceiptLedger, 'migrate_legacy', fault)
        with pytest.raises(RuntimeError):
            ReceiptLedger(path).__enter__()
    assert path.read_bytes() == before
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 0
        assert [dict(r) for r in conn.execute('SELECT * FROM receipts ORDER BY revision')] == rows
        assert {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'targets', 'receipts'}
    with ReceiptLedger(path) as ledger:
        assert len(ledger.list()) == len(rows)


@pytest.mark.parametrize('version,unknown', [(2, False), (99, False), (0, True), (1, True)])
def test_unknown_or_newer_ledger_refused_without_mutation(tmp_path, version, unknown):
    import sqlite3
    path = tmp_path / 'unknown.sqlite3'
    legacy_ledger(path)
    with sqlite3.connect(path) as conn:
        conn.execute(f'PRAGMA user_version={version}')
        if unknown:
            conn.execute('CREATE TABLE unknown_history(id TEXT PRIMARY KEY)')
            conn.execute("INSERT INTO unknown_history VALUES('retain')")
    before = (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
    error('VALIDATION_ERROR', lambda: ReceiptLedger(path).__enter__())
    assert (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) == before
    assert not path.with_name(path.name + '-wal').exists()


async def test_session_replacement_watcher_and_daemon_restart_keep_dms_pending(h, tmp_path, monkeypatch):
    import socket
    import httpx
    import agent_dms.watch as module
    from agent_dms.client import call, connect
    from agent_dms.config import private_write
    from agent_dms.models import canonical, digest
    a, b = h.add('Restart Manager'), h.add('Restart Worker')
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    url = f'http://127.0.0.1:{port}/mcp'
    token_file = tmp_path / 'watch.token'
    private_write(token_file, h.tokens[b])
    ledger_path = tmp_path / 'receipts.sqlite3'
    sink = Sink('not_started')
    monkeypatch.setattr(module, 'StdoutSink', lambda: sink)
    async def daemon_start():
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'agent_dms', 'serve', '--data-dir', str(h.data_dir), '--port', str(port),
                                                       stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        async with httpx.AsyncClient() as http:
            for _ in range(200):
                assert process.returncode is None
                try:
                    if (await http.get(url.replace('/mcp', '/health/ready'))).status_code == 200:
                        return process
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.02)
        raise AssertionError('isolated daemon not ready')
    async def wait_calls(expected):
        deadline = asyncio.get_running_loop().time() + 4
        while sink.calls < expected:
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)  # Let the durable finish complete before cancellation.
    async def stop_watcher(task):
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    daemon, task = await daemon_start(), None
    try:
        async with connect(url, h.tokens[a]) as manager, connect(url, h.tokens[b]) as worker:
            manager_session = await call(manager, 'session_open', {'client_session_key': 'manager', 'status': 'Checking session-aware watcher recovery', 'availability': 'working', 'idempotency_key': 'manager-open'})
            old = await call(worker, 'session_open', {'client_session_key': 'old-worker', 'status': 'Checking old watcher', 'availability': 'working', 'idempotency_key': 'old-open'})
            sent = await call(manager, 'dm_send', {'session_id': manager_session['session_id'], 'to_agent_id': b, 'body': 'Durable through notification session replacement', 'idempotency_key': 'send'})
            task = asyncio.create_task(module.watch(url, token_file, old['session_id'], ledger_path))
            await wait_calls(1)
            current = await call(worker, 'session_open', {'client_session_key': 'current-worker', 'status': 'Recovering current watcher', 'availability': 'working', 'takeover': True, 'idempotency_key': 'new-open'})
            with pytest.raises(DomainError) as stopped:
                await asyncio.wait_for(task, 2)
            assert stopped.value.code == 'UNAUTHENTICATED'
            task = None
        with ReceiptLedger(ledger_path) as ledger:
            old_receipt = ledger.list()[0]
            assert old_receipt['state'] == 'not_started'
        daemon.terminate()
        await asyncio.wait_for(daemon.wait(), 5)
        daemon = await daemon_start()
        sink.state = 'emitted'
        task = asyncio.create_task(module.watch(url, token_file, current['session_id'], ledger_path))
        await wait_calls(2)
        await stop_watcher(task)
        task = None
        with ReceiptLedger(ledger_path) as ledger:
            retired = ledger.get(old_receipt['id'])
            assert retired['state'] == 'superseded' and retired['attempts'] == 1
            receipts = ledger.list()
            assert len(receipts) == 2
            accepted = next(r for r in receipts if r['session_id'] == current['session_id'])
            assert accepted['state'] == 'emitted' and accepted['revision'] == old_receipt['revision'] == 1
            target = digest(canonical({'url': url, 'agent_id': b, 'sink': 'stdout', 'thread': None, 'workspace': None}))
            assert ledger.accepted_revision(target, current['session_id']) == 1
        # A watcher restart initializes from this session's watermark and stays quiet.
        waits = asyncio.Event()
        original_call = module.call
        async def observed_call(client, name, args):
            if name == 'inbox_wait':
                assert args['after_revision'] == 1
                waits.set()
            return await original_call(client, name, args)
        monkeypatch.setattr(module, 'call', observed_call)
        task = asyncio.create_task(module.watch(url, token_file, current['session_id'], ledger_path))
        await asyncio.wait_for(waits.wait(), 3)
        await asyncio.sleep(0.2)
        assert sink.calls == 2
        await stop_watcher(task)
        task = None
        async with connect(url, h.tokens[b]) as worker:
            args = {'session_id': current['session_id']}
            peek = await call(worker, 'inbox_peek', args)
            assert peek['counts']['pending'] == 1 and peek['items'][0]['message_id'] == sent['message_id']
            claim = await call(worker, 'inbox_next', {**args, 'idempotency_key': 'explicit-claim'})
            assert claim['items'][0]['message_id'] == sent['message_id']
            await call(worker, 'inbox_ack', {**args, 'claim_token': claim['claim_token'], 'message_ids': [sent['message_id']], 'idempotency_key': 'explicit-ack'})
            assert (await call(worker, 'inbox_peek', args))['counts']['pending'] == 0
    finally:
        if task is not None and not task.done():
            await stop_watcher(task)
        if daemon.returncode is None:
            daemon.terminate()
            await asyncio.wait_for(daemon.wait(), 5)


def test_session_recovery_rolls_back_supersession_when_new_intent_fails(tmp_path):
    import sqlite3
    with ReceiptLedger(tmp_path / 'ledger.sqlite3') as ledger:
        old = ledger.next_receipt('target', 'agent', 'old', None, 1, 1)
        ledger.conn.execute("""CREATE TRIGGER injected_failure BEFORE INSERT ON receipts
            WHEN NEW.session_id='new' BEGIN SELECT RAISE(ABORT,'injected intent write failure'); END""")
        with pytest.raises(sqlite3.IntegrityError):
            ledger.next_receipt('target', 'agent', 'new', None, 1, 1)
        assert ledger.get(old['id']) == old
        assert len(ledger.list()) == 1
        ledger.conn.execute('DROP TRIGGER injected_failure')
        assert ledger.next_receipt('target', 'agent', 'new', None, 1, 1)['session_id'] == 'new'
