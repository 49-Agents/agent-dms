import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_dms.cli import main
from agent_dms.operations import backup, doctor, restore
from agent_dms.service import Service
from agent_dms.storage import Store
from conftest import error


def test_online_backup_restore_preserves_ids_pending_live_writes(h, peers, tmp_path):
    a, b, _ = peers
    first = h.send(a, b)
    def writes():
        for i in range(25):
            h.send(a, b, str(i))
    snapshot = tmp_path / "backup.sqlite3"
    with ThreadPoolExecutor(2) as pool:
        writing = pool.submit(writes)
        saved = pool.submit(backup, h.service.store, snapshot)
        metadata = saved.result()
        writing.result()
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert Path(str(snapshot) + ".json").stat().st_mode & 0o777 == 0o600
    target = tmp_path / "restored"
    result = restore(snapshot, target)
    assert result["project_id"] == h.service.store.config.project_id
    restored = Service(Store(target, h.clock))
    assert restored.call(h.tokens[b], "agent_whoami", {})["agent_id"] == b
    inbox = restored.call(h.tokens[b], "inbox_peek", {"session_id": h.sessions[b]})
    assert inbox["items"][0]["message_id"] == first["message_id"]
    error("VALIDATION_ERROR", lambda: restore(snapshot, target))
    error("VALIDATION_ERROR", lambda: backup(h.service.store, snapshot))
    with snapshot.open("ab") as f:
        f.write(b"tamper")
    error("VALIDATION_ERROR", lambda: restore(snapshot, tmp_path / "tampered"))
    assert not (tmp_path / "tampered").exists()


def test_cli_help_configs_and_no_credentials(h, peers, tmp_path, capsys):
    a, b, _ = peers
    assert main(["agent", "--data-dir", str(h.data_dir), "list"]) == 0
    roster = json.loads(capsys.readouterr().out)
    assert roster[0].keys() == {"id", "name", "provider", "model", "state"}
    import tomllib
    for client in ("codex", "claude", "generic"):
        for transport in ("http", "stdio"):
            assert main(["config", "--data-dir", str(h.data_dir), "--client", client, "--agent", a, "--transport", transport, "--token-file", "/private/project/agent.token"]) == 0
            output = capsys.readouterr().out
            config = tomllib.loads(output) if client == "codex" else json.loads(output)
            assert config
            assert h.tokens[a] not in output
            assert "bearer_token_env_var" in output if client == "codex" and transport == "http" else True
    assert doctor(h.service.store)["sdk_version"] == "2.2.0"
    assert main(["backup", "--data-dir", str(h.data_dir), "--out", str(tmp_path / "cli.sqlite3")]) == 0
    assert json.loads(capsys.readouterr().out)["project_id"] == h.service.store.config.project_id
    assert main(["restore", "--snapshot", str(tmp_path / "cli.sqlite3"), "--data-dir", str(tmp_path / "new")]) == 0
    assert json.loads(capsys.readouterr().out)["project_id"] == h.service.store.config.project_id


async def test_second_daemon_fails_clearly(h, live):
    import asyncio
    import sys
    from urllib.parse import urlsplit
    url, app = live
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "agent_dms", "serve", "--data-dir", str(h.data_dir), "--port", str(urlsplit(url).port), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(process.communicate(), 3)
    assert process.returncode == 1 and stdout == b""
    assert json.loads(stderr)["code"] == "CAPACITY_LIMIT"
    assert "active owner" in json.loads(stderr)["message"]


def test_restore_directory_preflight_private_nesting_and_symlinks(h, tmp_path):
    from conftest import error
    from test_storage_identity import tree_state
    snapshot = tmp_path / 'snapshot.sqlite3'
    backup(h.service.store, snapshot)
    for mode in (0o755, 0o700):
        occupied = tmp_path / f'occupied-{mode}'
        occupied.mkdir(mode=mode)
        occupied.chmod(mode)
        (occupied / 'retain').write_text('unrelated')
        before = tree_state(occupied)
        error('VALIDATION_ERROR', lambda: restore(snapshot, occupied))
        assert tree_state(occupied) == before
    unsafe = tmp_path / 'unsafe-empty'
    unsafe.mkdir(mode=0o755)
    unsafe.chmod(0o755)
    before = tree_state(unsafe)
    error('VALIDATION_ERROR', lambda: restore(snapshot, unsafe))
    assert tree_state(unsafe) == before
    alias = tmp_path / 'alias'
    alias.symlink_to(unsafe, target_is_directory=True)
    error('VALIDATION_ERROR', lambda: restore(snapshot, alias / 'new'))
    assert tree_state(unsafe) == before
    parent = tmp_path / 'shared-parent'
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    target = parent / 'nested/private/state'
    restore(snapshot, target)
    assert parent.stat().st_mode & 0o777 == 0o755
    for directory in (parent / 'nested', parent / 'nested/private', target, target / 'credentials'):
        assert directory.stat().st_mode & 0o777 == 0o700
    empty_private = tmp_path / 'empty-private'
    empty_private.mkdir(mode=0o700)
    assert restore(snapshot, empty_private)['project_id'] == h.service.store.config.project_id
