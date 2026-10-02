import os
from pathlib import Path

import pytest

from agent_dms.errors import DomainError
from agent_dms.storage import ProcessLock, Store, initialize
from conftest import Harness, error


def test_init_reinit_modes_new_schema(h):
    before = h.service.store.config
    assert initialize(Path(before.project_root)) == before
    for path in h.data_dir.rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
    error("VALIDATION_ERROR", lambda: initialize(h.data_dir.parent.parent, h.data_dir))
    with ProcessLock(h.data_dir / "serve.lock"):
        error("CAPACITY_LIMIT", lambda: ProcessLock(h.data_dir / "serve.lock").__enter__())
    with h.service.store.transaction() as conn:
        conn.execute("INSERT INTO schema_migrations VALUES(99,0)")
    error("VALIDATION_ERROR", lambda: Store(h.data_dir))


def test_credential_rotation_revocation_isolation(h, tmp_path):
    a = h.add("  Cafe\u0301  ")
    error("VALIDATION_ERROR", lambda: h.add("CAFÉ"))
    h.open(a)
    old_token, old_session = h.tokens[a], h.sessions[a]
    other = Harness(tmp_path / "other")
    other.add("Café")
    error("UNAUTHENTICATED", lambda: other.service.call(old_token, "agent_whoami", {}))
    new = h.service.rotate_token(a)
    new_token = Path(new["credential_file"]).read_text().strip()
    assert new_token != old_token
    error("UNAUTHENTICATED", lambda: h.service.call(old_token, "agent_whoami", {}))
    error("SESSION_REQUIRED", lambda: h.service.call(new_token, "session_heartbeat", {"session_id": old_session}))
    h.tokens[a] = new_token
    h.open(a, "new")
    h.service.revoke(a)
    rotated_revoked = h.service.rotate_token(a)
    error("UNAUTHENTICATED", lambda: h.service.call(Path(rotated_revoked["credential_file"]).read_text().strip(), "agent_whoami", {}))
    assert h.service.operator_list()[0]["state"] == "revoked"
    assert set(h.service.operator_list()[0]) == {"id", "name", "provider", "model", "state"}


def test_symlinks_and_populated_targets(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    error("VALIDATION_ERROR", lambda: initialize(alias))
    state = root / "occupied"
    state.mkdir()
    (state / "other").write_text("retain")
    error("VALIDATION_ERROR", lambda: initialize(root, state))
    assert (state / "other").read_text() == "retain"


def test_token_file_failure_preserves_digest(h, monkeypatch):
    a = h.add("agent")
    import agent_dms.identity as identity
    monkeypatch.setattr(identity, "private_write", lambda *args: (_ for _ in ()).throw(OSError("injected disk failure")))
    with pytest.raises(OSError):
        h.service.rotate_token(a)
    assert h.call(a, "agent_whoami")["agent_id"] == a


def test_sqlite_uri_special_path_characters(tmp_path):
    harness = Harness(tmp_path / "project?#with space")
    agent = harness.add("path test")
    assert harness.call(agent, "agent_whoami")["agent_id"] == agent


def test_name_and_declared_metadata_boundaries(h):
    h.add("n" * 64)
    for value in ("", " \t", "n" * 65, "name\x00bad", "name\nline"):
        error("VALIDATION_ERROR", lambda value=value: h.add(value))
    h.service.add_agent("metadata", "p" * 100, "m" * 200)
    error("VALIDATION_ERROR", lambda: h.service.add_agent("bad-provider", "p" * 101))
    error("VALIDATION_ERROR", lambda: h.service.add_agent("bad-model", model="m" * 201))
