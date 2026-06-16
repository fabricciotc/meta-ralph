#!/usr/bin/env python3
"""
AgentFlow Dashboard Server
Servidor web local tipo Kanban/Jira para visualizar y gestionar tickets,
con orchestración automática del loop multi-agente cuando un ticket pasa
a "ready-for-work".
"""

import argparse
import concurrent.futures
import faulthandler
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path

import communication_bus as bus

from core import pm_analysis
from core.orchestrator import Orchestrator

# Permitir volcar stack traces de todos los threads con SIGUSR1 para debugging
faulthandler.enable()
try:
    faulthandler.register(signal.SIGUSR1, all_threads=True)
except Exception:
    pass

try:
    import pexpect
except ImportError:
    pexpect = None

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("META_RALPH_SECRET_KEY") or os.urandom(32)
_cors_origins = os.environ.get("META_RALPH_CORS_ORIGINS", "*")
socketio = SocketIO(app, cors_allowed_origins=_cors_origins.split(","))

DEFAULT_COLUMNS = [
    "backlog",
    "ready-for-work",
    "in-design",
    "in-progress",
    "in-review",
    "done",
]

DEFAULT_BOARD = {
    "columns": DEFAULT_COLUMNS.copy(),
    "tickets": [],
    "stats": {"total": 0, "done": 0, "inProgress": 0, "blocked": 0},
    "lastUpdated": datetime.now(timezone.utc).isoformat(),
}

BOARD_FILE = None
RUN_STATE_FILE = None
LOG_FILE = None


_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text):
    """Elimina códigos de escape ANSI de un texto."""
    return _ANSI_ESCAPE.sub("", text)


# Locks para acceso concurrente
# run_lock es RLock porque múltiples métodos del runner pueden anidarse
# (por ejemplo, self.log -> append_log -> with run_lock dentro de otro with run_lock).
run_lock = threading.RLock()
board_lock = threading.RLock()
_active_run_thread = None
paused_run_threads = {}


def get_meta_dir():
    """Devuelve el directorio scripts/meta-ralph relativo al proyecto."""
    return Path.cwd() / "scripts" / "meta-ralph"


def get_board_path():
    """Resuelve la ruta del board.json relativa al proyecto actual."""
    global BOARD_FILE
    if BOARD_FILE:
        return BOARD_FILE
    candidate = get_meta_dir() / "state" / "board.json"
    if candidate.exists():
        return candidate
    return Path(__file__).parent / "board.json"


def set_board_path(path):
    global BOARD_FILE
    BOARD_FILE = Path(path)
    BOARD_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_run_state_path():
    global RUN_STATE_FILE
    if RUN_STATE_FILE:
        return RUN_STATE_FILE
    return get_board_path().parent / "run-state.json"


def get_log_path():
    global LOG_FILE
    if LOG_FILE:
        return LOG_FILE
    return get_board_path().parent / "run.log"


def get_ticket_snapshot_path(ticket_id):
    """Ruta del snapshot de run-state para un ticket pausado."""
    return get_run_state_path().parent / f"run-state.{ticket_id}.json"


