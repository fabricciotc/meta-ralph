#!/bin/bash
# Create an isolated git worktree for a worker.
# Usage: create-worktree.sh <task_id> <base_branch>

set -e

TASK_ID="$1"
BASE_BRANCH="${2:-main}"

if [ -z "$TASK_ID" ]; then
  echo "Usage: create-worktree.sh <task_id> [base_branch]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform.sh
source "$SCRIPT_DIR/lib/platform.sh"

DATA_DIR="$(agenticflow_data_dir)"
WORKTREE_DIR="$DATA_DIR/worktrees/$TASK_ID"
BRANCH_NAME="agenticflow/task-$TASK_ID"

# Ensure the base branch exists locally.
if ! git show-ref --verify --quiet "refs/heads/$BASE_BRANCH"; then
  git branch "$BASE_BRANCH" "origin/$BASE_BRANCH" 2>/dev/null || true
fi

# Create worktree.
mkdir -p "$DATA_DIR/worktrees"
if [ -d "$WORKTREE_DIR" ]; then
  rm -rf "$WORKTREE_DIR"
fi

git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" "$BASE_BRANCH" >/dev/null 2>&1 || {
  # If the branch already exists, recreate it from the base branch.
  git branch -D "$BRANCH_NAME" 2>/dev/null || true
  git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" "$BASE_BRANCH" >/dev/null 2>&1
}

# Register worker state.
mkdir -p "$DATA_DIR/state/workers"
cat > "$DATA_DIR/state/workers/$TASK_ID.json" <<EOF
{
  "task_id": "$TASK_ID",
  "branch": "$BRANCH_NAME",
  "worktree": "$WORKTREE_DIR",
  "status": "running",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "$WORKTREE_DIR"
