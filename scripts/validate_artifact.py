"""Focused A24 check: install built wheel into a fresh private temporary venv."""
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
wheels = list((root / "dist").glob(f"agent_dms-{version}-*.whl"))
assert len(wheels) == 1, "Build exactly one wheel for the current version"
wheel = wheels[0]
with zipfile.ZipFile(wheel) as artifact:
    names = artifact.namelist()
    assert any(name.endswith("/licenses/LICENSE") for name in names)
    assert any(name.endswith("/licenses/THIRD_PARTY_NOTICES.md") for name in names)
    assert not any(".agent-dms" in name or ".venv" in name or "__pycache__" in name for name in names)
for path in (root / "examples").glob("*.json"):
    json.loads(path.read_text())
for path in (root / "examples").glob("*.toml"):
    tomllib.loads(path.read_text())
assert (root / "src/agent_dms/protocol.md").read_bytes() == (root / "docs/PROTOCOL.md").read_bytes()
with tempfile.TemporaryDirectory(prefix="agent-dms-artifact-") as temporary:
    temporary = Path(temporary)
    venv = temporary / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / "bin/python"
    with (temporary / "install.log").open("w") as log:
        subprocess.run([str(python), "-m", "pip", "install", "--require-hashes", "-r", str(root / "requirements.lock")], check=True, stdout=log, stderr=log)
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], check=True, stdout=log, stderr=log)
    subprocess.run([str(python), "-m", "pip", "check"], check=True)
    result = subprocess.run([str(venv / "bin/agent-dms"), "--help"], check=True, text=True, capture_output=True)
    assert all(command in result.stdout for command in ("init", "serve", "agent", "watch", "backup", "restore", "stdio"))
    assert subprocess.check_output([str(venv / "bin/agent-dms"), "--version"], text=True).strip() == f"agent-dms {version}"
    subprocess.run([str(python), "-c", "import agent_dms; from importlib.resources import files; assert files('agent_dms').joinpath('migrations/001_initial.sql').is_file(); assert files('agent_dms').joinpath('protocol.md').is_file()"], check=True, cwd=temporary)
    assert not (temporary / ".agent-dms").exists()
    console = str(venv / "bin/agent-dms")
    initialized = json.loads(subprocess.check_output([console, "init", "--project-root", str(temporary)], text=True))
    added = json.loads(subprocess.check_output([console, "agent", "--data-dir", str(temporary / ".agent-dms"), "add", "Wheel agent"], text=True))
    assert initialized["project_id"] and set(added) == {"agent_id", "credential_file"}
    roster = json.loads(subprocess.check_output([console, "agent", "--data-dir", str(temporary / ".agent-dms"), "list"], text=True))
    assert roster[0]["id"] == added["agent_id"]
    subprocess.run([str(python), str(root / "examples/demo.py")], check=True, cwd=temporary, timeout=90)
print("Fresh wheel, locked dependencies, resources, CLI, config examples and two-client DM/ACK demo: passed")
