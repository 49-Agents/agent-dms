import fcntl
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from importlib.resources import files

from .config import ProjectConfig, load_config, private_dir, private_write, safe_path, validate_directory
from .errors import DomainError, fail
from .models import canonical, new_id, utc_ms

SCHEMA_VERSION = 1


class ProcessLock:
    def __init__(self, path):
        self.path = safe_path(path)
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        if os.fstat(self.fd).st_mode & 0o077:
            os.close(self.fd)
            self.fd = None
            fail("VALIDATION_ERROR", "Lock file must already be private; repair its permissions to 0600 before retrying")
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            fail("CAPACITY_LIMIT", "State directory already has an active owner", True)
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Store:
    def __init__(self, data_dir, clock=utc_ms, id_factory=new_id):
        self.data_dir = safe_path(data_dir)
        validate_directory(self.data_dir)
        validate_directory(self.data_dir / "credentials")
        self.config = load_config(data_dir)
        self.path = safe_path(self.data_dir / "state.sqlite3")
        self.clock = clock
        self.id_factory = id_factory
        self.validate()
        secret_path = safe_path(self.data_dir / "cursor.key")
        self.cursor_secret = secret_path.read_bytes()
        if len(self.cursor_secret) < 32:
            fail("VALIDATION_ERROR", "Invalid cursor signing key")

    def connect(self):
        if not self.path.is_file():
            fail("VALIDATION_ERROR", "Missing initialized database")
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except sqlite3.OperationalError as exc:
            conn.close()
            if "locked" in str(exc) or "busy" in str(exc):
                fail("STORAGE_BUSY", "Storage is busy; retry with the same key", True)
            raise

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if "locked" in str(exc) or "busy" in str(exc):
                fail("STORAGE_BUSY", "Storage is busy; retry with the same key", True)
            raise
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def validate(self):
        conn = self.connect()
        try:
            version = conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
            if version != SCHEMA_VERSION:
                fail("VALIDATION_ERROR", "Unsupported database schema; no automatic rollback")
            row = conn.execute("SELECT id FROM project").fetchall()
            if len(row) != 1 or row[0][0] != self.config.project_id:
                fail("VALIDATION_ERROR", "Configuration and database project identity differ")
        except sqlite3.DatabaseError:
            fail("VALIDATION_ERROR", "Invalid database schema")
        finally:
            conn.close()


def initialization_preflight(root, project_root):
    """Read-only rejection checks, repeated authoritatively under the init lock."""
    if not root.exists():
        return None
    validate_directory(root)
    if safe_path(root / "project.json").exists():
        config = load_config(root)
        if config.project_root != str(project_root):
            fail("VALIDATION_ERROR", "State directory belongs to a different project root")
        validate_directory(root / "credentials")
        return config
    if any(p.name != "init.lock" for p in root.iterdir()):
        fail("VALIDATION_ERROR", "Refusing to initialize a populated state directory")
    return None


def initialize(project_root, data_dir=None, *, clock=utc_ms, id_factory=new_id):
    project_root = safe_path(project_root)
    if not project_root.is_dir():
        fail("VALIDATION_ERROR", "project-root must be an existing directory")
    root = safe_path(data_dir or project_root / ".agent-dms")
    initialization_preflight(root, project_root)
    private_dir(root)
    with ProcessLock(root / "init.lock"):
        config = initialization_preflight(root, project_root)
        if config is not None:
            Store(root, clock, id_factory)
            return config
        config = ProjectConfig(project_id=id_factory(), project_root=str(project_root), display_name=project_root.name)
        private_write(root / ".gitignore", "*\n")
        private_dir(root / "credentials")
        private_write(root / "cursor.key", secrets.token_bytes(32))
        db = root / "state.sqlite3"
        private_write(db, b"")
        conn = sqlite3.connect(db)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.executescript(files("agent_dms").joinpath("migrations/001_initial.sql").read_text())
            conn.execute("INSERT INTO schema_migrations VALUES(?,?)", (SCHEMA_VERSION, clock()))
            conn.execute("INSERT INTO project VALUES(?,?,?,1)", (config.project_id, config.display_name, clock()))
            conn.commit()
        finally:
            conn.close()
        private_write(root / "project.json", config.model_dump_json(indent=2) + "\n")
    return config
