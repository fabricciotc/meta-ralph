#!/usr/bin/env python3
"""Validate a fresh meta-ralph install."""

import json
import subprocess
import sys
from pathlib import Path


def venv_python_path(skill_dir: Path) -> Path:
    venv = skill_dir / "dashboard" / ".venv"
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main():
    skill_dir = Path(__file__).resolve().parent.parent
    venv = skill_dir / "dashboard" / ".venv"
    errors = []

    if not venv.exists():
        errors.append(f"venv missing: {venv}")
    else:
        python_bin = venv_python_path(skill_dir)
        result = run([str(python_bin), "-c", "import flask, yaml, requests"])
        if result.returncode != 0:
            errors.append(f"venv dependencies missing: {result.stderr}")

    config = skill_dir / "scripts" / "meta-ralph" / "config.json"
    if not config.exists():
        errors.append(f"config missing: {config}")
    else:
        try:
            data = json.loads(config.read_text())
            assert "preferred_backends" in data
        except Exception as exc:
            errors.append(f"config invalid: {exc}")

    local_bin = Path.home() / ".local" / "bin"
    symlink_local = local_bin / "meta-ralph"
    symlink_home = Path.home() / ".bin" / "meta-ralph"
    windows_launcher = local_bin / "meta-ralph.cmd"
    if (
        not symlink_local.exists()
        and not symlink_home.exists()
        and not windows_launcher.exists()
    ):
        errors.append("meta-ralph launcher not found in PATH dirs")

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    print("meta-ralph install looks good")


if __name__ == "__main__":
    main()
