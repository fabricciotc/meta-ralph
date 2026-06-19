#!/usr/bin/env python3
"""
AgenticFlow native app launcher.

This launcher no longer starts a web dashboard or opens a browser. It locates
the native Tauri desktop bundle (AgenticFlow.app / AgenticFlow.exe /
AgenticFlow.AppImage) and opens it. If the bundle is not installed yet, it
prints build/install instructions.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


BUNDLE_NAME = "AgenticFlow"


def get_repo_root() -> Path:
    """Return the repository root (parent of dashboard/)."""
    return Path(__file__).resolve().parent.parent


def _is_process_running(name: str) -> bool:
    """Best-effort check whether a process with the given name is running."""
    system = platform.system()
    try:
        if system == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}.exe", "/NH"],
                capture_output=True, text=True, check=False, timeout=5
            )
            return name in result.stdout
        else:
            result = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True, text=True, check=False, timeout=5
            )
            return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def _find_native_bundle() -> Path | None:
    """Return the path to the native AgenticFlow bundle, if it exists."""
    repo_root = get_repo_root()
    home = Path.home()
    system = platform.system()
    candidates: list[Path] = []

    if system == "Darwin":
        candidates = [
            repo_root / "src-tauri" / "target" / "release" / "bundle" / "macos" / f"{BUNDLE_NAME}.app",
            repo_root / "src-tauri" / "target" / "debug" / "bundle" / "macos" / f"{BUNDLE_NAME}.app",
            Path("/Applications") / f"{BUNDLE_NAME}.app",
            home / "Applications" / f"{BUNDLE_NAME}.app",
        ]
    elif system == "Windows":
        candidates = [
            repo_root / "src-tauri" / "target" / "release" / "bundle" / "nsis" / f"{BUNDLE_NAME}.exe",
            repo_root / "src-tauri" / "target" / "debug" / "bundle" / "nsis" / f"{BUNDLE_NAME}.exe",
            repo_root / "src-tauri" / "target" / "release" / f"{BUNDLE_NAME}.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / BUNDLE_NAME / f"{BUNDLE_NAME}.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / BUNDLE_NAME / f"{BUNDLE_NAME}.exe",
        ]
    else:
        # Linux / generic Unix
        candidates = [
            repo_root / "src-tauri" / "target" / "release" / "bundle" / "appimage" / f"{BUNDLE_NAME}.AppImage",
            repo_root / "src-tauri" / "target" / "debug" / "bundle" / "appimage" / f"{BUNDLE_NAME}.AppImage",
            Path("/usr/bin") / BUNDLE_NAME.lower(),
            Path("/usr/local/bin") / BUNDLE_NAME.lower(),
            home / ".local" / "bin" / BUNDLE_NAME.lower(),
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _open_path(path: Path) -> None:
    """Open a file/executable using the platform's native mechanism."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    elif system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        # Try to run AppImage/executable directly if executable; otherwise xdg-open.
        if os.access(path, os.X_OK):
            subprocess.Popen([str(path)], start_new_session=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)


def start_native_app() -> None:
    """Open the native AgenticFlow desktop app."""
    if _is_process_running(BUNDLE_NAME):
        print("AgenticFlow is already running.")
        return

    bundle = _find_native_bundle()
    if not bundle:
        print("AgenticFlow native app is not installed in this system.")
        print("")
        print("Build it locally with:")
        print("  scripts/build-sidecar.sh && npm run tauri build")
        print("")
        print("Or install a release DMG/EXE/AppImage and place it in a standard location.")
        sys.exit(1)

    print(f"Opening AgenticFlow native app: {bundle}")
    _open_path(bundle)


def stop_native_app() -> None:
    """Advise the user how to close the native app."""
    if not _is_process_running(BUNDLE_NAME):
        print("AgenticFlow is not running.")
        return
    print("AgenticFlow native app is running. Close it from its window (Cmd+Q / Alt+F4 / window close).")


def engine_status() -> None:
    """Print whether the native app process is running."""
    if _is_process_running(BUNDLE_NAME):
        print("AgenticFlow native app is running.")
    else:
        print("AgenticFlow native app is not running.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticFlow native app launcher")
    parser.add_argument(
        "command",
        choices=["start", "stop", "status"],
        default="start",
        nargs="?",
        help="start: open the native app; stop: show how to close it; status: show whether it is running",
    )
    # --no-browser is kept as a no-op for backward compatibility with old aliases.
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.command == "start":
        start_native_app()
    elif args.command == "stop":
        stop_native_app()
    elif args.command == "status":
        engine_status()


if __name__ == "__main__":
    main()
