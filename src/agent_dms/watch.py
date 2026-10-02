"""Optional client-local wakeups for existing clients, with explicit uncertainty."""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from .client import call, connect, read_token, service_url
from .errors import DomainError, fail
from .models import canonical, digest
from .notification_receipts import ReceiptLedger

FIXED_NUDGE = "agent-dms: pending work is available. Reconcile your inbox; notifications do not acknowledge messages."


def exact_uuid(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        fail("VALIDATION_ERROR", "Native thread must be an exact canonical UUID")
    return value


def codex_capability():
    executable = shutil.which("codex")
    if executable is None:
        return None
    try:
        result = subprocess.run([executable, "queue", "--help"], capture_output=True, timeout=5, check=False)
        output = result.stdout + result.stderr
        if result.returncode == 0 and b"--thread" in output and b"--message" in output:
            return executable
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


class StdoutSink:
    def dispatch(self):
        try:
            sys.stdout.write(FIXED_NUDGE + "\n")
            sys.stdout.flush()
            return "emitted"
        except (BrokenPipeError, OSError):
            return "uncertain"


class CodexSink:
    def __init__(self, thread, workspace, timeout=10):
        self.thread = exact_uuid(thread)
        self.workspace = Path(workspace).absolute()
        if not self.workspace.is_dir():
            fail("VALIDATION_ERROR", "Queue workspace must be an existing directory")
        self.timeout = timeout

    def dispatch(self):
        executable = codex_capability()
        if executable is None:
            return "not_started"
        try:
            process = subprocess.Popen([executable, "queue", "--thread", self.thread, "--message", FIXED_NUDGE], cwd=self.workspace, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return "not_started"
        try:
            return "accepted" if process.wait(timeout=self.timeout) == 0 else "uncertain"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return "uncertain"
        except BaseException:
            process.kill()
            process.wait()
            raise  # Dispatching stays durable; restart quarantines it.


def dispatch_hint(ledger, target, agent_id, session_id, native_thread, hint, sink):
    receipt = ledger.next_receipt(target, agent_id, session_id, native_thread, hint["notification_revision"], hint["available"])
    if receipt is None:
        return None
    ledger.dispatching(receipt["id"])
    try:
        state = sink.dispatch()
    except Exception:
        state = "uncertain"
    return ledger.finish(receipt["id"], state)


def authority_error(exc):
    if isinstance(exc, DomainError):
        return exc.code in {"UNAUTHENTICATED", "SESSION_SUPERSEDED", "SESSION_REQUIRED"}
    if isinstance(exc, BaseExceptionGroup):
        return any(authority_error(child) for child in exc.exceptions)
    response = getattr(exc, "response", None)
    return response is not None and getattr(response, "status_code", 0) in {401, 403}


async def watch(url, token_file, session_id, ledger_path, sink="stdout", thread=None, workspace=None):
    from .mcp_server import configure_safe_logging
    configure_safe_logging()
    service_url(url)
    exact_uuid(session_id)
    sink_impl = StdoutSink() if sink == "stdout" else CodexSink(thread, workspace)
    token = read_token(token_file)
    outage = False
    backoff = 1
    with ReceiptLedger(ledger_path) as ledger:
        while True:
            try:
                async with connect(url, token) as client:
                    who = await call(client, "agent_whoami", {})
                    target = digest(canonical({"url": url, "agent_id": who["agent_id"], "sink": sink, "thread": thread, "workspace": None if workspace is None else str(Path(workspace).absolute())}))
                    observed_revision = ledger.accepted_revision(target)
                    while True:
                        await call(client, "session_heartbeat", {"session_id": session_id})
                        hint = await call(client, "inbox_wait", {"session_id": session_id, "after_revision": observed_revision, "timeout_seconds": 25})
                        observed_revision = hint["notification_revision"]
                        if outage:
                            print("agent-dms watcher connection recovered", file=sys.stderr)
                            outage = False
                        backoff = 1
                        # Recheck authority immediately before a local external effect.
                        if hint["available"]:
                            await call(client, "session_heartbeat", {"session_id": session_id})
                            receipt = await asyncio.to_thread(dispatch_hint, ledger, target, who["agent_id"], session_id, thread, hint, sink_impl)
                            if receipt and receipt["state"] == "uncertain":
                                print("agent-dms wakeup is uncertain; reconcile its local receipt", file=sys.stderr)
                            if receipt and receipt["state"] == "uncertain" and sink == "stdout":
                                return
                            # New actionable revision returns promptly; avoid a hot loop on unchanged hints.
                            await asyncio.sleep(0.5 if receipt is None else 0.05)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if authority_error(exc):
                    fail("UNAUTHENTICATED", "Watcher lost credential or application-session authority; stopping")
                if not outage:
                    print("agent-dms watcher connection unavailable; retrying", file=sys.stderr)
                    outage = True
                await asyncio.sleep(backoff)
                backoff = min(30, backoff * 2)
