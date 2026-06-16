#!/bin/bash
# Instala meta-ralph como skill de Kimi Code CLI y como comando global.

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="meta-ralph"
KIMI_SKILLS_DIR="${KIMI_SKILLS_DIR:-$HOME/.kimi-code/skills}"
TARGET_SKILL_DIR="$KIMI_SKILLS_DIR/$SKILL_NAME"
SCRIPT="$SKILL_DIR/scripts/meta-ralph.sh"

if [ ! -f "$SCRIPT" ]; then
  echo "❌ No se encontró $SCRIPT"
  exit 1
fi

chmod +x "$SCRIPT"

# Python check
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 no está instalado. meta-ralph requiere Python 3.10+."
  exit 1
fi

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "❌ Se requiere Python 3.10+. Versión detectada: $PY_MAJOR.$PY_MINOR"
  exit 1
fi

# Git check
if ! command -v git >/dev/null 2>&1; then
  echo "❌ git no está instalado. meta-ralph requiere git."
  exit 1
fi

# Registrar skill
if [ "$SKILL_DIR" != "$TARGET_SKILL_DIR" ]; then
  mkdir -p "$KIMI_SKILLS_DIR"
  if [ -e "$TARGET_SKILL_DIR" ] || [ -L "$TARGET_SKILL_DIR" ]; then
    if [ "$(readlink -f "$TARGET_SKILL_DIR" 2>/dev/null || echo "")" != "$SKILL_DIR" ]; then
      echo "⚠️  $TARGET_SKILL_DIR ya existe y apunta a otro lugar."
      echo "   Elimínalo manualmente si quieres reinstalar este skill."
      exit 1
    fi
  else
    ln -sf "$SKILL_DIR" "$TARGET_SKILL_DIR"
    echo "🔗 Skill registrado: $TARGET_SKILL_DIR → $SKILL_DIR"
  fi
else
  echo "ℹ️  El skill ya está en $TARGET_SKILL_DIR"
fi

# Crear venv para el dashboard
DASHBOARD_DIR="$SKILL_DIR/dashboard"
VENV_DIR="$DASHBOARD_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "⚙️  Creando entorno virtual para el dashboard..."
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -q --upgrade pip
  "$VENV_DIR/bin/pip" install -q -r "$DASHBOARD_DIR/requirements.txt"
  echo "✅ Dashboard dependencies instaladas"
else
  echo "ℹ️  Entorno virtual del dashboard ya existe"
fi

# Crear estructura de proyecto de ejemplo
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
  echo "✅ Configuración inicial creada en $META_DIR/config.json"
fi

if [ ! -f "$META_DIR/prd.json" ]; then
  cat > "$META_DIR/prd.json" <<'EOF'
{
  "projectName": "Ejemplo",
  "stories": [
    {
      "id": "US-001",
      "title": "Historia de ejemplo",
      "description": "Descripción de la historia de usuario."
    }
  ]
}
EOF
  echo "✅ PRD de ejemplo creado en $META_DIR/prd.json"
fi

# Detectar shell y archivo de configuración
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

# Crear symlink en ~/.local/bin si existe, sino en ~/.bin
if [ -d "$HOME/.local/bin" ]; then
  BIN_DIR="$HOME/.local/bin"
else
  BIN_DIR="$HOME/.bin"
  mkdir -p "$BIN_DIR"
fi

ln -sf "$SCRIPT" "$BIN_DIR/meta-ralph"
echo "🔗 Symlink creado: $BIN_DIR/meta-ralph → $SCRIPT"

# Asegurar que BIN_DIR esté en PATH
if [ "$SHELL_NAME" = "fish" ]; then
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Meta-Ralph CLI" >> "$RC_FILE"
    echo "fish_add_path $BIN_DIR" >> "$RC_FILE"
    echo "✅ Agregado $BIN_DIR a PATH en $RC_FILE"
  else
    echo "ℹ️  $BIN_DIR ya está en PATH"
  fi
else
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Meta-Ralph CLI" >> "$RC_FILE"
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
    echo "✅ Agregado $BIN_DIR a PATH en $RC_FILE"
  else
    echo "ℹ️  $BIN_DIR ya está en PATH"
  fi
fi

# Reporte de backends detectados
echo ""
echo "🔍 Backends de IA detectados:"
BACKENDS_FOUND=0
detect_backend() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "  ✅ $1"
    BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
  else
    echo "  ❌ $1 (no instalado)"
  fi
}
detect_backend kimi
detect_backend claude
detect_backend cursor
detect_backend codex
if [ -n "$OPENAI_API_KEY" ]; then
  echo "  ✅ openai_api (OPENAI_API_KEY configurada)"
  BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
else
  echo "  ❌ openai_api (OPENAI_API_KEY no configurada)"
fi

if [ "$BACKENDS_FOUND" -eq 0 ]; then
  echo ""
  echo "⚠️  No se detectó ningún backend de IA. meta-ralph no podrá ejecutar prompts."
  echo "   Instala al menos uno de los siguientes:"
  echo "   - Kimi Code CLI: https://kimi.com/download"
  echo "   - Claude Code: https://claude.ai/download"
  echo "   - Cursor: https://cursor.com"
  echo "   - OpenAI Codex CLI: npm install -g @openai/codex"
  echo "   - O configura OPENAI_API_KEY para usar la API de OpenAI."
fi

echo ""
echo "✅ Meta-Ralph instalado como skill en $TARGET_SKILL_DIR"
echo "✅ Comando 'meta-ralph' disponible en $BIN_DIR"
echo ""
echo "Reinicia tu terminal o ejecuta:"
echo "   source $RC_FILE"
echo ""
echo "Luego, en un proyecto git:"
echo "   meta-ralph init"
echo "   meta-ralph run"
