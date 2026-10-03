import asyncio
import base64
import hashlib
import hmac
import json
import sqlite3
from collections import Counter

from .errors import DomainError, fail
from .identity import IdentityMixin
from .sessions import SessionsMixin
from .status import StatusMixin
from .messaging import MessagingMixin
from .inbox import InboxMixin
from .workstreams import WorkstreamsMixin
from .models import canonical, digest, key, limit, new_id

MUTATING = {"session_open", "status_set", "dm_send", "dm_reply", "inbox_next", "inbox_ack", "inbox_release", "inbox_renew", "workstream_start", "workstream_transition"}
FRESH = {"dm_send", "dm_reply", "workstream_start", "workstream_transition"}


class Service(IdentityMixin, SessionsMixin, StatusMixin, MessagingMixin, InboxMixin, WorkstreamsMixin):
    def __init__(self, store):
        self.store = store
        self.waiters = Counter()

    @property
    def now(self):
        return self.store.clock()

    def call(self, token, operation, arguments):
        with self.store.transaction() as conn:
            agent = self.authenticate(conn, token)
            args = dict(arguments)
            if "limit" in args:
                limit(args["limit"])
            if operation not in {"session_open", "agent_whoami"}:
                session = self.current_session(conn, agent, args.get("session_id"), allow_closed=operation == "session_close")
                if operation != "session_close":
                    self.touch(conn, session)
            receipt_key = None
            if operation in MUTATING:
                receipt_key = key(args.get("idempotency_key"))
                input_hash = digest(canonical({k: v for k, v in args.items() if k != "idempotency_key"}))
                receipt = conn.execute("SELECT * FROM idempotency WHERE principal_id=? AND operation=? AND key=?", (agent["id"], operation, receipt_key)).fetchone()
                if receipt:
                    if receipt["input_hash"] != input_hash:
                        fail("IDEMPOTENCY_CONFLICT", "This key was committed with different input")
                    result = json.loads(receipt["response"])
                    if operation == "session_open":
                        saved_session = self.current_session(conn, agent, result["session_id"])
                        self.touch(conn, saved_session)
                    if operation == "inbox_next" and result.get("claim_token"):
                        self.recover_expired(conn, agent["id"])
                        claim = conn.execute("SELECT * FROM claims WHERE token_digest=?", (digest(result["claim_token"]),)).fetchone()
                        result["claim_active"] = claim is not None and claim["state"] == "active" and claim["expires_at"] > self.now
                    return result
            if operation in FRESH:
                self.require_fresh(conn, agent)
            method = getattr(self, operation, None)
            if method is None or operation.startswith("_"):
                fail("NOT_FOUND", "Unknown operation")
            result = method(conn, agent, **args)
            if receipt_key is not None:
                conn.execute("INSERT INTO idempotency VALUES(?,?,?,?,?,?)", (agent["id"], operation, receipt_key, input_hash, canonical(result), self.now))
            return result

    def envelope(self, token, operation, arguments):
        request_id = new_id()
        try:
            return {"version": 1, "ok": True, "data": self.call(token, operation, arguments), "request_id": request_id}
        except DomainError as exc:
            return {"version": 1, "ok": False, "error": exc.as_dict(), "request_id": request_id}
        except Exception:
            return {"version": 1, "ok": False, "error": {"code": "INTERNAL_ERROR", "message": "Operation failed; use request ID for support", "retryable": False, "repair": {}}, "request_id": request_id}

    def sign_cursor(self, data):
        raw = canonical(data).encode()
        tag = hmac.new(self.store.cursor_secret, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + tag).decode().rstrip("=")

    def page_bounds(self, conn, agent, operation, filters, cursor, table, sequence="seq"):
        if not cursor:
            return 0, conn.execute(f"SELECT coalesce(max({sequence}),0) FROM {table}").fetchone()[0]
        try:
            if len(cursor) > 4096:
                raise ValueError
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            body, tag = raw[:-32], raw[-32:]
            if not hmac.compare_digest(tag, hmac.new(self.store.cursor_secret, body, hashlib.sha256).digest()):
                raise ValueError
            data = json.loads(body)
            if data["version"] != 1 or data["agent"] != agent["id"] or data["operation"] != operation or data["filters"] != filters or type(data["after"]) is not int or type(data["upper"]) is not int:
                raise ValueError
            return data["after"], data["upper"]
        except (ValueError, KeyError, TypeError):
            fail("VALIDATION_ERROR", "Cursor is invalid or belongs to another paging pass")

    def paged(self, agent, operation, cursor_filters, upper, entries, limit_value, **extra):
        limit(limit_value)
        visible = entries[:limit_value]
        cursor = None
        if len(entries) > limit_value:
            cursor = self.sign_cursor({"version": 1, "agent": agent["id"], "operation": operation, "filters": cursor_filters, "after": visible[-1][0], "upper": upper})
        return {"items": [v for _, v in visible], "cursor": cursor, **extra}

    async def wait(self, token, session_id, after_revision=0, timeout_seconds=25):
        if type(after_revision) is not int or after_revision < 0 or type(timeout_seconds) not in {int, float} or not 0 <= timeout_seconds <= 25:
            fail("VALIDATION_ERROR", "Wait requires nonnegative revision and timeout 0–25 seconds")
        with self.store.transaction() as conn:
            agent = self.authenticate(conn, token)
            self.current_session(conn, agent, session_id)
            principal = agent["id"]
        if self.waiters[principal] >= 2:
            fail("CAPACITY_LIMIT", "At most two long polls per agent are allowed", True)
        self.waiters[principal] += 1
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        try:
            while True:
                result = self.call(token, "inbox_hint", {"session_id": session_id, "after_revision": after_revision})
                if (result["changed"] and result["available"] > 0) or asyncio.get_running_loop().time() >= deadline:
                    return result
                await asyncio.sleep(min(0.1, max(0, deadline - asyncio.get_running_loop().time())))
        finally:
            self.waiters[principal] -= 1
            if self.waiters[principal] == 0:
                del self.waiters[principal]
