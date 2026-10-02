"""Client-local wakeup receipts. These never carry message bodies or ACK authority."""
import sqlite3

from .config import private_dir, private_write, safe_path
from .errors import fail
from .models import new_id, rfc3339, utc_ms
from .storage import ProcessLock

STATES = {"pending", "dispatching", "emitted", "accepted", "not_started", "uncertain"}


class ReceiptLedger:
    def __init__(self, path, clock=utc_ms):
        self.path = safe_path(path)
        private_dir(self.path.parent)
        if not self.path.exists():
            private_write(self.path, b"")
        if self.path.stat().st_mode & 0o077:
            fail("VALIDATION_ERROR", "Watcher ledger must be private")
        self.clock = clock
        self.lock = ProcessLock(self.path.with_suffix(self.path.suffix + ".lock"))
        self.conn = None

    def __enter__(self):
        self.lock.__enter__()
        try:
            self.conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS targets(target TEXT PRIMARY KEY, accepted_revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, target TEXT NOT NULL REFERENCES targets(target), agent_id TEXT NOT NULL, session_id TEXT NOT NULL, native_thread TEXT, revision INTEGER NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, retry_at INTEGER NOT NULL DEFAULT 0, reason TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(target,revision));
            """)
            self.conn.execute("UPDATE receipts SET state='uncertain',reason='Interrupted while dispatching',updated_at=? WHERE state='dispatching'", (self.clock(),))
            return self
        except BaseException:
            self.lock.__exit__()
            raise

    def __exit__(self, *args):
        if self.conn is not None:
            self.conn.close()
        self.lock.__exit__(*args)

    def accepted_revision(self, target):
        row = self.conn.execute("SELECT accepted_revision FROM targets WHERE target=?", (target,)).fetchone()
        return 0 if row is None else row[0]

    def next_receipt(self, target, agent_id, session_id, native_thread, revision, available):
        self.conn.execute("INSERT OR IGNORE INTO targets(target) VALUES(?)", (target,))
        if self.conn.execute("SELECT 1 FROM receipts WHERE target=? AND state IN ('uncertain','dispatching') LIMIT 1", (target,)).fetchone():
            return None
        # Retry preserves exact receipt identity/intention, never moves to a later revision.
        prior = self.conn.execute("SELECT * FROM receipts WHERE target=? AND state IN ('pending','not_started') ORDER BY created_at LIMIT 1", (target,)).fetchone()
        if prior is not None:
            if not available or prior["session_id"] != session_id or prior["retry_at"] > self.clock():
                return None
            return dict(prior)
        if available <= 0 or revision <= self.accepted_revision(target):
            return None
        receipt_id = new_id()
        self.conn.execute("INSERT INTO receipts(id,target,agent_id,session_id,native_thread,revision,state,created_at,updated_at) VALUES(?,?,?,?,?,?,'pending',?,?)", (receipt_id, target, agent_id, session_id, native_thread, revision, self.clock(), self.clock()))
        return self.get(receipt_id)

    def get(self, receipt_id):
        row = self.conn.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()
        if row is None:
            fail("NOT_FOUND", "Local receipt not found")
        return dict(row)

    def dispatching(self, receipt_id):
        changed = self.conn.execute("UPDATE receipts SET state='dispatching',attempts=attempts+1,updated_at=? WHERE id=? AND state IN ('pending','not_started')", (self.clock(), receipt_id)).rowcount
        if changed != 1:
            fail("INVALID_TRANSITION", "Receipt is not eligible for dispatch")

    def finish(self, receipt_id, state):
        if state not in {"emitted", "accepted", "not_started", "uncertain"}:
            fail("VALIDATION_ERROR", "Invalid receipt outcome")
        receipt = self.get(receipt_id)
        if receipt["state"] != "dispatching":
            fail("INVALID_TRANSITION", "Receipt is not dispatching")
        delay = min(60_000, 1000 * 2 ** min(receipt["attempts"], 6)) if state == "not_started" else 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute("UPDATE receipts SET state=?,retry_at=?,updated_at=? WHERE id=?", (state, self.clock() + delay, self.clock(), receipt_id))
            if state in {"emitted", "accepted"}:
                self.conn.execute("UPDATE targets SET accepted_revision=max(accepted_revision,?) WHERE target=?", (receipt["revision"], receipt["target"]))
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return self.get(receipt_id)

    def resolve(self, receipt_id, delivered, reason):
        from .models import text
        text(reason, "reason", 2000)
        receipt = self.get(receipt_id)
        if receipt["state"] != "uncertain":
            fail("INVALID_TRANSITION", "Only an exact uncertain receipt may be resolved")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            state = "accepted" if delivered else "pending"
            self.conn.execute("UPDATE receipts SET state=?,reason=?,retry_at=0,updated_at=? WHERE id=?", (state, reason, self.clock(), receipt_id))
            if delivered:
                self.conn.execute("UPDATE targets SET accepted_revision=max(accepted_revision,?) WHERE target=?", (receipt["revision"], receipt["target"]))
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return self.get(receipt_id)

    def list(self):
        return [{**dict(row), "created_at": rfc3339(row["created_at"]), "updated_at": rfc3339(row["updated_at"])} for row in self.conn.execute("SELECT * FROM receipts ORDER BY created_at,id")]
