#!/bin/bash
# Crea un git worktree aislado para un worker
# Uso: create-worktree.sh <task_id> <base_branch>

set -e

TASK_ID="$1"
BASE_BRANCH="${2:-main}"
META_DIR="${META_DIR:-scripts/meta-ralph}"

if [ -z "$TASK_ID" ]; then
  echo "❌ Uso: create-worktree.sh <task_id> [base_branch]"
  exit 1
fi

WORKTREE_DIR="$META_DIR/state/worktrees/$TASK_ID"
BRANCH_NAME="meta-ralph/task-$TASK_ID"

# Asegurar que el base branch existe localmente
if ! git show-ref --verify --quiet "refs/heads/$BASE_BRANCH"; then
  git branch "$BASE_BRANCH" "origin/$BASE_BRANCH" 2>/dev/null || true
fi

# Crear worktree
mkdir -p "$META_DIR/state/worktrees"
if [ -d "$WORKTREE_DIR" ]; then
  rm -rf "$WORKTREE_DIR"
fi

git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" "$BASE_BRANCH" >/dev/null 2>&1 || {
  # Si la branch ya existe, solo crear worktree
  git branch -D "$BRANCH_NAME" 2>/dev/null || true
  git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" "$BASE_BRANCH" >/dev/null 2>&1
}

# Registrar worker
mkdir -p "$META_DIR/state/workers"
cat > "$META_DIR/state/workers/$TASK_ID.json" <<EOF
{
  "task_id": "$TASK_ID",
  "branch": "$BRANCH_NAME",
  "worktree": "$WORKTREE_DIR",
  "status": "running",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "$WORKTREE_DIR"
