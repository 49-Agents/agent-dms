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


def tree_state(root):
    return {str(p.relative_to(root)): (p.stat().st_mode & 0o777, None if p.is_dir() else p.read_bytes())
            for p in [root, *root.rglob('*')]}


@pytest.mark.parametrize('mode', [0o755, 0o700])
def test_rejected_init_preserves_populated_directory(tmp_path, mode):
    project = tmp_path / 'project'
    project.mkdir()
    target = tmp_path / 'occupied'
    target.mkdir(mode=mode)
    target.chmod(mode)
    (target / 'retain').write_text('unrelated contents')
    before = tree_state(target)
    error('VALIDATION_ERROR', lambda: initialize(project, target))
    assert tree_state(target) == before
    assert not (target / 'init.lock').exists()


def test_wrong_project_init_preflight_preserves_state(h, tmp_path):
    other = tmp_path / 'other-project'
    other.mkdir()
    (h.data_dir / 'init.lock').unlink()
    before = tree_state(h.data_dir)
    error('VALIDATION_ERROR', lambda: initialize(other, h.data_dir))
    assert tree_state(h.data_dir) == before
    assert not (h.data_dir / 'init.lock').exists()


def test_nested_private_creation_preserves_existing_ancestors(tmp_path):
    project = tmp_path / 'public-parent'
    project.mkdir(mode=0o755)
    project.chmod(0o755)
    target = project / 'nested' / 'private' / 'state'
    config = initialize(project, target)
    assert initialize(project, target) == config
    assert project.stat().st_mode & 0o777 == 0o755
    for path in (project / 'nested', project / 'nested/private', target, target / 'credentials'):
        assert path.stat().st_mode & 0o777 == 0o700


def test_existing_unsafe_empty_or_file_targets_unchanged(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    target = tmp_path / 'unsafe-empty'
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    before = tree_state(target)
    with pytest.raises(DomainError, match='repair their permissions'):
        initialize(project, target)
    assert tree_state(target) == before
    file_target = tmp_path / 'file'
    file_target.write_text('retain')
    before = (file_target.read_bytes(), file_target.stat().st_mode)
    error('VALIDATION_ERROR', lambda: initialize(project, file_target))
    assert (file_target.read_bytes(), file_target.stat().st_mode) == before


def test_credential_directory_rejects_unsafe_mode_without_writes(h):
    agent = h.add('existing')
    credentials = h.data_dir / 'credentials'
    credentials.chmod(0o755)
    before = tree_state(credentials)
    for operation in (lambda: h.add('new'), lambda: h.service.rotate_token(agent), lambda: Store(h.data_dir)):
        error('VALIDATION_ERROR', operation)
        assert tree_state(credentials) == before
    assert h.call(agent, 'agent_whoami')['agent_id'] == agent


def test_concurrent_initialization_excludes_partial_publishing(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import agent_dms.storage as storage
    project = tmp_path / 'project'
    project.mkdir()
    target = project / '.agent-dms'
    entered, resume = Event(), Event()
    write = storage.private_write
    def paused_write(path, data):
        if path.name == '.gitignore':
            entered.set()
            assert resume.wait(3)
        return write(path, data)
    monkeypatch.setattr(storage, 'private_write', paused_write)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(initialize, project)
        try:
            assert entered.wait(3)
            error('CAPACITY_LIMIT', lambda: initialize(project))
        finally:
            resume.set()
        config = first.result()
    assert initialize(project) == config
    assert Store(target).config == config
