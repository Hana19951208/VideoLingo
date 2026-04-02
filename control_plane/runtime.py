from __future__ import annotations

import os
from pathlib import Path


def get_db_path() -> Path:
    return Path(os.environ.get("VIDEOLINGO_CONTROL_DB", "control_plane.db"))


def get_workspace_root() -> Path:
    return Path(os.environ.get("VIDEOLINGO_ACTIVE_WORKSPACE", "."))


def get_history_root() -> Path:
    return Path(os.environ.get("VIDEOLINGO_HISTORY_ROOT", "history"))


def get_log_root() -> Path:
    return Path(os.environ.get("VIDEOLINGO_LOG_ROOT", "logs"))


def ensure_runtime_dirs() -> None:
    for path in [get_db_path().parent, get_workspace_root(), get_history_root(), get_log_root()]:
        path.mkdir(parents=True, exist_ok=True)
