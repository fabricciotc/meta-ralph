#!/bin/bash
# Finalize a batch: merge to trunk if QA approves, or mark retry/replan.
# Usage: finalize-batch.sh <batch_id> <verdict> [failed_task_id]...

set -e

BATCH_ID="$1"
VERDICT="$2"
shift 2 || true
META_DIR="${META_DIR:-scripts/meta-ralph}"

# Resolve SKILL_DIR.
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
if [ -L "$SCRIPT_SOURCE" ]; then
  SCRIPT_SOURCE="$(readlink -f "$SCRIPT_SOURCE" 2>/dev/null || readlink "$SCRIPT_SOURCE" 2>/dev/null || echo "$SCRIPT_SOURCE")"
fi
SKILL_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"

if [ -z "$BATCH_ID" ] || [ -z "$VERDICT" ]; then
  echo "Usage: finalize-batch.sh <batch_id> <APPROVE|REJECT> [failed_task_id]..."
  exit 1
fi

BATCH_FILE="$META_DIR/state/batches/$BATCH_ID.json"
if [ ! -f "$BATCH_FILE" ]; then
  echo "Error: batch $BATCH_ID does not exist."
  exit 1
fi

TASKS=$(jq -r '.tasks[]' "$BATCH_FILE" 2>/dev/null || echo "")

if [ "$VERDICT" = "APPROVE" ]; then
  # Merge the whole batch.
  if "$SKILL_DIR/scripts/merge-batch.sh" "$BATCH_ID" $TASKS; then
    for TASK_ID in $TASKS; do
      "$SKILL_DIR/scripts/remove-worktree.sh" "$TASK_ID" 2>/dev/null || true
    done
    jq '.status = "completed" | .mergedAt = "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"' "$BATCH_FILE" > "$BATCH_FILE.tmp"
    mv "$BATCH_FILE.tmp" "$BATCH_FILE"
    echo "Batch $BATCH_ID merged."
  else
    jq '.status = "merge_failed"' "$BATCH_FILE" > "$BATCH_FILE.tmp"
    mv "$BATCH_FILE.tmp" "$BATCH_FILE"
    echo "Error: batch $BATCH_ID failed during merge."
    exit 1
  fi
else
  # REJECT: mark failed tasks and keep worktrees for retry.
  jq '.status = "rejected" | .rejectedAt = "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"' "$BATCH_FILE" > "$BATCH_FILE.tmp"
  mv "$BATCH_FILE.tmp" "$BATCH_FILE"
  for TASK_ID in "$@"; do
    "$SKILL_DIR/scripts/update-worker-state.sh" "$TASK_ID" "failed" "" 2>/dev/null || true
  done
  echo "Batch $BATCH_ID rejected. Worktrees preserved for retry."
fi
