"""Client-local wakeup receipts. These never carry message bodies or ACK authority."""
import sqlite3
from contextlib import contextmanager

from .config import private_dir, private_write, safe_path
from .errors import fail
from .models import new_id, rfc3339, utc_ms
from .storage import ProcessLock

LEDGER_SCHEMA_VERSION = 1
STATES = {"pending", "dispatching", "emitted", "accepted", "not_started", "uncertain", "superseded"}
LEGACY_COLUMNS = {"id", "target", "agent_id", "session_id", "native_thread", "revision", "state", "attempts", "retry_at", "reason", "created_at", "updated_at"}
RECEIPT_SCHEMA = """(
    id TEXT PRIMARY KEY, target TEXT NOT NULL REFERENCES targets(target),
    agent_id TEXT NOT NULL, session_id TEXT NOT NULL, native_thread TEXT,
    revision INTEGER NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    retry_at INTEGER NOT NULL DEFAULT 0, reason TEXT, created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL, superseded_at INTEGER, superseded_reason TEXT,
    UNIQUE(target,session_id,revision))"""


class ReceiptLedger:
    def __init__(self, path, clock=utc_ms):
        self.path = safe_path(path)
        private_dir(self.path.parent, private_existing=False)
        self.validate_file()
        self.clock = clock
        self.lock = ProcessLock(self.path.with_suffix(self.path.suffix + ".lock"))
        self.conn = None

    def validate_file(self):
        if self.path.exists() and (not self.path.is_file() or self.path.stat().st_mode & 0o077):
            fail("VALIDATION_ERROR", "Watcher ledger must be a private regular file; repair permissions to 0600 before retrying")

    def __enter__(self):
        self.lock.__enter__()
        try:
            self.validate_file()
            if not self.path.exists():
                private_write(self.path, b"")
            self.conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            # Refuse unknown schemas before journal changes or any durable write.
            self.initialize_schema()
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
            with self.transaction():
                self.conn.execute("UPDATE receipts SET state='uncertain',reason='Interrupted while dispatching',updated_at=? WHERE state='dispatching'", (self.clock(),))
            return self
        except BaseException:
            if self.conn is not None:
                self.conn.close()
                self.conn = None
            self.lock.__exit__()
            raise

    def __exit__(self, *args):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        self.lock.__exit__(*args)

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def initialize_schema(self):
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if version not in {0, LEDGER_SCHEMA_VERSION}:
            fail("VALIDATION_ERROR", "Unsupported watcher ledger schema; retain the ledger and use a compatible version")
        if version == LEDGER_SCHEMA_VERSION:
            if (tables != {"targets", "receipts", "session_acceptance"}
                    or self.columns("receipts") != LEGACY_COLUMNS | {"superseded_at", "superseded_reason"}
                    or self.columns("targets") != {"target", "accepted_revision"}
                    or self.columns("session_acceptance") != {"target", "session_id", "accepted_revision"}):
                fail("VALIDATION_ERROR", "Unknown watcher ledger schema; no automatic reset")
            return
        if tables and (tables != {"targets", "receipts"} or self.columns("receipts") != LEGACY_COLUMNS or self.columns("targets") != {"target", "accepted_revision"}):
            fail("VALIDATION_ERROR", "Unknown unversioned watcher ledger schema; no automatic reset")
        # Individual DDL statements remain inside this transaction (executescript would commit).
        with self.transaction():
            if tables:
                self.migrate_legacy()
            else:
                self.conn.execute("CREATE TABLE targets(target TEXT PRIMARY KEY, accepted_revision INTEGER NOT NULL DEFAULT 0)")
                self.conn.execute("CREATE TABLE receipts" + RECEIPT_SCHEMA)
                self.create_acceptance()
            self.conn.execute(f"PRAGMA user_version={LEDGER_SCHEMA_VERSION}")

    def columns(self, table):
        return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def create_acceptance(self):
        self.conn.execute("""CREATE TABLE session_acceptance(
            target TEXT NOT NULL REFERENCES targets(target), session_id TEXT NOT NULL,
            accepted_revision INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(target,session_id))""")

    def migrate_legacy(self):
        self.conn.execute("CREATE TABLE receipts_migrating" + RECEIPT_SCHEMA)
        columns = ",".join(sorted(LEGACY_COLUMNS))
        self.conn.execute(f"INSERT INTO receipts_migrating({columns}) SELECT {columns} FROM receipts")
        self.conn.execute("DROP TABLE receipts")
        self.conn.execute("ALTER TABLE receipts_migrating RENAME TO receipts")
        self.create_acceptance()
        self.conn.execute("""INSERT INTO session_acceptance(target,session_id,accepted_revision)
            SELECT target,session_id,max(revision) FROM receipts
            WHERE state IN ('emitted','accepted') GROUP BY target,session_id""")
        # Legacy targets.accepted_revision is preserved solely as historical data.

    def accepted_revision(self, target, session_id):
        row = self.conn.execute("SELECT accepted_revision FROM session_acceptance WHERE target=? AND session_id=?", (target, session_id)).fetchone()
        return 0 if row is None else row[0]

    def next_receipt(self, target, agent_id, session_id, native_thread, revision, available):
        with self.transaction():
            self.conn.execute("INSERT OR IGNORE INTO targets(target) VALUES(?)", (target,))
            # Uncertainty is shared across sessions at the same base target. Never bypass it.
            if self.conn.execute("SELECT 1 FROM receipts WHERE target=? AND state IN ('uncertain','dispatching') LIMIT 1", (target,)).fetchone():
                return None
            now = self.clock()
            self.conn.execute("""UPDATE receipts SET state='superseded',superseded_at=?,
                superseded_reason='Authenticated watcher owns a different application session'
                WHERE target=? AND session_id<>? AND state IN ('pending','not_started')""", (now, target, session_id))
            # Retry preserves exact receipt identity/intention, never a later captured revision.
            prior = self.conn.execute("SELECT * FROM receipts WHERE target=? AND session_id=? AND state IN ('pending','not_started') ORDER BY created_at,id LIMIT 1", (target, session_id)).fetchone()
            if prior is not None:
                if available <= 0 or prior["retry_at"] > now:
                    return None
                return dict(prior)
            if available <= 0 or revision <= self.accepted_revision(target, session_id):
                return None
            receipt_id = new_id()
            self.conn.execute("INSERT INTO receipts(id,target,agent_id,session_id,native_thread,revision,state,created_at,updated_at) VALUES(?,?,?,?,?,?,'pending',?,?)", (receipt_id, target, agent_id, session_id, native_thread, revision, now, now))
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

    def record_acceptance(self, receipt):
        self.conn.execute("""INSERT INTO session_acceptance(target,session_id,accepted_revision) VALUES(?,?,?)
            ON CONFLICT(target,session_id) DO UPDATE SET accepted_revision=max(accepted_revision,excluded.accepted_revision)""", (receipt["target"], receipt["session_id"], receipt["revision"]))

    def finish(self, receipt_id, state):
        if state not in {"emitted", "accepted", "not_started", "uncertain"}:
            fail("VALIDATION_ERROR", "Invalid receipt outcome")
        with self.transaction():
            receipt = self.get(receipt_id)
            if receipt["state"] != "dispatching":
                fail("INVALID_TRANSITION", "Receipt is not dispatching")
            delay = min(60_000, 1000 * 2 ** min(receipt["attempts"], 6)) if state == "not_started" else 0
            self.conn.execute("UPDATE receipts SET state=?,retry_at=?,updated_at=? WHERE id=?", (state, self.clock() + delay, self.clock(), receipt_id))
            if state in {"emitted", "accepted"}:
                self.record_acceptance(receipt)
            return self.get(receipt_id)

    def resolve(self, receipt_id, delivered, reason):
        from .models import text
        text(reason, "reason", 2000)
        with self.transaction():
            receipt = self.get(receipt_id)
            if receipt["state"] != "uncertain":
                fail("INVALID_TRANSITION", "Only an exact uncertain receipt may be resolved")
            state = "accepted" if delivered else "pending"
            self.conn.execute("UPDATE receipts SET state=?,reason=?,retry_at=0,updated_at=? WHERE id=?", (state, reason, self.clock(), receipt_id))
            if delivered:
                self.record_acceptance(receipt)
            return self.get(receipt_id)

    def list(self):
        return [{**dict(row), "created_at": rfc3339(row["created_at"]), "updated_at": rfc3339(row["updated_at"]),
                 "superseded_at": None if row["superseded_at"] is None else rfc3339(row["superseded_at"])}
                for row in self.conn.execute("SELECT * FROM receipts ORDER BY created_at,id")]
