#!/bin/bash
# Valida la estructura del skill meta-ralph

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

warn() {
  echo "⚠️  $1"
  ERRORS=$((ERRORS + 1))
}

ok() {
  echo "✅ $1"
}

echo "Validando skill meta-ralph en $SKILL_DIR..."
echo ""

# 1. SKILL.md existe
if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  warn "Falta SKILL.md"
else
  ok "SKILL.md presente"
fi

# 2. Frontmatter básico
if [ -f "$SKILL_DIR/SKILL.md" ]; then
  if head -5 "$SKILL_DIR/SKILL.md" | grep -q "^name:"; then
    ok "Frontmatter: name presente"
  else
    warn "Frontmatter: falta 'name'"
  fi

  if head -10 "$SKILL_DIR/SKILL.md" | grep -q "^description:"; then
    ok "Frontmatter: description presente"
  else
    warn "Frontmatter: falta 'description'"
  fi
fi

# 3. Scripts ejecutables
for script in meta-ralph.sh create-worktree.sh remove-worktree.sh merge-batch.sh update-worker-state.sh dispatch-workers.sh finalize-batch.sh; do
  if [ -x "$SKILL_DIR/scripts/$script" ]; then
    ok "Script ejecutable: $script"
  else
    warn "Script no ejecutable o faltante: $script"
  fi
done

# 4. Referencias
for ref in metagpt-roles.md worker-prompt-template.md qa-prompt-template.md orchestrator-prompt.md; do
  if [ -f "$SKILL_DIR/references/$ref" ]; then
    ok "Referencia: $ref"
  else
    warn "Falta referencia: $ref"
  fi
done

# 5. Assets
if [ -f "$SKILL_DIR/assets/prd-template.json" ]; then
  ok "Asset: prd-template.json"
else
  warn "Falta asset: prd-template.json"
fi

# 6. No archivos prohibidos
for bad in README.md INSTALLATION_GUIDE.md QUICK_REFERENCE.md CHANGELOG.md; do
  if [ -f "$SKILL_DIR/$bad" ]; then
    warn "Archivo prohibido presente: $bad"
  fi
done

if [ $ERRORS -eq 0 ]; then
  echo ""
  echo "🎉 Skill válido. Listo para usar."
  exit 0
else
  echo ""
  echo "⚠️  Se encontraron $ERRORS problema(s). Revísalos arriba."
  exit 1
fi
