#!/bin/bash
# Merge a worker batch into trunk using cherry-pick.
# Usage: merge-batch.sh <batch_id> [task_id1] [task_id2] ...

set -e

BATCH_ID="$1"
shift
META_DIR="${META_DIR:-scripts/meta-ralph}"

if [ -z "$BATCH_ID" ] || [ $# -eq 0 ]; then
  echo "Usage: merge-batch.sh <batch_id> <task_id>..."
  exit 1
fi

TRUNK=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")

# Save current HEAD for possible rollback.
BASE_HEAD=$(git rev-parse HEAD)

git checkout "$TRUNK" 2>/dev/null || git checkout -b "$TRUNK" 2>/dev/null || true

MERGED=()
FAILED=()

for TASK_ID in "$@"; do
  WORKER_FILE="$META_DIR/state/workers/$TASK_ID.json"
  if [ ! -f "$WORKER_FILE" ]; then
    FAILED+=("$TASK_ID")
    continue
  fi

  BRANCH=$(jq -r '.branch // empty' "$WORKER_FILE" 2>/dev/null || echo "")
  LAST_COMMIT=$(jq -r '.last_commit // empty' "$WORKER_FILE" 2>/dev/null || echo "")

  if [ -z "$LAST_COMMIT" ]; then
    # Try to read the latest commit from the branch.
    LAST_COMMIT=$(git rev-parse "$BRANCH" 2>/dev/null || echo "")
  fi

  if [ -z "$LAST_COMMIT" ]; then
    FAILED+=("$TASK_ID")
    continue
  fi

  # Check whether the commit is already in trunk.
  if git merge-base --is-ancestor "$LAST_COMMIT" HEAD 2>/dev/null; then
    MERGED+=("$TASK_ID")
    continue
  fi

  if git cherry-pick --no-commit "$LAST_COMMIT" >/dev/null 2>&1; then
    git commit -m "feat(meta-ralph): $TASK_ID batch $BATCH_ID" >/dev/null 2>&1
    MERGED+=("$TASK_ID")
  else
    git cherry-pick --abort 2>/dev/null || true
    FAILED+=("$TASK_ID")
  fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "FAILED ${FAILED[*]}"
  exit 1
fi

echo "MERGED ${MERGED[*]}"
