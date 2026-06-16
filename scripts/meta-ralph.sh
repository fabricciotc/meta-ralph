#!/bin/bash
# meta-ralph: MetaGPT multi-agent orchestrator launcher.

set -e

DASHBOARD_PORT="${META_RALPH_DASHBOARD_PORT:-5050}"

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
if [ -L "$SCRIPT_SOURCE" ]; then
  SCRIPT_SOURCE="$(readlink -f "$SCRIPT_SOURCE" 2>/dev/null || readlink "$SCRIPT_SOURCE" 2>/dev/null || echo "$SCRIPT_SOURCE")"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/platform.sh
source "$SCRIPT_DIR/lib/platform.sh"
META_DIR="scripts/meta-ralph"
MAX_WORKERS=20

show_help() {
  cat <<EOF
Meta-Ralph: MetaGPT multi-agent orchestrator

Usage:
  meta-ralph init                       Initialize meta-ralph in the current project
  meta-ralph run [options]              Run the multi-agent loop and start the dashboard
  meta-ralph status                     Show active worker state
  meta-ralph stop                       Stop active workers and the dashboard
  meta-ralph dashboard [--port N]       Start only the web dashboard
  meta-ralph --help                     Show this help

Run options:
  --max-workers N       Maximum parallel workers (default: 20)
  --skip-pm             Skip phase 1 and use an existing prd-expanded.json
  --skip-architect      Skip phase 2 and use an existing architecture.md
  --skip-planner        Skip phase 3 and use an existing execution-plan.json
  --max-time TIME       Maximum total run time, for example 60m or 2h
  --no-dashboard        Do not start the web dashboard during meta-ralph run

Backend options:
  META_RALPH_BACKEND=auto|kimi|claude|cursor|codex|openai_api|custom
  META_RALPH_BACKENDS="kimi claude cursor codex openai_api"
  META_RALPH_RUNNER_COMMAND='my-agent --prompt-file "$META_RALPH_PROMPT_FILE"'
EOF
}

cmd_init() {
  if [ ! -d ".git" ]; then
    echo "Error: run 'meta-ralph init' inside a git repository."
    exit 1
  fi

  mkdir -p "$META_DIR/state/workers" "$META_DIR/state/batches" "$META_DIR/state/pm-research" "$META_DIR/archive"

  if [ ! -f "$META_DIR/state/board.json" ]; then
    cat > "$META_DIR/state/board.json" <<'JSON'
{
  "columns": ["backlog", "in-design", "in-progress", "in-review", "done"],
  "tickets": [],
  "stats": {"total": 0, "done": 0, "inProgress": 0, "blocked": 0},
  "lastUpdated": ""
}
JSON
    echo "Created board at $META_DIR/state/board.json"
  fi

  if [ ! -f "$META_DIR/prd.json" ]; then
    cp "$SKILL_DIR/assets/prd-template.json" "$META_DIR/prd.json"
    echo "Created PRD template at $META_DIR/prd.json"
  fi

  if [ ! -f "$META_DIR/progress.txt" ]; then
    echo "# Meta-Ralph Progress Log" > "$META_DIR/progress.txt"
    echo "Started: $(date)" >> "$META_DIR/progress.txt"
    echo "---" >> "$META_DIR/progress.txt"
  fi

  echo "Meta-Ralph initialized in $META_DIR/"
  echo "Edit $META_DIR/prd.json, then run: meta-ralph run"
}

