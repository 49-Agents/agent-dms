import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .errors import fail


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    project_id: str
    project_root: str
    display_name: str


def safe_path(path):
    p = Path(path).absolute()
    for part in [p, *p.parents]:
        if part.is_symlink():
            fail("VALIDATION_ERROR", "Symlink state or credential targets are not supported")
    return p


def private_dir(path):
    path = safe_path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def private_write(path, data):
    path = safe_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data.encode() if isinstance(data, str) else data)
            stream.flush()
            os.fsync(stream.fileno())
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        # Leave any durable file for operator reconciliation; never publish a DB digest here.
        raise


def load_config(data_dir):
    root = safe_path(data_dir)
    path = safe_path(root / "project.json")
    try:
        config = ProjectConfig.model_validate_json(path.read_text())
        if config.version != 1:
            fail("VALIDATION_ERROR", "Unsupported configuration version")
        return config
    except (OSError, ValueError):
        fail("VALIDATION_ERROR", "State directory is not initialized or configuration is invalid")