def save_ticket_snapshot(ticket_id, state):
    """Guarda una copia del run-state actual para un ticket."""
    path = get_ticket_snapshot_path(ticket_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = dict(state)
    snapshot["snapshotTicketId"] = ticket_id
    snapshot["snapshotSavedAt"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
    except (IOError, TypeError) as exc:
        append_log(f"No se pudo guardar snapshot para {ticket_id}: {exc}", "error")


def load_ticket_snapshot(ticket_id):
    """Carga el snapshot de run-state de un ticket si existe."""
    path = get_ticket_snapshot_path(ticket_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        append_log(f"No se pudo cargar snapshot para {ticket_id}: {exc}", "error")
        return None


def delete_ticket_snapshot(ticket_id):
    """Elimina el snapshot de un ticket."""
    path = get_ticket_snapshot_path(ticket_id)
    if path.exists():
        path.unlink()


def list_ticket_snapshots():
    """Devuelve los ticketIds que tienen snapshot en disco."""
    parent = get_run_state_path().parent
    if not parent.exists():
        return []
    ids = []
    prefix = "run-state."
    suffix = ".json"
    for p in parent.iterdir():
        if p.is_file() and p.name.startswith(prefix) and p.name.endswith(suffix):
            ticket_id = p.name[len(prefix):-len(suffix)]
            if ticket_id:
                ids.append(ticket_id)
    return ids


def ensure_default_columns(board):
    """Migra el board para asegurar que tenga todas las columnas por defecto."""
    columns = board.get("columns", [])
    if not columns:
        board["columns"] = DEFAULT_COLUMNS.copy()
        return board

    new_columns = []
    backlog_seen = False
    for col in columns:
        if col == "backlog":
            backlog_seen = True
            new_columns.append(col)
            if "ready-for-work" not in columns:
                new_columns.append("ready-for-work")
        else:
            new_columns.append(col)

    # Si no había backlog, insertar ready-for-work al inicio
    if not backlog_seen and "ready-for-work" not in new_columns:
        new_columns.insert(0, "ready-for-work")

    # Asegurar que no haya duplicados y mantener orden
    final_columns = []
    for col in DEFAULT_COLUMNS:
        if col in new_columns and col not in final_columns:
            final_columns.append(col)
    for col in new_columns:
        if col not in final_columns:
            final_columns.append(col)

    board["columns"] = final_columns
    return board


def load_board():
    with board_lock:
        path = get_board_path()
        if not path.exists():
            save_board(DEFAULT_BOARD.copy())
            return DEFAULT_BOARD.copy()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in DEFAULT_BOARD.items():
                if key not in data:
                    data[key] = value
            data = ensure_default_columns(data)
            return data
        except (json.JSONDecodeError, IOError):
            return DEFAULT_BOARD.copy()


def save_board(board):
    with board_lock:
        path = get_board_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        board["lastUpdated"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(board, f, indent=2, ensure_ascii=False)


def _default_communication():
    return {
        "ticketId": None,
        "participants": {},
        "log": [],
        "pendingActions": [],
        "maxLogSize": 500,
    }


def load_run_state():
    path = get_run_state_path()
    if not path.exists():
        default = {
            "active": False,
            "ticketId": None,
            "status": "idle",
            "currentAgent": None,
            "progress": 0,
            "startedAt": None,
            "updatedAt": None,
            "logs": [],
            "queue": [],
            "agents": [],
            "pendingQuestions": [],
            "communication": _default_communication(),
        }
        save_run_state(default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "queue" not in data:
            data["queue"] = []
        if "agents" not in data:
            data["agents"] = []
        if "pendingQuestions" not in data:
            data["pendingQuestions"] = []
        if "communication" not in data or data.get("communication") is None:
            data["communication"] = _default_communication()
        return data
    except (json.JSONDecodeError, IOError):
        return {
            "active": False,
            "ticketId": None,
            "status": "idle",
            "currentAgent": None,
            "progress": 0,
            "startedAt": None,
            "updatedAt": None,
            "logs": [],
            "queue": [],
            "agents": [],
            "pendingQuestions": [],
            "communication": _default_communication(),
        }


def compute_run_summary(status, current_agent):
    """Genera un resumen corto (<=15 palabras) del estado actual del run."""
    if status == "completed":
        return "Loop completado exitosamente."
    if status == "failed":
        return "El loop falló. Revisa los logs."
    if status == "idle":
        return "Esperando un ticket en Ready for Work."
    if status == "in-design":
        if current_agent == "architect":
            return "Definiendo arquitectura y patrones técnicos globales."
        if current_agent == "project-manager":
            return "Armando plan de tareas y dependencias."
        return "Analizando requisitos con 5 PM Research Agents en paralelo."
    if status == "in-progress":
        return "Implementando tareas en paralelo con hasta 10 engineers."
    if status == "in-review":
        return "Revisando calidad: build y tests."
    return f"Estado {status}."


def save_run_state(state):
    path = get_run_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updatedAt"] = datetime.now(timezone.utc).isoformat()
    started_at = state.get("startedAt")
    if started_at:
        try:
            start_dt = datetime.fromisoformat(started_at)
            elapsed = (datetime.now(timezone.utc) - start_dt).total_seconds()
            state["elapsedSeconds"] = max(0, int(elapsed))
        except Exception:
            state["elapsedSeconds"] = None
    else:
        state["elapsedSeconds"] = None
    state["summary"] = compute_run_summary(state.get("status"), state.get("currentAgent"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def append_log(message, level="info"):
    """Agrega una línea al run.log y al run-state."""
    ts = datetime.now(timezone.utc).isoformat()
    entry = {"timestamp": ts, "level": level, "message": message}

    # Archivo de log plano
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{level.upper()}] {message}\n")

    # Estado
    with run_lock:
        state = load_run_state()
        state["logs"] = state.get("logs", []) + [entry]
        # Mantener últimos 500 logs
        state["logs"] = state["logs"][-500:]
        save_run_state(state)


def update_run_state(updates):
    with run_lock:
        state = load_run_state()
        state.update(updates)
        save_run_state(state)


QUESTION_TIMEOUT_SECONDS = 120
_question_timers = {}

# Waiters for synchronous user clarifications requested by the engineer squad.
# Maps question_id -> (threading.Event, dict("answer": str))
_clarification_waiters = {}


def _extract_ask_json(raw_text):
    """Extrae y valida el JSON de pregunta entre DECISION_REQUERIDA y FIN_PREGUNTA."""
    if not raw_text:
        return None
    text = strip_ansi(raw_text)
    start = text.rfind("DECISION_REQUERIDA")
    if start == -1:
        return None
    end = text.find("FIN_PREGUNTA", start)
    if end == -1:
        return None
    json_text = text[start + len("DECISION_REQUERIDA"):end].strip()
    # Debe ser un objeto JSON
    if not json_text.startswith("{"):
        return None
    try:
        return json.loads(json_text)
    except Exception:
        return None


def _question_id(ticket_id, phase_name, agent_id=None):
    base = f"{ticket_id}-{phase_name.lower().replace(' ', '-')}"
    if agent_id:
        base += f"-{agent_id}"
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-")


def _question_answer_path(question):
    """Devuelve la ruta del archivo de respuesta para una pregunta."""
    safe_phase = question.get("phase", "").lower().replace(' ', '-')
    return get_meta_dir() / "state" / f"answer-{question['ticketId']}-{safe_phase}.txt"


def _write_answer_file(question, answer_text):
    """Escribe la respuesta en el archivo que expect está esperando."""
    try:
        answer_path = _question_answer_path(question)
        answer_path.parent.mkdir(parents=True, exist_ok=True)
        answer_path.write_text(answer_text, encoding="utf-8")
        return True
    except Exception as exc:
        append_log(f"Error escribiendo answer file: {exc}", "error")
        return False


def _auto_answer_question(question_id):
    """Responde automáticamente una pregunta si el usuario no lo hizo a tiempo."""
    auto_answer = "Decide solo (timeout)"
    q = answer_user_question(question_id, auto_answer)
    if q:
        _write_answer_file(q, auto_answer)
        append_log(f"Pregunta {question_id} auto-respondida por timeout.", "warning")
    _question_timers.pop(question_id, None)


def create_user_question(ticket_id, phase_name, agent_id, agent_name, question, context, options):
    """Registra una pregunta pendiente del usuario y notifica al frontend."""
    with run_lock:
        state = load_run_state()
        questions = state.setdefault("pendingQuestions", [])
        qid = _question_id(ticket_id, phase_name, agent_id)
        # Evitar duplicados para la misma fase/agente
        for q in questions:
            if q.get("id") == qid and q.get("status") == "pending":
                return q
        now = datetime.now(timezone.utc)
        q = {
            "id": qid,
            "ticketId": ticket_id,
            "phase": phase_name,
            "agentId": agent_id,
            "agentName": agent_name,
            "question": question,
            "context": context,
            "options": options or ["A", "B"],
            "status": "pending",
            "createdAt": now.isoformat(),
            "expiresAt": (now.timestamp() + QUESTION_TIMEOUT_SECONDS),
            "answeredAt": None,
            "answer": None,
        }
        questions.append(q)
        save_run_state(state)
        socketio.emit("pending_question", q)

    # Timer: si no responden antes de expiresAt, el agente decide solo
    delay = max(0.0, q["expiresAt"] - datetime.now(timezone.utc).timestamp())
    timer = threading.Timer(delay, _auto_answer_question, args=[qid])
    timer.daemon = True
    timer.start()
    _question_timers[qid] = timer
    return q


def answer_user_question(question_id, answer_text):
    """Guarda la respuesta del usuario y actualiza el estado."""
    timer = _question_timers.pop(question_id, None)
    if timer:
        timer.cancel()
    answered = None
    with run_lock:
        state = load_run_state()
        questions = state.setdefault("pendingQuestions", [])
        for q in questions:
            if q.get("id") == question_id and q.get("status") == "pending":
                q["answer"] = answer_text
                q["status"] = "answered"
                q["answeredAt"] = datetime.now(timezone.utc).isoformat()
                save_run_state(state)
                socketio.emit("question_answered", q)
                answered = q
                break

    # Wake up any synchronous waiter (e.g. engineer squad clarification).
    waiter = _clarification_waiters.pop(question_id, None)
    if waiter:
        event, container = waiter
        container["answer"] = answer_text
        event.set()

    return answered


def has_pending_question(ticket_id=None, phase_name=None, agent_id=None):
    """Devuelve True si existe una pregunta pendiente que coincida con los filtros."""
    with run_lock:
        state = load_run_state()
        for q in state.get("pendingQuestions", []):
            if q.get("status") != "pending":
                continue
            if ticket_id and q.get("ticketId") != ticket_id:
                continue
            if phase_name and q.get("phase") != phase_name:
                continue
            if agent_id and q.get("agentId") != agent_id:
                continue
            return True
    return False


def schedule_pending_question_timers():
    """Reprograma timers para preguntas pendientes tras un reinicio del servidor."""
    with run_lock:
        state = load_run_state()
        pending = [q for q in state.get("pendingQuestions", []) if q.get("status") == "pending"]
    for q in pending:
        qid = q.get("id")
        if not qid or qid in _question_timers:
            continue
        delay = max(0.0, q.get("expiresAt", 0) - datetime.now(timezone.utc).timestamp())
        timer = threading.Timer(delay, _auto_answer_question, args=[qid])
        timer.daemon = True
        timer.start()
        _question_timers[qid] = timer
        print(f"Timer reprogramado para pregunta {qid} (faltan {int(delay)}s)")


def _agent_log(state, agent_id, message, level="info"):
    """Añade un log a un agente en run-state."""
    ts = datetime.now(timezone.utc).isoformat()
    for agent in state.get("agents", []):
        if agent.get("id") == agent_id:
            agent.setdefault("logs", []).append({"timestamp": ts, "level": level, "message": message})
            # mantener últimos 100 logs por agente
            agent["logs"] = agent["logs"][-100:]
            break


def _ensure_agent(state, agent_id, name, role, parent_id=None, status="queued", progress=0):
    """Crea un agente si no existe y devuelvelo."""
    for agent in state.get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    agent = {
        "id": agent_id,
        "name": name,
        "role": role,
        "parentId": parent_id,
        "status": status,
        "progress": progress,
        "logs": [],
        "outputs": [],
    }
    state.setdefault("agents", []).append(agent)
    return agent


def _update_agent(state, agent_id, **kwargs):
    """Actualiza campos de un agente y añade log opcional."""
    for agent in state.get("agents", []):
        if agent.get("id") == agent_id:
            for key, value in kwargs.items():
                if key != "log":
                    agent[key] = value
            if "log" in kwargs:
                msg = kwargs["log"]
                level = kwargs.get("log_level", "info")
                _agent_log(state, agent_id, msg, level)
            return agent
    return None


def recompute_stats(board):
    tickets = board.get("tickets", [])
    stats = {
        "total": len(tickets),
        "done": sum(1 for t in tickets if t.get("status") == "done"),
        "inProgress": sum(
            1
            for t in tickets
            if t.get("status")
            in ["ready-for-work", "in-design", "in-progress", "in-review"]
        ),
        "blocked": sum(1 for t in tickets if t.get("blocked", False)),
    }
    board["stats"] = stats
    return board


def notify_board_update():
    with board_lock:
        board = load_board()
        recompute_stats(board)
        save_board(board)
        socketio.emit("board_update", board)


def emit_communication_update(state):
    try:
        socketio.emit("communication_update", state.get("communication") or {})
    except Exception:
        pass


def update_ticket_status(ticket_id, status, extra=None):
    with board_lock:
        board = load_board()
        ticket = next((t for t in board["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            return None
        ticket["status"] = status
        ticket["updatedAt"] = datetime.now(timezone.utc).isoformat()
        if extra:
            ticket.update(extra)
        recompute_stats(board)
        save_board(board)
        socketio.emit("board_update", board)
    return ticket


def update_ticket_runtime(ticket_id, **kwargs):
    """Actualiza campos de ejecución de un ticket sin tocar su status."""
    with board_lock:
        board = load_board()
        ticket = next((t for t in board["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            return None
        for key, value in kwargs.items():
            ticket[key] = value
        ticket["updatedAt"] = datetime.now(timezone.utc).isoformat()
        save_board(board)
        socketio.emit("board_update", board)
    return ticket


def decision_request_instruction():
    """Instrucción que se añade a prompts para que agentes pidan decisiones al usuario."""
    return (
        "\n\n--- INSTRUCCIÓN DE DECISIÓN ---\n"
        "IMPORTANTE: en el 99% de los casos debes tomar la decisión tú mismo y seguir avanzando. "
        "Solo usa el formato de abajo cuando te encuentres con un impedimento REAL que te impida continuar "
        "sin una decisión explícita del usuario (por ejemplo, cambiar una API pública, eliminar datos, "
        "elegir entre opciones que afecten arquitectura de largo plazo, o costos/riesgos importantes).\n\n"
        "Si necesitas esa decisión, usa EXACTAMENTE este formato (markdown plano):\n\n"
        "DECISION_REQUERIDA\n"
        "{\n"
        '  "agent": "tu nombre o rol",\n'
        '  "question": "¿Pregunta clara para el usuario?",\n'
        '  "options": ["A) Opción A", "B) Opción B"],\n'
        '  "context": "Explica por qué es un impedimento y qué implica cada opción."\n'
        "}\n"
        "FIN_PREGUNTA\n\n"
        "Después de escribir esto NO hagas nada más; el sistema pausará la ejecución y te enviará la respuesta del usuario. "
        "Si el usuario no responde en 2 minutos o elige 'decide solo', deberás tomar la decisión por tu cuenta."
    )


def slugify_title(title, max_length=40):
    """Genera un slug seguro para nombre de branch a partir del título."""
    if not title:
        return "sin-titulo"
    text = title.lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ü": "u", "ñ": "n", "ç": "c",
        "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
        "â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u",
        "ä": "a", "ë": "e", "ï": "i", "ö": "o", "ü": "u",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    if not text:
        return "sin-titulo"
    return text[:max_length].rstrip("-")


def resolve_repo_path(repo_path):
    """Devuelve la ruta absoluta del repo.

    Si es relativa, primero prueba contra cwd; si no existe, prueba contra
    el directorio padre de cwd (útil cuando el dashboard corre dentro de un
    subproyecto y el repo está al mismo nivel o en el padre).
    """
    if not repo_path:
        return ""
    repo = Path(repo_path)
    if repo.is_absolute():
        return str(repo.resolve())
    candidates = [Path.cwd() / repo, Path.cwd().parent / repo]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    # Si ninguno existe, devolver el primero para que el mensaje de error sea consistente
    return str((Path.cwd() / repo).resolve())


def validate_git_repo(repo_path):
    """Valida que repo_path sea un folder existente.

    Git es opcional: si el folder tiene .git se creará una branch, pero no
    es requisito para que el ticket pueda ejecutarse.
    """
    if not repo_path:
        return "REPO_MISSING", "El ticket no tiene un repo configurado."
    repo = Path(resolve_repo_path(repo_path))
    if not repo.exists() or not repo.is_dir():
        return (
            "REPO_NOT_FOUND",
            f"El folder '{repo_path}' no existe.",
        )
    return None, None


def create_git_branch(repo_path, ticket_id, title):
    """Crea o cambia a la branch feature/<ticketId>-<slug> si el folder es un repo Git.

    Si el folder no tiene .git, no se crea branch y se retorna branch_name="".
    Devuelve (branch_name, error_code, error_message).
    """
    repo_path = resolve_repo_path(repo_path)
    git_dir = Path(repo_path) / ".git"
    if not git_dir.exists():
        return "", None, None

    slug = slugify_title(title)
    branch = f"feature/{ticket_id}-{slug}"
    try:
        exists = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--verify", branch],
            capture_output=True,
            text=True,
        )
        if exists.returncode == 0:
            subprocess.run(
                ["git", "-C", repo_path, "checkout", branch],
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            subprocess.run(
                ["git", "-C", repo_path, "checkout", "-b", branch],
                capture_output=True,
                text=True,
                check=True,
            )
        return branch, None, None
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        return None, "BRANCH_CREATE_FAILED", f"No se pudo crear la branch: {err}"


def find_kimi_cli():
    """Busca el ejecutable de kimi CLI."""
    candidate = os.environ.get("KIMI_CLI", shutil.which("kimi"))
    if candidate:
        return candidate
    home = Path.home()
    for rel in [".kimi-code/bin/kimi", ".kimi/bin/kimi", ".local/bin/kimi"]:
        p = home / rel
        if p.exists():
            return str(p)
    return None


class AgentRunner(threading.Thread):
    """Thread que ejecuta el loop multi-agente para un ticket."""

    def __init__(self, ticket, resume=False):
        super().__init__(daemon=True)
        self.ticket = ticket
        self.ticket_id = ticket["id"]
        self.resume = bool(resume)
        self.kimi = find_kimi_cli()
        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._resume_event = threading.Event()
        from core.runners.registry import BackendRegistry
        from core.skills_registry import SkillsRegistry
        self.backend_registry = BackendRegistry.default()
        self.skills_registry = SkillsRegistry()
        available = [b.name for b in self.backend_registry.available_backends()]
        self.log(f"Backends disponibles: {available}", "info")
        self.orchestrator = Orchestrator(
            ticket,
            resume=resume,
            callbacks=self._orchestrator_callbacks(),
            backend_registry=self.backend_registry,
            skills_registry=self.skills_registry,
        )

    def stop(self):
        """Solicita la detención ordenada del runner."""
        self._stop_event.set()
        self._pause_event.clear()
        self._resume_event.set()
        if hasattr(self, "orchestrator") and self.orchestrator:
            self.orchestrator.stop()
        self._stop_runtime_heartbeat()

    def pause(self):
        """Pausa el runner en el próximo checkpoint."""
        self._resume_event.clear()
        self._pause_event.set()
        if hasattr(self, "orchestrator") and self.orchestrator:
            self.orchestrator.pause()
        update_run_state({"active": False, "status": "paused"})
        self.log(f"Ticket {self.ticket_id} pausado.", "warning")

    def resume(self):
        """Reanuda un runner pausado."""
        self._pause_event.clear()
        self._resume_event.set()
        if hasattr(self, "orchestrator") and self.orchestrator:
            self.orchestrator.resume()

    def _should_stop(self):
        """Retorna True si se solicitó detener el runner."""
        return self._stop_event.is_set()

    def _is_paused(self):
        """Retorna True si el runner está pausado."""
        return self._pause_event.is_set()

    def _check_pause(self):
        """Si está pausado, bloquea hasta reanudar o detener."""
        if not self._is_paused():
            return
        self.log(f"Ticket {self.ticket_id} en pausa. Esperando reanudación...")
        while self._is_paused() and not self._should_stop():
            self._resume_event.wait(timeout=1.0)
            self._resume_event.clear()
        if not self._should_stop():
            self.log(f"Ticket {self.ticket_id} reanudado.")

    def _should_stop_or_pause(self):
        """Retorna True si se solicitó detener; si está pausado, espera primero."""
        self._check_pause()
        return self._should_stop()

    def log(self, msg, level="info"):
        append_log(f"[{self.ticket_id}] {msg}", level)

    def _runtime_heartbeat(self):
        """Actualiza cada segundo el tiempo transcurrido y resumen en el ticket."""
        while not self._stop_heartbeat.is_set():
            self._stop_heartbeat.wait(1)
            if self._stop_heartbeat.is_set():
                break
            try:
                board = load_board()
                ticket = next((t for t in board.get("tickets", []) if t["id"] == self.ticket_id), None)
                if not ticket or not ticket.get("startedAt"):
                    continue
                start_dt = datetime.fromisoformat(ticket["startedAt"])
                elapsed = max(0, int((datetime.now(timezone.utc) - start_dt).total_seconds()))
                state = load_run_state()
                summary = compute_run_summary(state.get("status"), state.get("currentAgent"))
                update_ticket_runtime(self.ticket_id, elapsedSeconds=elapsed, summary=summary)
            except Exception:
                # No interrumpir el run por errores del heartbeat
                pass

    def _start_runtime_heartbeat(self):
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(target=self._runtime_heartbeat, daemon=True)
        self._heartbeat_thread.start()

    def _stop_runtime_heartbeat(self):
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)

    def _agent_log(self, agent_id, message, level="info"):
        with run_lock:
            state = load_run_state()
            _agent_log(state, agent_id, message, level)
            save_run_state(state)

    def _ensure_agent(self, agent_id, name, role, parent_id=None, status="queued", progress=0):
        with run_lock:
            state = load_run_state()
            agent = _ensure_agent(state, agent_id, name, role, parent_id, status, progress)
            save_run_state(state)
            return agent

    def _update_agent(self, agent_id, **kwargs):
        with run_lock:
            state = load_run_state()
            old_status = None
            for a in state.get("agents", []):
                if a.get("id") == agent_id:
                    old_status = a.get("status")
                    break
            agent = _update_agent(state, agent_id, **kwargs)
            if agent and "status" in kwargs and kwargs["status"] != old_status:
                bus.publish_event(
                    state,
                    agent_id,
                    "status_changed",
                    {"from": old_status, "to": kwargs["status"]},
                )
            save_run_state(state)
            emit_communication_update(state)
            return agent

    def _add_agent_message(self, sender_id, recipient_id, question):
        """Registra una pregunta de un agente a otro y la expone en run-state."""
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        message = {
            "id": msg_id,
            "from": sender_id,
            "to": recipient_id,
            "question": question,
            "answer": None,
            "status": "pending",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with run_lock:
            state = load_run_state()
            state.setdefault("messages", []).append(message)
            save_run_state(state)
        self.log(f"{sender_id} preguntó a {recipient_id}: {question[:100]}...")
        return message

    def _answer_agent_message(self, message_id, answer):
        """Marca una pregunta como respondida."""
        answered_msg = None
        with run_lock:
            state = load_run_state()
            for msg in state.get("messages", []):
                if msg.get("id") == message_id:
                    msg["answer"] = answer
                    msg["status"] = "answered"
                    msg["answeredAt"] = datetime.now(timezone.utc).isoformat()
                    save_run_state(state)
                    answered_msg = msg
                    break
        if answered_msg:
            self.log(f"{answered_msg['to']} respondió a {answered_msg['from']}: {answer[:100]}...")
        return answered_msg

    def _consult_agent(self, sender_id, recipient_id, question, timeout_seconds=30, task_context=None):
        """Consulta a otro agente y espera una respuesta generada por Kimi.

        Si el agente consultado no tiene contexto, se escala al orchestrator.
        Si el orchestrator tampoco puede responder, se genera una respuesta
        automática basada en el contexto del proyecto (recurso último).
        """
        msg = self._add_agent_message(sender_id, recipient_id, question)

        # Resolver nombres para el prompt
        with run_lock:
            state = load_run_state()
            agents_by_id = {a["id"]: a for a in state.get("agents", [])}
        sender_name = agents_by_id.get(sender_id, {}).get("name", sender_id)
        recipient_name = agents_by_id.get(recipient_id, {}).get("name", recipient_id)

        context_text = self._build_consultation_context(task_context)

        prompt = f"""Activa la skill 'dotnet' y aplica sus convenciones y mejores prácticas a todo el código .NET que generes.

Eres el agente {recipient_name} ({recipient_id}). Tu compañero {sender_name} ({sender_id}) te pregunta:

"{question}"

CONTEXTO DEL PROYECTO:
{context_text}

Responde de forma concisa y técnica. Si realmente no tienes información suficiente para responder, responde EXACTAMENTE con la frase: NO_TENGO_CONTEXTO_SUFICIENTE"""

        output = self._run_kimi_prompt(
            prompt,
            phase_name=f"Consulta {recipient_id}",
            timeout_seconds=timeout_seconds,
            agent_id=recipient_id,
        )
        answer = (output or "").strip() or "NO_TENGO_CONTEXTO_SUFICIENTE"

        # Escalamiento 1: si el agente no tiene contexto, consultar al orchestrator
        if "NO_TENGO_CONTEXTO_SUFICIENTE" in answer:
            self.log(f"{recipient_id} no tuvo contexto; escalando a orchestrator...", "warning")
            answer = self._consult_orchestrator(question, context_text)

        self._answer_agent_message(msg["id"], answer)
        return answer

    def _build_consultation_context(self, task_context=None):
        """Construye un contexto enriquecido para consultas entre agentes."""
        parts = []
        title = self.ticket.get("title", "")
        description = self.ticket.get("description", "")
        parts.append(f"Ticket: {title}\nDescripción: {description}")

        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
        if prd_path.exists():
            try:
                prd_text = prd_path.read_text(encoding="utf-8")[:2000]
                parts.append(f"PRD (resumen):\n{prd_text}\n---")
            except Exception as exc:
                parts.append(f"No se pudo leer el PRD: {exc}")

        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
        if tasks_path.exists():
            try:
                tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
                if tasks and isinstance(tasks, list):
                    summary = "\n".join(
                        f"- {t.get('id')}: {t.get('title')} (dependencias: {t.get('dependencies', [])}, complejidad: {t.get('complexity', '-')})"
                        for t in tasks
                    )
                    parts.append(f"Tareas planificadas:\n{summary}\n---")
            except Exception as exc:
                parts.append(f"No se pudieron leer las tareas: {exc}")

        if task_context:
            parts.append(f"Contexto de la tarea actual:\n{task_context}")

        return "\n\n".join(parts)

    def _get_dependency_context(self, deps):
        """Recopila el contexto de tareas dependientes ya completadas."""
        if not deps:
            return ""
        lines = ["Contexto de tareas previas (dependencias):"]
        with run_lock:
            state = load_run_state()
            for dep_id in deps:
                dep_agent_id = f"engineer-{dep_id}"
                agent = next((a for a in state.get("agents", []) if a.get("id") == dep_agent_id), None)
                if not agent:
                    lines.append(f"- {dep_id}: aún no hay información del agente.")
                    continue
                logs = agent.get("logs", []) or []
                last_logs = "\n  ".join(
                    f"[{log.get('level', 'info')}] {log.get('message', '')}"
                    for log in logs[-5:]
                )
                outputs = agent.get("outputs", []) or []
                outputs_summary = "\n  ".join(f"- {os.path.basename(p)}" for p in outputs[-8:]) or "Sin outputs registrados"
                lines.append(
                    f"- {dep_id} ({agent.get('status')}):\n"
                    f"  Últimos logs:\n  {last_logs}\n"
                    f"  Archivos generados/modificados:\n  {outputs_summary}"
                )
        return "\n\n".join(lines)

    def _consult_orchestrator(self, question, context_text):
        """Consulta al orchestrator cuando otro agente no tiene contexto."""
        prompt = f"""Activa la skill 'dotnet' y aplica sus convenciones y mejores prácticas a todo el código .NET que generes.

Eres el Orchestrator Principal del proyecto. Un agente del equipo hizo una pregunta y no tuvo suficiente contexto. Tú tienes acceso al PRD, tareas y ticket. Responde de forma concisa y técnica.

PREGUNTA DEL AGENTE:
"{question}"

CONTEXTO DEL PROYECTO:
{context_text}

Si realmente no tienes información suficiente para responder, responde EXACTAMENTE con la frase: NO_TENGO_CONTEXTO_SUFICIENTE"""

        output = self._run_kimi_prompt(
            prompt,
            phase_name="Consulta Orchestrator",
            timeout_seconds=60,
            agent_id="orchestrator",
        )
        answer = (output or "").strip()
        if answer and "NO_TENGO_CONTEXTO_SUFICIENTE" not in answer:
            return answer

        # Escalamiento 2: generar respuesta automática con IA como recurso último
        self.log("Orchestrator tampoco tuvo contexto; generando respuesta automática...", "warning")
        return self._auto_generate_answer(question, context_text)

    def _auto_generate_answer(self, question, context_text):
        """Genera una respuesta automática cuando nadie del equipo tiene contexto."""
        prompt = f"""Activa la skill 'dotnet' y aplica sus convenciones y mejores prácticas a todo el código .NET que generes.

Eres un experto en .NET y arquitectura de software. Un agente del equipo hizo una pregunta y nadie (incluido el orchestrator) tuvo contexto suficiente. Debes asumir la mejor respuesta posible basada en el contexto disponible y las mejores prácticas.

PREGUNTA DEL AGENTE:
"{question}"

CONTEXTO DEL PROYECTO:
{context_text}

Responde de forma concisa y práctica. Asume decisiones razonables para un MVP .NET con Clean Architecture, MediatR, EF Core y vistas cshtml. NO digas que no tienes contexto; proporciona una respuesta útil que permita continuar la implementación."""

        output = self._run_kimi_prompt(
            prompt,
            phase_name="Auto-respuesta IA",
            timeout_seconds=60,
            agent_id="orchestrator",
        )
        return (output or "").strip() or "Asumir implementación estándar según el PRD y continuar con las convenciones .NET."

    def _is_context_lacking(self, answer):
        """Detecta si una respuesta indica falta de contexto."""
        if not answer:
            return True
        phrases = [
            "NO_TENGO_CONTEXTO_SUFICIENTE",
            "no tengo suficiente contexto",
            "no tengo contexto",
            "no tengo información suficiente",
            "no puedo responder",
            "no sé",
        ]
        return any(p.lower() in answer.lower() for p in phrases)

    def _get_messages_for(self, participant_id, message_type=None, handled=False):
        with run_lock:
            state = load_run_state()
            return bus.get_messages_for(state, participant_id, message_type, handled)

    def _mark_message_handled(self, message_id, result=None):
        with run_lock:
            state = load_run_state()
            bus.mark_handled(state, message_id, result)
            save_run_state(state)
            emit_communication_update(state)

    def _get_task_context(self, task_id):
        """Carga la definición de una tarea desde el plan de tareas."""
        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
        if not tasks_path.exists():
            return None
        try:
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            return next((t for t in tasks if t.get("id") == task_id), None)
        except Exception:
            return None

    def _request_help(self, requester_id, helper_id, task_id, question):
        """Engineer asks another engineer for help; resolved via _consult_agent."""
        task = self._get_task_context(task_id)
        task_title = task.get("title", task_id) if task else task_id
        task_desc = task.get("description", "") if task else ""
        task_deps = task.get("dependencies", []) if task else []
        context_str = (
            f"Tarea solicitante: {task_id} - {task_title}\n"
            f"Descripción: {task_desc}\n"
            f"Dependencias: {task_deps}"
        )
        answer = self._consult_agent(
            requester_id,
            helper_id,
            f"Necesito ayuda con la tarea {task_id}: {question}",
            timeout_seconds=60,
            task_context=context_str,
        )
        with run_lock:
            state = load_run_state()
            msg = bus.send_message(
                state,
                helper_id,
                requester_id,
                "notify_completion",
                {"taskId": task_id, "helpAnswer": answer},
            )
            bus.mark_handled(state, msg["id"])
            save_run_state(state)
            emit_communication_update(state)
        return answer

    def _request_clarification(self, sender_id, recipient_id, topic, question):
        """Engineer asks PM/Architect for clarification; resolved via _consult_agent."""
        task = self._get_task_context(topic) if topic and topic.startswith("T") else None
        task_title = task.get("title", topic) if task else topic
        task_desc = task.get("description", "") if task else ""
        context_str = (
            f"Tema/tarea: {task_title}\n"
            f"Descripción: {task_desc}"
        )
        answer = self._consult_agent(
            sender_id,
            recipient_id,
            f"Pregunta de aclaración sobre {topic}: {question}",
            timeout_seconds=60,
            task_context=context_str,
        )
        with run_lock:
            state = load_run_state()
            msg = bus.send_message(
                state,
                recipient_id,
                sender_id,
                "notify_completion",
                {"topic": topic, "answer": answer, "clarification": True},
            )
            bus.mark_handled(state, msg["id"])
            save_run_state(state)
            emit_communication_update(state)
        return answer

    def _parse_engineer_coordination_messages(self, agent_id, output):
        """Parse REQUEST_HELP / REQUEST_CLARIFICATION lines from engineer output and send bus messages."""
        if not output:
            return
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("REQUEST_HELP:"):
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    helper_id = parts[1].strip()
                    question = parts[2].strip()
                    with run_lock:
                        state = load_run_state()
                        bus.send_message(state, agent_id, helper_id, "request_help", {"taskId": agent_id.replace("engineer-", ""), "question": question})
                        save_run_state(state)
                        emit_communication_update(state)
            elif line.startswith("REQUEST_CLARIFICATION:"):
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    recipient_id = parts[1].strip()
                    topic = parts[2].strip()
                    question = parts[3].strip()
                    with run_lock:
                        state = load_run_state()
                        bus.send_message(state, agent_id, recipient_id, "request_clarification", {"topic": topic, "question": question})
                        save_run_state(state)
                        emit_communication_update(state)

    def _run_shell(self, cmd, cwd, timeout=300):
        if not cwd:
            return False, "No working directory"
        try:
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, (result.stdout or "") + (result.stderr or "")
        except Exception as exc:
            return False, str(exc)

    def _run_dotnet_build(self, repo_path):
        return self._run_shell(["dotnet", "build"], repo_path, timeout=300)

    def _run_dotnet_test(self, repo_path):
        return self._run_shell(["dotnet", "test"], repo_path, timeout=300)

    def _get_git_diff(self, repo_path):
        git_dir = Path(repo_path) / ".git"
        if not git_dir.exists():
            return ""
        ok, out = self._run_shell(["git", "diff"], repo_path, timeout=60)
        return out if ok else ""

    def set_phase(self, agent, status, progress):
        now = datetime.now(timezone.utc)
        update_run_state(
            {
                "active": True,
                "ticketId": self.ticket_id,
                "currentAgent": agent,
                "status": status,
                "progress": progress,
            }
        )
        # Sincronizar la columna del ticket con la fase actual
        if status in ("in-design", "in-progress", "in-review"):
            update_ticket_status(self.ticket_id, status)

        # Actualizar métricas de ejecución en el ticket
        board = load_board()
        ticket = next((t for t in board.get("tickets", []) if t["id"] == self.ticket_id), None)
        started_at = ticket.get("startedAt") if ticket else None
        elapsed = None
        if started_at:
            try:
                start_dt = datetime.fromisoformat(started_at)
                elapsed = max(0, int((now - start_dt).total_seconds()))
            except Exception:
                pass
        runtime_updates = {"summary": compute_run_summary(status, agent)}
        if elapsed is not None:
            runtime_updates["elapsedSeconds"] = elapsed
        if status in ("completed", "failed"):
            runtime_updates["finishedAt"] = now.isoformat()
            if elapsed is not None:
                runtime_updates["totalSeconds"] = elapsed
        update_ticket_runtime(self.ticket_id, **runtime_updates)

    def _orchestrator_callbacks(self):
        """Callbacks que el Orchestrator real usa para integrarse con el dashboard."""
        return {
            "run_kimi": self._run_kimi_prompt,
            "log": self.log,
            "set_phase": self.set_phase,
            "ensure_agent": self._ensure_agent,
            "update_agent": self._update_agent,
            "request_design_review": self._wait_for_design_answers,
            "request_clarification": self._wait_for_user_clarification,
            "collect_outputs": self._collect_agent_outputs,
            "get_dependency_context": self._get_dependency_context,
            "on_started": self._on_orchestrator_started,
            "on_complete": self._on_orchestrator_complete,
        }

    def _on_orchestrator_started(self, ticket):
        with run_lock:
            state = load_run_state()
            state.update({
                "active": True,
                "ticketId": self.ticket_id,
                "status": "in-design",
                "currentAgent": "orchestrator",
                "progress": 5,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "logs": [],
                "agents": [],
                "messages": [],
                "communication": {
                    "ticketId": self.ticket_id,
                    "participants": {},
                    "log": [],
                    "pendingActions": [],
                    "maxLogSize": 500,
                },
                "designReview": None,
            })
            _ensure_agent(state, "orchestrator", "Orchestrator Principal", "orchestrator", None, "running", 5)
            bus.register_participant(state, {
                "id": "orchestrator",
                "name": "Orchestrator Principal",
                "role": "orchestrator",
                "description": "Coordina las 5 fases del software factory loop",
                "capabilities": ["orchestration", "coordination"],
                "tools": ["dispatch", "monitor"],
            })
            _agent_log(state, "orchestrator", "Ticket movido a Ready for work. Iniciando software factory loop...")
            save_run_state(state)
            emit_communication_update(state)

        now = datetime.now(timezone.utc)
        update_ticket_status(self.ticket_id, "in-design")
        update_ticket_runtime(
            self.ticket_id,
            startedAt=now.isoformat(),
            elapsedSeconds=0,
            summary="Iniciando software factory loop...",
        )
        self._start_runtime_heartbeat()

    def _on_orchestrator_complete(self, success):
        self._stop_runtime_heartbeat()
        if success:
            update_ticket_status(self.ticket_id, "done")
            self._update_agent("orchestrator", status="done", progress=100, log="Loop completado. Ticket marcado como Done.", log_level="success")
            update_run_state({"active": False, "ticketId": None, "status": "completed", "progress": 100, "currentAgent": None})
            self.log("Loop completado. Ticket marcado como Done.", "success")
        else:
            self._update_agent("orchestrator", status="failed", log="El loop falló. Revisa los logs.", log_level="error")
            update_run_state({"active": False, "ticketId": None, "status": "failed", "progress": 0, "currentAgent": None})
        # Marcar run como inactivo si este runner sigue siendo el activo
        time.sleep(1)
        with run_lock:
            state = load_run_state()
            if state.get("ticketId") == self.ticket_id:
                state["active"] = False
                save_run_state(state)
        paused_run_threads.pop(self.ticket_id, None)
        delete_ticket_snapshot(self.ticket_id)

    def run(self):
        try:
            self.orchestrator.run()
        except Exception as exc:
            self.log(f"Error en el loop: {exc}", "error")
            self._update_agent("orchestrator", status="failed", log=f"Error en el loop: {exc}", log_level="error")
            update_run_state({"active": False, "ticketId": None, "status": "failed", "progress": 0, "currentAgent": None})
            self._stop_runtime_heartbeat()
            paused_run_threads.pop(self.ticket_id, None)
            delete_ticket_snapshot(self.ticket_id)

    def _run_planner_and_execution(self):
        """Ejecuta las fases de Planning, Execution y QA. Usado durante un resume."""
        self._check_pause()
        self._agent_log("orchestrator", "Fase 3/5: Planning & Dispatch — armando batches y DAG de dependencias.")
        self.set_phase("project-manager", "in-design", 60)
        self.run_planner()
        if self._should_stop_or_pause():
            self.log("Run detenido por solicitud del usuario tras Planning.", "warning")
            return

        self._agent_log("orchestrator", "Fase 4/5: Parallel Execution — implementando tareas en worktrees aislados.")
        update_ticket_status(self.ticket_id, "in-progress")
        self.set_phase("engineer-squad", "in-progress", 75)
        self.run_execution()
        if self._should_stop_or_pause():
            self.log("Run detenido por solicitud del usuario tras Execution.", "warning")
            return

        self._agent_log("orchestrator", "Fase 5/5: QA Review — revisando integración del batch.")
        self.set_phase("qa-engineer", "in-review", 90)
        self.run_qa()
        if self._should_stop_or_pause():
            self.log("Run detenido por solicitud del usuario tras QA.", "warning")
            return

        update_ticket_status(self.ticket_id, "done")
        self._update_agent("orchestrator", status="done", progress=100, log="Loop completado. Ticket marcado como Done.", log_level="success")
        update_run_state({"active": False, "ticketId": None, "status": "completed", "progress": 100, "currentAgent": None})
        self.log("Loop completado. Ticket marcado como Done.", "success")

    def _resume_loop(self):
        """Reanuda el loop desde la fase que quedó guardada en run-state."""
        state = load_run_state()
        review = state.get("designReview") or {}

        if not review.get("answered"):
            self._agent_log("orchestrator", "Reanudando desde Architecture/Design Review.")
            self.set_phase("architect", "in-design", 40)
            self.run_architect()
            if self._should_stop_or_pause():
                return
            prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
            questions = self._generate_design_questions(prd_path)
            answers = self._wait_for_design_answers(questions, timeout_seconds=60)
            if self._should_stop_or_pause():
                return
            self.log(f"Respuestas de design review: {answers}")
            self._run_planner_and_execution()
            return

        self._agent_log("orchestrator", "Reanudando desde Planning/Execution.")
        self._run_planner_and_execution()

    def run_pm_analysis(self):
        """Ejecuta el análisis de PM usando múltiples agentes Kimi en paralelo.

        Los subagentes envían sus reportes al PM Lead por el bus de comunicación.
        El PM Lead consolida los hallazgos en un PRD y, si detecta gaps, puede
        solicitar clarificaciones a los subagentes y reejecutarlos.
        """
        self.set_phase("pm-research-agents", "in-design", 15)

        subagents = [
            ("pm-domain", "Domain Analyst", "dominio de negocio, entidades, reglas y flujos principales"),
            ("pm-ux", "UX Researcher", "experiencia de usuario, vistas, flujos de pantalla y validaciones de frontend"),
            ("pm-technical", "Technical Analyst", "stack técnico, arquitectura, patrones y decisiones técnicas"),
            ("pm-integration", "Integration Analyst", "integraciones con APIs de terceros, bases de datos y servicios externos"),
            ("pm-risk", "Risk Analyst", "riesgos, seguridad, compliance, permisos y manejo de errores"),
        ]

        self._ensure_agent("pm-research-agents", "PM Research Agents", "lead", "orchestrator", "running", 10)
        for sub_id, sub_name, _ in subagents:
            self._ensure_agent(sub_id, sub_name, "sub", "pm-research-agents", "queued", 0)

        with run_lock:
            state = load_run_state()
            bus.register_participant(state, {
                "id": "pm-research-agents",
                "name": "PM Research Agents",
                "role": "lead",
                "description": "Grupo de investigación de PM en paralelo",
                "capabilities": ["research", "consolidation"],
                "tools": ["kimi_prompt"],
            })
            for sub_id, sub_name, focus in subagents:
                bus.register_participant(state, {
                    "id": sub_id,
                    "name": sub_name,
                    "role": "sub",
                    "description": f"Investiga {focus}",
                    "capabilities": ["research", "analysis"],
                    "tools": ["kimi_prompt", "web_search"],
                })
            save_run_state(state)
            emit_communication_update(state)

        title = self.ticket.get("title", "")
        description = self.ticket.get("description", "")
        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"

        # Si ya existe un PRD pre-generado, saltar el análisis y usarlo directamente.
        if prd_path.exists() and prd_path.stat().st_size > 100:
            self.log(f"PRD pre-generado encontrado en {prd_path}; saltando PM Research.")
            for sub_id, sub_name, _ in subagents:
                self._update_agent(sub_id, status="done", progress=100,
                                   log=f"{sub_name} completado (PRD pre-generado).")
            self._update_agent("pm-research-agents", status="done", progress=100,
                               log="PRD pre-generado reutilizado.")
            self.set_phase("pm-lead", "in-design", 35)
            return

        self._update_agent("pm-research-agents", status="running", progress=10,
                           log="Lanzando PM Research Agents con roles MetaGPT...")

        def log_callback(message, level="info"):
            self.log(message, level)

        # Ejecutar Fase 1 con el nuevo motor basado en roles/actions.
        # Los subagentes corren en paralelo dentro del Environment.
        generated_prd = pm_analysis.run_pm_analysis(
            self.ticket,
            run_kimi=lambda prompt, phase_name, timeout_seconds, agent_id=None: self._run_kimi_prompt(
                prompt,
                phase_name=phase_name,
                timeout_seconds=timeout_seconds,
                agent_id=agent_id,
            ),
            max_rounds=10,
            log_callback=log_callback,
        )

        if generated_prd and generated_prd.exists():
            self.log(f"Plan detallado guardado en {generated_prd}")
            final_prd_content = generated_prd.read_text(encoding="utf-8")
            with run_lock:
                state = load_run_state()
                bus.send_message(
                    state,
                    "pm-research-agents",
                    "orchestrator",
                    "notify_completion",
                    {"artifact": "PRD", "path": str(generated_prd), "preview": final_prd_content[:500]},
                )
                save_run_state(state)
                emit_communication_update(state)
        else:
            self.log("No se generó PRD; usando fallback local.", "warning")
            self._write_fallback_prd(prd_path, title, description)

        for sub_id, sub_name, _ in subagents:
            self._update_agent(sub_id, status="done", progress=100,
                               log=f"{sub_name} completado.")
        self._update_agent("pm-research-agents", status="done", progress=100,
                           log="PM Research Agents consolidaron el PRD.")
        self.set_phase("pm-lead", "in-design", 35)

    def _parse_clarifications(self, output):
        """Busca en el output del consolidador un bloque CLARIFICACIONES: sub_id: pregunta."""
        clarifications = {}
        marker = "CLARIFICACIONES:"
        idx = output.find(marker)
        if idx == -1:
            return clarifications
        block = output[idx + len(marker):]
        # Cortar al siguiente encabezado markdown o fin de bloque
        next_header = block.find("\n#")
        if next_header != -1:
            block = block[:next_header]
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("-") or line.startswith("*"):
                continue
            if ":" in line:
                sub_id, question = line.split(":", 1)
                sub_id = sub_id.strip()
                question = question.strip()
                valid_ids = {"pm-domain", "pm-ux", "pm-technical", "pm-integration", "pm-risk"}
                if sub_id in valid_ids and question:
                    clarifications[sub_id] = question
        return clarifications

    def _build_pm_subagent_prompt(self, sub_id, focus, title, description, follow_up=None):
        role_name = {
            "pm-domain": "Domain Analyst",
            "pm-ux": "UX Researcher",
            "pm-technical": "Technical Analyst",
            "pm-integration": "Integration Analyst",
            "pm-risk": "Risk Analyst",
        }.get(sub_id, sub_id)
        follow_up_section = ""
        if follow_up:
            follow_up_section = (
                "\n\nEL PM LEAD TE HA PEDIDO AMPLIAR TU ANÁLISIS CON ESTA PREGUNTA/CLARIFICACIÓN:\n"
                f"{follow_up}\n\n"
                "Responde directamente a la solicitud del PM Lead, manteniendo el mismo formato de salida."
            )
        return (
            f"Eres el {role_name} de AgentFlow, una software factory estilo MetaGPT con múltiples agentes. "
            f"Tu enfoque exclusivo es: {focus}. "
            "Investiga el codebase del proyecto actual SOLO desde el ángulo que te corresponde. "
            "NO implementes código; solo investiga, analiza y documenta hallazgos. "
            "Sé conciso pero completo; prioriza calidad sobre extensión.\n\n"
            "Tu salida debe ser un markdown con estas secciones:\n"
            "1. Hallazgos clave (máximo 10 bullets).\n"
            "2. Requisitos funcionales / no funcionales relevantes a tu área.\n"
            "3. Riesgos, supuestos o preguntas abiertas.\n"
            "4. Archivos o áreas del codebase relevantes.\n\n"
            f"TICKET:\nTÍTULO: {title}\nDESCRIPCIÓN: {description}"
            + follow_up_section
            + "\n\nResponde en español."
            + decision_request_instruction()
        )

    def _build_pm_consolidator_prompt(self, title, description, research_files, prd_path):
        research_content = ""
        for sub_id, path in research_files.items():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    # Truncar cada análisis para no saturar el contexto del consolidador.
                    lines = f.readlines()[:150]
                    research_content += f"\n\n--- {sub_id} ---\n\n" + "".join(lines)
            except Exception as exc:
                research_content += f"\n\n--- {sub_id} ---\n\nError leyendo hallazgos: {exc}"
        return (
            "Eres el Lead Product Manager de AgentFlow. Cinco PM Research Agents investigaron un ticket. "
            "Consolida SUS HALLAZGOS en un Product Requirements Document (PRD) conciso y accionable. "
            "NO inventes requisitos que no aparezcan en los hallazgos; tu trabajo es sintetizar lo que ya se investigó.\n\n"
            f"TICKET:\nTÍTULO: {title}\nDESCRIPCIÓN: {description}\n\n"
            "HALLAZGOS DE LOS AGENTES:\n" + research_content + "\n\n"
            "Genera un PRD en markdown con estas secciones (conciso, máximo 2 párrafos por sección):\n"
            "1. Resumen ejecutivo\n"
            "2. Requisitos funcionales principales (numerados, con prioridad Alta/Media/Baja)\n"
            "3. Requisitos no funcionales clave\n"
            "4. User stories y criterios de aceptación\n"
            "5. Tareas técnicas sugeridas con dependencias y estimaciones (S/M/L)\n"
            "6. Riesgos, supuestos y preguntas abiertas\n\n"
            f"Escribe el PRD completo en formato markdown en este archivo: {prd_path}\n\n"
            "Responde en español. Al final confirma brevemente que guardaste el PRD."
            + decision_request_instruction()
        )

    def _extract_prd_from_output(self, output, title, description):
        """Extrae el contenido del PRD del output crudo de Kimi."""
        lines = output.splitlines()
        prd_lines = []
        capture = False
        for line in lines:
            stripped = line.strip()
            # Iniciar captura al ver encabezado de PRD o markdown
            if stripped.startswith("# PRD") or stripped.startswith("# 1.") or stripped.startswith("## 1."):
                capture = True
            if capture:
                prd_lines.append(line)
        if prd_lines:
            return "\n".join(prd_lines)
        # Fallback: si no hay marcadores claros, devolver todo excepto líneas de UI
        filtered = []
        for line in lines:
            if any(skip in line for skip in ["K2.7 Code", "context:", "yolo", "MCP server", "thinking...", "working...", "Welcome to Kimi"]):
                continue
            filtered.append(line)
        return f"# PRD Detallado: {title}\n\n**Descripción original:**\n\n{description}\n\n---\n\n" + "\n".join(filtered[-200:])

    def _build_pm_prompt(self, title, description, prd_path):
        return (
            "Eres el Lead Product Manager de Meta-Ralph, una software factory estilo MetaGPT con múltiples agentes. "
            "Un ticket acaba de pasar a In Design y debes producir un Product Requirements Document (PRD) muy detallado.\n\n"
            "Actúa como si hubieras coordinado 5 PM Research Agents (Domain/UX, Technical, Integrations, Risks, Task Breakdown) "
            "y consolida sus hallazgos en un único PRD.\n\n"
            "El PRD debe incluir obligatoriamente:\n"
            "1. Resumen ejecutivo\n"
            "2. Declaración del problema / oportunidad\n"
            "3. User personas\n"
            "4. Requisitos funcionales (numerados, con prioridad)\n"
            "5. Requisitos no funcionales\n"
            "6. User stories y criterios de aceptación\n"
            "7. Preguntas abiertas, supuestos y riesgos\n"
            "8. Tareas técnicas sugeridas con dependencias y estimaciones de esfuerzo (S/M/L)\n"
            "9. Áreas / archivos del codebase afectados\n"
            "10. Notas de cada PM Research Agent\n\n"
            "Además, escribe el PRD completo en formato markdown en este archivo: {prd_path}\n\n"
            "TICKET:\n"
            f"TÍTULO: {title}\n\n"
            f"DESCRIPCIÓN: {description}\n\n"
            "Responde en español. Al final confirma brevemente que guardaste el PRD."
        ).format(prd_path=prd_path)

    def _write_fallback_prd(self, prd_path, title, description):
        """Genera un PRD detallado local simulando múltiples PM Research Agents."""
        desc_lower = (description or "").lower()
        title_lower = (title or "").lower()
        is_whatsapp = "whatsapp" in desc_lower or "whatsapp" in title_lower
        is_messaging = is_whatsapp or "sms" in desc_lower or "mensajeria" in desc_lower or "mensajería" in desc_lower

        if is_whatsapp:
            domain_reqs = [
                "CRUD de plantillas de mensaje WhatsApp con estados (borrador, enviada, aprobada, rechazada).",
                "Interfaz de usuario similar al módulo de SMS (vista, estructura, filtros).",
                "Integración con proveedor WhatsApp (ej. Teleprom) mediante interfaz abstracta.",
                "Asignación de listas de personas con valores de metadata dinámica.",
                "Configuración de credenciales vía App Settings usando IOptions pattern.",
                "Historial de envíos, estados de entrega y reintentos.",
                "Soporte para múltiples proveedores sin cambiar la interfaz de negocio.",
            ]
            affected = [
                "`EC.Ent` / `EntidadesFacturacionFD`: entidades Plantilla, Envio, ContactoMetadata.",
                "`EC.Buss`: servicios de envío e interfaz `IWhatsappSender`.",
                "`EC.Web` / `AppWeb.Scord.NetCore`: vistas y controllers/API.",
                "`EC.Data`: repositorios y migraciones.",
            ]
            tasks = [
                ("Crear entidades Plantilla, Envio, ContactoMetadata", "—", "M"),
                ("Definir interfaz `IWhatsappSender` y DTOs", "1", "S"),
                ("Implementar adaptador para proveedor (Teleprom/u otro)", "2", "L"),
                ("Crear vista UI tipo SMS para plantillas", "1", "L"),
                ("Crear vista de ejecución de envíos", "3, 4", "M"),
                ("Configurar IOptions para credenciales", "3", "S"),
                ("Tests unitarios e integración", "3, 5, 6", "M"),
            ]
        elif is_messaging:
            domain_reqs = [
                "CRUD de campañas y mensajes.",
                "Vista unificada de canales (SMS/WhatsApp).",
                "Gestión de listas de contactos y metadata.",
                "Proveedor abstracto configurable.",
                "Historial y trazabilidad de envíos.",
            ]
            affected = [
                "`EC.Ent`: entidades de campaña, contacto y envío.",
                "`EC.Buss`: servicios de mensajería.",
                "`EC.Web` / `AppWeb.Scord.NetCore`: UI y API.",
            ]
            tasks = [
                ("Modelar entidades de dominio", "—", "M"),
                ("Definir abstracción de proveedor", "1", "S"),
                ("Implementar proveedor principal", "2", "L"),
                ("Crear vistas de campañas", "1", "M"),
                ("Integrar envíos con cola/async", "3, 4", "M"),
                ("Tests", "3, 5", "S"),
            ]
        else:
            domain_reqs = [
                f"Implementar la funcionalidad descrita en el ticket: {title}.",
                "Persistencia y consulta de datos necesarios.",
                "Validaciones de negocio y manejo de errores.",
                "Exposición de la funcionalidad vía UI y/o API.",
                "Tests que cubran el happy path y casos de error.",
            ]
            affected = [
                "Capa de entidades: nuevos modelos o ajustes a existentes.",
                "Capa de negocio: servicios y reglas.",
                "Capa de presentación/API: controllers / endpoints.",
                "Capa de datos: repositorios y migraciones.",
            ]
            tasks = [
                ("Analizar y modelar entidades de dominio", "—", "M"),
                ("Definir contratos de servicio", "1", "S"),
                ("Implementar lógica de negocio", "2", "L"),
                ("Crear UI / endpoints", "2", "M"),
                ("Agregar validaciones y manejo de errores", "3, 4", "S"),
                ("Tests unitarios e integración", "3, 4, 5", "M"),
            ]

        req_lines = "\n".join(f"{i+1}. {r}" for i, r in enumerate(domain_reqs))
        task_rows = "\n".join(
            f"| {i+1} | {name} | {deps} | {effort} |" for i, (name, deps, effort) in enumerate(tasks)
        )
        affected_lines = "\n".join(f"- {a}" for a in affected)

        content = f"""# PRD Detallado: {title}

**Ticket:** {self.ticket_id}
**Fecha:** {datetime.now(timezone.utc).isoformat()}

## 1. Resumen Ejecutivo
Se requiere implementar: **{title}**. Este documento consolida el análisis de cinco PM Research Agents (Domain/UX, Technical, Integrations, Risks, Task Breakdown).

## 2. Declaración del problema / oportunidad
{description or "(Sin descripción proporcionada)"}

## 3. User Personas
- **Usuario final:** interactúa con la nueva funcionalidad a través de la aplicación.
- **Administrador:** configura parámetros, credenciales y reglas de negocio.
- **Auditor / soporte:** consulta estados, logs e historial.

## 4. Requisitos funcionales
{req_lines}

## 5. Requisitos no funcionales
- Seguridad: credenciales y datos sensibles fuera del código, usando configuración segura.
- Mantenibilidad: capas bien separadas (entidades, negocio, datos, presentación/API).
- Escalabilidad: operaciones pesadas preferentemente asíncronas.
- Observabilidad: logs estructurados y mensajes de error claros.
- Calidad: cobertura de tests para lógica de negocio crítica.

## 6. User Stories y criterios de aceptación
**US-1:** Como usuario final quiero acceder a la funcionalidad para completar mi tarea.
- CA: La funcionalidad está disponible en la UI/API según corresponda.
- CA: Los datos se persisten correctamente.

**US-2:** Como administrador quiero configurar la funcionalidad para adaptarla al negocio.
- CA: Los parámetros de configuración son editables.
- CA: Las validaciones impiden configuraciones inválidas.

## 7. Preguntas abiertas, supuestos y riesgos
- Supuesto: el alcance se limita a lo descrito en el ticket.
- Riesgo: dependencias con APIs o servicios externos; mitigación con abstracciones.
- Pregunta abierta: ¿existen reglas de negocio adicionales no mencionadas?

## 8. Tareas técnicas sugeridas (con dependencias y esfuerzo)
| # | Tarea | Dependencias | Esfuerzo |
|---|-------|--------------|----------|
{task_rows}

## 9. Áreas afectadas
{affected_lines}

## 10. Notas de los PM Research Agents
- **Domain/UX:** La experiencia debe ser consistente con los módulos existentes.
- **Technical:** Se recomienda usar patrones ya establecidos en el proyecto (IOptions, repositorios, servicios).
- **Integrations:** Si hay APIs de terceros, encapsular detrás de una interfaz.
- **Risks:** Validar permisos y manejar fallos de proveedores externos.
- **Task Breakdown:** Dividir en tareas pequeñas para permitir ejecución paralela por engineers.
"""
        with open(prd_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.log(f"Plan detallado guardado en {prd_path}")

    def run_architect(self):
        self._ensure_agent("architect", "Architect", "lead", "orchestrator", "running", 40)
        self._update_agent("architect", progress=60, log="Definiendo patrones técnicos, APIs y convenciones.")
        self.log("Arquitecto define patrones técnicos, APIs y convenciones.")
        time.sleep(1.5)
        self._update_agent("architect", status="done", progress=100, log="Arquitectura definida.")
        self.set_phase("architect", "in-design", 50)

    def _generate_design_questions(self, prd_path):
        """Genera preguntas de diseño con respuestas asumidas usando Kimi."""
        prd_text = ""
        if prd_path.exists():
            prd_text = prd_path.read_text(encoding="utf-8")[:4000]

        prompt = f"""Eres un arquitecto senior. Revisa el siguiente PRD y genera de 3 a 5 preguntas de diseño técnico que deberían confirmarse con el usuario antes de implementar.

Para cada pregunta, incluye una respuesta asumida razonable basada en el PRD.

PRD:
{prd_text}

Responde ÚNICAMENTE con un JSON válido en este formato exacto:
[
  {{
    "id": "q1",
    "question": "¿Qué framework .NET usar?",
    "assumedAnswer": ".NET 8 Web API",
    "inputType": "text"
  }},
  {{
    "id": "q2",
    "question": "¿Qué base de datos usar para pruebas?",
    "assumedAnswer": "Entity Framework Core InMemory",
    "inputType": "text"
  }}
]

No incluyas explicaciones fuera del JSON."""

        output = self._run_kimi_prompt(prompt, phase_name="Design Questions", timeout_seconds=120, agent_id="architect")
        try:
            # Buscar JSON en el output
            start = output.find("[")
            end = output.rfind("]")
            if start != -1 and end != -1 and end > start:
                questions = json.loads(output[start:end+1])
                if isinstance(questions, list) and len(questions) > 0:
                    return questions
        except Exception as exc:
            self.log(f"Error parseando preguntas de diseño: {exc}", "warning")

        # Fallback: preguntas por defecto
        return [
            {
                "id": "q1",
                "question": "¿Qué versión/framework .NET usar para el backend?",
                "assumedAnswer": ".NET 8 Web API",
                "inputType": "text",
            },
            {
                "id": "q2",
                "question": "¿Qué tecnología usar para acceso a datos / base de datos en desarrollo?",
                "assumedAnswer": "Entity Framework Core InMemory",
                "inputType": "text",
            },
            {
                "id": "q3",
                "question": "¿Qué tipo de frontend incluir (si aplica)?",
                "assumedAnswer": "HTML + JavaScript vanilla minimalista",
                "inputType": "text",
            },
            {
                "id": "q4",
                "question": "¿Qué framework de tests usar?",
                "assumedAnswer": "xUnit con EF Core InMemory",
                "inputType": "text",
            },
        ]

    def _wait_for_design_answers(self, questions, timeout_seconds=60):
        """Pausa el run para que el usuario revise/confirmé las respuestas de diseño.

        Si no responde antes del timeout, se usan las respuestas asumidas.
        """
        self.log(f"Pausando para revisión de diseño. El usuario tiene {timeout_seconds}s para responder.")
        self.set_phase("design-review", "design-review", 55)

        review_id = str(uuid.uuid4())
        review = {
            "id": review_id,
            "questions": questions,
            "answered": False,
            "expiresAt": (datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)).isoformat(),
            "timeoutSeconds": timeout_seconds,
        }

        with run_lock:
            state = load_run_state()
            state["designReview"] = review
            state["status"] = "design-review"
            state["currentAgent"] = "design-review"
            state["summary"] = "Esperando confirmación de diseño del usuario."
            save_run_state(state)

        answered_event = threading.Event()
        answers_received = {"answers": None}
        self._design_review_event = answered_event
        self._design_review_answers = answers_received

        def timeout_handler():
            time.sleep(timeout_seconds)
            if not answered_event.is_set():
                self.log("Timeout de revisión de diseño. Usando respuestas asumidas.", "warning")
                final_answers = {q["id"]: q.get("assumedAnswer", "") for q in questions}
                answers_received["answers"] = final_answers
                answered_event.set()
                self._finalize_design_review(final_answers, auto=True)

        timer_thread = threading.Thread(target=timeout_handler, daemon=True)
        timer_thread.start()

        answered_event.wait()
        return answers_received["answers"]

    def _wait_for_user_clarification(self, question, timeout_seconds=300):
        """Block until the user answers a clarification question from the squad.

        Falls back to a default answer if the timeout expires.
        """
        self.log(f"Engineer Squad solicita aclaración al usuario ({timeout_seconds}s).")
        q = create_user_question(
            ticket_id=self.ticket_id,
            phase_name="engineer-squad",
            agent_id="engineer-squad",
            agent_name="Engineer Squad Lead",
            question=question,
            context="Escalación del Engineer Squad Lead por una duda de implementación.",
            options=None,
        )
        qid = q["id"]
        answered_event = threading.Event()
        answer_container = {"answer": ""}
        _clarification_waiters[qid] = (answered_event, answer_container)
        try:
            answered = answered_event.wait(timeout=timeout_seconds)
            if not answered:
                self.log("Timeout esperando aclaración del usuario. El squad decide solo.", "warning")
                answer_user_question(qid, "Decide solo (timeout del squad)")
        finally:
            _clarification_waiters.pop(qid, None)
        return answer_container["answer"] or "Decide solo (timeout del squad)"

    def _finalize_design_review(self, answers, auto=False):
        """Guarda las respuestas finales y limpia el estado de revisión."""
        with run_lock:
            state = load_run_state()
            review = state.get("designReview", {})
            review["answered"] = True
            review["finalAnswers"] = answers
            review["auto"] = auto
            state["designReview"] = review
            state["status"] = "in-design"
            state["currentAgent"] = "project-manager"
            state["summary"] = "Revisión de diseño completada. Continuando con planificación."
            save_run_state(state)
        self.log(f"Revisión de diseño finalizada. Respuestas: {answers}")
        if hasattr(self, "_design_review_event"):
            self._design_review_event.set()

    def run_planner(self):
        self._ensure_agent("project-manager", "Project Manager", "lead", "orchestrator", "running", 60)
        self._update_agent("project-manager", progress=70, log="Construyendo DAG y batches de trabajo.")
        self.log("Project Manager construye DAG y batches de trabajo.")

        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"

        # Si ya existe un plan de tareas pre-generado, reutilizarlo.
        if tasks_path.exists() and tasks_path.stat().st_size > 50:
            try:
                with open(tasks_path, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
                if tasks and isinstance(tasks, list):
                    self.log(f"Plan de tareas pre-generado encontrado en {tasks_path}; saltando Planner.")
                    self._update_agent("project-manager", status="done", progress=100, log=f"Plan reutilizado con {len(tasks)} tareas.")
                    self.set_phase("project-manager", "in-progress", 65)
                    return
            except Exception as exc:
                self.log(f"Error leyendo tasks pre-generado: {exc}; generando nuevo plan.", "warning")

        if prd_path.exists() and self.kimi:
            prompt = self._build_planner_prompt(prd_path, tasks_path)
            output = self._run_kimi_prompt(prompt, phase_name="Planner", timeout_seconds=600, agent_id="project-manager")
            tasks = self._parse_tasks_from_output(output)
            if not tasks:
                self.log("Planner no devolvió JSON válido; usando plan por defecto para CRUD .NET.", "warning")
                self.log(f"Output del planner (primeros 500 chars): {output[:500]}", "debug")
                tasks = self._build_default_crud_tasks()
        else:
            self.log("PRD no disponible o kimi no encontrado; usando plan por defecto.", "warning")
            tasks = self._build_default_crud_tasks()

        with open(tasks_path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)

        self._update_agent("project-manager", status="done", progress=100, log=f"Plan generado con {len(tasks)} tareas.")
        self.set_phase("project-manager", "in-progress", 65)

    def _build_default_crud_tasks(self):
        """Plan de tareas estándar para un CRUD de productos en .NET con Clean Architecture."""
        title = self.ticket.get("title", "CRUD de productos")
        return [
            {
                "id": "T1",
                "title": "Crear solución y proyectos .NET",
                "description": "Crear la solución y los proyectos Domain, Application, Infrastructure y Web. Configurar referencias y paquetes NuGet (MediatR, EF Core, FluentValidation).",
                "files_to_touch": [
                    "CrudProductos.sln",
                    "src/CrudProductos.Domain/CrudProductos.Domain.csproj",
                    "src/CrudProductos.Application/CrudProductos.Application.csproj",
                    "src/CrudProductos.Infrastructure/CrudProductos.Infrastructure.csproj",
                    "src/CrudProductos.Web/CrudProductos.Web.csproj",
                ],
                "dependencies": [],
                "complexity": "medium",
                "qa_checklist": ["La solución compila", "Los proyectos tienen las referencias correctas"],
            },
            {
                "id": "T2",
                "title": "Definir entidad Producto en capa de dominio",
                "description": "Crear la entidad Product con propiedades Id, Name, Description, Price y StockQuantity. Agregar reglas de dominio básicas.",
                "files_to_touch": ["src/CrudProductos.Domain/Entities/Product.cs"],
                "dependencies": ["T1"],
                "complexity": "low",
                "qa_checklist": ["La entidad es un POCO puro", "Las propiedades son adecuadas para el CRUD"],
            },
            {
                "id": "T3",
                "title": "Configurar DbContext y repositorio",
                "description": "Crear ApplicationDbContext con DbSet<Product>, configurar EF Core InMemory/SQLite e implementar IProductRepository.",
                "files_to_touch": [
                    "src/CrudProductos.Infrastructure/Data/ApplicationDbContext.cs",
                    "src/CrudProductos.Application/Interfaces/IProductRepository.cs",
                    "src/CrudProductos.Infrastructure/Repositories/ProductRepository.cs",
                ],
                "dependencies": ["T2"],
                "complexity": "medium",
                "qa_checklist": ["El DbContext se registra en DI", "El repositorio expone operaciones async"],
            },
            {
                "id": "T4",
                "title": "Crear commands y queries con MediatR",
                "description": "Definir CreateProductCommand, UpdateProductCommand, DeleteProductCommand, GetProductByIdQuery y GetProductListQuery con sus handlers.",
                "files_to_touch": [
                    "src/CrudProductos.Application/Features/Products/Commands/CreateProductCommand.cs",
                    "src/CrudProductos.Application/Features/Products/Commands/UpdateProductCommand.cs",
                    "src/CrudProductos.Application/Features/Products/Commands/DeleteProductCommand.cs",
                    "src/CrudProductos.Application/Features/Products/Queries/GetProductByIdQuery.cs",
                    "src/CrudProductos.Application/Features/Products/Queries/GetProductListQuery.cs",
                    "src/CrudProductos.Application/DTOs/ProductDto.cs",
                ],
                "dependencies": ["T2", "T3"],
                "complexity": "medium",
                "qa_checklist": ["Cada handler usa IProductRepository", "Los handlers son async"],
            },
            {
                "id": "T5",
                "title": "Crear controlador y vistas cshtml",
                "description": "Implementar ProductsController con acciones Index, Details, Create, Edit, Delete y las vistas Razor correspondientes.",
                "files_to_touch": [
                    "src/CrudProductos.Web/Controllers/ProductsController.cs",
                    "src/CrudProductos.Web/Views/Products/Index.cshtml",
                    "src/CrudProductos.Web/Views/Products/Create.cshtml",
                    "src/CrudProductos.Web/Views/Products/Edit.cshtml",
                    "src/CrudProductos.Web/Views/Products/Details.cshtml",
                    "src/CrudProductos.Web/Views/Products/Delete.cshtml",
                ],
                "dependencies": ["T4"],
                "complexity": "high",
                "qa_checklist": ["Todas las vistas renderizan", "El CRUD funciona end-to-end"],
            },
            {
                "id": "T6",
                "title": "Configurar DI y middleware en Program.cs",
                "description": "Registrar MediatR, FluentValidation, EF Core y el repositorio en Program.cs. Configurar el pipeline de middleware.",
                "files_to_touch": [
                    "src/CrudProductos.Web/Program.cs",
                    "src/CrudProductos.Web/appsettings.json",
                    "src/CrudProductos.Web/appsettings.Development.json",
                ],
                "dependencies": ["T3", "T5"],
                "complexity": "low",
                "qa_checklist": ["La aplicación inicia sin errores", "Los servicios se resuelven correctamente"],
            },
            {
                "id": "T7",
                "title": "Agregar validaciones con FluentValidation",
                "description": "Crear validadores para CreateProductCommand y UpdateProductCommand. Name requerido, Price >= 0, StockQuantity >= 0.",
                "files_to_touch": [
                    "src/CrudProductos.Application/Features/Products/Validators/CreateProductCommandValidator.cs",
                    "src/CrudProductos.Application/Features/Products/Validators/UpdateProductCommandValidator.cs",
                ],
                "dependencies": ["T4"],
                "complexity": "low",
                "qa_checklist": ["Las reglas de validación están cubiertas", "Un command inválido retorna 400"],
            },
            {
                "id": "T8",
                "title": "Crear tests unitarios e integración",
                "description": "Agregar proyectos de test con xUnit, tests unitarios para handlers y tests de integración con WebApplicationFactory.",
                "files_to_touch": [
                    "tests/CrudProductos.Application.Tests/CrudProductos.Application.Tests.csproj",
                    "tests/CrudProductos.Application.Tests/Handlers/CreateProductCommandHandlerTests.cs",
                    "tests/CrudProductos.Web.Tests/CrudProductos.Web.Tests.csproj",
                    "tests/CrudProductos.Web.Tests/ProductsApiIntegrationTests.cs",
                ],
                "dependencies": ["T6"],
                "complexity": "high",
                "qa_checklist": ["dotnet test pasa", "Se cubren crear, listar, obtener, editar y eliminar"],
            },
        ]

    def _build_planner_prompt(self, prd_path, tasks_path):
        title = self.ticket.get("title", "")
        description = self.ticket.get("description", "")
        return f"""Eres un arquitecto de software senior. Lee el PRD en {prd_path} y el ticket '{title}' con descripción: {description}.

Genera un JSON con tareas de implementación concretas. Cada tarea debe tener:
- id: string único (T1, T2, ...)
- title: título corto
- description: instrucciones detalladas para un ingeniero
- files_to_touch: array de rutas relativas de archivos .cs a crear/modificar
- dependencies: array de ids de tareas que deben terminar antes
- complexity: "low", "medium" o "high"
- qa_checklist: array de 2-5 strings con lo que QA debe verificar

REGLAS ESTRICTAS:
1. Máximo 10 tareas. Prioriza archivos .cs del proyecto .NET.
2. Responde ÚNICAMENTE con un JSON válido (array de objetos).
3. NO escribas el JSON en archivo; el sistema lo extraerá de tu respuesta.
4. NO incluyas markdown, explicaciones, ni pensamientos fuera del JSON.
5. El JSON debe empezar con [ y terminar con ].
6. Asegúrate de que el JSON sea parseable.

Ejemplo de formato esperado:
[
  {{
    "id": "T1",
    "title": "Crear solución y proyectos .NET",
    "description": "Inicializar la solución y los proyectos Domain, Application, Infrastructure y Web.",
    "files_to_touch": ["CrudProductos.sln", "src/CrudProductos.Domain/CrudProductos.Domain.csproj"],
    "dependencies": [],
    "complexity": "medium",
    "qa_checklist": ["La solución compila", "Los proyectos tienen las referencias correctas"]
  }}
]"""

    def _parse_tasks_from_output(self, output):
        if not output:
            return []

        # 1. Buscar bloque JSON en markdown code block
        code_block_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', output, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except Exception:
                pass

        # 2. Buscar array JSON con conteo de corchetes (más robusto que find/rfind)
        try:
            start = output.find('[')
            if start != -1:
                depth = 0
                in_string = False
                escape = False
                for i in range(start, len(output)):
                    c = output[i]
                    if escape:
                        escape = False
                        continue
                    if c == '\\':
                        escape = True
                        continue
                    if c == '"' and not in_string:
                        in_string = True
                    elif c == '"' and in_string:
                        in_string = False
                    elif not in_string:
                        if c == '[':
                            depth += 1
                        elif c == ']':
                            depth -= 1
                            if depth == 0:
                                return json.loads(output[start:i+1])
        except Exception:
            pass

        # 3. Si no hay array, buscar objeto con key "tasks"
        try:
            start = output.find('{')
            end = output.rfind('}')
            if start != -1 and end != -1 and end > start:
                data = json.loads(output[start:end+1])
                if isinstance(data, list):
                    return data
                if "tasks" in data and isinstance(data["tasks"], list):
                    return data["tasks"]
        except Exception:
            pass
        return []

    def run_execution(self):
        self._ensure_agent("engineer-squad", "Engineer Squad", "lead", "orchestrator", "running", 75)
        self._update_agent("engineer-squad", progress=80, log="Implementando tareas en el repo en paralelo.")
        self.log("Engineers implementando tareas en el repo en paralelo.")

        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
        repo_path = self.ticket.get("repoPath", "")
        branch = self.ticket.get("branch", "")

        if not tasks_path.exists():
            self.log("No se encontró tasks.json; saltando ejecución.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No había tareas para ejecutar.")
            self.set_phase("engineer-squad", "in-progress", 85)
            return

        with open(tasks_path, "r", encoding="utf-8") as f:
            tasks = json.load(f)

        if not tasks:
            self.log("Planner no generó tareas; saltando ejecución.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No había tareas para ejecutar.")
            self.set_phase("engineer-squad", "in-progress", 85)
            return

        if not repo_path:
            self.log("No hay repo configurado; saltando ejecución.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No hay repo configurado.")
            self.set_phase("engineer-squad", "in-progress", 85)
            return

        with run_lock:
            state = load_run_state()
            bus.publish_event(state, "engineer-squad", "batch_started", {"taskCount": len(tasks)})
            save_run_state(state)
            emit_communication_update(state)

        results = self._execute_tasks_parallel(tasks, repo_path, branch)

        with run_lock:
            state = load_run_state()
            bus.publish_event(state, "engineer-squad", "batch_completed", {"taskCount": len(tasks), "results": results})
            save_run_state(state)
            emit_communication_update(state)

        self._update_agent("engineer-squad", status="done", progress=100, log="Ejecución completada.")
        self.set_phase("engineer-squad", "in-progress", 85)

    def _mark_task_failed(self, agent_id, tid, reason):
        """Publica task_failed y marca el agente como fallido."""
        with run_lock:
            state = load_run_state()
            _update_agent(state, agent_id, status="failed", progress=100, log=f"Tarea {tid} falló: {reason}")
            bus.publish_event(state, agent_id, "task_failed", {"taskId": tid, "reason": reason})
            save_run_state(state)
            emit_communication_update(state)

    def _run_single_engineer_task(self, task, status, results, lock, stop_event):
        """Ejecuta una tarea de engineer individual y actualiza estado compartido."""
        tid = task["id"]
        agent_id = f"engineer-{tid}"
        repo_path = self.ticket.get("repoPath", "")
        branch = self.ticket.get("branch", "")
        self.log(f"[{agent_id}] Hilo de tarea iniciado para {tid}.")
        with run_lock:
            state = load_run_state()
            _ensure_agent(state, agent_id, f"Engineer {tid}", "sub", "engineer-squad", "running", 0)
            bus.register_participant(state, {
                "id": agent_id,
                "name": f"Engineer {tid}",
                "role": "sub",
                "description": f"Implementa tarea {tid}",
                "capabilities": ["coding", "dotnet"],
                "tools": ["kimi_prompt", "dotnet_build", "git"],
            })
            _update_agent(state, agent_id, progress=20, log=f"Iniciando tarea: {task['title']}")
            bus.publish_event(state, agent_id, "task_started", {"taskId": tid, "title": task.get("title")})
            save_run_state(state)
            emit_communication_update(state)

        deps = task.get("dependencies", []) or []
        task_context = (
            f"Tarea actual: {task.get('id')} - {task.get('title')}\n"
            f"Descripción: {task.get('description', '')}\n"
            f"Dependencias: {deps}\n"
            f"Archivos a tocar: {task.get('files_to_touch', [])}\n"
            f"QA checklist: {task.get('qa_checklist', [])}"
        )

        # Contexto del proyecto completo y de dependencias ya terminadas.
        project_context = self._build_consultation_context(task_context=task_context)
        dependency_context = self._get_dependency_context(deps)
        if dependency_context:
            self._update_agent(agent_id, progress=25, log=f"Contexto de {len(deps)} dependencia(s) incorporado.")

        help_msgs = self._get_messages_for(agent_id, "request_help", handled=False)
        for msg in help_msgs:
            payload = msg.get("payload", {})
            self._request_help(msg["from"], agent_id, payload.get("taskId"), payload.get("question", ""))
            self._mark_message_handled(msg["id"])

        clarification_msgs = self._get_messages_for(agent_id, "request_clarification", handled=False)
        for msg in clarification_msgs:
            payload = msg.get("payload", {})
            self._request_clarification(msg["from"], agent_id, payload.get("topic", ""), payload.get("question", ""))
            self._mark_message_handled(msg["id"])

        prompt = self._build_engineer_prompt(task, repo_path, branch, project_context, dependency_context)
        try:
            output = self._run_kimi_prompt(prompt, phase_name=f"Engineer {tid}", timeout_seconds=1800, agent_id=agent_id)
            self._parse_engineer_coordination_messages(agent_id, output)
            with lock:
                if output:
                    status[tid] = "done"
                    results[tid] = True
                else:
                    status[tid] = "failed"
                    results[tid] = False

            if output:
                self._update_agent(agent_id, status="done", progress=100, log=f"Tarea {tid} completada.")
                with run_lock:
                    state = load_run_state()
                    bus.publish_event(state, agent_id, "task_completed", {"taskId": tid})
                    bus.send_message(
                        state,
                        agent_id,
                        "qa-engineer",
                        "request_review",
                        {"taskId": tid, "title": task.get("title"), "files": task.get("files_to_touch", [])},
                    )
                    save_run_state(state)
                    emit_communication_update(state)
                self._collect_agent_outputs(agent_id, repo_path)
            else:
                self._mark_task_failed(agent_id, tid, "no output")
                stop_event.set()
        except Exception as exc:
            with lock:
                status[tid] = "failed"
                results[tid] = False
            self._mark_task_failed(agent_id, tid, str(exc))
            stop_event.set()

    def _collect_agent_outputs(self, agent_id, repo_path):
        """Recopila archivos modificados por un agente y los guarda en su estado."""
        if not repo_path or not os.path.isdir(repo_path):
            return
        git_dir = os.path.join(repo_path, ".git")
        if not os.path.isdir(git_dir):
            return
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "diff", "--name-only"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if not files:
                return
            with run_lock:
                state = load_run_state()
                for agent in state.get("agents", []):
                    if agent.get("id") == agent_id:
                        existing = set(agent.get("outputs", []))
                        for rel in files:
                            abs_path = os.path.normpath(os.path.join(repo_path, rel))
                            existing.add(abs_path)
                        agent["outputs"] = sorted(existing)
                        save_run_state(state)
                        break
        except Exception as exc:
            self.log(f"No se pudieron recopilar outputs de {agent_id}: {exc}", "warning")

    def _execute_tasks_parallel(self, tasks, repo_path, branch):
        """Ejecuta tareas respetando dependencias, con pool paralelo."""
        max_workers = 10
        task_by_id = {t["id"]: t for t in tasks}
        status = {t["id"]: "queued" for t in tasks}
        results = {}
        lock = threading.Lock()
        stop_event = threading.Event()

        self.log(f"[execute_tasks_parallel] Iniciando ejecución de {len(tasks)} tareas.")

        # Reutilizar tareas que ya habían terminado o fallado en una ejecución previa.
        skipped_done = []
        skipped_failed = []
        with run_lock:
            state = load_run_state()
            for t in tasks:
                tid = t["id"]
                agent_id = f"engineer-{tid}"
                agent = next((a for a in state.get("agents", []) if a.get("id") == agent_id), None)
                if agent and agent.get("status") == "done":
                    status[tid] = "done"
                    results[tid] = True
                    skipped_done.append(tid)
                elif agent and agent.get("status") == "failed":
                    status[tid] = "failed"
                    results[tid] = False
                    skipped_failed.append(tid)
        if skipped_done:
            self.log(f"Tareas ya completadas; se omiten en la reanudación: {', '.join(skipped_done)}.")
        if skipped_failed:
            self.log(f"Tareas que habían fallado; se omiten en la reanudación: {', '.join(skipped_failed)}.")

        def can_run(task):
            deps = task.get("dependencies", []) or []
            return all(status.get(d) == "done" for d in deps)

        def run_task(task):
            self._run_single_engineer_task(task, status, results, lock, stop_event)

        pending = set(t["id"] for t in tasks if status.get(t["id"]) == "queued")
        running_threads = {}
        self.log(f"[execute_tasks_parallel] Tareas pendientes iniciales: {', '.join(sorted(pending))}.")

        while pending or running_threads:
            if stop_event.is_set():
                self.log("[execute_tasks_parallel] Stop event activado; esperando threads y bloqueando pendientes.")
                # Esperar a que terminen los que corren y marcar pendientes como blocked
                for t in list(running_threads.values()):
                    t.join(timeout=10)
                with lock:
                    for tid in list(pending):
                        status[tid] = "blocked"
                        agent_id = f"engineer-{tid}"
                        self._ensure_agent(agent_id, f"Engineer {tid}", "sub", "engineer-squad", "blocked", 0)
                        self._update_agent(agent_id, status="blocked", progress=0, log="Bloqueado por fallo en dependencia.")
                break

            # Lanzar tareas listas hasta llenar el pool
            while len(running_threads) < max_workers and pending:
                ready_tasks = [task_by_id[tid] for tid in pending if can_run(task_by_id[tid])]
                if not ready_tasks:
                    blocked_list = sorted(pending)
                    self.log(f"[execute_tasks_parallel] No hay tareas listas todavía; pendientes bloqueadas por dependencias: {', '.join(blocked_list)}.")
                    break
                task = ready_tasks[0]
                tid = task["id"]
                pending.remove(tid)
                status[tid] = "running"
                self.log(f"[execute_tasks_parallel] Lanzando {tid}: {task.get('title', '')}.")
                t = threading.Thread(target=run_task, args=(task,), daemon=True)
                running_threads[tid] = t
                t.start()

            if not running_threads:
                # No hay listos ni corriendo: posible ciclo o todo bloqueado
                self.log("[execute_tasks_parallel] Sin threads corriendo ni listos; saliendo del loop.")
                break

            # Esperar a que termine alguno
            while running_threads:
                done_threads = [tid for tid, t in running_threads.items() if not t.is_alive()]
                if done_threads:
                    for tid in done_threads:
                        del running_threads[tid]
                    self.log(f"[execute_tasks_parallel] Threads finalizados: {', '.join(done_threads)}; corriendo: {', '.join(running_threads)}; pendientes: {', '.join(sorted(pending))}.")
                    break
                time.sleep(0.5)

        self.log(f"Ejecución paralela finalizada: {sum(1 for v in results.values() if v)}/{len(tasks)} exitosas.")
        return results

    def _restart_engineer_task(self, agent_id):
        """Reinicia una tarea engineer individual."""
        tid = agent_id.split("-", 1)[1] if "-" in agent_id else None
        if not tid:
            return
        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
        if not tasks_path.exists():
            return
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except Exception:
            return
        task = next((t for t in tasks if t.get("id") == tid), None)
        if not task:
            return
        status = {tid: "queued"}
        results = {}
        lock = threading.Lock()
        stop_event = threading.Event()
        self._run_single_engineer_task(task, status, results, lock, stop_event)

    def _restart_pm_subagent(self, agent_id):
        """Reinicia un subagente de PM volviendo a ejecutar la fase de análisis."""
        self.log(f"Reiniciando subagente PM {agent_id}; re-ejecutando análisis.")
        self.run_pm_analysis()

    def _restart_agent(self, agent_id):
        """Resetea el estado de un agente y lo re-ejecuta cuando es posible."""
        with run_lock:
            state = load_run_state()
            agent = next((a for a in state.get("agents", []) if a.get("id") == agent_id), None)
            if not agent:
                return False
            agent["status"] = "queued"
            agent["progress"] = 0
            agent["logs"] = []
            agent["restartedAt"] = datetime.now(timezone.utc).isoformat()
            save_run_state(state)
        socketio.emit("run_state_update", state)

        if agent_id.startswith("engineer-"):
            threading.Thread(target=self._restart_engineer_task, args=(agent_id,), daemon=True).start()
        elif agent_id.startswith("pm-") or agent_id == "pm-research-agents":
            threading.Thread(target=self._restart_pm_subagent, args=(agent_id,), daemon=True).start()
        elif agent_id == "architect":
            threading.Thread(target=self.run_architect, daemon=True).start()
        elif agent_id == "project-manager":
            threading.Thread(target=self.run_planner, daemon=True).start()
        elif agent_id == "qa-engineer":
            threading.Thread(target=self.run_qa, daemon=True).start()
        return True

    def _build_engineer_prompt(self, task, repo_path, branch, project_context="", dependency_context=""):
        files = ", ".join(task.get("files_to_touch", []) or ["archivos relevantes del proyecto"])
        branch_clause = f" en la branch {branch}" if branch else ""
        project_section = f"\n\n--- CONTEXTO DEL PROYECTO ---\n{project_context}" if project_context else ""
        dependency_section = f"\n\n--- CONTEXTO DE DEPENDENCIAS ---\n{dependency_context}" if dependency_context else ""
        return f"""Eres un ingeniero senior .NET. Trabaja en el repo {repo_path}{branch_clause}.

META GENERAL:
Eres parte de un equipo que ejecuta el ticket descrito abajo. Ya tienes el orden de trabajo, el PRD, el plan de tareas y el contexto de las dependencias. Tu trabajo es implementar TU tarea de forma autónoma, asumiendo las mejores prácticas de .NET y sin detenerte a preguntar por dudas rutinarias. Solo detente si hay un impedimento real que no puedas resolver con el contexto proporcionado.

REGLAS OBLIGATORIAS:
- Si el repo no tiene un archivo .csproj o .sln, DEBES crear primero un proyecto .NET 8 válido con `dotnet new webapi -n CrudProductos` (o nombre apropiado).
- Crea/modifica archivos directamente en el filesystem usando comandos de shell o escribiendo archivos.
- Después de crear/editar archivos, ejecuta `dotnet build` en {repo_path} para verificar que compila.
- Si hay tests, ejecuta `dotnet test`.
- NO respondas solo con explicaciones; debes crear los archivos reales en disco.

TU TAREA:

Título: {task.get('title', '')}
Descripción: {task.get('description', '')}
Archivos relevantes: {files}

Al terminar, reporta:
1. Qué archivos modificaste o creaste.
2. Resultado de `dotnet build` (éxito/error).
3. Un QA checklist de 3-5 bullets de lo que se debe verificar.

Sé concreto y escribe código funcional en C# siguiendo patrones comunes de ASP.NET Core / .NET.{project_section}{dependency_section}

COORDINACIÓN (OPCIONAL):
Si durante la implementación encuentras un bloqueo real que no puedas resolver solo, puedes incluir UNA línea EXACTAMENTE con uno de estos formatos:
REQUEST_HELP:<id_del_helper>:<pregunta>
REQUEST_CLARIFICATION:<id_del_pm_o_architect>:<tema>:<pregunta>

No uses estos mecanismos para dudas rutinarias o decisiones de diseño menores: asume la mejor decisión y continúa."""
        + decision_request_instruction()

    def run_qa(self):
        self._agent_log("orchestrator", "Fase 5/5: QA Review — revisando integración del batch.")
        self.set_phase("qa-engineer", "in-review", 90)

        # Register main QA participant
        self._ensure_agent("qa-engineer", "QA Engineer", "lead", "orchestrator", "running", 90)
        self._update_agent("qa-engineer", progress=95, log="Revisando diffs y tests del batch.")
        self.log("QA revisando diffs y tests del batch.")
        with run_lock:
            state = load_run_state()
            bus.register_participant(state, {
                "id": "qa-engineer",
                "name": "QA Engineer",
                "role": "qa",
                "description": "Revisa integración, build y tests del batch",
                "capabilities": ["qa_review", "build_verification", "test_verification"],
                "tools": ["dotnet_build", "dotnet_test", "git_diff"],
            })
            save_run_state(state)
            emit_communication_update(state)

        repo_path = self.ticket.get("repoPath", "")
        branch = self.ticket.get("branch", "")

        max_correction_rounds = 3
        for correction_round in range(max_correction_rounds):
            review_msgs = self._get_messages_for("qa-engineer", "request_review", handled=False)
            if not review_msgs:
                self.log("No hay más revisiones pendientes.")
                break

            self._agent_log("qa-engineer", f"Revisión {correction_round + 1}/{max_correction_rounds}: {len(review_msgs)} tarea(s) pendiente(s).")

            build_ok, build_output = self._run_dotnet_build(repo_path)
            test_ok, test_output = self._run_dotnet_test(repo_path)
            diff = self._get_git_diff(repo_path)

            rejected_items = []
            rejected_lock = threading.Lock()

            def review_one(msg):
                payload = msg.get("payload", {})
                task_id = payload.get("taskId")
                engineer_id = msg.get("from")
                qa_agent_id = f"qa-{task_id}"

                self._ensure_agent(qa_agent_id, f"QA {task_id}", "qa", "qa-engineer", "running", 90)
                self._update_agent(qa_agent_id, progress=50, log=f"Revisando tarea {task_id}.")

                branch_clause = f" en la branch {branch}" if branch else ""
                review_prompt = f"""Eres un QA Engineer senior .NET. Revisa los cambios de la tarea {task_id}{branch_clause} del repo {repo_path}.

Diff:
{diff}

Build: {'OK' if build_ok else 'FAIL'}
{build_output}

Tests: {'OK' if test_ok else 'FAIL'}
{test_output}

Si encuentras problemas, responde EXACTAMENTE con:
RECHAZO: <motivo>
SUGERENCIA: <sugerencia de corrección>

Si todo está bien, responde EXACTAMENTE con:
APROBADO"""
                review_result = self._run_kimi_prompt(review_prompt, phase_name=f"QA Review {task_id}", timeout_seconds=600, agent_id=qa_agent_id) or ""

                if "APROBADO" in review_result.upper() and build_ok and test_ok:
                    with run_lock:
                        state = load_run_state()
                        completion_msg = bus.send_message(state, qa_agent_id, engineer_id, "notify_completion", {"taskId": task_id, "review": review_result[:500]})
                        bus.mark_handled(state, completion_msg["id"])
                        save_run_state(state)
                        emit_communication_update(state)
                    self._mark_message_handled(msg["id"], {"status": "approved"})
                    self._update_agent(qa_agent_id, status="done", progress=100, log=f"Tarea {task_id} aprobada.")
                    return None

                reason = ""
                suggestion = ""
                for line in review_result.splitlines():
                    if line.upper().startswith("RECHAZO:"):
                        reason = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("SUGERENCIA:"):
                        suggestion = line.split(":", 1)[1].strip()
                if not reason:
                    reason = "Build o tests fallaron" if not (build_ok and test_ok) else "Revisión no aprobó"

                with run_lock:
                    state = load_run_state()
                    rejection_msg = bus.send_message(state, qa_agent_id, engineer_id, "reject_with_feedback", {"taskId": task_id, "reason": reason, "suggestedFix": suggestion})
                    save_run_state(state)
                    emit_communication_update(state)
                self._mark_message_handled(msg["id"], {"status": "rejected", "reason": reason})
                self._update_agent(qa_agent_id, status="failed", progress=100, log=f"Tarea {task_id} rechazada: {reason[:120]}")
                return {
                    "engineer_id": engineer_id,
                    "task_id": task_id,
                    "reason": reason,
                    "suggested_fix": suggestion,
                    "rejection_id": rejection_msg["id"],
                }

            max_workers = min(5, len(review_msgs))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(review_one, msg) for msg in review_msgs]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                        if result:
                            with rejected_lock:
                                rejected_items.append(result)
                    except Exception as exc:
                        self.log(f"Error en revisión paralela: {exc}", "error")

            # Process rejections -> corrections
            if not rejected_items:
                break

            self._agent_log("qa-engineer", f"Corrigiendo {len(rejected_items)} rechazo(s)...")
            for item in rejected_items:
                engineer_id = item["engineer_id"]
                task_id = item["task_id"]
                reason = item["reason"]
                suggested_fix = item["suggested_fix"]

                self._agent_log(engineer_id, f"Corrigiendo {task_id}: {reason[:120]}", "warning")

                tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
                task = {}
                if tasks_path.exists():
                    try:
                        with open(tasks_path, "r", encoding="utf-8") as f:
                            tasks = json.load(f)
                        task = next((t for t in tasks if t.get("id") == task_id), {})
                    except Exception:
                        pass

                branch_clause = f" en la branch {branch}" if branch else ""
                prompt = f"""Eres un ingeniero senior .NET. Trabaja en el repo {repo_path}{branch_clause}.

La tarea {task_id} fue rechazada por QA.
Motivo: {reason}
Sugerencia: {suggested_fix}
Título original: {task.get('title', '')}
Descripción original: {task.get('description', '')}

Corrige el código respetando el motivo del rechazo. Después ejecuta `dotnet build` y `dotnet test` si hay tests.
Reporta los archivos modificados y el resultado de la build.
"""
                self._run_kimi_prompt(prompt, phase_name=f"Fix {task_id}", timeout_seconds=1800, agent_id=engineer_id)

                with run_lock:
                    state = load_run_state()
                    bus.send_message(state, engineer_id, "qa-engineer", "request_review", {"taskId": task_id, "reason": "corrección post-rechazo"})
                    save_run_state(state)
                    emit_communication_update(state)
                self._mark_message_handled(item["rejection_id"], {"status": "corrected"})

        # Final summary
        pending = self._get_messages_for("qa-engineer", "request_review", handled=False)
        rejections = self._get_messages_for("qa-engineer", "reject_with_feedback", handled=False)
        if pending or rejections:
            msg = f"{len(pending)} revision(es) y {len(rejections)} rechazo(s) quedaron pendientes tras {max_correction_rounds} rondas. QA no aprobó."
            self._agent_log("qa-engineer", msg, "error")
            raise RuntimeError(msg)

        self._update_agent("qa-engineer", status="done", progress=100, log="QA Review completado.")
        self._agent_log("qa-engineer", "QA Review completado.", "success")

    def chat_with_agent(self, recipient_id, message):
        """Responde un mensaje humano como el agente indicado.

        Se usa el mismo backend de Kimi configurado para el runner, con contexto
        del ticket, PRD y tareas planificadas.
        """
        with run_lock:
            state = load_run_state()
            agents_by_id = {a["id"]: a for a in state.get("agents", [])}
        recipient_name = agents_by_id.get(recipient_id, {}).get("name", recipient_id)
        context_text = self._build_consultation_context()

        prompt = f"""Activa la skill 'dotnet' y aplica sus convenciones y mejores prácticas a todo el código .NET que generes.

Eres el agente {recipient_name} ({recipient_id}) de una software factory estilo MetaGPT. El operador humano te escribe:

"{message}"

CONTEXTO DEL PROYECTO:
{context_text}

Responde de forma concisa, técnica y útil. Si el mensaje es una instrucción (por ejemplo, "reintentar", "mejora", "revisa", "reactiva"), indica cómo la aplicarías o qué necesitas. Si no tienes suficiente contexto, dílo claramente."""

        output = self._run_kimi_prompt(
            prompt,
            phase_name=f"Chat {recipient_id}",
            timeout_seconds=60,
            agent_id=recipient_id,
        )
        return (output or "No pude generar una respuesta en este momento.").strip()

    def _run_kimi_prompt(self, prompt, phase_name="Agent", timeout_seconds=120, agent_id=None):
        """Ejecuta un prompt con kimi CLI en modo prompt (-p) y retorna el contenido.

        Usamos 'kimi -p' en lugar de 'kimi --yolo' interactivo porque solo en modo -p
        Kimi CLI puede usar tools (Write, Edit, Bash) y realmente crear/modificar archivos.
        """
        safe_phase = phase_name.lower().replace(' ', '-')
        output_path = get_meta_dir() / "state" / f"output-{self.ticket_id}-{safe_phase}.txt"
        prompt_path = get_meta_dir() / "state" / f"prompt-{self.ticket_id}-{safe_phase}.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Limpiar output previo
        if output_path.exists():
            output_path.unlink()

        # Guardar prompt en archivo
        prompt_path.write_text(prompt, encoding="utf-8")

        def log_to_agent(message, level="info"):
            self.log(message, level)
            if agent_id:
                self._agent_log(agent_id, message, level)

        try:
            kimi = find_kimi_cli()
            if not kimi:
                log_to_agent("No se encontró el ejecutable de Kimi.", "error")
                return None

            log_to_agent(f"Ejecutando Kimi -p para {phase_name} (timeout {timeout_seconds}s)...")
            # Aplicamos la skill de .NET por defecto a todo el desarrollo.
            dotnet_prefix = (
                "Activa la skill 'dotnet' y aplica sus convenciones y mejores prácticas "
                "a todo el código .NET que generes. "
            )
            full_prompt = dotnet_prefix + prompt
            # Ejecutamos kimi -p con el prompt completo como argumento.
            # 'kimi -p' permite tool use y por tanto puede crear/editar archivos.
            # El working directory debe ser el repo del ticket para que las tools
            # (Bash/Write/Edit) operen directamente sobre el código.
            repo_path = self.ticket.get("repoPath") or ""
            cwd = resolve_repo_path(repo_path) or str(Path.cwd())
            proc = subprocess.run(
                [kimi, "-p", full_prompt],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            output = proc.stdout or ""
            if proc.stderr:
                output += "\n" + proc.stderr

            output_path.write_text(output, encoding="utf-8")

            if proc.returncode != 0:
                log_to_agent(f"{phase_name} finalizó con código {proc.returncode}", "warning")

            # Logs del final
            lines = [strip_ansi(l) for l in output.splitlines() if strip_ansi(l).strip()]
            for line in lines[-50:]:
                log_to_agent(f"[{phase_name}] {line[:250]}")

            return "\n".join(lines)
        except subprocess.TimeoutExpired:
            log_to_agent(f"{phase_name} excedió el tiempo límite ({timeout_seconds}s)", "error")
            return None
        except Exception as exc:
            log_to_agent(f"{phase_name} error: {exc}", "error")
            return None


def pause_active_ticket():
    """Pausa el ticket que está corriendo actualmente, guarda snapshot y conserva el thread."""
    global _active_run_thread
    with run_lock:
        state = load_run_state()
    if not state.get("active"):
        return False, "No hay ticket corriendo"
    ticket_id = state.get("ticketId")
    if not ticket_id:
        return False, "No hay ticket activo"

    # Guardar snapshot del estado actual antes de limpiar el global
    save_ticket_snapshot(ticket_id, state)

    if _active_run_thread and _active_run_thread.is_alive():
        _active_run_thread.pause()
        paused_run_threads[ticket_id] = _active_run_thread
        _active_run_thread = None
        # Limpiar run-state global para que el dashboard no muestre el ticket anterior
        reset_run_state_to_idle()
        return True, f"Ticket {ticket_id} pausado"

    # No hay runner vivo, pero igual dejamos el snapshot y limpiamos
    reset_run_state_to_idle()
    return True, f"Ticket {ticket_id} pausado (sin runner activo)"


def play_ticket(ticket_id):
    """Pone un ticket a correr. Si ya hay otro corriendo, lo pausa primero."""
    global _active_run_thread
    board = load_board()
    ticket = next((t for t in board.get("tickets", []) if t.get("id") == ticket_id), None)
    if not ticket:
        return False, "Ticket no encontrado"

    with run_lock:
        state = load_run_state()

    # Ya corriendo
    if state.get("active") and state.get("ticketId") == ticket_id:
        return True, "El ticket ya está corriendo"

    # Pausar otro ticket si hay uno corriendo
    if state.get("active"):
        ok, msg = pause_active_ticket()
        if not ok:
            return False, f"No se pudo pausar el ticket activo: {msg}"
        state = load_run_state()

    # Reanudar thread pausado en memoria
    if ticket_id in paused_run_threads:
        thread = paused_run_threads.pop(ticket_id)
        if thread.is_alive():
            snapshot = load_ticket_snapshot(ticket_id)
            restored = {}
            if snapshot:
                restored = dict(snapshot)
            restored.update({
                "active": True,
                "ticketId": ticket_id,
                "status": (snapshot.get("status") if snapshot else state.get("status")) or "running",
                "currentAgent": snapshot.get("currentAgent") if snapshot else state.get("currentAgent"),
            })
            update_run_state(restored)
            thread.resume()
            _active_run_thread = thread
            delete_ticket_snapshot(ticket_id)
            return True, f"Ticket {ticket_id} reanudado"

    # Reanudar desde snapshot en disco (reinicio o pausa previa sin thread vivo)
    snapshot = load_ticket_snapshot(ticket_id)
    if snapshot:
        restored = dict(snapshot)
        restored.update({"active": True, "ticketId": ticket_id})
        update_run_state(restored)
        started = start_automatic_run(ticket, resume=True, queue_if_active=False)
        if started:
            delete_ticket_snapshot(ticket_id)
            return True, f"Ticket {ticket_id} reanudado desde snapshot"
        return False, "No se pudo iniciar el runner desde snapshot"

    # Iniciar desde cero
    started = start_automatic_run(ticket, resume=False, queue_if_active=False)
    if started:
        return True, f"Ticket {ticket_id} iniciado"
    return False, "No se pudo iniciar el ticket"


def restart_ticket(ticket_id):
    """Restart a ticket from scratch: stop runner, delete artifacts and run-state, then re-run.

    This deletes the run snapshot, generated artifacts (PRD, tasks, architecture,
    design review) and the in-memory/disk run state for the ticket. It then moves
    the ticket back to ready-for-work and starts the pipeline as if it were new.
    Source code changes in the project repo are NOT reverted.
    """
    global _active_run_thread

    board = load_board()
    ticket = next((t for t in board.get("tickets", []) if t.get("id") == ticket_id), None)
    if not ticket:
        return False, "Ticket no encontrado"

    # Stop active runner for this ticket.
    if (
        _active_run_thread
        and _active_run_thread.is_alive()
        and getattr(_active_run_thread, "ticket_id", None) == ticket_id
    ):
        _active_run_thread.stop()
        _active_run_thread.join(timeout=3)
        _active_run_thread = None

    # Remove any paused thread for this ticket.
    paused_run_threads.pop(ticket_id, None)

    # Delete snapshot on disk.
    delete_ticket_snapshot(ticket_id)

    # Delete generated artifacts.
    state_dir = get_meta_dir() / "state"
    if state_dir.exists():
        for pattern in [
            f"prd-{ticket_id}.md",
            f"tasks-{ticket_id}.json",
            f"architecture-{ticket_id}.md",
            f"design-review-{ticket_id}.*",
        ]:
            for path in state_dir.glob(pattern):
                try:
                    path.unlink()
                except OSError:
                    pass

    # Reset global run-state to idle.
    reset_run_state_to_idle()

    # Move ticket back to ready-for-work.
    update_ticket_status(ticket_id, "ready-for-work")

    # Start from scratch.
    ok, msg = play_ticket(ticket_id)
    if ok:
        return True, f"Ticket {ticket_id} reiniciado desde cero"
    return False, f"No se pudo reiniciar el ticket: {msg}"


def start_automatic_run(ticket, resume=False, queue_if_active=True):
    """Inicia el loop multi-agente para un ticket. Si resume=True, reanuda desde run-state existente."""
    global _active_run_thread

    with run_lock:
        state = load_run_state()
        if state.get("active"):
            if queue_if_active:
                queue = state.get("queue", [])
                if ticket["id"] not in queue:
                    queue.append(ticket["id"])
                    state["queue"] = queue
                    save_run_state(state)
                queue_position = len(queue)
                active_ticket_id = state.get("ticketId")
                append_log(
                    f"Ya hay un run activo para {active_ticket_id}. "
                    f"Ticket {ticket['id']} agregado a la cola (posición {queue_position}).",
                    "warning",
                )
            return False

    _active_run_thread = AgentRunner(ticket, resume=resume)
    _active_run_thread.start()
    return True


def resume_run(ticket):
    """Reanuda un run previamente interrumpido para el ticket dado."""
    global _active_run_thread
    if _active_run_thread and _active_run_thread.is_alive():
        return False, "Ya hay un runner activo"
    state = load_run_state()
    if state.get("ticketId") != ticket["id"]:
        return False, "El ticket no coincide con run-state"
    started = start_automatic_run(ticket, resume=True)
    if not started:
        return False, "No se pudo iniciar el runner"
    return True, "Run reanudado"


def reset_run_state_to_idle():
    """Limpia run-state a valores idle, conservando solo la cola."""
    with run_lock:
        state = load_run_state()
        queue = state.get("queue", [])
        state = {
            "active": False,
            "ticketId": None,
            "status": "idle",
            "currentAgent": None,
            "progress": 0,
            "startedAt": None,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "elapsedSeconds": None,
            "summary": compute_run_summary("idle", None),
            "logs": [],
            "queue": queue,
            "agents": [],
            "messages": [],
            "pendingQuestions": [],
            "communication": _default_communication(),
            "designReview": None,
        }
        save_run_state(state)
        socketio.emit("run_state_update", state)


def stop_active_run(reason="Detenido por usuario"):
    """Detiene el runner activo y limpia el run-state."""
    global _active_run_thread

    runner = _active_run_thread
    if runner and runner.is_alive():
        append_log(f"{reason}. Deteniendo runner {runner.ticket_id}...", "warning")
        runner.stop()
        # Esperar un poco a que el runner reconozca la señal
        runner.join(timeout=3)

    with run_lock:
        state = load_run_state()
        state["active"] = False
        save_run_state(state)

    reset_run_state_to_idle()
    _active_run_thread = None


def _find_next_runnable_ticket(board=None, exclude_ids=None):
    """Busca el siguiente ticket listo para ejecutar en el board."""
    if board is None:
        board = load_board()
    exclude_ids = set(exclude_ids or [])
    runnable_statuses = ["ready-for-work", "in-design"]
    candidates = [
        t for t in board.get("tickets", [])
        if t.get("status") in runnable_statuses and t.get("id") not in exclude_ids
    ]
    if not candidates:
        return None
    # Ordenar por updatedAt ascendente (el más antiguo primero)
    candidates.sort(key=lambda t: t.get("updatedAt") or t.get("createdAt") or "")
    return candidates[0]


def process_next_in_queue():
    """Procesa el siguiente ticket en la cola o board cuando termina un run."""
    global _active_run_thread

    with run_lock:
        state = load_run_state()
        queue = state.get("queue", [])

    # Primero intentar con la cola interna
    next_ticket = None
    while queue:
        next_ticket_id = queue.pop(0)
        board = load_board()
        ticket = next((t for t in board["tickets"] if t["id"] == next_ticket_id), None)
        if ticket and ticket.get("status") in ["ready-for-work", "in-design"]:
            next_ticket = ticket
            break
        append_log(f"Ticket {next_ticket_id} en cola ya no existe o no está listo. Saltando.", "warning")

    # Si no hay cola, buscar siguiente ticket runnable en el board
    if not next_ticket:
        board = load_board()
        next_ticket = _find_next_runnable_ticket(board)
        if next_ticket:
            append_log(f"Siguiente ticket automático del board: {next_ticket['id']}")

    if not next_ticket:
        append_log("No hay más tickets en cola ni listos para ejecutar.")
        reset_run_state_to_idle()
        _active_run_thread = None
        return False

    # Guardar cola actualizada
    with run_lock:
        state = load_run_state()
        state["queue"] = queue
        save_run_state(state)

    update_ticket_status(next_ticket["id"], "ready-for-work")
    _active_run_thread = AgentRunner(next_ticket, resume=False)
    _active_run_thread.start()
    return True


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


@app.route("/api/board", methods=["GET"])
def api_board():
    board = load_board()
    recompute_stats(board)
    save_board(board)
    return jsonify(board)


@app.route("/api/run-state", methods=["GET"])
def api_run_state():
    state = load_run_state()
    state["pausedTickets"] = list_ticket_snapshots()
    return jsonify(state)


@app.route("/api/tickets/<ticket_id>/play", methods=["POST"])
def api_play_ticket(ticket_id):
    ok, msg = play_ticket(ticket_id)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@app.route("/api/tickets/<ticket_id>/restart", methods=["POST"])
def api_restart_ticket(ticket_id):
    ok, msg = restart_ticket(ticket_id)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@app.route("/api/tickets/<ticket_id>/pause", methods=["POST"])
def api_pause_ticket(ticket_id):
    state = load_run_state()
    if state.get("ticketId") != ticket_id:
        return jsonify({"ok": False, "message": "Este ticket no está corriendo"}), 400
    ok, msg = pause_active_ticket()
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@app.route("/api/participants", methods=["GET"])
def api_participants():
    with run_lock:
        state = load_run_state()
        return jsonify(bus.get_participants(state))


@app.route("/api/communication", methods=["GET"])
def api_communication():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    type_filter = request.args.get("type") or None
    participant_id = request.args.get("participantId") or None
    message_type = request.args.get("messageType") or None
    with run_lock:
        state = load_run_state()
        log = bus.get_log(state, limit, offset, type_filter, participant_id, message_type)
        return jsonify({
            "entries": log,
            "participants": bus.get_participants(state),
            "pendingActions": bus.get_pending_actions(state),
        })


def get_model_name():
    """Devuelve el modelo en uso. Intenta consultar `kimi --version`."""
    kimi = find_kimi_cli()
    if kimi:
        try:
            result = subprocess.run(
                [kimi, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip().splitlines()[0]
                if version:
                    return version
        except Exception:
            pass
    return "Kimi K2.7 Code"


@app.route("/api/system-info", methods=["GET"])
def api_system_info():
    return jsonify({"model": get_model_name()})


def _estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 4)


def _build_traces(state, limit=60):
    """Construye una lista de traces combinando logs de agentes, eventos del bus y mensajes."""
    traces = []

    # Logs de agentes
    for agent in state.get("agents", []):
        logs = agent.get("logs", []) or []
        for idx, log in enumerate(logs):
            msg = log.get("message", "")
            ts = log.get("timestamp")
            duration = None
            if idx + 1 < len(logs) and ts:
                try:
                    t1 = datetime.fromisoformat(ts)
                    t2 = datetime.fromisoformat(logs[idx + 1].get("timestamp", ""))
                    duration = max(0, int((t2 - t1).total_seconds() * 1000))
                except Exception:
                    pass
            level = log.get("level", "info")
            status = {"error": "err", "warning": "wrn"}.get(level, "ok")
            traces.append({
                "id": f"{agent['id']}-log-{idx}",
                "timestamp": ts,
                "agentId": agent.get("id"),
                "agentName": agent.get("name"),
                "name": agent.get("name", "Agent"),
                "type": "agent.log",
                "durationMs": duration,
                "tokensEstimated": _estimate_tokens(msg),
                "status": status,
                "message": msg[:180],
                "level": level,
            })

    # Eventos del bus de comunicación
    for ev in state.get("communication", {}).get("log", []) or []:
        ev_type = ev.get("eventType", "event")
        status = "ok"
        if ev_type in ("task_failed", "task_rejected"):
            status = "err"
        elif ev_type in ("task_started", "batch_started"):
            status = "live"
        elif ev_type == "status_changed" and ev.get("payload", {}).get("to") == "failed":
            status = "err"
        payload_text = ""
        try:
            payload_text = json.dumps(ev.get("payload", {}), ensure_ascii=False)
        except Exception:
            pass
        traces.append({
            "id": ev.get("id") or f"ev-{len(traces)}",
            "timestamp": ev.get("timestamp"),
            "agentId": ev.get("participantId"),
            "agentName": ev.get("participantId"),
            "name": ev_type,
            "type": "event",
            "durationMs": None,
            "tokensEstimated": _estimate_tokens(payload_text),
            "status": status,
            "message": payload_text[:140],
            "level": status,
        })

    # Mensajes entre agentes
    for msg in state.get("messages", []) or []:
        content = msg.get("answer") or msg.get("question") or ""
        status = "ok" if msg.get("status") == "answered" else "live"
        traces.append({
            "id": msg.get("id") or f"msg-{len(traces)}",
            "timestamp": msg.get("timestamp"),
            "agentId": msg.get("from"),
            "agentName": msg.get("from"),
            "name": f"{msg.get('from', '?')} → {msg.get('to', '?')}",
            "type": "message",
            "durationMs": None,
            "tokensEstimated": _estimate_tokens(content),
            "status": status,
            "message": (msg.get("question") or "")[:140],
            "level": status,
        })

    # Calcular duración de eventos de tarea usando pares started/completed
    started = {}
    for t in traces:
        if t["type"] == "event" and t["name"] == "task_started":
            started[(t.get("agentId"), t.get("message"))] = t
    for t in traces:
        if t["type"] == "event" and t["name"] == "task_completed":
            key = (t.get("agentId"), t.get("message"))
            start_trace = started.get(key)
            if start_trace and start_trace["timestamp"] and t["timestamp"]:
                try:
                    t1 = datetime.fromisoformat(start_trace["timestamp"])
                    t2 = datetime.fromisoformat(t["timestamp"])
                    t["durationMs"] = max(0, int((t2 - t1).total_seconds() * 1000))
                except Exception:
                    pass

    traces.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return traces[:limit]


def _build_graph(state):
    """Construye nodos y aristas para el grafo de agentes."""
    nodes = []
    for a in state.get("agents", []) or []:
        nodes.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "role": a.get("role"),
            "status": a.get("status"),
            "progress": a.get("progress"),
            "parentId": a.get("parentId"),
        })
    edges = []
    seen = set()
    for a in state.get("agents", []) or []:
        parent = a.get("parentId")
        if parent:
            key = (parent, a["id"])
            if key not in seen:
                edges.append({"source": parent, "target": a["id"], "type": "parent"})
                seen.add(key)
    for msg in state.get("messages", []) or []:
        key = (msg.get("from"), msg.get("to"))
        if key[0] and key[1] and key not in seen:
            edges.append({"source": key[0], "target": key[1], "type": "message"})
            seen.add(key)
    return {"nodes": nodes, "edges": edges}


@app.route("/api/traces", methods=["GET"])
def api_traces():
    with run_lock:
        state = load_run_state()
    limit = request.args.get("limit", 60, type=int)
    return jsonify(_build_traces(state, limit=limit))


@app.route("/api/graph", methods=["GET"])
def api_graph():
    with run_lock:
        state = load_run_state()
    return jsonify(_build_graph(state))


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/api/run-state/logs", methods=["POST"])
def api_append_log():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    level = data.get("level", "info").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    append_log(message, level)
    return jsonify({"ok": True})


@app.route("/api/questions", methods=["GET"])
def api_list_questions():
    state = load_run_state()
    status_filter = request.args.get("status")
    questions = state.get("pendingQuestions", [])
    if status_filter:
        questions = [q for q in questions if q.get("status") == status_filter]
    return jsonify({"questions": questions})


@app.route("/api/questions/<question_id>/answer", methods=["POST"])
def api_answer_question(question_id):
    data = request.get_json(silent=True) or {}
    answer = data.get("answer", "").strip()
    if not answer:
        return jsonify({"error": "answer required"}), 400

    q = answer_user_question(question_id, answer)
    if not q:
        return jsonify({"error": "question not found or already answered"}), 404

    if not _write_answer_file(q, answer):
        return jsonify({"error": "could not write answer file"}), 500

    return jsonify({"ok": True, "question": q})


@app.route("/api/questions/<question_id>/skip", methods=["POST"])
def api_skip_question(question_id):
    """El usuario elige no responder; el agente decide solo."""
    answer = "Decide solo (usuario)"
    q = answer_user_question(question_id, answer)
    if not q:
        return jsonify({"error": "question not found or already answered"}), 404

    if not _write_answer_file(q, answer):
        return jsonify({"error": "could not write answer file"}), 500

    return jsonify({"ok": True, "question": q})


@app.route("/api/design-review", methods=["GET"])
def api_design_review():
    """Devuelve la revisión de diseño activa (preguntas + respuestas asumidas)."""
    state = load_run_state()
    review = state.get("designReview")
    if not review:
        return jsonify({"active": False})
    return jsonify({
        "active": not review.get("answered", False),
        "review": review,
    })


@app.route("/api/design-review/extend", methods=["POST"])
def api_design_review_extend():
    """Extiende el tiempo de espera de la revisión de diseño en 60 segundos."""
    with run_lock:
        state = load_run_state()
        review = state.get("designReview")
        if not review or review.get("answered"):
            return jsonify({"error": "No hay revisión activa"}), 404
        extra = 60
        review["timeoutSeconds"] = review.get("timeoutSeconds", 60) + extra
        review["expiresAt"] = (datetime.now(timezone.utc) + timedelta(seconds=extra)).isoformat()
        review["extended"] = True
        state["designReview"] = review
        save_run_state(state)
    return jsonify({"ok": True, "review": review})


@app.route("/api/design-review/answer", methods=["POST"])
def api_design_review_answer():
    """Recibe las respuestas del usuario y continúa el loop."""
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        return jsonify({"error": "answers debe ser un objeto"}), 400

    with run_lock:
        state = load_run_state()
        review = state.get("designReview")
        if not review or review.get("answered"):
            return jsonify({"error": "No hay revisión activa"}), 404

        # Guardar respuestas
        review["answered"] = True
        review["finalAnswers"] = answers
        review["answeredAt"] = datetime.now(timezone.utc).isoformat()
        review["auto"] = False
        state["designReview"] = review
        state["status"] = "in-design"
        state["currentAgent"] = "project-manager"
        state["summary"] = "Revisión de diseño completada por el usuario. Continuando..."
        save_run_state(state)

    # Notificar al runner que ya hay respuestas
    global _active_run_thread
    runner = _active_run_thread
    if runner and hasattr(runner, "_design_review_event"):
        runner._design_review_answers["answers"] = answers
        runner._design_review_event.set()

    return jsonify({"ok": True, "review": review})


@app.route("/api/tickets", methods=["POST"])
def api_create_ticket():
    data = request.get_json(silent=True) or {}
    now = datetime.now(timezone.utc).isoformat()
    ticket = {
        "id": data.get("id") or f"TKT-{uuid.uuid4().hex[:6].upper()}",
        "title": data.get("title", "Nuevo ticket").strip(),
        "description": data.get("description", "").strip(),
        "status": data.get("status", "backlog"),
        "repoPath": data.get("repoPath", "").strip(),
        "branch": data.get("branch", "").strip(),
        "assigneeRole": data.get("assigneeRole", "").strip(),
        "featureFocus": data.get("featureFocus", "").strip(),
        "storyId": data.get("storyId", "").strip(),
        "taskId": data.get("taskId", "").strip(),
        "labels": data.get("labels", []),
        "blocked": bool(data.get("blocked", False)),
        "createdAt": data.get("createdAt") or now,
        "updatedAt": now,
    }
    with board_lock:
        board = load_board()
        board["tickets"].append(ticket)
        recompute_stats(board)
        save_board(board)
        socketio.emit("board_update", board)

    if ticket["status"] == "ready-for-work":
        err_code, err_msg = validate_git_repo(ticket.get("repoPath"))
        if err_code:
            with board_lock:
                board = load_board()
                board["tickets"] = [t for t in board["tickets"] if t["id"] != ticket["id"]]
                save_board(board)
            return jsonify({"error": err_code, "message": err_msg}), 400

        branch, err_code, err_msg = create_git_branch(
            ticket["repoPath"], ticket["id"], ticket["title"]
        )
        if err_code:
            with board_lock:
                board = load_board()
                board["tickets"] = [t for t in board["tickets"] if t["id"] != ticket["id"]]
                save_board(board)
            return jsonify({"error": err_code, "message": err_msg}), 400

        ticket["branch"] = branch
        ticket["repoPath"] = resolve_repo_path(ticket["repoPath"])
        with board_lock:
            board = load_board()
            for t in board["tickets"]:
                if t["id"] == ticket["id"]:
                    t["branch"] = branch
                    t["repoPath"] = ticket["repoPath"]
            save_board(board)
            socketio.emit("board_update", board)

        start_automatic_run(ticket)

    return jsonify(ticket), 201


@app.route("/api/tickets/<ticket_id>", methods=["PATCH", "PUT"])
def api_update_ticket(ticket_id):
    data = request.get_json(silent=True) or {}
    with board_lock:
        board = load_board()
        ticket = next((t for t in board["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404

        old_status = ticket.get("status")

        allowed = {
            "title",
            "description",
            "status",
            "repoPath",
            "branch",
            "assigneeRole",
            "featureFocus",
            "storyId",
            "taskId",
            "labels",
            "blocked",
        }
        for key, value in data.items():
            if key in allowed:
                ticket[key] = value
        if "repoPath" in data:
            ticket["repoPath"] = resolve_repo_path(ticket["repoPath"])
        ticket["updatedAt"] = datetime.now(timezone.utc).isoformat()
        recompute_stats(board)
        save_board(board)
        socketio.emit("board_update", board)

    new_status = ticket.get("status")

    # Si se mueve el ticket activo a backlog o done manualmente, detener ejecución
    if old_status != new_status and new_status in ("backlog", "done"):
        state = load_run_state()
        if state.get("ticketId") == ticket_id:
            stop_active_run(
                f"Ticket {ticket_id} movido a {new_status}; deteniendo ejecución"
            )
            # Si fue movido a done manualmente, continuar con el siguiente ticket
            if new_status == "done":
                process_next_in_queue()

    if old_status != new_status and new_status == "ready-for-work":
        # Reiniciar métricas de ejecución para que el ticket comience de 0
        with board_lock:
            board = load_board()
            for t in board["tickets"]:
                if t["id"] == ticket_id:
                    t.pop("startedAt", None)
                    t.pop("elapsedSeconds", None)
                    t.pop("totalSeconds", None)
                    t.pop("finishedAt", None)
                    t.pop("summary", None)
                    t["branch"] = ""
                    t["updatedAt"] = datetime.now(timezone.utc).isoformat()
            save_board(board)
            socketio.emit("board_update", board)

        err_code, err_msg = validate_git_repo(ticket.get("repoPath"))
        if err_code:
            ticket["status"] = old_status
            with board_lock:
                board = load_board()
                for t in board["tickets"]:
                    if t["id"] == ticket_id:
                        t["status"] = old_status
                save_board(board)
                socketio.emit("board_update", board)
            return jsonify({"error": err_code, "message": err_msg}), 400

        branch, err_code, err_msg = create_git_branch(
            ticket["repoPath"], ticket["id"], ticket["title"]
        )
        if err_code:
            ticket["status"] = old_status
            with board_lock:
                board = load_board()
                for t in board["tickets"]:
                    if t["id"] == ticket_id:
                        t["status"] = old_status
                save_board(board)
                socketio.emit("board_update", board)
            return jsonify({"error": err_code, "message": err_msg}), 400

        ticket["branch"] = branch
        ticket["repoPath"] = resolve_repo_path(ticket["repoPath"])
        with board_lock:
            board = load_board()
            for t in board["tickets"]:
                if t["id"] == ticket_id:
                    t["branch"] = branch
                    t["repoPath"] = ticket["repoPath"]
            save_board(board)
            socketio.emit("board_update", board)

        start_automatic_run(ticket)

    return jsonify(ticket)


@app.route("/api/tickets/<ticket_id>", methods=["DELETE"])
def api_delete_ticket(ticket_id):
    with board_lock:
        board = load_board()
        original_len = len(board["tickets"])
        board["tickets"] = [t for t in board["tickets"] if t["id"] != ticket_id]
        if len(board["tickets"]) == original_len:
            return jsonify({"error": "Ticket not found"}), 404
        recompute_stats(board)
        save_board(board)
        socketio.emit("board_update", board)
    return jsonify({"deleted": True})


@app.route("/api/tickets/<ticket_id>/agents/<agent_id>/restart", methods=["POST"])
def api_restart_agent(ticket_id, agent_id):
    with board_lock:
        board = load_board()
        ticket = next((t for t in board.get("tickets", []) if t.get("id") == ticket_id), None)
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404
        if ticket.get("status") == "backlog":
            return jsonify({"error": "El ticket está en backlog"}), 409

    runner = _active_run_thread
    if runner and runner.is_alive() and runner.ticket_id == ticket_id:
        ok = runner._restart_agent(agent_id)
        if not ok:
            return jsonify({"error": "Agent not found"}), 404
        return jsonify({"ok": True, "agentId": agent_id})

    # No hay runner activo: reanudar el loop si el agente es un coordinador de fase.
    if agent_id in ("orchestrator", "engineer-squad", "project-manager"):
        ok, msg = resume_run(ticket)
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "agentId": agent_id, "resumed": True, "message": "Run reanudado desde el estado anterior."})

    # Reinicio puntual de un engineer sin runner activo.
    if agent_id.startswith("engineer-"):
        temp_runner = AgentRunner(ticket, resume=True)
        ok = temp_runner._restart_agent(agent_id)
        if not ok:
            return jsonify({"error": "Agent not found"}), 404
        return jsonify({"ok": True, "agentId": agent_id})

    return jsonify({"error": "No hay runner activo para reiniciar este agente"}), 409


@app.route("/api/open-path", methods=["POST"])
def api_open_path():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    open_folder = bool(data.get("folder", False))
    if not path:
        return jsonify({"error": "Path required"}), 400
    target = os.path.dirname(path) if open_folder else path
    if not os.path.exists(target):
        return jsonify({"error": "La ruta no existe"}), 404
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
        elif sys.platform == "win32":
            os.startfile(target)
        else:
            subprocess.run(["xdg-open", target], check=False)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/read-file", methods=["POST"])
def api_read_file():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    if not path:
        return jsonify({"error": "Path required"}), 400
    if not os.path.isfile(path):
        return jsonify({"error": "El archivo no existe"}), 404
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        max_len = 100_000
        if len(content) > max_len:
            content = content[:max_len] + "\n\n[Contenido truncado; abre el archivo para verlo completo]"
        return jsonify({"path": path, "content": content})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@socketio.on("connect")
def handle_connect():
    board = load_board()
    recompute_stats(board)
    save_board(board)
    emit("board_update", board)
    emit("run_state_update", load_run_state())


@socketio.on("request_update")
def handle_request_update():
    notify_board_update()
    emit("run_state_update", load_run_state())


@socketio.on("chat_send")
def handle_chat_send(data):
    """Recibe un mensaje del operador humano dirigido a un agente.

    El mensaje se guarda en el log de comunicación y, si hay un runner activo,
    se pide una respuesta al agente seleccionado usando el backend de IA.
    """
    recipient = (data or {}).get("to", "orchestrator")
    text = ((data or {}).get("message") or "").strip()
    if not text:
        return

    with run_lock:
        state = load_run_state()
        bus.send_message(state, "user", recipient, "chat", {"text": text})
        save_run_state(state)
    emit_communication_update(state)

    runner = _active_run_thread
    if runner and runner.is_alive():
        def respond():
            try:
                answer = runner.chat_with_agent(recipient, text)
                with run_lock:
                    state = load_run_state()
                    bus.send_message(state, recipient, "user", "chat", {"text": answer})
                    save_run_state(state)
                emit_communication_update(state)
            except Exception as exc:
                append_log(f"Error en chat con {recipient}: {exc}", "error")

        threading.Thread(target=respond, daemon=True).start()
    else:
        with run_lock:
            state = load_run_state()
            bus.send_message(
                state,
                "system",
                "user",
                "chat",
                {"text": "No hay un run activo. Inicia un ticket para chatear con los agentes."},
            )
            save_run_state(state)
        emit_communication_update(state)


def main():
    parser = argparse.ArgumentParser(description="AgentFlow Dashboard Server")
    parser.add_argument("--port", type=int, default=5050, help="Puerto del servidor")
    parser.add_argument("--board", type=str, default=None, help="Ruta a board.json")
    parser.add_argument("--no-browser", action="store_true", help="No abrir navegador")
    args = parser.parse_args()

    if args.board:
        set_board_path(args.board)
        # Derivar run-state y log del mismo directorio
        board_path = Path(args.board)
        global RUN_STATE_FILE, LOG_FILE
        RUN_STATE_FILE = board_path.parent / "run-state.json"
        LOG_FILE = board_path.parent / "run.log"

    # Asegurar que board.json exista y tenga la estructura nueva
    board = load_board()
    board = ensure_default_columns(board)
    recompute_stats(board)
    save_board(board)

    # Inicializar run-state y preservar runs interrumpidos como snapshots
    state = load_run_state()
    if state.get("active"):
        ticket_id = state.get("ticketId")
        if state.get("status") in ("completed", "failed"):
            state["active"] = False
            if ticket_id:
                delete_ticket_snapshot(ticket_id)
        elif ticket_id:
            # Guardar snapshot para poder reanudar tras reinicio
            save_ticket_snapshot(ticket_id, state)
            append_log(
                f"Run {ticket_id} interrumpido por reinicio del servidor. "
                "Snapshot guardado; puedes reanudarlo desde el dashboard.",
                "warning",
            )
            reset_run_state_to_idle()
            state = load_run_state()
        else:
            state["active"] = False
    save_run_state(state)

    # Reprogramar timers de preguntas pendientes
    schedule_pending_question_timers()

    # Procesar cola pendiente al arrancar
    if not state.get("active") and state.get("queue"):
        threading.Thread(target=process_next_in_queue, daemon=True).start()

    # Auto-resume de runs interrumpidos por reinicio del servidor
    state = load_run_state()
    if not state.get("active") and state.get("status") == "failed" and state.get("ticketId") and state.get("interruptedByRestart"):
        board = load_board()
        ticket = next((t for t in board.get("tickets", []) if t.get("id") == state["ticketId"]), None)
        if ticket and ticket.get("status") not in ("backlog", "done"):
            append_log(
                f"[AUTO-RESUME] Reanudando {ticket['id']} tras reinicio del servidor.",
                "warning",
            )
            # Limpiar la bandera para no reanudar en bucle si vuelve a fallar por otro motivo
            state["interruptedByRestart"] = False
            save_run_state(state)
            start_automatic_run(ticket, resume=True)

    if not args.no_browser:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{args.port}")

        threading.Thread(target=open_browser, daemon=True).start()

    print(f"AgentFlow Dashboard corriendo en http://localhost:{args.port}")
    print(f"Board: {get_board_path()}")
    print(f"Run state: {get_run_state_path()}")
    socketio.run(app, host="0.0.0.0", port=args.port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