cmd_status() {
  if [ ! -d "$META_DIR/state/workers" ]; then
    echo "Meta-Ralph is not initialized. Run: meta-ralph init"
    exit 1
  fi

  echo "Meta-Ralph Status"
  echo "-----------------"

  local active=0
  for f in "$META_DIR/state/workers"/*.json; do
    [ -e "$f" ] || continue
    local status
    status=$(jq -r '.status // "unknown"' "$f" 2>/dev/null || echo "unknown")
    local task_id
    task_id=$(jq -r '.task_id // "unknown"' "$f" 2>/dev/null || echo "unknown")
    if [ "$status" = "running" ]; then
      echo "  Worker $task_id: RUNNING"
      active=$((active + 1))
    elif [ "$status" = "completed" ]; then
      echo "  Worker $task_id: COMPLETED"
    elif [ "$status" = "failed" ]; then
      echo "  Worker $task_id: FAILED"
    fi
  done

  if [ "$active" -eq 0 ]; then
    echo "  No active workers."
  else
    echo "  Active workers: $active"
  fi
}

cmd_stop() {
  if [ ! -d "$META_DIR/state" ]; then
    echo "Meta-Ralph is not initialized."
    exit 1
  fi

  echo "Stopping Meta-Ralph workers..."
  for f in "$META_DIR/state/workers"/*.json; do
    [ -e "$f" ] || continue
    local status
    status=$(jq -r '.status // ""' "$f" 2>/dev/null || echo "")
    if [ "$status" = "running" ]; then
      local task_id
      task_id=$(jq -r '.task_id // ""' "$f" 2>/dev/null || echo "")
      echo "  Stopping worker $task_id"
      jq '.status = "stopped"' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    fi
  done

  local dashboard_pid_file="$META_DIR/state/dashboard.pid"
  if [ -f "$dashboard_pid_file" ]; then
    local pid
    pid=$(cat "$dashboard_pid_file")
    if is_process_running "$pid"; then
      echo "Stopping dashboard (PID $pid)..."
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$dashboard_pid_file"
  fi

  echo "Workers and dashboard stopped."
}

dashboard_venv() {
  local venv_dir="$SKILL_DIR/dashboard/.venv"
  local py
  local pip

  py="$(python_cmd)" || {
    echo "Error: Python 3.10+ is required for the Meta-Ralph dashboard." >&2
    exit 1
  }

  if [ ! -d "$venv_dir" ]; then
    echo "Installing dashboard dependencies..."
    "$py" -m venv "$venv_dir"
    pip="$(venv_pip "$venv_dir")"
    "$pip" install -q -r "$SKILL_DIR/dashboard/requirements.txt"
  fi

  echo "$venv_dir"
}

resolve_dashboard_python() {
  local venv_dir
  local py

  venv_dir="$(dashboard_venv)"
  py="$(resolve_venv_python "$venv_dir")" || {
    echo "Error: dashboard virtualenv python not found at $(venv_python "$venv_dir")" >&2
    exit 1
  }

  echo "$py"
}

cmd_dashboard() {
  local port="$DASHBOARD_PORT"
  local no_browser=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --port)
        port="$2"
        shift 2
        ;;
      --port=*)
        port="${1#*=}"
        shift
        ;;
      --no-browser)
        no_browser="--no-browser"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  local venv_dir
  local python_bin
  venv_dir=$(dashboard_venv)
  python_bin=$(resolve_dashboard_python)

  local board_file
  board_file="$(pwd)/$META_DIR/state/board.json"

  if [ ! -f "$board_file" ]; then
    echo "Could not find $board_file. Run first: meta-ralph init"
    exit 1
  fi

  echo "Starting Meta-Ralph Dashboard at http://localhost:$port"
  "$python_bin" "$SKILL_DIR/dashboard/server.py" --port "$port" --board "$board_file" $no_browser
}

run_with_backend() {
  local backend="$1"
  local prompt_file="$2"
  local prompt
  prompt="$(cat "$prompt_file")"

  export META_RALPH_PROMPT="$prompt"
  export META_RALPH_PROMPT_FILE="$prompt_file"

  case "$backend" in
    kimi)
      if command_exists kimi; then
        kimi -p "$prompt"
        return $?
      fi
      ;;
    claude)
      if command_exists claude; then
        claude -p "$prompt"
        return $?
      fi
      ;;
    cursor)
      run_cursor_agent "$prompt_file"
      return $?
      ;;
    codex)
      if command_exists codex; then
        codex exec "$prompt"
        return $?
      fi
      ;;
    openai_api)
      if [ -n "$OPENAI_API_KEY" ]; then
        local py
        py="$(python_cmd)" || return 127
        "$py" - "$prompt_file" <<'PY'
import json
import os
import sys
import urllib.request

prompt_path = sys.argv[1]
with open(prompt_path, "r", encoding="utf-8") as fh:
    prompt = fh.read()

model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
}).encode("utf-8")
request = urllib.request.Request(
    f"{base_url}/chat/completions",
    data=payload,
    headers={
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=3600) as response:
    data = json.loads(response.read().decode("utf-8"))
print(data["choices"][0]["message"]["content"])
PY
        return $?
      fi
      ;;
    custom)
      if [ -n "$META_RALPH_RUNNER_COMMAND" ]; then
        bash -lc "$META_RALPH_RUNNER_COMMAND"
        return $?
      fi
      ;;
  esac

  return 127
}

run_ai_prompt() {
  local prompt_file="$1"
  local backend="${META_RALPH_BACKEND:-auto}"
  local backends="${META_RALPH_BACKENDS:-kimi claude cursor codex openai_api}"

  if [ "$backend" != "auto" ]; then
    echo "Running orchestrator with backend: $backend"
    run_with_backend "$backend" "$prompt_file"
    return $?
  fi

  local candidate
  for candidate in $backends; do
    echo "Trying AI backend: $candidate"
    if run_with_backend "$candidate" "$prompt_file"; then
      return 0
    fi
    echo "Backend unavailable or failed: $candidate"
  done

  if [ -n "$META_RALPH_RUNNER_COMMAND" ]; then
    echo "Trying custom AI backend."
    run_with_backend custom "$prompt_file"
    return $?
  fi

  echo "Error: no usable AI backend found."
  echo "Set META_RALPH_BACKEND, META_RALPH_BACKENDS, or META_RALPH_RUNNER_COMMAND."
  return 1
}

cmd_run() {
  if [ ! -d "$META_DIR" ]; then
    echo "Error: Meta-Ralph is not initialized. Run first: meta-ralph init"
    exit 1
  fi

  if [ ! -f "$META_DIR/prd.json" ]; then
    echo "Error: could not find $META_DIR/prd.json. Edit it with your user stories."
    exit 1
  fi

  local skip_pm=""
  local skip_architect=""
  local skip_planner=""
  local max_time=""
  local no_dashboard=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --max-workers)
        MAX_WORKERS="$2"
        shift 2
        ;;
      --max-workers=*)
        MAX_WORKERS="${1#*=}"
        shift
        ;;
      --skip-pm)
        skip_pm="true"
        shift
        ;;
      --skip-architect)
        skip_architect="true"
        shift
        ;;
      --skip-planner)
        skip_planner="true"
        shift
        ;;
      --max-time)
        max_time="$2"
        shift 2
        ;;
      --max-time=*)
        max_time="${1#*=}"
        shift
        ;;
      --no-dashboard)
        no_dashboard="true"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  local prompt_file
  prompt_file=$(mktemp)

  local orch_template="$SKILL_DIR/references/orchestrator-prompt.md"
  if [ ! -f "$orch_template" ]; then
    echo "Error: could not find $orch_template"
    exit 1
  fi

  if [ "$no_dashboard" != "true" ]; then
    local dashboard_pid_file="$META_DIR/state/dashboard.pid"
    if [ -f "$dashboard_pid_file" ] && is_process_running "$(cat "$dashboard_pid_file")"; then
      echo "Dashboard is already running at http://localhost:$DASHBOARD_PORT"
    else
      local python_bin
      local board_file
      local dashboard_pid
      python_bin=$(resolve_dashboard_python)
      board_file="$(pwd)/$META_DIR/state/board.json"
      mkdir -p "$META_DIR/state"
      dashboard_pid=$(start_dashboard_background \
        "$python_bin" \
        "$SKILL_DIR/dashboard/server.py" \
        "$DASHBOARD_PORT" \
        "$board_file" \
        "$META_DIR/state/dashboard.log")
      echo "$dashboard_pid" >"$dashboard_pid_file"
      echo "Dashboard started at http://localhost:$DASHBOARD_PORT"
    fi
  fi

  BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || git branch --show-current 2>/dev/null || echo "main")

  sed -e "s|{{PROJECT_ROOT}}|$(pwd)|g" \
      -e "s|{{META_DIR}}|$META_DIR|g" \
      -e "s|{{MAX_WORKERS}}|$MAX_WORKERS|g" \
      -e "s|{{SKIP_PM}}|$skip_pm|g" \
      -e "s|{{SKIP_ARCHITECT}}|$skip_architect|g" \
      -e "s|{{SKIP_PLANNER}}|$skip_planner|g" \
      -e "s|{{MAX_TIME}}|$max_time|g" \
      -e "s|{{BASE_BRANCH}}|$BASE_BRANCH|g" \
      -e "s|{{SKILL_DIR}}|$SKILL_DIR|g" \
      "$orch_template" > "$prompt_file"

  echo "Starting Meta-Ralph Orchestrator..."
  echo "  Max workers: $MAX_WORKERS"
  echo "  PRD: $META_DIR/prd.json"
  echo "  Base branch: $BASE_BRANCH"
  echo "  Backend: ${META_RALPH_BACKEND:-auto}"

  run_ai_prompt "$prompt_file"
  local exit_code=$?
  rm -f "$prompt_file"
  return $exit_code
}

CMD="${1:-}"
shift || true

case "$CMD" in
  init)
    cmd_init "$@"
    ;;
  run)
    cmd_run "$@"
    ;;
  status)
    cmd_status "$@"
    ;;
  stop)
    cmd_stop "$@"
    ;;
  dashboard)
    cmd_dashboard "$@"
    ;;
  --help|-h|help)
    show_help
    ;;
  "")
    echo "Error: missing command. Use meta-ralph --help."
    exit 1
    ;;
  *)
    echo "Error: unknown command: $CMD"
    show_help
    exit 1
    ;;
esac
