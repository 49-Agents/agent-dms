import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from importlib.metadata import version
from pathlib import Path

from .config import ProjectConfig, private_dir, private_write, safe_path
from .errors import fail
from .models import canonical, new_id, rfc3339, utc_ms
from .storage import SCHEMA_VERSION, Store


def file_hash(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def validate_snapshot(path, metadata):
    path = safe_path(path)
    if not isinstance(metadata, dict) or metadata.get("version") != 1 or file_hash(path) != metadata.get("sha256") or metadata.get("schema_version") != SCHEMA_VERSION:
        fail("VALIDATION_ERROR", "Snapshot hash or schema is invalid")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            fail("VALIDATION_ERROR", "Snapshot integrity validation failed")
        schema = conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
        projects = conn.execute("SELECT id,display_name FROM project").fetchall()
        if schema != SCHEMA_VERSION or len(projects) != 1 or projects[0][0] != metadata.get("project_id"):
            fail("VALIDATION_ERROR", "Snapshot project or schema is invalid")
        return projects[0]
    except sqlite3.DatabaseError:
        fail("VALIDATION_ERROR", "Snapshot database is invalid")
    finally:
        conn.close()


def backup(store, out):
    out = safe_path(out)
    sidecar = safe_path(str(out) + ".json")
    if out.exists() or sidecar.exists():
        fail("VALIDATION_ERROR", "Backup target already exists")
    staging = out.with_name(out.name + ".partial-" + new_id())
    private_write(staging, b"")
    source = store.connect()
    target = sqlite3.connect(staging)
    try:
        source.backup(target, pages=128, sleep=0.01)
        target.execute("PRAGMA journal_mode=DELETE")
        target.close()
        metadata = {"version": 1, "project_id": store.config.project_id, "schema_version": SCHEMA_VERSION, "sha256": file_hash(staging), "created_at": rfc3339(store.clock())}
        validate_snapshot(staging, metadata)
        with staging.open("rb") as stream:
            os.fsync(stream.fileno())
        os.link(staging, out)  # Never overwrite a concurrently created target.
        private_write(sidecar, canonical(metadata) + "\n")
        staging.unlink()
        return metadata
    finally:
        source.close()
        target.close()


def restore(snapshot, data_dir):
    snapshot = safe_path(snapshot)
    sidecar = safe_path(str(snapshot) + ".json")
    try:
        metadata = json.loads(sidecar.read_text())
    except (ValueError, OSError):
        fail("VALIDATION_ERROR", "Snapshot metadata is missing or invalid")
    project_id, display_name = validate_snapshot(snapshot, metadata)
    root = safe_path(data_dir)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        fail("VALIDATION_ERROR", "Restore requires a new empty directory")
    root = private_dir(root)
    # O_EXCL ensures another restore cannot overwrite partially created state.
    private_write(root / ".gitignore", "*\n")
    private_dir(root / "credentials")
    private_write(root / "state.sqlite3", b"")
    with snapshot.open("rb") as source, (root / "state.sqlite3").open("r+b") as target:
        shutil.copyfileobj(source, target, 1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    private_write(root / "cursor.key", secrets.token_bytes(32))
    config = ProjectConfig(project_id=project_id, display_name=display_name, project_root=str(root.parent))
    private_write(root / "project.json", config.model_dump_json(indent=2) + "\n")
    Store(root)
    return {"project_id": project_id, "schema_version": SCHEMA_VERSION}


def doctor(store):
    store.validate()
    unsafe = []
    for path in [store.data_dir, *store.data_dir.rglob("*")]:
        mode = path.lstat().st_mode
        if path.is_symlink() or (mode & 0o077):
            unsafe.append(path.name)
    from .watch import codex_capability
    return {"ok": not unsafe, "project_id": store.config.project_id, "schema_version": SCHEMA_VERSION,
            "permissions_private": not unsafe, "unsafe_entry_count": len(unsafe),
            "sdk_version": version("mcp"), "sdk_expected": "2.2.0", "codex_queue_available": codex_capability() is not None,
            "sqlite_version": sqlite3.sqlite_version}


def client_config(client, transport, agent_id, url, token_file):
    from .client import service_url
    service_url(url)
    env_name = "AGENT_DMS_TOKEN_" + agent_id.replace("-", "_").upper()
    if transport == "stdio":
        entry = {"command": "agent-dms", "args": ["stdio", "--url", url, "--token-file", str(token_file)]}
        if client == "codex":
            return "[mcp_servers.agent_dms]\ncommand = \"agent-dms\"\nargs = " + json.dumps(entry["args"]) + "\n"
        return json.dumps({"mcpServers": {"agent-dms": entry}}, indent=2)
    if client == "codex":
        return f'[mcp_servers.agent_dms]\nurl = {json.dumps(url)}\nbearer_token_env_var = {json.dumps(env_name)}\n'
    entry = {"type": "http", "url": url, "headers": {"Authorization": "Bearer ${" + env_name + "}"}}
    return json.dumps({"mcpServers": {"agent-dms": entry}}, indent=2)
