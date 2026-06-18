#!/bin/bash
# Install meta-ralph as an assistant skill and global CLI command.

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$SKILL_DIR/scripts"
# shellcheck source=scripts/lib/platform.sh
source "$SCRIPT_DIR/lib/platform.sh"
SKILL_NAME="meta-ralph"
SCRIPT="$SCRIPT_DIR/meta-ralph.sh"

if [ ! -f "$SCRIPT" ]; then
  echo "Error: $SCRIPT was not found."
  exit 1
fi

chmod +x "$SCRIPT"

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

register_skill_dir() {
  local label="$1"
  local base_dir="$2"
  local target="$base_dir/$SKILL_NAME"

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

register_skill_dir "Kimi Code" "${KIMI_CODE_SKILLS_DIR:-$HOME/.kimi-code/skills}"
register_skill_dir "Kimi" "${KIMI_SKILLS_DIR:-$HOME/.kimi/skills}"
register_skill_dir "Claude" "${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
register_skill_dir "Cursor" "${CURSOR_SKILLS_DIR:-$HOME/.cursor/skills-cursor}"
register_skill_dir "Codex" "${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"

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

META_DIR="$SKILL_DIR/scripts/meta-ralph"
mkdir -p "$META_DIR/state"
if [ ! -f "$META_DIR/config.json" ]; then
  cat > "$META_DIR/config.json" <<'EOF'
{
  "preferred_backends": ["kimi", "claude", "cursor", "codex", "openai_api"],
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
  "api_key_path": "~/.config/meta-ralph/openai_api_key"
}
EOF
  echo "Created default config at $META_DIR/config.json"
fi

if [ ! -f "$META_DIR/prd.json" ]; then
  cat > "$META_DIR/prd.json" <<'EOF'
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
  echo "Created example PRD at $META_DIR/prd.json"
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

ln -sf "$SCRIPT" "$BIN_DIR/meta-ralph"
echo "Created CLI symlink: $BIN_DIR/meta-ralph -> $SCRIPT"

AGENTICFLOW_SCRIPT="$SCRIPT_DIR/agenticflow"
if [ -f "$AGENTICFLOW_SCRIPT" ]; then
  ln -sf "$AGENTICFLOW_SCRIPT" "$BIN_DIR/agenticflow"
  echo "Created CLI symlink: $BIN_DIR/agenticflow -> $AGENTICFLOW_SCRIPT"
fi

if is_windows; then
  GIT_BASH="$(git_bash_path)" || GIT_BASH="/c/Program Files/Git/bin/bash.exe"
  GIT_BASH_CMD="$(to_windows_cmd_path "$GIT_BASH")"
  SCRIPT_CMD="$(to_windows_cmd_path "$SCRIPT")"
  cat >"$BIN_DIR/meta-ralph.cmd" <<EOF
@echo off
"$GIT_BASH_CMD" "$SCRIPT_CMD" %*
EOF
  echo "Created Windows launcher: $BIN_DIR/meta-ralph.cmd"

  AGENTICFLOW_CMD_SCRIPT="$SCRIPT_DIR/agenticflow.cmd"
  if [ -f "$AGENTICFLOW_CMD_SCRIPT" ]; then
    cp "$AGENTICFLOW_CMD_SCRIPT" "$BIN_DIR/agenticflow.cmd"
    echo "Created Windows launcher: $BIN_DIR/agenticflow.cmd"
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
echo "You can still use the legacy CLI:"
echo "  meta-ralph init"
echo "  meta-ralph run"
echo ""
echo "Restart your terminal or run:"
echo "  source $RC_FILE"
