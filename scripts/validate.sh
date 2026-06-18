#!/bin/bash
# Validate the AgenticFlow application structure.

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

warn() {
  echo "WARN: $1"
  ERRORS=$((ERRORS + 1))
}

ok() {
  echo "OK: $1"
}

echo "Validating AgenticFlow app at $APP_DIR..."
echo ""

# 1. Executable scripts.
for script in agenticflow create-worktree.sh remove-worktree.sh merge-batch.sh update-worker-state.sh dispatch-workers.sh finalize-batch.sh; do
  if [ -x "$APP_DIR/scripts/$script" ]; then
    ok "Executable script: $script"
  else
    warn "Script is missing or not executable: $script"
  fi
done

# 2. References.
for ref in metagpt-roles.md worker-prompt-template.md qa-prompt-template.md orchestrator-prompt.md; do
  if [ -f "$APP_DIR/references/$ref" ]; then
    ok "Reference: $ref"
  else
    warn "Missing reference: $ref"
  fi
done

# 3. Assets.
if [ -f "$APP_DIR/assets/prd-template.json" ]; then
  ok "Asset: prd-template.json"
else
  warn "Missing asset: prd-template.json"
fi

if [ $ERRORS -eq 0 ]; then
  echo ""
  echo "AgenticFlow app is valid and ready to use."
  exit 0
else
  echo ""
  echo "Found $ERRORS issue(s). Review the output above."
  exit 1
fi
