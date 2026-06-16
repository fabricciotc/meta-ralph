#!/usr/bin/env python3
"""Validate a fresh meta-ralph install."""

import json
import subprocess
import sys
from pathlib import Path


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main():
    skill_dir = Path(__file__).resolve().parent.parent
    venv = skill_dir / "dashboard" / ".venv"
    errors = []

    if not venv.exists():
        errors.append(f"venv missing: {venv}")
    else:
        result = run([str(venv / "bin" / "python"), "-c", "import flask, yaml, requests"])
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

    symlink_local = Path.home() / ".local" / "bin" / "meta-ralph"
    symlink_home = Path.home() / ".bin" / "meta-ralph"
    if not symlink_local.exists() and not symlink_home.exists():
        errors.append("meta-ralph symlink not found in PATH dirs")

    if errors:
        print("❌ Validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("✅ meta-ralph install looks good")


if __name__ == "__main__":
    main()
