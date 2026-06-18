#!/bin/bash
# Install AgenticFlow as a standalone local program.

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$APP_DIR/scripts"
# shellcheck source=scripts/lib/platform.sh
source "$SCRIPT_DIR/lib/platform.sh"
AGENTICFLOW_SCRIPT="$SCRIPT_DIR/agenticflow"

if [ ! -f "$AGENTICFLOW_SCRIPT" ]; then
  echo "Error: $AGENTICFLOW_SCRIPT was not found."
  exit 1
fi

chmod +x "$AGENTICFLOW_SCRIPT"

PY_BIN="$(python_cmd)" || {
  echo "Error: python3 or python is not installed. AgenticFlow requires Python 3.10+."
  exit 1
}

PY_MAJOR=$("$PY_BIN" -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$("$PY_BIN" -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "Error: Python 3.10+ is required. Detected: $PY_MAJOR.$PY_MINOR"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is not installed. AgenticFlow requires git."
  exit 1
fi

DASHBOARD_DIR="$APP_DIR/dashboard"
VENV_DIR="$DASHBOARD_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating dashboard virtual environment..."
  "$PY_BIN" -m venv "$VENV_DIR"
  "$(venv_pip "$VENV_DIR")" install -q --upgrade pip
  "$(venv_pip "$VENV_DIR")" install -q -r "$DASHBOARD_DIR/requirements.txt"
  echo "Dashboard dependencies installed."
else
  echo "Dashboard virtual environment already exists."
fi

STATE_DIR="$APP_DIR/.agenticflow"
mkdir -p "$STATE_DIR/state"
if [ ! -f "$STATE_DIR/config.json" ]; then
  cat > "$STATE_DIR/config.json" <<'EOF'
{
  "preferred_backends": ["kimi", "claude", "cursor", "copilot", "codex", "openai_api"],
  "model_overrides": {
    "openai_api": "gpt-4o-mini"
  },
  "timeout_defaults": {
    "pm_research": 600,
    "architect": 600,
    "planning": 600,
    "engineer": 1800,
    "qa": 600
  },
  "api_key_path": "~/.config/agenticflow/openai_api_key"
}
EOF
  echo "Created default config at $STATE_DIR/config.json"
fi

if [ ! -f "$STATE_DIR/prd.json" ]; then
  cat > "$STATE_DIR/prd.json" <<'EOF'
{
  "projectName": "Example",
  "stories": [
    {
      "id": "US-001",
      "title": "Example story",
      "description": "Describe the user story here."
    }
  ]
}
EOF
  echo "Created example PRD at $STATE_DIR/prd.json"
fi

SHELL_NAME="$(basename "$SHELL")"
case "$SHELL_NAME" in
  zsh)
    RC_FILE="$HOME/.zshrc"
    ;;
  bash)
    RC_FILE="$HOME/.bashrc"
    if [ "$(uname -s)" = "Darwin" ]; then
      RC_FILE="$HOME/.bash_profile"
    fi
    ;;
  fish)
    RC_FILE="$HOME/.config/fish/config.fish"
    mkdir -p "$(dirname "$RC_FILE")"
    ;;
  *)
    RC_FILE="$HOME/.profile"
    ;;
esac

if [ -d "$HOME/.local/bin" ]; then
  BIN_DIR="$HOME/.local/bin"
else
  BIN_DIR="$HOME/.bin"
  mkdir -p "$BIN_DIR"
fi

ln -sf "$AGENTICFLOW_SCRIPT" "$BIN_DIR/agenticflow"
echo "Created CLI symlink: $BIN_DIR/agenticflow -> $AGENTICFLOW_SCRIPT"

if is_windows; then
  APP_DIR_CMD="$(to_windows_cmd_path "$APP_DIR")"
  cat >"$BIN_DIR/agenticflow.cmd" <<EOF
@echo off
setlocal EnableExtensions
set "REPO_ROOT=$APP_DIR_CMD"

where python >nul 2>nul
if %errorlevel% == 0 (
    python "%REPO_ROOT%\\dashboard\\launcher.py" %*
    exit /b %errorlevel%
)

where python3 >nul 2>nul
if %errorlevel% == 0 (
    python3 "%REPO_ROOT%\\dashboard\\launcher.py" %*
    exit /b %errorlevel%
)

echo Error: python or python3 is not installed.
exit /b 1
EOF
  echo "Created Windows launcher: $BIN_DIR/agenticflow.cmd"
fi

if [ "$SHELL_NAME" = "fish" ]; then
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# AgenticFlow CLI" >> "$RC_FILE"
    echo "fish_add_path $BIN_DIR" >> "$RC_FILE"
    echo "Added $BIN_DIR to PATH in $RC_FILE"
  else
    echo "$BIN_DIR is already in PATH configuration."
  fi
else
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# AgenticFlow CLI" >> "$RC_FILE"
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
    echo "Added $BIN_DIR to PATH in $RC_FILE"
  else
    echo "$BIN_DIR is already in PATH configuration."
  fi
fi

echo ""
echo "Detected AI backends:"
BACKENDS_FOUND=0
detect_backend() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "  ok: $1"
    BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
  else
    echo "  missing: $1"
  fi
}

detect_backend kimi
detect_backend claude
if command -v cursor-agent >/dev/null 2>&1 || command -v agent >/dev/null 2>&1; then
  echo "  ok: cursor-agent"
  BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
else
  echo "  missing: cursor-agent"
fi
detect_backend copilot
detect_backend codex
if [ -n "$OPENAI_API_KEY" ]; then
  echo "  ok: openai_api (OPENAI_API_KEY is set)"
  BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
else
  echo "  missing: openai_api (OPENAI_API_KEY is not set)"
fi

if [ "$BACKENDS_FOUND" -eq 0 ]; then
  echo ""
  echo "No AI backend was detected yet. The dashboard will ask you to link one when it starts."
  echo "Supported options:"
  echo "  - kimi (Kimi Code CLI)"
  echo "  - claude (Claude Code CLI)"
  echo "  - cursor-agent / agent (Cursor agent CLI)"
  echo "  - copilot (GitHub Copilot CLI)"
  echo "  - codex (Codex CLI)"
  echo "  - OPENAI_API_KEY environment variable"
fi

echo ""
echo "AgenticFlow installed."
echo ""
echo "To start the local engine and open the dashboard:"
echo "  agenticflow start"
echo ""
echo "Then install the PWA from Chrome/Edge:"
echo "  1. Open http://localhost:5050"
echo "  2. Click the install icon in the address bar (or menu > Install AgenticFlow)"
echo ""
echo "Restart your terminal or run:"
echo "  source $RC_FILE"
