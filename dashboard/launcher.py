#!/usr/bin/env python3
"""
AgenticFlow local engine launcher.

Starts the Flask dashboard server in the background, opens the PWA in the
user's default browser, and manages the process lifecycle (status/stop).
"""

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


DASHBOARD_PORT = int(os.environ.get("AGENTICFLOW_PORT") or os.environ.get("META_RALPH_DASHBOARD_PORT") or "5050")
DEFAULT_HOST = os.environ.get("AGENTICFLOW_HOST", "127.0.0.1")


def get_repo_root() -> Path:
    """Return the repository root (parent of dashboard/)."""
    return Path(__file__).resolve().parent.parent


def get_dashboard_dir() -> Path:
    return Path(__file__).resolve().parent


def get_venv_dir() -> Path:
    return get_dashboard_dir() / ".venv"


def get_pid_file() -> Path:
    return get_dashboard_dir() / ".engine.pid"


def get_python_cmd() -> str:
    """Return the Python interpreter from the virtual environment."""
    venv = get_venv_dir()
    if platform.system() == "Windows":
        candidate = venv / "Scripts" / "python.exe"
    else:
        candidate = venv / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        print("Error: python3 or python is not installed.", file=sys.stderr)
        sys.exit(1)
    return python


def get_pip_cmd() -> str:
    venv = get_venv_dir()
    if platform.system() == "Windows":
        candidate = venv / "Scripts" / "pip.exe"
    else:
        candidate = venv / "bin" / "pip"
    if candidate.exists():
        return str(candidate)
    pip = shutil.which("pip3") or shutil.which("pip")
    if not pip:
        print("Error: pip is not available.", file=sys.stderr)
        sys.exit(1)
    return pip


def ensure_venv() -> None:
    """Create and configure the dashboard virtual environment if needed."""
    venv = get_venv_dir()
    if venv.exists():
        return
    print("Creating AgenticFlow virtual environment...")
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        print("Error: python3 or python is not installed.", file=sys.stderr)
        sys.exit(1)
    subprocess.run([python, "-m", "venv", str(venv)], check=True)
    pip = get_pip_cmd()
    subprocess.run([pip, "install", "-q", "--upgrade", "pip"], check=False)
    requirements = get_dashboard_dir() / "requirements.txt"
    subprocess.run([pip, "install", "-q", "-r", str(requirements)], check=True)
    print("Virtual environment ready.")


def start_engine(open_browser: bool = True) -> None:
    """Start the local engine in the background."""
    ensure_venv()

    pid_file = get_pid_file()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _is_process_running(pid):
                print(f"AgenticFlow engine is already running (PID {pid}).")
                if open_browser:
                    _open_dashboard()
                return
        except ValueError:
            pass

    python = get_python_cmd()
    server_script = get_dashboard_dir() / "server.py"
    env = os.environ.copy()
    env["AGENTICFLOW_PORT"] = str(DASHBOARD_PORT)

    print(f"Starting AgenticFlow engine on http://{DEFAULT_HOST}:{DASHBOARD_PORT} ...")
    process = subprocess.Popen(
        [python, str(server_script), "--port", str(DASHBOARD_PORT), "--host", DEFAULT_HOST, "--no-browser"],
        cwd=str(get_dashboard_dir()),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid_file.write_text(str(process.pid))
    print(f"Engine started (PID {process.pid}).")

    # Wait briefly for the server to come up.
    for _ in range(20):
        if _is_port_open(DEFAULT_HOST, DASHBOARD_PORT):
            break
        time.sleep(0.25)

    if open_browser:
        _open_dashboard()


def stop_engine() -> None:
    """Stop the local engine."""
    pid_file = get_pid_file()
    if not pid_file.exists():
        print("AgenticFlow engine is not running.")
        return
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        print("Invalid PID file; removing it.")
        pid_file.unlink(missing_ok=True)
        return

    if not _is_process_running(pid):
        print("AgenticFlow engine is not running.")
        pid_file.unlink(missing_ok=True)
        return

    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    pid_file.unlink(missing_ok=True)
    print("AgenticFlow engine stopped.")


def engine_status() -> None:
    """Print the current engine status."""
    pid_file = get_pid_file()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _is_process_running(pid):
                print(f"AgenticFlow engine is running (PID {pid}).")
                print(f"Dashboard: http://{DEFAULT_HOST}:{DASHBOARD_PORT}")
                return
        except ValueError:
            pass
    print("AgenticFlow engine is not running.")


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in result.stdout
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _is_port_open(host: str, port: int) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _find_installed_pwa() -> Path | None:
    """Return the path to an installed AgenticFlow PWA app, if any."""
    home = Path.home()
    system = platform.system()
    candidates = []

    if system == "Darwin":
        candidates = [
            Path("/Applications/AgenticFlow.app"),
            home / "Applications" / "AgenticFlow.app",
            home / "Applications" / "Chrome Apps.localized" / "AgenticFlow.app",
            home / "Applications" / "Chrome Apps" / "AgenticFlow.app",
        ]
    elif system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA")
        appdata = os.environ.get("APPDATA")
        if local_appdata:
            candidates.append(Path(local_appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Chrome Apps" / "AgenticFlow.lnk")
            candidates.append(Path(local_appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AgenticFlow.lnk")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Chrome Apps" / "AgenticFlow.lnk")
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AgenticFlow.lnk")
    else:
        candidates = [
            home / ".local" / "share" / "applications" / "AgenticFlow.desktop",
            home / ".local" / "share" / "applications" / "chrome-AgenticFlow-Default.desktop",
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _open_dashboard() -> None:
    url = f"http://{DEFAULT_HOST}:{DASHBOARD_PORT}"
    pwa = _find_installed_pwa()
    if pwa:
        print(f"Opening installed PWA: {pwa}")
        try:
            if platform.system() == "Darwin":
                subprocess.run(["open", "-a", pwa.name.replace(".app", ""), url], check=False)
            elif platform.system() == "Windows":
                os.startfile(str(pwa))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(pwa)], check=False)
            return
        except Exception as exc:
            print(f"Could not open PWA ({exc}), falling back to browser.")
    print(f"Opening {url}")
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticFlow local engine launcher")
    parser.add_argument("command", choices=["start", "stop", "status"], default="start", nargs="?")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    args = parser.parse_args()

    if args.command == "start":
        start_engine(open_browser=not args.no_browser)
    elif args.command == "stop":
        stop_engine()
    elif args.command == "status":
        engine_status()


if __name__ == "__main__":
    main()
