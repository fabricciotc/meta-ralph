#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TARGET_TRIPLE=$(rustc --print host-tuple)
SIDECAR_NAME="dashboard-server-${TARGET_TRIPLE}"

cd dashboard

# Prefer uv + a standalone CPython to avoid Anaconda/PyInstaller runtime issues.
if command -v uv >/dev/null 2>&1; then
  echo "Using uv to build the sidecar..."
  uv python install 3.12
  uv venv --python 3.12 --clear .venv-uv
  # shellcheck source=/dev/null
  source .venv-uv/bin/activate
  uv pip install -r requirements.txt pyinstaller
else
  echo "uv not found; falling back to system python3 venv..."
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  # shellcheck source=/dev/null
  source .venv/bin/activate
  pip install -q --upgrade pip pyinstaller
  pip install -q -r requirements.txt
fi

echo "Building sidecar with PyInstaller..."
pyinstaller -y --clean --onefile --name dashboard-server \
  --add-data "static:static" \
  --add-data "core/role_skills_registry.yaml:core" \
  --hidden-import engineio.async_drivers.threading \
  --hidden-import core.runners.copilot_cli \
  server.py

cd "$REPO_ROOT"
mkdir -p src-tauri/binaries

# Remove the old binary first to avoid stale macOS Gatekeeper caches.
rm -f "src-tauri/binaries/${SIDECAR_NAME}"
cp "dashboard/dist/dashboard-server" "src-tauri/binaries/${SIDECAR_NAME}"
chmod +x "src-tauri/binaries/${SIDECAR_NAME}"

echo "Sidecar ready: src-tauri/binaries/${SIDECAR_NAME}"
