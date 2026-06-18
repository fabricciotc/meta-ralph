#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TARGET_TRIPLE=$(rustc --print host-tuple)
SIDECAR_NAME="dashboard-server-${TARGET_TRIPLE}"

cd dashboard

if [ ! -d ".venv" ]; then
  echo "Creating dashboard virtual environment..."
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

pip install -q --upgrade pip pyinstaller
pip install -q -r requirements.txt

echo "Building sidecar with PyInstaller..."
pyinstaller --onefile --name dashboard-server \
  --add-data "static:static" \
  --add-data "core/role_skills_registry.yaml:core" \
  server.py

cd "$REPO_ROOT"
mkdir -p src-tauri/binaries

cp "dashboard/dist/dashboard-server" "src-tauri/binaries/${SIDECAR_NAME}"
chmod +x "src-tauri/binaries/${SIDECAR_NAME}"

echo "Sidecar ready: src-tauri/binaries/${SIDECAR_NAME}"
