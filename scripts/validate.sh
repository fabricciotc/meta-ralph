#!/bin/bash
# Validate the meta-ralph skill structure.

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

warn() {
  echo "WARN: $1"
  ERRORS=$((ERRORS + 1))
}

ok() {
  echo "OK: $1"
}

echo "Validating meta-ralph skill at $SKILL_DIR..."
echo ""

# 1. SKILL.md exists.
if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  warn "Missing SKILL.md"
else
  ok "SKILL.md present"
fi

# 2. Basic frontmatter.
if [ -f "$SKILL_DIR/SKILL.md" ]; then
  if head -5 "$SKILL_DIR/SKILL.md" | grep -q "^name:"; then
    ok "Frontmatter: name present"
  else
    warn "Frontmatter: missing 'name'"
  fi

  if head -10 "$SKILL_DIR/SKILL.md" | grep -q "^description:"; then
    ok "Frontmatter: description present"
  else
    warn "Frontmatter: missing 'description'"
  fi
fi

# 3. Executable scripts.
for script in meta-ralph.sh create-worktree.sh remove-worktree.sh merge-batch.sh update-worker-state.sh dispatch-workers.sh finalize-batch.sh; do
  if [ -x "$SKILL_DIR/scripts/$script" ]; then
    ok "Executable script: $script"
  else
    warn "Script is missing or not executable: $script"
  fi
done

# 4. References.
for ref in metagpt-roles.md worker-prompt-template.md qa-prompt-template.md orchestrator-prompt.md; do
  if [ -f "$SKILL_DIR/references/$ref" ]; then
    ok "Reference: $ref"
  else
    warn "Missing reference: $ref"
  fi
done

# 5. Assets.
if [ -f "$SKILL_DIR/assets/prd-template.json" ]; then
  ok "Asset: prd-template.json"
else
  warn "Missing asset: prd-template.json"
fi

# 6. Forbidden generated docs.
for bad in README.md INSTALLATION_GUIDE.md QUICK_REFERENCE.md CHANGELOG.md; do
  if [ -f "$SKILL_DIR/$bad" ]; then
    warn "Forbidden file present: $bad"
  fi
done

if [ $ERRORS -eq 0 ]; then
  echo ""
  echo "Skill is valid and ready to use."
  exit 0
else
  echo ""
  echo "Found $ERRORS issue(s). Review the output above."
  exit 1
fi
