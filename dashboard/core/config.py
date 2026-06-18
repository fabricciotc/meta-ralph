from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    "preferredBackend": None,
    "backendConfig": {},
    "projectsRoot": None,
}


def get_meta_dir() -> Path:
    """Return the scripts/meta-ralph directory relative to the project.

    Prefer the current working directory when it already contains the
    meta-ralph scripts folder (used when the dashboard runs inside a project).
    Otherwise fall back to the skill repository root.
    """
    cwd_candidate = Path.cwd() / "scripts" / "meta-ralph"
    if cwd_candidate.exists():
        return cwd_candidate
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "scripts" / "meta-ralph"


def get_config_path() -> Path:
    return get_meta_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    path = get_config_path()
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
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_preferred_backend() -> Optional[str]:
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
