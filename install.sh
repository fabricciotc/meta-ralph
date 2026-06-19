#!/bin/bash
# Install AgenticFlow as a standalone desktop/CLI application.
#
# Usage:
#   ./install.sh           # normal application install
#   ./install.sh --skill   # also register as an assistant skill

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$SKILL_DIR/scripts"
# shellcheck source=scripts/lib/platform.sh
source "$SCRIPT_DIR/lib/platform.sh"
LEGACY_SCRIPT="$SCRIPT_DIR/meta-ralph.sh"
AGENTICFLOW_SCRIPT="$SCRIPT_DIR/agenticflow"

INSTALL_AS_SKILL=""
if [ "${1:-}" = "--skill" ]; then
  INSTALL_AS_SKILL=1
fi

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

# Optional skill registration.
register_skill_dir() {
  local label="$1"
  local base_dir="$2"
  local target="$base_dir/meta-ralph"

  if [ -z "$base_dir" ]; then
    return
  fi

  mkdir -p "$base_dir"

  if [ "$SKILL_DIR" = "$target" ]; then
    echo "Skill already lives in the $label skill directory: $target"
    return
  fi

  if [ -e "$target" ] || [ -L "$target" ]; then
    local resolved
    resolved="$(readlink -f "$target" 2>/dev/null || echo "")"
    if [ "$resolved" = "$SKILL_DIR" ]; then
      echo "$label skill already registered: $target"
      return
    fi
    echo "Warning: $target already exists and points elsewhere. Skipping $label registration."
    return
  fi

  ln -sf "$SKILL_DIR" "$target"
  echo "Registered $label skill: $target -> $SKILL_DIR"
}

if [ -n "$INSTALL_AS_SKILL" ]; then
  register_skill_dir "Kimi Code" "${KIMI_CODE_SKILLS_DIR:-$HOME/.kimi-code/skills}"
  register_skill_dir "Kimi" "${KIMI_SKILLS_DIR:-$HOME/.kimi/skills}"
  register_skill_dir "Claude" "${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
  register_skill_dir "Cursor" "${CURSOR_SKILLS_DIR:-$HOME/.cursor/skills-cursor}"
  register_skill_dir "Codex" "${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"
fi

DASHBOARD_DIR="$SKILL_DIR/dashboard"
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

# Create the application data directory and default config.
DATA_DIR="$(agenticflow_data_dir)"
STATE_DIR="$DATA_DIR/state"
mkdir -p "$STATE_DIR" "$DATA_DIR/logs"

CONFIG_FILE="$DATA_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<'EOF'
{
  "preferredBackend": null,
  "backendConfig": {},
  "projectsRoot": null,
  "maxWorkers": 10
}
EOF
  echo "Created default config at $CONFIG_FILE"
fi

if [ ! -f "$STATE_DIR/prd.json" ]; then
  cp "$SKILL_DIR/assets/prd-template.json" "$STATE_DIR/prd.json"
  echo "Created PRD template at $STATE_DIR/prd.json"
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

chmod +x "$AGENTICFLOW_SCRIPT"
ln -sf "$AGENTICFLOW_SCRIPT" "$BIN_DIR/agenticflow"
echo "Created CLI symlink: $BIN_DIR/agenticflow -> $AGENTICFLOW_SCRIPT"

if [ -f "$LEGACY_SCRIPT" ]; then
  chmod +x "$LEGACY_SCRIPT"
  ln -sf "$LEGACY_SCRIPT" "$BIN_DIR/meta-ralph"
  echo "Created legacy CLI symlink: $BIN_DIR/meta-ralph -> $LEGACY_SCRIPT"
fi

if is_windows; then
  GIT_BASH="$(git_bash_path)" || GIT_BASH="/c/Program Files/Git/bin/bash.exe"
  GIT_BASH_CMD="$(to_windows_cmd_path "$GIT_BASH")"

  if [ -f "$AGENTICFLOW_SCRIPT" ]; then
    AGENTICFLOW_CMD_SCRIPT="$SCRIPT_DIR/agenticflow.cmd"
    if [ -f "$AGENTICFLOW_CMD_SCRIPT" ]; then
      cp "$AGENTICFLOW_CMD_SCRIPT" "$BIN_DIR/agenticflow.cmd"
      echo "Created Windows launcher: $BIN_DIR/agenticflow.cmd"
    fi
  fi

  if [ -f "$LEGACY_SCRIPT" ]; then
    SCRIPT_CMD="$(to_windows_cmd_path "$LEGACY_SCRIPT")"
    cat >"$BIN_DIR/meta-ralph.cmd" <<EOF
@echo off
"$GIT_BASH_CMD" "$SCRIPT_CMD" %*
EOF
    echo "Created Windows launcher: $BIN_DIR/meta-ralph.cmd"
  fi
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
detect_backend codex
if command -v copilot >/dev/null 2>&1 || command -v gh >/dev/null 2>&1; then
  echo "  ok: copilot"
  BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
else
  echo "  missing: copilot"
fi
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
  echo "  - codex (Codex CLI)"
  echo "  - copilot / gh (GitHub Copilot CLI)"
  echo "  - OPENAI_API_KEY environment variable"
fi

echo ""
echo "AgenticFlow installed."
echo ""
echo "Data directory: $DATA_DIR"
echo ""
echo "To open the native AgenticFlow desktop app:"
echo "  agenticflow start"
echo ""
echo "Legacy CLI still works:"
echo "  meta-ralph init"
echo "  meta-ralph run"
echo "  meta-ralph dashboard"
echo ""
echo "Restart your terminal or run:"
echo "  source $RC_FILE"
