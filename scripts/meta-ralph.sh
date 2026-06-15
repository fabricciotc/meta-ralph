#!/bin/bash
# meta-ralph — MetaGPT Multi-Agent Orchestrator launcher
# Uso: meta-ralph [init|run|status|stop|dashboard] [opciones]

DASHBOARD_PORT=5050

set -e

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
if [ -L "$SCRIPT_SOURCE" ]; then
  SCRIPT_SOURCE="$(readlink -f "$SCRIPT_SOURCE" 2>/dev/null || readlink "$SCRIPT_SOURCE" 2>/dev/null || echo "$SCRIPT_SOURCE")"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
META_DIR="scripts/meta-ralph"
MAX_WORKERS=20

show_help() {
  cat <<EOF
Meta-Ralph — MetaGPT Multi-Agent Orchestrator para Kimi Code CLI

Uso:
  meta-ralph init                       Inicializa meta-ralph en el proyecto
  meta-ralph run [opciones]             Ejecuta el loop multi-agente y abre dashboard
  meta-ralph status                     Muestra estado de workers activos
  meta-ralph stop                       Detiene todos los workers activos y el dashboard
  meta-ralph dashboard [--port N]       Lanza solo el dashboard web
  meta-ralph --help                     Muestra esta ayuda

Opciones de run:
  --max-workers N       Máximo de workers en paralelo (default: 20)
  --skip-pm             Saltar fase 1 (usar prd-expanded.json existente)
  --skip-architect      Saltar fase 2 (usar architecture.md existente)
  --skip-planner        Saltar fase 3 (usar execution-plan.json existente)
  --max-time TIME       Tiempo máximo total (ej: 60m, 2h)
  --no-dashboard        No lanzar el dashboard web en meta-ralph run
EOF
}

cmd_init() {
  if [ ! -d ".git" ]; then
    echo "❌ Error: Debes ejecutar meta-ralph init dentro de un repo git."
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
    echo "📋 Board inicial creado en $META_DIR/state/board.json"
  fi

  if [ ! -f "$META_DIR/prd.json" ]; then
    cp "$SKILL_DIR/assets/prd-template.json" "$META_DIR/prd.json"
    echo "📝 Template de PRD creado en $META_DIR/prd.json"
  fi

  if [ ! -f "$META_DIR/progress.txt" ]; then
    echo "# Meta-Ralph Progress Log" > "$META_DIR/progress.txt"
    echo "Started: $(date)" >> "$META_DIR/progress.txt"
    echo "---" >> "$META_DIR/progress.txt"
  fi

  echo "✅ Meta-Ralph inicializado en $META_DIR/"
  echo "   Edita $META_DIR/prd.json con tus historias de usuario y luego corre: meta-ralph run"
}

