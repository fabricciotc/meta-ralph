"""Application path helpers for AgenticFlow.

AgenticFlow stores user data in the OS-native application data directory:

- macOS:   ~/Library/Application Support/AgenticFlow
- Linux:   ~/.local/share/AgenticFlow  (or $XDG_DATA_HOME/AgenticFlow)
- Windows: %LOCALAPPDATA%/AgenticFlow

Set AGENTICFLOW_DATA_DIR to override this location.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path
from typing import Optional, Union


def _user_data_dir() -> Path:
    """Return the OS-native user data directory for AgenticFlow."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "AgenticFlow"
    if system == "Linux":
        base = os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / "AgenticFlow"
        return Path.home() / ".local" / "share" / "AgenticFlow"
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "AgenticFlow"
        return Path.home() / "AppData" / "Local" / "AgenticFlow"
    # Fallback for unexpected platforms.
    return Path.home() / ".agenticflow" / "data"


def get_app_data_dir() -> Path:
    """Return the root application data directory.

    Honors the AGENTICFLOW_DATA_DIR environment variable.
    """
    env_dir = os.environ.get("AGENTICFLOW_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
    else:
        path = _user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"


def get_state_dir() -> Path:
    path = get_app_data_dir() / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    path = get_app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_board_path() -> Path:
    return get_state_dir() / "board.json"


def get_run_state_path() -> Path:
    return get_state_dir() / "run-state.json"


def get_log_path() -> Path:
    return get_logs_dir() / "run.log"


def get_ticket_snapshot_path(ticket_id: Union[str, int]) -> Path:
    return get_state_dir() / "snapshots" / f"run-state.{ticket_id}.json"


def get_worktrees_dir() -> Path:
    path = get_app_data_dir() / "worktrees"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_name(name: str) -> str:
    """Make a string safe for use as a directory name."""
    safe = re.sub(r"[^\w\-_.]", "_", name)
    safe = re.sub(r"_+", "_", safe).strip("_.")
    return safe or "project"


def get_worktree_dir(project_name: str, ticket_id: Union[str, int]) -> Path:
    path = get_worktrees_dir() / sanitize_name(project_name) / str(ticket_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_engineer_notes_dir(repo_path: Union[str, Path]) -> Path:
    return Path(repo_path) / ".agenticflow" / "engineer-notes"


def migrate_legacy_state() -> None:
    """Move state from the old PyInstaller/frozen layout into the new layout.

    Old layout: ~/.agenticflow/data/scripts/meta-ralph/state
    New layout: <app-data-dir>/state
    """
    legacy_root = Path.home() / ".agenticflow" / "data" / "scripts" / "meta-ralph"
    legacy_state = legacy_root / "state"
    if not legacy_state.exists():
        return

    state_dir = get_state_dir()
    if state_dir.exists() and any(state_dir.iterdir()):
        # Already have state in the new layout; don't overwrite.
        return

    state_dir.mkdir(parents=True, exist_ok=True)
    for item in legacy_state.iterdir():
        dest = state_dir / item.name
        if dest.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Also migrate legacy config if present.
    legacy_config = legacy_root / "config.json"
    if legacy_config.exists():
        config_path = get_config_path()
        if not config_path.exists():
            shutil.copy2(legacy_config, config_path)
