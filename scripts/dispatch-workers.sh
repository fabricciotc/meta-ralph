#!/bin/bash
# Worker dispatch helper. It does not spawn assistant child agents.
# This script only prepares state and worktrees for a batch.
# Usage: dispatch-workers.sh <batch_id> <max_workers> <task_id1> [task_id2] ...

set -e

BATCH_ID="$1"
MAX_WORKERS="$2"
shift 2
META_DIR="${META_DIR:-scripts/meta-ralph}"
BASE_BRANCH="${BASE_BRANCH:-$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin//' | sed 's|^/||' || echo "main")}"

# Resolve SKILL_DIR.
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
if [ -L "$SCRIPT_SOURCE" ]; then
  SCRIPT_SOURCE="$(readlink -f "$SCRIPT_SOURCE" 2>/dev/null || readlink "$SCRIPT_SOURCE" 2>/dev/null || echo "$SCRIPT_SOURCE")"
fi
SKILL_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"

if [ -z "$BATCH_ID" ] || [ -z "$MAX_WORKERS" ] || [ $# -eq 0 ]; then
  echo "Usage: dispatch-workers.sh <batch_id> <max_workers> <task_id>..."
  exit 1
fi

if [ $# -gt "$MAX_WORKERS" ]; then
  echo "Error: batch $BATCH_ID exceeds MAX_WORKERS=$MAX_WORKERS; it has $# tasks."
  exit 1
fi

mkdir -p "$META_DIR/state/batches"

BATCH_FILE="$META_DIR/state/batches/$BATCH_ID.json"
TASKS_JSON=$(printf '%s\n' "$@" | jq -R . | jq -s .)

cat > "$BATCH_FILE" <<EOF
{
  "batchId": "$BATCH_ID",
  "status": "dispatching",
  "tasks": $TASKS_JSON,
  "maxWorkers": $MAX_WORKERS,
  "baseBranch": "$BASE_BRANCH",
  "startedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

for TASK_ID in "$@"; do
  WORKTREE_DIR=$("$SKILL_DIR/scripts/create-worktree.sh" "$TASK_ID" "$BASE_BRANCH" 2>/dev/null || echo "")
  if [ -z "$WORKTREE_DIR" ]; then
    echo "Error: failed to create worktree for $TASK_ID"
    exit 1
  fi
  echo "  Worktree created: $TASK_ID"
done

echo "BATCH_READY $BATCH_ID"