cmd_status() {
  if [ ! -d "$META_DIR/state/workers" ]; then
    echo "⚠️  Meta-Ralph no está inicializado. Ejecuta: meta-ralph init"
    exit 1
  fi

  echo "📊 Meta-Ralph Status"
  echo "--------------------"

  local active=0
  for f in "$META_DIR/state/workers"/*.json; do
    [ -e "$f" ] || continue
    local status
    status=$(jq -r '.status // "unknown"' "$f" 2>/dev/null || echo "unknown")
    local task_id
    task_id=$(jq -r '.task_id // "unknown"' "$f" 2>/dev/null || echo "unknown")
    if [ "$status" = "running" ]; then
      echo "  🟡 Worker $task_id — RUNNING"
      active=$((active + 1))
    elif [ "$status" = "completed" ]; then
      echo "  🟢 Worker $task_id — COMPLETED"
    elif [ "$status" = "failed" ]; then
      echo "  🔴 Worker $task_id — FAILED"
    fi
  done

  if [ "$active" -eq 0 ]; then
    echo "  ⚪ No hay workers activos."
  else
    echo "  Total activos: $active"
  fi
}

cmd_stop() {
  if [ ! -d "$META_DIR/state" ]; then
    echo "⚠️  Meta-Ralph no está inicializado."
    exit 1
  fi

  echo "🛑 Deteniendo workers de Meta-Ralph..."
  for f in "$META_DIR/state/workers"/*.json; do
    [ -e "$f" ] || continue
    local status
    status=$(jq -r '.status // ""' "$f" 2>/dev/null || echo "")
    if [ "$status" = "running" ]; then
      local task_id
      task_id=$(jq -r '.task_id // ""' "$f" 2>/dev/null || echo "")
      echo "  - Deteniendo worker $task_id"
      jq '.status = "stopped"' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    fi
  done

  local DASHBOARD_PID_FILE="$META_DIR/state/dashboard.pid"
  if [ -f "$DASHBOARD_PID_FILE" ]; then
    local pid
    pid=$(cat "$DASHBOARD_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "🛑 Deteniendo dashboard (PID $pid)..."
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$DASHBOARD_PID_FILE"
  fi

  echo "✅ Workers y dashboard detenidos."
}

dashboard_venv() {
  local VENV_DIR="$SKILL_DIR/dashboard/.venv"
  if [ ! -d "$VENV_DIR" ]; then
    echo "⚙️  Instalando dependencias del dashboard..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$SKILL_DIR/dashboard/requirements.txt"
  fi
  echo "$VENV_DIR"
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

  local VENV_DIR
  VENV_DIR=$(dashboard_venv)

  local BOARD_FILE
  BOARD_FILE="$(pwd)/$META_DIR/state/board.json"

  if [ ! -f "$BOARD_FILE" ]; then
    echo "⚠️  No se encontró $BOARD_FILE. Ejecuta primero: meta-ralph init"
    exit 1
  fi

  echo "🌐 Lanzando Meta-Ralph Dashboard en http://localhost:$port"
  "$VENV_DIR/bin/python" "$SKILL_DIR/dashboard/server.py" --port "$port" --board "$BOARD_FILE" $no_browser
}

cmd_run() {
  if [ ! -d "$META_DIR" ]; then
    echo "❌ Error: Meta-Ralph no está inicializado. Ejecuta primero: meta-ralph init"
    exit 1
  fi

  if [ ! -f "$META_DIR/prd.json" ]; then
    echo "❌ Error: No se encontró $META_DIR/prd.json. Edítalo con tus historias."
    exit 1
  fi

  # Parse args
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

  # Build orchestrator prompt from template
  local PROMPT_FILE
  PROMPT_FILE=$(mktemp)

  ORCH_TEMPLATE="$SKILL_DIR/references/orchestrator-prompt.md"
  if [ ! -f "$ORCH_TEMPLATE" ]; then
    echo "❌ Error: No se encontró $ORCH_TEMPLATE"
    exit 1
  fi

  # Launch dashboard in background unless --no-dashboard
  if [ "$no_dashboard" != "true" ]; then
    local DASHBOARD_PID_FILE="$META_DIR/state/dashboard.pid"
    if [ -f "$DASHBOARD_PID_FILE" ] && kill -0 "$(cat "$DASHBOARD_PID_FILE")" 2>/dev/null; then
      echo "🌐 Dashboard ya está corriendo en http://localhost:$DASHBOARD_PORT"
    else
      local VENV_DIR
      VENV_DIR=$(dashboard_venv)
      local BOARD_FILE
      BOARD_FILE="$(pwd)/$META_DIR/state/board.json"
      mkdir -p "$META_DIR/state"
      nohup "$VENV_DIR/bin/python" "$SKILL_DIR/dashboard/server.py" \
        --port "$DASHBOARD_PORT" \
        --board "$BOARD_FILE" \
        --no-browser > "$META_DIR/state/dashboard.log" 2>&1 &
      echo $! > "$DASHBOARD_PID_FILE"
      echo "🌐 Dashboard lanzado en http://localhost:$DASHBOARD_PORT"
    fi
  fi

  BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || git branch --show-current 2>/dev/null || echo "main")

  # Read template and substitute variables
  sed -e "s|{{PROJECT_ROOT}}|$(pwd)|g" \
      -e "s|{{META_DIR}}|$META_DIR|g" \
      -e "s|{{MAX_WORKERS}}|$MAX_WORKERS|g" \
      -e "s|{{SKIP_PM}}|$skip_pm|g" \
      -e "s|{{SKIP_ARCHITECT}}|$skip_architect|g" \
      -e "s|{{SKIP_PLANNER}}|$skip_planner|g" \
      -e "s|{{MAX_TIME}}|$max_time|g" \
      -e "s|{{BASE_BRANCH}}|$BASE_BRANCH|g" \
      -e "s|{{SKILL_DIR}}|$SKILL_DIR|g" \
      "$ORCH_TEMPLATE" > "$PROMPT_FILE"

  echo "🚀 Lanzando Meta-Ralph Orchestrator..."
  echo "   Max workers: $MAX_WORKERS"
  echo "   PRD: $META_DIR/prd.json"
  echo "   Base branch: $BASE_BRANCH"

  kimi --print --yes --prompt "$(cat "$PROMPT_FILE")"
  rm -f "$PROMPT_FILE"
}

# Entry
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
    echo "❌ Error: Falta comando. Usa meta-ralph --help para ver opciones."
    exit 1
    ;;
  *)
    echo "❌ Error: Comando desconocido: $CMD"
    show_help
    exit 1
    ;;
esac
