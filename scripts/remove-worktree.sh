#!/bin/bash
# Remove a git worktree and its associated branch.
# Usage: remove-worktree.sh <task_id>

set -e

TASK_ID="$1"
META_DIR="${META_DIR:-scripts/meta-ralph}"

if [ -z "$TASK_ID" ]; then
  echo "Usage: remove-worktree.sh <task_id>"
  exit 1
fi

WORKER_FILE="$META_DIR/state/workers/$TASK_ID.json"
if [ ! -f "$WORKER_FILE" ]; then
  echo "Worker $TASK_ID was not found."
  exit 0
fi

WORKTREE=$(jq -r '.worktree // empty' "$WORKER_FILE" 2>/dev/null || echo "")
BRANCH=$(jq -r '.branch // empty' "$WORKER_FILE" 2>/dev/null || echo "")

if [ -n "$WORKTREE" ] && [ -d "$WORKTREE/.git" ]; then
  git worktree remove "$WORKTREE" --force 2>/dev/null || rm -rf "$WORKTREE"
fi

if [ -n "$BRANCH" ] && [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
  git branch -D "$BRANCH" 2>/dev/null || true
fi

rm -f "$WORKER_FILE"
echo "Worktree $TASK_ID removed."
