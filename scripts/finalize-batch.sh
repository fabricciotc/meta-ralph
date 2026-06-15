#!/bin/bash
# Finaliza un batch: merge al trunk si QA aprueba, o marca retry/replan.
# Uso: finalize-batch.sh <batch_id> <verdict> [failed_task_id]...

set -e

BATCH_ID="$1"
VERDICT="$2"
shift 2 || true
META_DIR="${META_DIR:-scripts/meta-ralph}"

# Resolver SKILL_DIR (ruta global del skill)
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
if [ -L "$SCRIPT_SOURCE" ]; then
  SCRIPT_SOURCE="$(readlink -f "$SCRIPT_SOURCE" 2>/dev/null || readlink "$SCRIPT_SOURCE" 2>/dev/null || echo "$SCRIPT_SOURCE")"
fi
SKILL_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"

if [ -z "$BATCH_ID" ] || [ -z "$VERDICT" ]; then
  echo "❌ Uso: finalize-batch.sh <batch_id> <APPROVE|REJECT> [failed_task_id]..."
  exit 1
fi

BATCH_FILE="$META_DIR/state/batches/$BATCH_ID.json"
if [ ! -f "$BATCH_FILE" ]; then
  echo "❌ Batch $BATCH_ID no existe"
  exit 1
fi

TASKS=$(jq -r '.tasks[]' "$BATCH_FILE" 2>/dev/null || echo "")

if [ "$VERDICT" = "APPROVE" ]; then
  # Mergear todo el batch
  if "$SKILL_DIR/scripts/merge-batch.sh" "$BATCH_ID" $TASKS; then
    for TASK_ID in $TASKS; do
      "$SKILL_DIR/scripts/remove-worktree.sh" "$TASK_ID" 2>/dev/null || true
    done
    jq '.status = "completed" | .mergedAt = "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"' "$BATCH_FILE" > "$BATCH_FILE.tmp"
    mv "$BATCH_FILE.tmp" "$BATCH_FILE"
    echo "✅ Batch $BATCH_ID mergeado"
  else
    jq '.status = "merge_failed"' "$BATCH_FILE" > "$BATCH_FILE.tmp"
    mv "$BATCH_FILE.tmp" "$BATCH_FILE"
    echo "❌ Batch $BATCH_ID falló en merge"
    exit 1
  fi
else
  # REJECT: marcar tasks fallidas y conservar worktrees para retry
  jq '.status = "rejected" | .rejectedAt = "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"' "$BATCH_FILE" > "$BATCH_FILE.tmp"
  mv "$BATCH_FILE.tmp" "$BATCH_FILE"
  for TASK_ID in "$@"; do
    "$SKILL_DIR/scripts/update-worker-state.sh" "$TASK_ID" "failed" "" 2>/dev/null || true
  done
  echo "🔄 Batch $BATCH_ID rechazado, worktrees preservados para retry"
fi
