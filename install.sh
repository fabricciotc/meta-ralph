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

# Registrar el skill en el directorio de skills de Kimi Code CLI
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
  if command -v python3 >/dev/null 2>&1; then
    echo "⚙️  Creando entorno virtual para el dashboard..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$DASHBOARD_DIR/requirements.txt"
    echo "✅ Dashboard dependencies instaladas"
  else
    echo "⚠️  python3 no encontrado. El dashboard requiere Python 3."
  fi
else
  echo "ℹ️  Entorno virtual del dashboard ya existe"
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
if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
  echo "" >> "$RC_FILE"
  echo "# Meta-Ralph CLI" >> "$RC_FILE"
  echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
  echo "✅ Agregado $BIN_DIR a PATH en $RC_FILE"
else
  echo "ℹ️  $BIN_DIR ya está en PATH"
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
