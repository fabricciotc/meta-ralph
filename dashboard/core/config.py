from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.paths import get_config_path

DEFAULT_CONFIG: Dict[str, Any] = {
    "preferredBackend": None,
    "backendConfig": {},
    "projectsRoot": None,
    "maxWorkers": 10,
}


def get_config_path_local() -> Path:
    """Return the application config file path."""
    return get_config_path()


def load_config() -> Dict[str, Any]:
    path = get_config_path_local()
    if not path.exists():
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = value
        return data
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    path = get_config_path_local()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_preferred_backend() -> Optional[str]:
    env_backend = os.environ.get("AGENTICFLOW_BACKEND") or os.environ.get("META_RALPH_BACKEND")
    if env_backend and env_backend != "auto":
        return env_backend
    return load_config().get("preferredBackend")


def set_preferred_backend(name: Optional[str]) -> None:
    config = load_config()
    config["preferredBackend"] = name
    save_config(config)


def get_projects_root() -> Optional[str]:
    return load_config().get("projectsRoot")


def set_projects_root(path: Optional[str]) -> None:
    config = load_config()
    config["projectsRoot"] = path
    save_config(config)


def get_max_workers() -> int:
    """Return the configured max parallel workers.

    Priority:
      1. AGENTICFLOW_MAX_WORKERS environment variable.
      2. maxWorkers field in config.json.
      3. DEFAULT_CONFIG (10).
    """
    env_value = os.environ.get("AGENTICFLOW_MAX_WORKERS")
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            pass
    return int(load_config().get("maxWorkers", DEFAULT_CONFIG["maxWorkers"]))


def set_max_workers(value: int) -> None:
    config = load_config()
    config["maxWorkers"] = max(1, int(value))
    save_config(config)
