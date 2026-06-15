#!/bin/bash
# Actualiza el estado de un worker
# Uso: update-worker-state.sh <task_id> <status> [last_commit] [result_json]

set -e

TASK_ID="$1"
STATUS="$2"
LAST_COMMIT="${3:-}"
RESULT_JSON="${4:-}"
META_DIR="${META_DIR:-scripts/meta-ralph}"

if [ -z "$TASK_ID" ] || [ -z "$STATUS" ]; then
  echo "❌ Uso: update-worker-state.sh <task_id> <status> [last_commit] [result_json]"
  exit 1
fi

WORKER_FILE="$META_DIR/state/workers/$TASK_ID.json"
if [ ! -f "$WORKER_FILE" ]; then
  echo "❌ Worker $TASK_ID no existe"
  exit 1
fi

TMP=$(mktemp)
jq --arg status "$STATUS" \
   --arg commit "$LAST_COMMIT" \
   --arg ended_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '.status = $status | .ended_at = $ended_at | if $commit != "" then .last_commit = $commit else . end' \
   "$WORKER_FILE" > "$TMP"

if [ -n "$RESULT_JSON" ]; then
  jq --argjson result "$RESULT_JSON" '.result = $result' "$TMP" > "$TMP.2"
  mv "$TMP.2" "$TMP"
fi

mv "$TMP" "$WORKER_FILE"
echo "✅ Worker $TASK_ID actualizado a $STATUS"
