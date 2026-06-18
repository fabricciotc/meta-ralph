#!/usr/bin/env python3
"""Validate a fresh AgenticFlow install."""

import json
import subprocess
import sys
from pathlib import Path


def venv_python_path(app_dir: Path) -> Path:
    venv = app_dir / "dashboard" / ".venv"
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main():
    app_dir = Path(__file__).resolve().parent.parent
    venv = app_dir / "dashboard" / ".venv"
    errors = []

    if not venv.exists():
        errors.append(f"venv missing: {venv}")
    else:
        python_bin = venv_python_path(app_dir)
        result = run([str(python_bin), "-c", "import flask, yaml, requests"])
        if result.returncode != 0:
            errors.append(f"venv dependencies missing: {result.stderr}")

    config = app_dir / ".agenticflow" / "config.json"
    if not config.exists():
        errors.append(f"config missing: {config}")
    else:
        try:
            data = json.loads(config.read_text(encoding="utf-8-sig"))
            assert "preferred_backends" in data
        except Exception as exc:
            errors.append(f"config invalid: {exc}")

    local_bin = Path.home() / ".local" / "bin"
    symlink_local = local_bin / "agenticflow"
    symlink_home = Path.home() / ".bin" / "agenticflow"
    windows_launcher = local_bin / "agenticflow.cmd"
    if (
        not symlink_local.exists()
        and not symlink_home.exists()
        and not windows_launcher.exists()
    ):
        errors.append("agenticflow launcher not found in PATH dirs")

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    print("AgenticFlow install looks good")


if __name__ == "__main__":
    main()
