#!/bin/bash
# update-board.sh: safely update a ticket status in board.json.
# Usage: update-board.sh <ticket_id> <status> [blocked]

set -e

TICKET_ID="$1"
STATUS="$2"
BLOCKED="${3:-}"

if [ -z "$TICKET_ID" ] || [ -z "$STATUS" ]; then
  echo "Usage: $0 <ticket_id> <status> [blocked]"
  exit 1
fi

META_DIR="${META_DIR:-scripts/meta-ralph}"
BOARD_FILE="$META_DIR/state/board.json"

if [ ! -f "$BOARD_FILE" ]; then
  echo "Error: could not find $BOARD_FILE"
  exit 1
fi

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

JQ_FILTER="
  .tickets |= map(
    if .id == \"$TICKET_ID\" then
      .status = \"$STATUS\" |
      .updatedAt = \"$NOW\" |
      if \"$BLOCKED\" == "true" then .blocked = true
      elif \"$BLOCKED\" == "false" then .blocked = false
      else . end
    else . end
  )
"

jq "$JQ_FILTER" "$BOARD_FILE" > "$BOARD_FILE.tmp" && mv "$BOARD_FILE.tmp" "$BOARD_FILE"
echo "Ticket $TICKET_ID -> $STATUS"
