#!/bin/bash
# Install meta-ralph as an assistant skill and global CLI command.

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="meta-ralph"
SCRIPT="$SKILL_DIR/scripts/meta-ralph.sh"

if [ ! -f "$SCRIPT" ]; then
  echo "Error: $SCRIPT was not found."
  exit 1
fi

chmod +x "$SCRIPT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is not installed. Meta-Ralph requires Python 3.10+."
  exit 1
fi

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "Error: Python 3.10+ is required. Detected: $PY_MAJOR.$PY_MINOR"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is not installed. Meta-Ralph requires git."
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
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -q --upgrade pip
  "$VENV_DIR/bin/pip" install -q -r "$DASHBOARD_DIR/requirements.txt"
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

if [ "$SHELL_NAME" = "fish" ]; then
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Meta-Ralph CLI" >> "$RC_FILE"
    echo "fish_add_path $BIN_DIR" >> "$RC_FILE"
    echo "Added $BIN_DIR to PATH in $RC_FILE"
  else
    echo "$BIN_DIR is already in PATH configuration."
  fi
else
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Meta-Ralph CLI" >> "$RC_FILE"
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
detect_backend cursor
detect_backend codex
if [ -n "$OPENAI_API_KEY" ]; then
  echo "  ok: openai_api (OPENAI_API_KEY is set)"
  BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
else
  echo "  missing: openai_api (OPENAI_API_KEY is not set)"
fi

if [ "$BACKENDS_FOUND" -eq 0 ]; then
  echo ""
  echo "Warning: no AI backend was detected. Meta-Ralph will not be able to run prompts yet."
  echo "Install at least one backend or set META_RALPH_RUNNER_COMMAND for a custom runner."
fi

echo ""
echo "Meta-Ralph installed."
echo "CLI command: $BIN_DIR/meta-ralph"
echo ""
echo "Restart your terminal or run:"
echo "  source $RC_FILE"
echo ""
echo "Then, in a git project:"
echo "  meta-ralph init"
echo "  meta-ralph run"
