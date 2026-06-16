#!/usr/bin/env python3
"""
AgentFlow Dashboard Server
Local Kanban/Jira-style web server for viewing and managing tickets,
with automatic multi-agent loop orchestration when a ticket moves to
"ready-for-work".
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

# Allow dumping stack traces for all threads with SIGUSR1 during debugging.
faulthandler.enable()
try:
    faulthandler.register(signal.SIGUSR1, all_threads=True)
except Exception:
    pass

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
    """Remove ANSI escape codes from text."""
    return _ANSI_ESCAPE.sub("", text)


# Locks for concurrent access.
# run_lock is an RLock because multiple runner methods can be nested.
run_lock = threading.RLock()
board_lock = threading.RLock()
_active_run_thread = None
paused_run_threads = {}


def get_meta_dir():
    """Return the scripts/meta-ralph directory relative to the project."""
    return Path.cwd() / "scripts" / "meta-ralph"


def get_board_path():
    """Resolve the board.json path relative to the current project."""
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
    """Path for a paused ticket run-state snapshot."""
    return get_run_state_path().parent / f"run-state.{ticket_id}.json"


def save_ticket_snapshot(ticket_id, state):
    """Save a copy of the current run-state for a ticket."""
    path = get_ticket_snapshot_path(ticket_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = dict(state)
    snapshot["snapshotTicketId"] = ticket_id
    snapshot["snapshotSavedAt"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
    except (IOError, TypeError) as exc:
        append_log(f"Could not save snapshot for {ticket_id}: {exc}", "error")


def load_ticket_snapshot(ticket_id):
    """Load a ticket run-state snapshot if one exists."""
    path = get_ticket_snapshot_path(ticket_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        append_log(f"Could not load snapshot for {ticket_id}: {exc}", "error")
        return None


def delete_ticket_snapshot(ticket_id):
    """Delete a ticket snapshot."""
    path = get_ticket_snapshot_path(ticket_id)
    if path.exists():
        path.unlink()


def list_ticket_snapshots():
    """Return ticket IDs that have a snapshot on disk."""
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
    """Migrate the board so all default columns exist."""
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

    # If backlog did not exist, insert ready-for-work at the beginning.
    if not backlog_seen and "ready-for-work" not in new_columns:
        new_columns.insert(0, "ready-for-work")

    # Ensure there are no duplicates and preserve order.
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
    """Generate a short summary of the current run state."""
    if status == "completed":
        return "Loop completed successfully."
    if status == "failed":
        return "The loop failed. Check the logs."
    if status == "idle":
        return "Waiting for a ticket in Ready for Work."
    if status == "in-design":
        if current_agent == "architect":
            return "Defining architecture and global technical patterns."
        if current_agent == "project-manager":
            return "Building the task and dependency plan."
        return "Analyzing requirements with PM Research Agents."
    if status == "in-progress":
        return "Implementing tasks with parallel Engineers."
    if status == "in-review":
        return "Reviewing quality: build and tests."
    return f"Status {status}."


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
    """Add one line to run.log and run-state."""
    ts = datetime.now(timezone.utc).isoformat()
    entry = {"timestamp": ts, "level": level, "message": message}

    # Plain log file.
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{level.upper()}] {message}\n")

    # State.
    with run_lock:
        state = load_run_state()
        state["logs"] = state.get("logs", []) + [entry]
        # Keep the latest 500 logs.
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
    """Extract and validate question JSON between DECISION_REQUIRED and END_QUESTION."""
    if not raw_text:
        return None
    text = strip_ansi(raw_text)
    start = text.rfind("DECISION_REQUIRED")
    if start == -1:
        return None
    end = text.find("END_QUESTION", start)
    if end == -1:
        return None
    json_text = text[start + len("DECISION_REQUIRED"):end].strip()
    # Must be a JSON object.
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
    """Return the answer file path for a question."""
    safe_phase = question.get("phase", "").lower().replace(' ', '-')
    return get_meta_dir() / "state" / f"answer-{question['ticketId']}-{safe_phase}.txt"


def _write_answer_file(question, answer_text):
    """Write the answer to the file the runner is waiting for."""
    try:
        answer_path = _question_answer_path(question)
        answer_path.parent.mkdir(parents=True, exist_ok=True)
        answer_path.write_text(answer_text, encoding="utf-8")
        return True
    except Exception as exc:
        append_log(f"Error writing answer file: {exc}", "error")
        return False


def _auto_answer_question(question_id):
    """Automatically answer a question if the user did not answer in time."""
    auto_answer = "Decide automatically (timeout)"
    q = answer_user_question(question_id, auto_answer)
    if q:
        _write_answer_file(q, auto_answer)
        append_log(f"Question {question_id} auto-answered after timeout.", "warning")
    _question_timers.pop(question_id, None)


def create_user_question(ticket_id, phase_name, agent_id, agent_name, question, context, options):
    """Register a pending user question and notify the frontend."""
    with run_lock:
        state = load_run_state()
        questions = state.setdefault("pendingQuestions", [])
        qid = _question_id(ticket_id, phase_name, agent_id)
        # Avoid duplicates for the same phase/agent.
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

    # Timer: if no answer arrives before expiresAt, the agent decides automatically.
    delay = max(0.0, q["expiresAt"] - datetime.now(timezone.utc).timestamp())
    timer = threading.Timer(delay, _auto_answer_question, args=[qid])
    timer.daemon = True
    timer.start()
    _question_timers[qid] = timer
    return q


def answer_user_question(question_id, answer_text):
    """Save the user answer and update state."""
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
    """Return True if a matching pending question exists."""
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
    """Reschedule timers for pending questions after a server restart."""
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
        print(f"Timer rescheduled for question {qid} ({int(delay)}s remaining)")


def _agent_log(state, agent_id, message, level="info"):
    """Add a log entry to an agent in run-state."""
    ts = datetime.now(timezone.utc).isoformat()
    for agent in state.get("agents", []):
        if agent.get("id") == agent_id:
            agent.setdefault("logs", []).append({"timestamp": ts, "level": level, "message": message})
            # Keep the latest 100 logs per agent.
            agent["logs"] = agent["logs"][-100:]
            break


def _ensure_agent(state, agent_id, name, role, parent_id=None, status="queued", progress=0):
    """Create an agent if missing and return it."""
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
    """Update agent fields and optionally add a log entry."""
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


def _reconcile_stale_qa_agents(state) -> bool:
    """Fix per-task QA agents left queued after QA lead completed."""
    agents = state.get("agents") or []
    agents_by_id = {agent.get("id"): agent for agent in agents}
    qa_lead = agents_by_id.get("qa-engineer")
    if not qa_lead or qa_lead.get("status") != "done":
        return False

    stale_qa = [
        agent for agent in agents
        if str(agent.get("id", "")).startswith("qa-")
        and agent.get("id") != "qa-engineer"
        and agent.get("status") in {"queued", "running"}
    ]
    if not stale_qa:
        return False

    verdict_by_task = {}
    for entry in reversed((state.get("communication") or {}).get("log", [])):
        if entry.get("type") != "message":
            continue
        payload = entry.get("payload") or {}
        cause = payload.get("causeBy") or ""
        if cause not in {"review_approved", "reject_with_feedback"}:
            continue
        metadata = payload.get("metadata") or {}
        task_id = metadata.get("task_id") or payload.get("taskId")
        if not task_id:
            from_id = entry.get("from") or ""
            if from_id.startswith("qa-"):
                task_id = from_id[3:]
        if task_id:
            verdict_by_task[task_id] = cause

    changed = False
    for agent in stale_qa:
        agent_id = agent.get("id")
        task_id = agent_id[3:] if agent_id and agent_id.startswith("qa-") else ""
        verdict = verdict_by_task.get(task_id)
        if verdict == "review_approved":
            _update_agent(
                state,
                agent_id,
                status="done",
                progress=100,
                log=f"Task {task_id} approved (reconciled).",
            )
            changed = True
        elif verdict == "reject_with_feedback":
            _update_agent(
                state,
                agent_id,
                status="failed",
                progress=100,
                log=f"Task {task_id} rejected (reconciled).",
            )
            changed = True
    return changed


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
    """Update ticket runtime fields without changing status."""
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
    """Instruction appended to prompts so agents can request user decisions."""
    return (
        "\n\n--- DECISION INSTRUCTION ---\n"
        "IMPORTANT: in 99% of cases, make the decision yourself and keep moving. "
        "Use the format below only when you hit a REAL blocker that prevents progress "
        "without an explicit user decision, such as changing a public API, deleting data, "
        "choosing between options that affect long-term architecture, or taking on major cost/risk.\n\n"
        "If you need that decision, use EXACTLY this plain markdown format:\n\n"
        "DECISION_REQUIRED\n"
        "{\n"
        '  "agent": "your name or role",\n'
        '  "question": "Clear question for the user",\n'
        '  "options": ["A) Option A", "B) Option B"],\n'
        '  "context": "Explain why this is a blocker and what each option implies."\n'
        "}\n"
        "END_QUESTION\n\n"
        "After writing this, do nothing else; the system will pause execution and send you the user's answer. "
        "If the user does not answer within 2 minutes or chooses automatic decision, decide on your own."
    )


def slugify_title(title, max_length=40):
    """Generate a safe branch-name slug from a title."""
    if not title:
        return "untitled"
    text = title.lower()
    replacements = {
        "\u00e1": "a", "\u00e9": "e", "\u00ed": "i", "\u00f3": "o", "\u00fa": "u",
        "\u00fc": "u", "\u00f1": "n", "\u00e7": "c",
        "\u00e0": "a", "\u00e8": "e", "\u00ec": "i", "\u00f2": "o", "\u00f9": "u",
        "\u00e2": "a", "\u00ea": "e", "\u00ee": "i", "\u00f4": "o", "\u00fb": "u",
        "\u00e4": "a", "\u00eb": "e", "\u00ef": "i", "\u00f6": "o",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    if not text:
        return "untitled"
    return text[:max_length].rstrip("-")


def resolve_repo_path(repo_path):
    """Return the absolute repository path.

    If it is relative, first try it against cwd; if it does not exist, try the
    parent directory. This helps when the dashboard runs inside a subproject and
    the repo is at the same level or in the parent.
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
    # If none exists, return the first candidate so the error message is stable.
    return str((Path.cwd() / repo).resolve())


def validate_git_repo(repo_path):
    """Validate that repo_path is an existing folder.

    Git is optional: if the folder has .git, a branch will be created, but git
    is not required for a ticket to run.
    """
    if not repo_path:
        return "REPO_MISSING", "The ticket does not have a repository configured."
    repo = Path(resolve_repo_path(repo_path))
    if not repo.exists() or not repo.is_dir():
        return (
            "REPO_NOT_FOUND",
            f"Folder '{repo_path}' does not exist.",
        )
    return None, None


def create_git_branch(repo_path, ticket_id, title):
    """Create or switch to feature/<ticketId>-<slug> when the folder is a Git repo.

    If the folder has no .git directory, no branch is created and branch_name="" is returned.
    Returns (branch_name, error_code, error_message).
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
        return None, "BRANCH_CREATE_FAILED", f"Could not create branch: {err}"


class AgentRunner(threading.Thread):
    """Thread that runs the multi-agent loop for one ticket."""

    def __init__(self, ticket, resume=False):
        super().__init__(daemon=True)
        self.ticket = ticket
        self.ticket_id = ticket["id"]
        self.resume = bool(resume)
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
        self.log(f"Available backends: {available}", "info")
        self.orchestrator = Orchestrator(
            ticket,
            resume=resume,
            callbacks=self._orchestrator_callbacks(),
            backend_registry=self.backend_registry,
            skills_registry=self.skills_registry,
        )

    def stop(self):
        """Request an orderly runner stop."""
        self._stop_event.set()
        self._pause_event.clear()
        self._resume_event.set()
        if hasattr(self, "orchestrator") and self.orchestrator:
            self.orchestrator.stop()
        self._stop_runtime_heartbeat()

    def pause(self):
        """Pause the runner at the next checkpoint."""
        self._resume_event.clear()
        self._pause_event.set()
        if hasattr(self, "orchestrator") and self.orchestrator:
            self.orchestrator.pause()
        update_run_state({"active": False, "status": "paused"})
        self.log(f"Ticket {self.ticket_id} paused.", "warning")

    def resume(self):
        """Resume a paused runner."""
        self._pause_event.clear()
        self._resume_event.set()
        if hasattr(self, "orchestrator") and self.orchestrator:
            self.orchestrator.resume()

    def _should_stop(self):
        """Return True if a stop was requested."""
        return self._stop_event.is_set()

    def _is_paused(self):
        """Return True if the runner is paused."""
        return self._pause_event.is_set()

    def _check_pause(self):
        """If paused, block until resume or stop."""
        if not self._is_paused():
            return
        self.log(f"Ticket {self.ticket_id} is paused. Waiting for resume...")
        while self._is_paused() and not self._should_stop():
            self._resume_event.wait(timeout=1.0)
            self._resume_event.clear()
        if not self._should_stop():
            self.log(f"Ticket {self.ticket_id} resumed.")

    def _should_stop_or_pause(self):
        """Return True if stop was requested; if paused, wait first."""
        self._check_pause()
        return self._should_stop()

    def log(self, msg, level="info"):
        append_log(f"[{self.ticket_id}] {msg}", level)

    def _runtime_heartbeat(self):
        """Update elapsed runtime and ticket summary every second."""
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
                # Do not interrupt the run because of heartbeat errors.
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

    def _publish_internal_message(self, msg):
        """Mirror core Environment messages into the visible communication bus."""
        if not msg or getattr(msg, "sent_from", None) == "system":
            return
        recipients = sorted(getattr(msg, "send_to", set()) or {"all"})
        if not recipients:
            recipients = ["all"]
        # Log once even when the original message has multiple recipients; this
        # keeps the Agent Internal Communication panel readable.
        to_label = ", ".join(recipients)
        payload = {
            "text": self._summarize_internal_message(msg),
            "causeBy": getattr(msg, "cause_by", "message"),
            "metadata": self._safe_message_metadata(getattr(msg, "metadata", {}) or {}),
        }
        message_type = self._message_type_for_bus(getattr(msg, "cause_by", "message"))
        with run_lock:
            state = load_run_state()
            bus.send_message(
                state,
                getattr(msg, "sent_from", "unknown"),
                to_label,
                message_type,
                payload,
                add_pending=False,
            )
            save_run_state(state)
            emit_communication_update(state)

    def _message_type_for_bus(self, cause_by):
        return {
            "research": "research_finding",
            "request_clarification": "request_clarification",
            "clarifications_requested": "request_clarification",
            "prd_ready": "notify_completion",
            "task_assigned": "task_assignment",
            "squad_instruction": "squad_instruction",
            "task_completed": "notify_completion",
            "task_failed": "task_failed",
            "task_report": "task_report",
            "squad_chat": "chat",
            "pm_chat": "chat",
            "request_info_from_pm": "request_clarification",
            "request_info_from_pm_response": "notify_completion",
            "escalate_to_user": "request_clarification",
            "batch_completed": "notify_completion",
            "request_review": "request_review",
            "review_approved": "notify_completion",
            "reject_with_feedback": "reject_with_feedback",
            "qa_batch_reviewed": "notify_completion",
        }.get(cause_by, cause_by or "message")

    def _summarize_internal_message(self, msg):
        content = (getattr(msg, "content", "") or "").strip()
        metadata = getattr(msg, "metadata", {}) or {}
        cause_by = getattr(msg, "cause_by", "")
        if cause_by == "research":
            label = metadata.get("sub_id") or getattr(msg, "sent_from", "PM research")
            return f"{label} shared research findings: {content[:700]}"
        if cause_by == "task_report":
            return (
                f"{metadata.get('engineer_id', msg.sent_from)} reported task "
                f"{metadata.get('task_id', 'unknown')} as {metadata.get('status', 'unknown')}: "
                f"{metadata.get('summary', content)[:500]}"
            )
        if cause_by in {"review_approved", "reject_with_feedback"}:
            verdict = "approved" if metadata.get("approved") else "rejected"
            return f"QA {verdict} task {metadata.get('task_id', 'unknown')}: {metadata.get('reason', content)[:500]}"
        if cause_by == "prd_ready":
            return f"PM Lead consolidated the PRD: {metadata.get('preview', content)[:500]}"
        return content[:800] if content else cause_by.replace("_", " ").title()

    def _safe_message_metadata(self, metadata):
        safe = {}
        for key, value in metadata.items():
            if callable(value):
                continue
            try:
                json.dumps(value, default=str)
                safe[key] = value
            except Exception:
                safe[key] = str(value)
        return safe

    def _add_agent_message(self, sender_id, recipient_id, question):
        """Register a question from one agent to another and expose it in run-state."""
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
        self.log(f"{sender_id} asked {recipient_id}: {question[:100]}...")
        return message

    def _answer_agent_message(self, message_id, answer):
        """Mark a question as answered."""
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
            self.log(f"{answered_msg['to']} answered {answered_msg['from']}: {answer[:100]}...")
        return answered_msg

    def _consult_agent(self, sender_id, recipient_id, question, timeout_seconds=30, task_context=None):
        """Ask another agent and wait for a response from the configured backend.

        If the consulted agent lacks context, escalate to the orchestrator.
        If the orchestrator cannot answer either, generate an automatic answer
        from the available project context as a last resort.
        """
        msg = self._add_agent_message(sender_id, recipient_id, question)

        # Resolve names for the prompt.
        with run_lock:
            state = load_run_state()
            agents_by_id = {a["id"]: a for a in state.get("agents", [])}
        sender_name = agents_by_id.get(sender_id, {}).get("name", sender_id)
        recipient_name = agents_by_id.get(recipient_id, {}).get("name", recipient_id)

        context_text = self._build_consultation_context(task_context)

        prompt = f"""Activate the 'dotnet' skill and apply its conventions and best practices to all .NET code you generate.

You are agent {recipient_name} ({recipient_id}). Your teammate {sender_name} ({sender_id}) asks:

"{question}"

PROJECT CONTEXT:
{context_text}

Respond concisely and technically. If you truly do not have enough information, respond EXACTLY with: INSUFFICIENT_CONTEXT"""

        output = self._run_ai_prompt(
            prompt,
            phase_name=f"Consult {recipient_id}",
            timeout_seconds=timeout_seconds,
            agent_id=recipient_id,
        )
        answer = (output or "").strip() or "INSUFFICIENT_CONTEXT"

        # Escalation 1: if the agent lacks context, consult the orchestrator.
        if "INSUFFICIENT_CONTEXT" in answer:
            self.log(f"{recipient_id} lacked context; escalating to orchestrator...", "warning")
            answer = self._consult_orchestrator(question, context_text)

        self._answer_agent_message(msg["id"], answer)
        return answer

    def _build_consultation_context(self, task_context=None):
        """Build enriched context for inter-agent consultation."""
        parts = []
        title = self.ticket.get("title", "")
        description = self.ticket.get("description", "")
        parts.append(f"Ticket: {title}\nDescription: {description}")

        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
        if prd_path.exists():
            try:
                prd_text = prd_path.read_text(encoding="utf-8")[:2000]
                parts.append(f"PRD (summary):\n{prd_text}\n---")
            except Exception as exc:
                parts.append(f"Could not read PRD: {exc}")

        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
        if tasks_path.exists():
            try:
                tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
                if tasks and isinstance(tasks, list):
                    summary = "\n".join(
                        f"- {t.get('id')}: {t.get('title')} (dependencies: {t.get('dependencies', [])}, complexity: {t.get('complexity', '-')})"
                        for t in tasks
                    )
                    parts.append(f"Planned tasks:\n{summary}\n---")
            except Exception as exc:
                parts.append(f"Could not read tasks: {exc}")

        if task_context:
            parts.append(f"Current task context:\n{task_context}")

        return "\n\n".join(parts)

    def _get_dependency_context(self, deps):
        """Collect context from completed dependency tasks."""
        if not deps:
            return ""
        lines = ["Previous task context (dependencies):"]
        with run_lock:
            state = load_run_state()
            for dep_id in deps:
                dep_agent_id = f"engineer-{dep_id}"
                agent = next((a for a in state.get("agents", []) if a.get("id") == dep_agent_id), None)
                if not agent:
                    lines.append(f"- {dep_id}: no agent information yet.")
                    continue
                logs = agent.get("logs", []) or []
                last_logs = "\n  ".join(
                    f"[{log.get('level', 'info')}] {log.get('message', '')}"
                    for log in logs[-5:]
                )
                outputs = agent.get("outputs", []) or []
                outputs_summary = "\n  ".join(f"- {os.path.basename(p)}" for p in outputs[-8:]) or "No outputs recorded"
                lines.append(
                    f"- {dep_id} ({agent.get('status')}):\n"
                    f"  Latest logs:\n  {last_logs}\n"
                    f"  Generated/modified files:\n  {outputs_summary}"
                )
        return "\n\n".join(lines)

    def _consult_orchestrator(self, question, context_text):
        """Consult the orchestrator when another agent lacks context."""
        prompt = f"""Activate the 'dotnet' skill and apply its conventions and best practices to all .NET code you generate.

You are the project Lead Orchestrator. A team agent asked a question and did not have enough context. You have access to the PRD, tasks, and ticket. Respond concisely and technically.

AGENT QUESTION:
"{question}"

PROJECT CONTEXT:
{context_text}

If you truly do not have enough information, respond EXACTLY with: INSUFFICIENT_CONTEXT"""

        output = self._run_ai_prompt(
            prompt,
            phase_name="Consult Orchestrator",
            timeout_seconds=60,
            agent_id="orchestrator",
        )
        answer = (output or "").strip()
        if answer and "INSUFFICIENT_CONTEXT" not in answer:
            return answer

        # Escalation 2: generate an automatic AI answer as a last resort.
        self.log("Orchestrator also lacked context; generating an automatic answer...", "warning")
        return self._auto_generate_answer(question, context_text)

    def _auto_generate_answer(self, question, context_text):
        """Generate an automatic answer when no team member has context."""
        prompt = f"""Activate the 'dotnet' skill and apply its conventions and best practices to all .NET code you generate.

You are an expert in .NET and software architecture. A team agent asked a question and nobody, including the orchestrator, had enough context. Assume the best possible answer from the available context and best practices.

AGENT QUESTION:
"{question}"

PROJECT CONTEXT:
{context_text}

Respond concisely and practically. Assume reasonable decisions for a .NET MVP with Clean Architecture, MediatR, EF Core, and cshtml views. Do NOT say that you lack context; provide a useful answer that lets implementation continue."""

        output = self._run_ai_prompt(
            prompt,
            phase_name="Automatic AI Answer",
            timeout_seconds=60,
            agent_id="orchestrator",
        )
        return (output or "").strip() or "Assume standard implementation according to the PRD and continue with .NET conventions."

    def _is_context_lacking(self, answer):
        """Detect whether an answer indicates missing context."""
        if not answer:
            return True
        phrases = [
            "INSUFFICIENT_CONTEXT",
            "not enough context",
            "insufficient context",
            "I cannot answer",
            "I don't know",
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
        """Load a task definition from the task plan."""
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
            f"Requesting task: {task_id} - {task_title}\n"
            f"Description: {task_desc}\n"
            f"Dependencies: {task_deps}"
        )
        answer = self._consult_agent(
            requester_id,
            helper_id,
            f"I need help with task {task_id}: {question}",
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
            f"Topic/task: {task_title}\n"
            f"Description: {task_desc}"
        )
        answer = self._consult_agent(
            sender_id,
            recipient_id,
            f"Clarification question about {topic}: {question}",
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
        # Sync the ticket column with the current phase.
        if status in ("in-design", "in-progress", "in-review"):
            update_ticket_status(self.ticket_id, status)

        # Update ticket execution metrics.
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
        """Callbacks used by the real Orchestrator to integrate with the dashboard."""
        return {
            "run_ai": self._run_ai_prompt,
            "log": self.log,
            "set_phase": self.set_phase,
            "ensure_agent": self._ensure_agent,
            "update_agent": self._update_agent,
            "request_design_review": self._wait_for_design_answers,
            "request_clarification": self._wait_for_user_clarification,
            "collect_outputs": self._collect_agent_outputs,
            "get_dependency_context": self._get_dependency_context,
            "publish_message": self._publish_internal_message,
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
                "name": "Main Orchestrator",
                "role": "orchestrator",
                "description": "Coordinates the 5 phases of the software factory loop",
                "capabilities": ["orchestration", "coordination"],
                "tools": ["dispatch", "monitor"],
            })
            _agent_log(state, "orchestrator", "Ticket moved to Ready for work. Starting software factory loop...")
            save_run_state(state)
            emit_communication_update(state)

        now = datetime.now(timezone.utc)
        update_ticket_status(self.ticket_id, "in-design")
        update_ticket_runtime(
            self.ticket_id,
            startedAt=now.isoformat(),
            elapsedSeconds=0,
            summary="Starting software factory loop...",
        )
        self._start_runtime_heartbeat()

    def _on_orchestrator_complete(self, success):
        self._stop_runtime_heartbeat()
        if success:
            update_ticket_status(self.ticket_id, "done")
            self._update_agent("orchestrator", status="done", progress=100, log="Loop completed. Ticket marked as Done.", log_level="success")
            update_run_state({"active": False, "ticketId": self.ticket_id, "status": "completed", "progress": 100, "currentAgent": None})
            self.log("Loop completed. Ticket marked as Done.", "success")
        else:
            self._update_agent("orchestrator", status="failed", log="The loop failed. Check the logs.", log_level="error")
            update_run_state({"active": False, "ticketId": self.ticket_id, "status": "failed", "progress": 0, "currentAgent": None})
        # Mark the run inactive if this runner is still the active one.
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
            self.log(f"Loop error: {exc}", "error")
            self._update_agent("orchestrator", status="failed", log=f"Loop error: {exc}", log_level="error")
            update_run_state({"active": False, "ticketId": self.ticket_id, "status": "failed", "progress": 0, "currentAgent": None})
            self._stop_runtime_heartbeat()
            paused_run_threads.pop(self.ticket_id, None)
            delete_ticket_snapshot(self.ticket_id)

    def _run_planner_and_execution(self):
        """Run Planning, Execution, and QA phases during resume."""
        self._check_pause()
        self._agent_log("orchestrator", "Phase 3/5: Planning & Dispatch: building batches and dependency DAG.")
        self.set_phase("project-manager", "in-design", 60)
        self.run_planner()
        if self._should_stop_or_pause():
            self.log("Run stopped by user request after Planning.", "warning")
            return

        self._agent_log("orchestrator", "Phase 4/5: Parallel Execution: implementing tasks in isolated worktrees.")
        update_ticket_status(self.ticket_id, "in-progress")
        self.set_phase("engineer-squad", "in-progress", 75)
        self.run_execution()
        if self._should_stop_or_pause():
            self.log("Run stopped by user request after Execution.", "warning")
            return

        self._agent_log("orchestrator", "Phase 5/5: QA Review: reviewing batch integration.")
        self.set_phase("qa-engineer", "in-review", 90)
        self.run_qa()
        if self._should_stop_or_pause():
            self.log("Run stopped by user request after QA.", "warning")
            return

        update_ticket_status(self.ticket_id, "done")
        self._update_agent("orchestrator", status="done", progress=100, log="Loop completed. Ticket marked as Done.", log_level="success")
        update_run_state({"active": False, "ticketId": self.ticket_id, "status": "completed", "progress": 100, "currentAgent": None})
        self.log("Loop completed. Ticket marked as Done.", "success")

    def _resume_loop(self):
        """Resume the loop from the phase saved in run-state."""
        state = load_run_state()
        review = state.get("designReview") or {}

        if not review.get("answered"):
            self._agent_log("orchestrator", "Resuming from Architecture/Design Review.")
            self.set_phase("architect", "in-design", 40)
            self.run_architect()
            if self._should_stop_or_pause():
                return
            prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
            questions = self._generate_design_questions(prd_path)
            answers = self._wait_for_design_answers(questions, timeout_seconds=60)
            if self._should_stop_or_pause():
                return
            self.log(f"Design review answers: {answers}")
            self._run_planner_and_execution()
            return

        self._agent_log("orchestrator", "Resuming from Planning/Execution.")
        self._run_planner_and_execution()

    def run_pm_analysis(self):
        """Run PM analysis using multiple research agents.

        Subagents send reports to the PM Lead through the communication bus.
        The PM Lead consolidates findings into a PRD and can request
        clarification from subagents when gaps are detected.
        """
        self.set_phase("pm-research-agents", "in-design", 15)

        subagents = [
            ("pm-domain", "Domain Analyst", "business domain, entities, rules, and main flows"),
            ("pm-ux", "UX Researcher", "user experience, views, screen flows, and frontend validation"),
            ("pm-technical", "Technical Analyst", "technical stack, architecture, patterns, and technical decisions"),
            ("pm-integration", "Integration Analyst", "third-party APIs, databases, and external services"),
            ("pm-risk", "Risk Analyst", "risks, security, compliance, permissions, and error handling"),
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
                "description": "Parallel PM research group",
                "capabilities": ["research", "consolidation"],
                "tools": ["ai_prompt"],
            })
            for sub_id, sub_name, focus in subagents:
                bus.register_participant(state, {
                    "id": sub_id,
                    "name": sub_name,
                    "role": "sub",
                    "description": f"Researches {focus}",
                    "capabilities": ["research", "analysis"],
                    "tools": ["ai_prompt", "web_search"],
                })
            save_run_state(state)
            emit_communication_update(state)

        title = self.ticket.get("title", "")
        description = self.ticket.get("description", "")
        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"

        # If a pre-generated PRD exists, skip analysis and use it directly.
        if prd_path.exists() and prd_path.stat().st_size > 100:
            self.log(f"Pre-generated PRD found at {prd_path}; skipping PM Research.")
            for sub_id, sub_name, _ in subagents:
                self._update_agent(sub_id, status="done", progress=100,
                                   log=f"{sub_name} completed (pre-generated PRD).")
            self._update_agent("pm-research-agents", status="done", progress=100,
                               log="Pre-generated PRD reused.")
            self.set_phase("pm-lead", "in-design", 35)
            return

        self._update_agent("pm-research-agents", status="running", progress=10,
                           log="Launching PM Research Agents with MetaGPT roles...")

        def log_callback(message, level="info"):
            self.log(message, level)

        # Run Phase 1 with the roles/actions engine.
        # Subagents run in parallel inside the Environment.
        generated_prd = pm_analysis.run_pm_analysis(
            self.ticket,
            run_ai=lambda prompt, phase_name, timeout_seconds, agent_id=None: self._run_ai_prompt(
                prompt,
                phase_name=phase_name,
                timeout_seconds=timeout_seconds,
                agent_id=agent_id,
            ),
            max_rounds=10,
            log_callback=log_callback,
        )

        if generated_prd and generated_prd.exists():
            self.log(f"Detailed plan saved at {generated_prd}")
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
            self.log("No PRD was generated; using local fallback.", "warning")
            self._write_fallback_prd(prd_path, title, description)

        for sub_id, sub_name, _ in subagents:
            self._update_agent(sub_id, status="done", progress=100,
                               log=f"{sub_name} completed.")
        self._update_agent("pm-research-agents", status="done", progress=100,
                           log="PM Research Agents consolidated the PRD.")
        self.set_phase("pm-lead", "in-design", 35)

    def _parse_clarifications(self, output):
        """Find clarification requests in consolidator output."""
        clarifications = {}
        marker = "PENDING CLARIFICATIONS:"
        idx = output.find(marker)
        if idx == -1:
            return clarifications
        block = output[idx + len(marker):]
        # Stop at the next markdown heading or the end of the block.
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
                "\n\nTHE PM LEAD ASKED YOU TO EXPAND YOUR ANALYSIS WITH THIS QUESTION/CLARIFICATION:\n"
                f"{follow_up}\n\n"
                "Answer the PM Lead request directly while keeping the same output format."
            )
        return (
            f"You are the {role_name} for AgentFlow, a MetaGPT-style multi-agent software factory. "
            f"Your exclusive focus is: {focus}. "
            "Research the current project codebase ONLY from your assigned angle. "
            "Do NOT implement code; only research, analyze, and document findings. "
            "Be concise but complete; prioritize quality over length.\n\n"
            "Your output must be markdown with these sections:\n"
            "1. Key findings (maximum 10 bullets).\n"
            "2. Functional and non-functional requirements relevant to your area.\n"
            "3. Risks, assumptions, or open questions.\n"
            "4. Relevant codebase files or areas.\n\n"
            f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}"
            + follow_up_section
            + "\n\nRespond in English."
            + decision_request_instruction()
        )

    def _build_pm_consolidator_prompt(self, title, description, research_files, prd_path):
        research_content = ""
        for sub_id, path in research_files.items():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    # Truncate each analysis to avoid saturating the consolidator context.
                    lines = f.readlines()[:150]
                    research_content += f"\n\n--- {sub_id} ---\n\n" + "".join(lines)
            except Exception as exc:
                research_content += f"\n\n--- {sub_id} ---\n\nError reading findings: {exc}"
        return (
            "You are the Lead Product Manager for AgentFlow. Five PM Research Agents investigated a ticket. "
            "Consolidate THEIR FINDINGS into a concise, actionable Product Requirements Document (PRD). "
            "Do NOT invent requirements that are not supported by the findings; synthesize what was researched.\n\n"
            f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}\n\n"
            "AGENT FINDINGS:\n" + research_content + "\n\n"
            "Generate a markdown PRD with these sections (concise, maximum 2 paragraphs per section):\n"
            "1. Executive summary\n"
            "2. Main functional requirements (numbered, with High/Medium/Low priority)\n"
            "3. Key non-functional requirements\n"
            "4. User stories and acceptance criteria\n"
            "5. Suggested technical tasks with dependencies and estimates (S/M/L)\n"
            "6. Risks, assumptions, and open questions\n\n"
            f"Write the complete markdown PRD to this file: {prd_path}\n\n"
            "Respond in English. At the end, briefly confirm that you saved the PRD."
            + decision_request_instruction()
        )

    def _extract_prd_from_output(self, output, title, description):
        """Extract PRD content from raw backend output."""
        lines = output.splitlines()
        prd_lines = []
        capture = False
        for line in lines:
            stripped = line.strip()
            # Start capture when a PRD or markdown heading appears.
            if stripped.startswith("# PRD") or stripped.startswith("# 1.") or stripped.startswith("## 1."):
                capture = True
            if capture:
                prd_lines.append(line)
        if prd_lines:
            return "\n".join(prd_lines)
        # Fallback: if there are no clear markers, return everything except UI lines.
        filtered = []
        for line in lines:
            if any(skip in line for skip in ["context:", "MCP server", "thinking...", "working..."]):
                continue
            filtered.append(line)
        return f"# Detailed PRD: {title}\n\n**Original description:**\n\n{description}\n\n---\n\n" + "\n".join(filtered[-200:])

    def _build_pm_prompt(self, title, description, prd_path):
        return (
            "You are the Lead Product Manager for Meta-Ralph, a MetaGPT-style multi-agent software factory. "
            "A ticket just moved to In Design and you must produce a detailed Product Requirements Document (PRD).\n\n"
            "Act as if you coordinated 5 PM Research Agents (Domain/UX, Technical, Integrations, Risks, Task Breakdown) "
            "and consolidated their findings into one PRD.\n\n"
            "The PRD must include:\n"
            "1. Executive summary\n"
            "2. Problem or opportunity statement\n"
            "3. User personas\n"
            "4. Functional requirements (numbered, with priority)\n"
            "5. Non-functional requirements\n"
            "6. User stories and acceptance criteria\n"
            "7. Open questions, assumptions, and risks\n"
            "8. Suggested technical tasks with dependencies and effort estimates (S/M/L)\n"
            "9. Affected codebase areas or files\n"
            "10. Notes from each PM Research Agent\n\n"
            "Also write the complete markdown PRD to this file: {prd_path}\n\n"
            "TICKET:\n"
            f"TITLE: {title}\n\n"
            f"DESCRIPTION: {description}\n\n"
            "Respond in English. At the end, briefly confirm that you saved the PRD."
        ).format(prd_path=prd_path)

    def _write_fallback_prd(self, prd_path, title, description):
        """Generate a detailed local fallback PRD simulating multiple PM Research Agents."""
        desc_lower = (description or "").lower()
        title_lower = (title or "").lower()
        is_whatsapp = "whatsapp" in desc_lower or "whatsapp" in title_lower
        is_messaging = is_whatsapp or "sms" in desc_lower or "messaging" in desc_lower

        if is_whatsapp:
            domain_reqs = [
                "CRUD for WhatsApp message templates with states such as draft, sent, approved, and rejected.",
                "User interface similar to the SMS module, including view structure and filters.",
                "WhatsApp provider integration through an abstract interface.",
                "Assignment of people lists with dynamic metadata values.",
                "Credential configuration through App Settings using the IOptions pattern.",
                "Send history, delivery states, and retries.",
                "Support for multiple providers without changing the business interface.",
            ]
            affected = [
                "`EC.Ent` / `EntidadesFacturacionFD`: Template, Send, and ContactMetadata entities.",
                "`EC.Buss`: sending services and `IWhatsappSender` interface.",
                "`EC.Web` / `AppWeb.Scord.NetCore`: views and controllers/API.",
                "`EC.Data`: repositories and migrations.",
            ]
            tasks = [
                ("Create Template, Send, and ContactMetadata entities", "-", "M"),
                ("Define `IWhatsappSender` interface and DTOs", "1", "S"),
                ("Implement provider adapter such as Teleprom or another provider", "2", "L"),
                ("Create SMS-style template UI", "1", "L"),
                ("Create send execution view", "3, 4", "M"),
                ("Configure IOptions for credentials", "3", "S"),
                ("Unit and integration tests", "3, 5, 6", "M"),
            ]
        elif is_messaging:
            domain_reqs = [
                "CRUD for campaigns and messages.",
                "Unified channel view for SMS/WhatsApp.",
                "Contact list and metadata management.",
                "Configurable abstract provider.",
                "Send history and traceability.",
            ]
            affected = [
                "`EC.Ent`: campaign, contact, and send entities.",
                "`EC.Buss`: messaging services.",
                "`EC.Web` / `AppWeb.Scord.NetCore`: UI and API.",
            ]
            tasks = [
                ("Model domain entities", "-", "M"),
                ("Define provider abstraction", "1", "S"),
                ("Implement primary provider", "2", "L"),
                ("Create campaign views", "1", "M"),
                ("Integrate sends with queue/async processing", "3, 4", "M"),
                ("Tests", "3, 5", "S"),
            ]
        else:
            domain_reqs = [
                f"Implement the functionality described in the ticket: {title}.",
                "Persist and query the required data.",
                "Business validation and error handling.",
                "Expose the functionality through UI and/or API.",
                "Tests covering the happy path and error cases.",
            ]
            affected = [
                "Entity layer: new models or updates to existing models.",
                "Business layer: services and rules.",
                "Presentation/API layer: controllers and endpoints.",
                "Data layer: repositories and migrations.",
            ]
            tasks = [
                ("Analyze and model domain entities", "-", "M"),
                ("Define service contracts", "1", "S"),
                ("Implement business logic", "2", "L"),
                ("Create UI / endpoints", "2", "M"),
                ("Add validation and error handling", "3, 4", "S"),
                ("Unit and integration tests", "3, 4, 5", "M"),
            ]

        req_lines = "\n".join(f"{i+1}. {r}" for i, r in enumerate(domain_reqs))
        task_rows = "\n".join(
            f"| {i+1} | {name} | {deps} | {effort} |" for i, (name, deps, effort) in enumerate(tasks)
        )
        affected_lines = "\n".join(f"- {a}" for a in affected)

        content = f"""# Detailed PRD: {title}

**Ticket:** {self.ticket_id}
**Date:** {datetime.now(timezone.utc).isoformat()}

## 1. Executive Summary
Required implementation: **{title}**. This document consolidates the analysis of five PM Research Agents (Domain/UX, Technical, Integrations, Risks, Task Breakdown).

## 2. Problem / Opportunity Statement
{description or "(No description provided)"}

## 3. User Personas
- **End user:** interacts with the new functionality through the application.
- **Administrator:** configures parameters, credentials, and business rules.
- **Auditor / support:** reviews states, logs, and history.

## 4. Functional Requirements
{req_lines}

## 5. Non-Functional Requirements
- Security: credentials and sensitive data stay out of code and use secure configuration.
- Maintainability: clear layer separation between entities, business, data, and presentation/API.
- Scalability: heavy operations should preferably be asynchronous.
- Observability: structured logs and clear error messages.
- Quality: test coverage for critical business logic.

## 6. User Stories And Acceptance Criteria
**US-1:** As an end user, I want to access the functionality so I can complete my task.
- AC: The functionality is available in the UI/API as appropriate.
- AC: Data is persisted correctly.

**US-2:** As an administrator, I want to configure the functionality so it fits the business.
- AC: Configuration parameters are editable.
- AC: Validation prevents invalid configuration.

## 7. Open Questions, Assumptions, And Risks
- Assumption: scope is limited to what is described in the ticket.
- Risk: dependencies on APIs or external services; mitigate with abstractions.
- Open question: are there additional business rules not mentioned?

## 8. Suggested Technical Tasks (With Dependencies And Effort)
| # | Task | Dependencies | Effort |
|---|-------|--------------|----------|
{task_rows}

## 9. Affected Areas
{affected_lines}

## 10. PM Research Agent Notes
- **Domain/UX:** The experience should remain consistent with existing modules.
- **Technical:** Prefer established project patterns such as IOptions, repositories, and services.
- **Integrations:** If third-party APIs are involved, encapsulate them behind an interface.
- **Risks:** Validate permissions and handle external provider failures.
- **Task Breakdown:** Split work into small tasks to enable parallel Engineer execution.
"""
        with open(prd_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.log(f"Detailed plan saved at {prd_path}")

    def run_architect(self):
        self._ensure_agent("architect", "Architect", "lead", "orchestrator", "running", 40)
        self._update_agent("architect", progress=60, log="Defining technical patterns, APIs, and conventions.")
        self.log("Architect defines technical patterns, APIs, and conventions.")
        time.sleep(1.5)
        self._update_agent("architect", status="done", progress=100, log="Architecture defined.")
        self.set_phase("architect", "in-design", 50)

    def _generate_design_questions(self, prd_path):
        """Generate design questions with assumed answers using the configured backend."""
        prd_text = ""
        if prd_path.exists():
            prd_text = prd_path.read_text(encoding="utf-8")[:4000]

        prompt = f"""You are a senior architect. Review the following PRD and generate 3 to 5 technical design questions that should be confirmed with the user before implementation.

For each question, include a reasonable assumed answer based on the PRD.

PRD:
{prd_text}

Respond ONLY with valid JSON in this exact format:
[
  {{
    "id": "q1",
    "question": "Which .NET framework should be used?",
    "assumedAnswer": ".NET 8 Web API",
    "inputType": "text"
  }},
  {{
    "id": "q2",
    "question": "Which database should be used for tests?",
    "assumedAnswer": "Entity Framework Core InMemory",
    "inputType": "text"
  }}
]

Do not include explanations outside the JSON."""

        output = self._run_ai_prompt(prompt, phase_name="Design Questions", timeout_seconds=120, agent_id="architect")
        try:
            # Find JSON in the output.
            start = output.find("[")
            end = output.rfind("]")
            if start != -1 and end != -1 and end > start:
                questions = json.loads(output[start:end+1])
                if isinstance(questions, list) and len(questions) > 0:
                    return questions
        except Exception as exc:
            self.log(f"Error parsing design questions: {exc}", "warning")

        # Fallback: default questions.
        return [
            {
                "id": "q1",
                "question": "Which .NET version/framework should be used for the backend?",
                "assumedAnswer": ".NET 8 Web API",
                "inputType": "text",
            },
            {
                "id": "q2",
                "question": "Which technology should be used for data access / development database?",
                "assumedAnswer": "Entity Framework Core InMemory",
                "inputType": "text",
            },
            {
                "id": "q3",
                "question": "What type of frontend should be included, if applicable?",
                "assumedAnswer": "Minimal HTML + vanilla JavaScript",
                "inputType": "text",
            },
            {
                "id": "q4",
                "question": "Which test framework should be used?",
                "assumedAnswer": "xUnit con EF Core InMemory",
                "inputType": "text",
            },
        ]

    def _wait_for_design_answers(self, questions, timeout_seconds=60):
        """Pause the run so the user can review or confirm design answers.

        If the timeout expires, assumed answers are used.
        """
        self.log(f"Pausing for design review. The user has {timeout_seconds}s to respond.")
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
            state["summary"] = "Waiting for user design confirmation."
            save_run_state(state)

        answered_event = threading.Event()
        answers_received = {"answers": None}
        self._design_review_event = answered_event
        self._design_review_answers = answers_received

        def timeout_handler():
            time.sleep(timeout_seconds)
            if not answered_event.is_set():
                self.log("Design review timed out. Using assumed answers.", "warning")
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
        self.log(f"Engineer Squad requests user clarification ({timeout_seconds}s).")
        q = create_user_question(
            ticket_id=self.ticket_id,
            phase_name="engineer-squad",
            agent_id="engineer-squad",
            agent_name="Engineer Squad Lead",
            question=question,
            context="Escalation from the Engineer Squad Lead for an implementation question.",
            options=None,
        )
        qid = q["id"]
        answered_event = threading.Event()
        answer_container = {"answer": ""}
        _clarification_waiters[qid] = (answered_event, answer_container)
        try:
            answered = answered_event.wait(timeout=timeout_seconds)
            if not answered:
                self.log("Timed out waiting for user clarification. The squad will decide automatically.", "warning")
                answer_user_question(qid, "Decide automatically (squad timeout)")
        finally:
            _clarification_waiters.pop(qid, None)
        return answer_container["answer"] or "Decide automatically (squad timeout)"

    def _finalize_design_review(self, answers, auto=False):
        """Save final answers and clear review state."""
        with run_lock:
            state = load_run_state()
            review = state.get("designReview", {})
            review["answered"] = True
            review["finalAnswers"] = answers
            review["auto"] = auto
            state["designReview"] = review
            state["status"] = "in-design"
            state["currentAgent"] = "project-manager"
            state["summary"] = "Design review completed. Continuing with planning."
            save_run_state(state)
        self.log(f"Design review finished. Answers: {answers}")
        if hasattr(self, "_design_review_event"):
            self._design_review_event.set()

    def run_planner(self):
        self._ensure_agent("project-manager", "Project Manager", "lead", "orchestrator", "running", 60)
        self._update_agent("project-manager", progress=70, log="Building DAG and work batches.")
        self.log("Project Manager builds DAG and work batches.")

        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"

        # If a pre-generated task plan exists, reuse it.
        if tasks_path.exists() and tasks_path.stat().st_size > 50:
            try:
                with open(tasks_path, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
                if tasks and isinstance(tasks, list):
                    self.log(f"Pre-generated task plan found at {tasks_path}; skipping Planner.")
                    self._update_agent("project-manager", status="done", progress=100, log=f"Reused plan with {len(tasks)} tasks.")
                    self.set_phase("project-manager", "in-progress", 65)
                    return
            except Exception as exc:
                self.log(f"Error reading pre-generated tasks: {exc}; generating a new plan.", "warning")

        if prd_path.exists() and self.backend_registry.available_backends():
            prompt = self._build_planner_prompt(prd_path, tasks_path)
            output = self._run_ai_prompt(prompt, phase_name="Planner", timeout_seconds=600, agent_id="project-manager")
            tasks = self._parse_tasks_from_output(output)
            if not tasks:
                self.log("Planner did not return valid JSON; using default .NET CRUD plan.", "warning")
                self.log(f"Planner output (first 500 chars): {output[:500]}", "debug")
                tasks = self._build_default_crud_tasks()
        else:
            self.log("PRD unavailable or no AI backend found; using default plan.", "warning")
            tasks = self._build_default_crud_tasks()

        with open(tasks_path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)

        self._update_agent("project-manager", status="done", progress=100, log=f"Generated plan with {len(tasks)} tasks.")
        self.set_phase("project-manager", "in-progress", 65)

    def _build_default_crud_tasks(self):
        """Default task plan for a .NET product CRUD with Clean Architecture."""
        title = self.ticket.get("title", "Product CRUD")
        return [
            {
                "id": "T1",
                "title": "Create .NET solution and projects",
                "description": "Create the Domain, Application, Infrastructure, and Web projects. Configure references and NuGet packages such as MediatR, EF Core, and FluentValidation.",
                "files_to_touch": [
                    "CrudProductos.sln",
                    "src/CrudProductos.Domain/CrudProductos.Domain.csproj",
                    "src/CrudProductos.Application/CrudProductos.Application.csproj",
                    "src/CrudProductos.Infrastructure/CrudProductos.Infrastructure.csproj",
                    "src/CrudProductos.Web/CrudProductos.Web.csproj",
                ],
                "dependencies": [],
                "complexity": "medium",
                "qa_checklist": ["The solution builds", "Projects have the correct references"],
            },
            {
                "id": "T2",
                "title": "Define Product entity in domain layer",
                "description": "Create the Product entity with Id, Name, Description, Price, and StockQuantity properties. Add basic domain rules.",
                "files_to_touch": ["src/CrudProductos.Domain/Entities/Product.cs"],
                "dependencies": ["T1"],
                "complexity": "low",
                "qa_checklist": ["The entity is a pure POCO", "Properties are appropriate for the CRUD"],
            },
            {
                "id": "T3",
                "title": "Configure DbContext and repository",
                "description": "Crear ApplicationDbContext con DbSet<Product>, configurar EF Core InMemory/SQLite e implementar IProductRepository.",
                "files_to_touch": [
                    "src/CrudProductos.Infrastructure/Data/ApplicationDbContext.cs",
                    "src/CrudProductos.Application/Interfaces/IProductRepository.cs",
                    "src/CrudProductos.Infrastructure/Repositories/ProductRepository.cs",
                ],
                "dependencies": ["T2"],
                "complexity": "medium",
                "qa_checklist": ["DbContext is registered in DI", "Repository exposes async operations"],
            },
            {
                "id": "T4",
                "title": "Create commands and queries with MediatR",
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
                "qa_checklist": ["Each handler uses IProductRepository", "Handlers are async"],
            },
            {
                "id": "T5",
                "title": "Create controller and cshtml views",
                "description": "Implement ProductsController with Index, Details, Create, Edit, and Delete actions plus the corresponding Razor views.",
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
                "qa_checklist": ["All views render", "The CRUD works end-to-end"],
            },
            {
                "id": "T6",
                "title": "Configure DI and middleware in Program.cs",
                "description": "Registrar MediatR, FluentValidation, EF Core y el repositorio en Program.cs. Configurar el pipeline de middleware.",
                "files_to_touch": [
                    "src/CrudProductos.Web/Program.cs",
                    "src/CrudProductos.Web/appsettings.json",
                    "src/CrudProductos.Web/appsettings.Development.json",
                ],
                "dependencies": ["T3", "T5"],
                "complexity": "low",
                "qa_checklist": ["Application starts without errors", "Services resolve correctly"],
            },
            {
                "id": "T7",
                "title": "Add validation with FluentValidation",
                "description": "Create validators for CreateProductCommand and UpdateProductCommand. Name is required, Price >= 0, StockQuantity >= 0.",
                "files_to_touch": [
                    "src/CrudProductos.Application/Features/Products/Validators/CreateProductCommandValidator.cs",
                    "src/CrudProductos.Application/Features/Products/Validators/UpdateProductCommandValidator.cs",
                ],
                "dependencies": ["T4"],
                "complexity": "low",
                "qa_checklist": ["Validation rules are covered", "An invalid command returns 400"],
            },
            {
                "id": "T8",
                "title": "Create unit and integration tests",
                "description": "Add xUnit test projects, unit tests for handlers, and integration tests with WebApplicationFactory.",
                "files_to_touch": [
                    "tests/CrudProductos.Application.Tests/CrudProductos.Application.Tests.csproj",
                    "tests/CrudProductos.Application.Tests/Handlers/CreateProductCommandHandlerTests.cs",
                    "tests/CrudProductos.Web.Tests/CrudProductos.Web.Tests.csproj",
                    "tests/CrudProductos.Web.Tests/ProductsApiIntegrationTests.cs",
                ],
                "dependencies": ["T6"],
                "complexity": "high",
                "qa_checklist": ["dotnet test passes", "Create, list, get, edit, and delete are covered"],
            },
        ]

    def _build_planner_prompt(self, prd_path, tasks_path):
        title = self.ticket.get("title", "")
        description = self.ticket.get("description", "")
        return f"""You are a senior software architect. Read the PRD at {prd_path} and the ticket '{title}' with description: {description}.

Generate JSON with concrete implementation tasks. Each task must include:
- id: unique string (T1, T2, ...)
- title: short title
- description: detailed instructions for an Engineer
- files_to_touch: array of relative .cs file paths to create/modify
- dependencies: array of task IDs that must finish first
- complexity: "low", "medium", or "high"
- qa_checklist: array of 2-5 strings describing what QA must verify

STRICT RULES:
1. Maximum 10 tasks. Prioritize .cs files in the .NET project.
2. Respond ONLY with valid JSON (array of objects).
3. Do NOT write the JSON to a file; the system will extract it from your response.
4. Do NOT include markdown, explanations, or thoughts outside the JSON.
5. The JSON must start with [ and end with ].
6. Ensure the JSON is parseable.

Expected format example:
[
  {{
    "id": "T1",
    "title": "Create .NET solution and projects",
    "description": "Initialize the Domain, Application, Infrastructure, and Web projects.",
    "files_to_touch": ["CrudProductos.sln", "src/CrudProductos.Domain/CrudProductos.Domain.csproj"],
    "dependencies": [],
    "complexity": "medium",
    "qa_checklist": ["The solution builds", "Projects have the correct references"]
  }}
]"""

    def _parse_tasks_from_output(self, output):
        if not output:
            return []

        # 1. Find a JSON block inside a markdown code block.
        code_block_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', output, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except Exception:
                pass

        # 2. Find a JSON array by bracket counting, which is more robust than find/rfind.
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

        # 3. If there is no array, look for an object with a "tasks" key.
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
        self._update_agent("engineer-squad", progress=80, log="Implementing tasks in the repository in parallel.")
        self.log("Engineers are implementing tasks in the repository in parallel.")

        tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
        repo_path = self.ticket.get("repoPath", "")
        branch = self.ticket.get("branch", "")

        if not tasks_path.exists():
            self.log("tasks.json was not found; skipping execution.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No tasks to execute.")
            self.set_phase("engineer-squad", "in-progress", 85)
            return

        with open(tasks_path, "r", encoding="utf-8") as f:
            tasks = json.load(f)

        if not tasks:
            self.log("Planner did not generate tasks; skipping execution.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No tasks to execute.")
            self.set_phase("engineer-squad", "in-progress", 85)
            return

        if not repo_path:
            self.log("No repository configured; skipping execution.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No repository configured.")
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

        self._update_agent("engineer-squad", status="done", progress=100, log="Execution completed.")
        self.set_phase("engineer-squad", "in-progress", 85)

    def _mark_task_failed(self, agent_id, tid, reason):
        """Publish task_failed and mark the agent as failed."""
        with run_lock:
            state = load_run_state()
            _update_agent(state, agent_id, status="failed", progress=100, log=f"Task {tid} failed: {reason}")
            bus.publish_event(state, agent_id, "task_failed", {"taskId": tid, "reason": reason})
            save_run_state(state)
            emit_communication_update(state)

    def _run_single_engineer_task(self, task, status, results, lock, stop_event):
        """Run one Engineer task and update shared state."""
        tid = task["id"]
        agent_id = f"engineer-{tid}"
        repo_path = self.ticket.get("repoPath", "")
        branch = self.ticket.get("branch", "")
        self.log(f"[{agent_id}] Task thread started for {tid}.")
        with run_lock:
            state = load_run_state()
            _ensure_agent(state, agent_id, f"Engineer {tid}", "sub", "engineer-squad", "running", 0)
            bus.register_participant(state, {
                "id": agent_id,
                "name": f"Engineer {tid}",
                "role": "sub",
                "description": f"Implements task {tid}",
                "capabilities": ["coding", "dotnet"],
                "tools": ["ai_prompt", "dotnet_build", "git"],
            })
            _update_agent(state, agent_id, progress=20, log=f"Starting task: {task['title']}")
            bus.publish_event(state, agent_id, "task_started", {"taskId": tid, "title": task.get("title")})
            save_run_state(state)
            emit_communication_update(state)

        deps = task.get("dependencies", []) or []
        task_context = (
            f"Current task: {task.get('id')} - {task.get('title')}\n"
            f"Description: {task.get('description', '')}\n"
            f"Dependencies: {deps}\n"
            f"Files to touch: {task.get('files_to_touch', [])}\n"
            f"QA checklist: {task.get('qa_checklist', [])}"
        )

        # Full project context and completed dependency context.
        project_context = self._build_consultation_context(task_context=task_context)
        dependency_context = self._get_dependency_context(deps)
        if dependency_context:
            self._update_agent(agent_id, progress=25, log=f"Context from {len(deps)} dependency/dependencies included.")

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
            output = self._run_ai_prompt(prompt, phase_name=f"Engineer {tid}", timeout_seconds=1800, agent_id=agent_id)
            self._parse_engineer_coordination_messages(agent_id, output)
            with lock:
                if output:
                    status[tid] = "done"
                    results[tid] = True
                else:
                    status[tid] = "failed"
                    results[tid] = False

            if output:
                self._update_agent(agent_id, status="done", progress=100, log=f"Task {tid} completed.")
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
        """Collect files modified by an agent and save them into agent state."""
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
            self.log(f"Could not collect outputs for {agent_id}: {exc}", "warning")

    def _execute_tasks_parallel(self, tasks, repo_path, branch):
        """Run tasks with dependencies using a parallel pool."""
        max_workers = 10
        task_by_id = {t["id"]: t for t in tasks}
        status = {t["id"]: "queued" for t in tasks}
        results = {}
        lock = threading.Lock()
        stop_event = threading.Event()

        self.log(f"[execute_tasks_parallel] Starting execution of {len(tasks)} tasks.")

        # Reuse tasks that already completed or failed in a previous run.
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
            self.log(f"Already completed tasks skipped during resume: {', '.join(skipped_done)}.")
        if skipped_failed:
            self.log(f"Previously failed tasks skipped during resume: {', '.join(skipped_failed)}.")

        def can_run(task):
            deps = task.get("dependencies", []) or []
            return all(status.get(d) == "done" for d in deps)

        def run_task(task):
            self._run_single_engineer_task(task, status, results, lock, stop_event)

        pending = set(t["id"] for t in tasks if status.get(t["id"]) == "queued")
        running_threads = {}
        self.log(f"[execute_tasks_parallel] Initial pending tasks: {', '.join(sorted(pending))}.")

        while pending or running_threads:
            if stop_event.is_set():
                self.log("[execute_tasks_parallel] Stop event activated; waiting for threads and blocking pending tasks.")
                # Wait for running threads to finish and mark pending tasks as blocked.
                for t in list(running_threads.values()):
                    t.join(timeout=10)
                with lock:
                    for tid in list(pending):
                        status[tid] = "blocked"
                        agent_id = f"engineer-{tid}"
                        self._ensure_agent(agent_id, f"Engineer {tid}", "sub", "engineer-squad", "blocked", 0)
                        self._update_agent(agent_id, status="blocked", progress=0, log="Blocked by dependency failure.")
                break

            # Launch ready tasks until the pool is full.
            while len(running_threads) < max_workers and pending:
                ready_tasks = [task_by_id[tid] for tid in pending if can_run(task_by_id[tid])]
                if not ready_tasks:
                    blocked_list = sorted(pending)
                    self.log(f"[execute_tasks_parallel] No tasks are ready yet; pending tasks are blocked by dependencies: {', '.join(blocked_list)}.")
                    break
                task = ready_tasks[0]
                tid = task["id"]
                pending.remove(tid)
                status[tid] = "running"
                self.log(f"[execute_tasks_parallel] Launching {tid}: {task.get('title', '')}.")
                t = threading.Thread(target=run_task, args=(task,), daemon=True)
                running_threads[tid] = t
                t.start()

            if not running_threads:
                # No ready or running tasks: possible cycle or everything is blocked.
                self.log("[execute_tasks_parallel] No running or ready threads; leaving loop.")
                break

            # Wait until one thread finishes.
            while running_threads:
                done_threads = [tid for tid, t in running_threads.items() if not t.is_alive()]
                if done_threads:
                    for tid in done_threads:
                        del running_threads[tid]
                    self.log(f"[execute_tasks_parallel] Finished threads: {', '.join(done_threads)}; running: {', '.join(running_threads)}; pending: {', '.join(sorted(pending))}.")
                    break
                time.sleep(0.5)

        self.log(f"Parallel execution finished: {sum(1 for v in results.values() if v)}/{len(tasks)} successful.")
        return results

    def _restart_engineer_task(self, agent_id):
        """Restart one Engineer task."""
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
        """Restart a PM subagent by rerunning the analysis phase."""
        self.log(f"Restarting PM subagent {agent_id}; rerunning analysis.")
        self.run_pm_analysis()

    def _restart_agent(self, agent_id):
        """Reset agent state and rerun it when possible."""
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
        files = ", ".join(task.get("files_to_touch", []) or ["relevant project files"])
        branch_clause = f" on branch {branch}" if branch else ""
        project_section = f"\n\n--- PROJECT CONTEXT ---\n{project_context}" if project_context else ""
        dependency_section = f"\n\n--- DEPENDENCY CONTEXT ---\n{dependency_context}" if dependency_context else ""
        return f"""You are a senior .NET Engineer. Work in repo {repo_path}{branch_clause}.

GENERAL GOAL:
You are part of a team executing the ticket below. You already have the work order, PRD, task plan, and dependency context. Your job is to implement YOUR task autonomously, assuming .NET best practices and without stopping for routine questions. Stop only if there is a real blocker that cannot be resolved from the provided context.

REQUIRED RULES:
- If the repo does not have a .csproj or .sln file, first create a valid .NET 8 project with `dotnet new webapi -n CrudProducts` or an appropriate name.
- Create/modify files directly on disk using shell commands or file writes.
- After creating/editing files, run `dotnet build` in {repo_path} to verify compilation.
- If tests exist, run `dotnet test`.
- Do NOT respond only with explanations; create the real files on disk.

YOUR TASK:

Title: {task.get('title', '')}
Description: {task.get('description', '')}
Relevant files: {files}

When finished, report:
1. Which files you modified or created.
2. `dotnet build` result (success/error).
3. A QA checklist with 3-5 bullets of what should be verified.

Be concrete and write functional C# code following common ASP.NET Core / .NET patterns.{project_section}{dependency_section}

OPTIONAL COORDINATION:
If you find a real blocker during implementation that you cannot resolve alone, include ONE line EXACTLY in one of these formats:
REQUEST_HELP:<helper_id>:<question>
REQUEST_CLARIFICATION:<pm_or_architect_id>:<topic>:<question>

Do not use these mechanisms for routine questions or minor design decisions; assume the best decision and continue."""
        + decision_request_instruction()

    def run_qa(self):
        self._agent_log("orchestrator", "Phase 5/5: QA Review: reviewing batch integration.")
        self.set_phase("qa-engineer", "in-review", 90)

        # Register main QA participant
        self._ensure_agent("qa-engineer", "QA Engineer", "lead", "orchestrator", "running", 90)
        self._update_agent("qa-engineer", progress=95, log="Reviewing batch diffs and tests.")
        self.log("QA reviewing batch diffs and tests.")
        with run_lock:
            state = load_run_state()
            bus.register_participant(state, {
                "id": "qa-engineer",
                "name": "QA Engineer",
                "role": "qa",
                "description": "Reviews integration, build, and tests for the batch",
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
                self.log("No more pending reviews.")
                break

            self._agent_log("qa-engineer", f"Review {correction_round + 1}/{max_correction_rounds}: {len(review_msgs)} pending task(s).")

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
                self._update_agent(qa_agent_id, progress=50, log=f"Reviewing task {task_id}.")

                branch_clause = f" on branch {branch}" if branch else ""
                review_prompt = f"""You are a senior .NET QA Engineer. Review the changes for task {task_id}{branch_clause} in repo {repo_path}.

Diff:
{diff}

Build: {'OK' if build_ok else 'FAIL'}
{build_output}

Tests: {'OK' if test_ok else 'FAIL'}
{test_output}

If you find problems, respond EXACTLY with:
REJECTED: <reason>
SUGGESTION: <correction suggestion>

If everything is correct, respond EXACTLY with:
APPROVED"""
                review_result = self._run_ai_prompt(review_prompt, phase_name=f"QA Review {task_id}", timeout_seconds=600, agent_id=qa_agent_id) or ""

                if "APPROVED" in review_result.upper() and build_ok and test_ok:
                    with run_lock:
                        state = load_run_state()
                        completion_msg = bus.send_message(state, qa_agent_id, engineer_id, "notify_completion", {"taskId": task_id, "review": review_result[:500]})
                        bus.mark_handled(state, completion_msg["id"])
                        save_run_state(state)
                        emit_communication_update(state)
                    self._mark_message_handled(msg["id"], {"status": "approved"})
                    self._update_agent(qa_agent_id, status="done", progress=100, log=f"Task {task_id} approved.")
                    return None

                reason = ""
                suggestion = ""
                for line in review_result.splitlines():
                    if line.upper().startswith("REJECTED:"):
                        reason = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("SUGGESTION:"):
                        suggestion = line.split(":", 1)[1].strip()
                if not reason:
                    reason = "Build or tests failed" if not (build_ok and test_ok) else "Review was not approved"

                with run_lock:
                    state = load_run_state()
                    rejection_msg = bus.send_message(state, qa_agent_id, engineer_id, "reject_with_feedback", {"taskId": task_id, "reason": reason, "suggestedFix": suggestion})
                    save_run_state(state)
                    emit_communication_update(state)
                self._mark_message_handled(msg["id"], {"status": "rejected", "reason": reason})
                self._update_agent(qa_agent_id, status="failed", progress=100, log=f"Task {task_id} rejected: {reason[:120]}")
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
                        self.log(f"Error during parallel review: {exc}", "error")

            # Process rejections -> corrections
            if not rejected_items:
                break

            self._agent_log("qa-engineer", f"Correcting {len(rejected_items)} rejection(s)...")
            for item in rejected_items:
                engineer_id = item["engineer_id"]
                task_id = item["task_id"]
                reason = item["reason"]
                suggested_fix = item["suggested_fix"]

                self._agent_log(engineer_id, f"Correcting {task_id}: {reason[:120]}", "warning")

                tasks_path = get_meta_dir() / "state" / f"tasks-{self.ticket_id}.json"
                task = {}
                if tasks_path.exists():
                    try:
                        with open(tasks_path, "r", encoding="utf-8") as f:
                            tasks = json.load(f)
                        task = next((t for t in tasks if t.get("id") == task_id), {})
                    except Exception:
                        pass

                branch_clause = f" on branch {branch}" if branch else ""
                prompt = f"""You are a senior .NET Engineer. Work in repo {repo_path}{branch_clause}.

Task {task_id} was rejected by QA.
Reason: {reason}
Suggestion: {suggested_fix}
Original title: {task.get('title', '')}
Original description: {task.get('description', '')}

Fix the code according to the rejection reason. Then run `dotnet build` and `dotnet test` if tests exist.
Report the modified files and build result.
"""
                self._run_ai_prompt(prompt, phase_name=f"Fix {task_id}", timeout_seconds=1800, agent_id=engineer_id)

                with run_lock:
                    state = load_run_state()
                    bus.send_message(state, engineer_id, "qa-engineer", "request_review", {"taskId": task_id, "reason": "post-rejection correction"})
                    save_run_state(state)
                    emit_communication_update(state)
                self._mark_message_handled(item["rejection_id"], {"status": "corrected"})

        # Final summary
        pending = self._get_messages_for("qa-engineer", "request_review", handled=False)
        rejections = self._get_messages_for("qa-engineer", "reject_with_feedback", handled=False)
        if pending or rejections:
            msg = f"{len(pending)} review(s) and {len(rejections)} rejection(s) remained after {max_correction_rounds} rounds. QA did not approve."
            self._agent_log("qa-engineer", msg, "error")
            raise RuntimeError(msg)

        self._update_agent("qa-engineer", status="done", progress=100, log="QA Review completed.")
        self._agent_log("qa-engineer", "QA Review completed.", "success")

    def chat_with_agent(self, recipient_id, message):
        """Answer a human message as the selected agent.

        Uses the same configured backend as the runner, with ticket, PRD, and
        planned-task context.
        """
        with run_lock:
            state = load_run_state()
            agents_by_id = {a["id"]: a for a in state.get("agents", [])}
        recipient_name = agents_by_id.get(recipient_id, {}).get("name", recipient_id)
        context_text = self._build_consultation_context()

        prompt = f"""You are agent {recipient_name} ({recipient_id}) in a MetaGPT-style software factory. The human operator writes:

"{message}"

PROJECT CONTEXT:
{context_text}

Reply rules (strict):
- Output ONLY your final message to the human. No internal reasoning, planning, or tool notes.
- Do NOT mention skills, sessions, CLI commands, or "To resume this session".
- Use the same language as the human's message.
- Be concise and useful (2-6 sentences unless they ask for detail).
- If the message is an instruction such as "retry", "improve", "review", or "reactivate", explain how you would apply it or what you need.
- If you lack context, say so clearly in one short paragraph."""

        raw_output = self._run_ai_prompt(
            prompt,
            phase_name=f"Chat {recipient_id}",
            timeout_seconds=60,
            agent_id=recipient_id,
        )
        from core.chat_formatter import format_chat_response

        formatted = format_chat_response(raw_output or "")
        if not formatted.get("reply"):
            formatted["reply"] = "I could not generate an answer right now."
            formatted["text"] = formatted["reply"]
        return formatted

    def _run_ai_prompt(self, prompt, phase_name="Agent", timeout_seconds=120, agent_id=None):
        """Run a prompt through the configured AI backend registry."""
        safe_phase = phase_name.lower().replace(' ', '-')
        output_path = get_meta_dir() / "state" / f"output-{self.ticket_id}-{safe_phase}.txt"
        prompt_path = get_meta_dir() / "state" / f"prompt-{self.ticket_id}-{safe_phase}.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Clear previous output.
        if output_path.exists():
            output_path.unlink()

        # Save prompt to file.
        prompt_path.write_text(prompt, encoding="utf-8")

        def log_to_agent(message, level="info"):
            self.log(message, level)
            if agent_id:
                self._agent_log(agent_id, message, level)

        try:
            available = self.backend_registry.available_backends()
            if not available:
                log_to_agent("No AI backend executable or API credentials were found.", "error")
                return None

            backend_names = ", ".join(backend.name for backend in available)
            log_to_agent(f"Running AI backend for {phase_name} (available: {backend_names}; timeout {timeout_seconds}s)...")
            # Apply the .NET skill by default to all development prompts.
            dotnet_prefix = (
                "Activate the 'dotnet' skill and apply its conventions and best practices "
                "to all .NET code you generate. "
            )
            full_prompt = dotnet_prefix + prompt
            # The working directory must be the ticket repo so tools operate on code.
            repo_path = self.ticket.get("repoPath") or ""
            cwd = resolve_repo_path(repo_path) or str(Path.cwd())

            previous_cwd = os.getcwd()
            try:
                os.chdir(cwd)
                output = self.backend_registry.run_prompt(
                    full_prompt,
                    phase_name=phase_name,
                    timeout_seconds=timeout_seconds,
                    agent_id=agent_id,
                ) or ""
            finally:
                os.chdir(previous_cwd)

            output_path.write_text(output, encoding="utf-8")

            # Tail logs.
            lines = [strip_ansi(l) for l in output.splitlines() if strip_ansi(l).strip()]
            for line in lines[-50:]:
                log_to_agent(f"[{phase_name}] {line[:250]}")

            return "\n".join(lines)
        except subprocess.TimeoutExpired:
            log_to_agent(f"{phase_name} exceeded the timeout ({timeout_seconds}s)", "error")
            return None
        except Exception as exc:
            log_to_agent(f"{phase_name} error: {exc}", "error")
            return None

    def _available_backend_names(self):
        try:
            return [backend.name for backend in self.backend_registry.available_backends()]
        except Exception:
            return []


def pause_active_ticket():
    """Pause the currently running ticket, save a snapshot, and keep the thread."""
    global _active_run_thread
    with run_lock:
        state = load_run_state()
    if not state.get("active"):
        return False, "No ticket is running"
    ticket_id = state.get("ticketId")
    if not ticket_id:
        return False, "No active ticket"

    # Save a snapshot of the current state before clearing the global state.
    save_ticket_snapshot(ticket_id, state)

    if _active_run_thread and _active_run_thread.is_alive():
        _active_run_thread.pause()
        paused_run_threads[ticket_id] = _active_run_thread
        _active_run_thread = None
        # Clear global run-state so the dashboard does not show the previous ticket.
        reset_run_state_to_idle()
        return True, f"Ticket {ticket_id} paused"

    # No live runner, but still keep the snapshot and clean state.
    reset_run_state_to_idle()
    return True, f"Ticket {ticket_id} paused (no active runner)"


def play_ticket(ticket_id):
    """Start a ticket. If another ticket is running, pause it first."""
    global _active_run_thread
    board = load_board()
    ticket = next((t for t in board.get("tickets", []) if t.get("id") == ticket_id), None)
    if not ticket:
        return False, "Ticket not found"

    with run_lock:
        state = load_run_state()

    # Already running.
    if state.get("active") and state.get("ticketId") == ticket_id:
        return True, "Ticket is already running"

    # Pause another ticket if one is running.
    if state.get("active"):
        ok, msg = pause_active_ticket()
        if not ok:
            return False, f"Could not pause the active ticket: {msg}"
        state = load_run_state()

    # Resume an in-memory paused thread.
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
            return True, f"Ticket {ticket_id} resumed"

    # Resume from a disk snapshot (restart or previous pause without a live thread).
    snapshot = load_ticket_snapshot(ticket_id)
    if snapshot:
        restored = dict(snapshot)
        restored.update({"active": True, "ticketId": ticket_id})
        update_run_state(restored)
        started = start_automatic_run(ticket, resume=True, queue_if_active=False)
        if started:
            delete_ticket_snapshot(ticket_id)
            return True, f"Ticket {ticket_id} resumed from snapshot"
        return False, "Could not start the runner from snapshot"

    # Start from scratch.
    started = start_automatic_run(ticket, resume=False, queue_if_active=False)
    if started:
        return True, f"Ticket {ticket_id} started"
    return False, "Could not start the ticket"


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
        return False, "Ticket not found"

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
        return True, f"Ticket {ticket_id} restarted from scratch"
    return False, f"Could not restart ticket: {msg}"


def start_automatic_run(ticket, resume=False, queue_if_active=True):
    """Start the multi-agent loop for a ticket. If resume=True, resume from existing run-state."""
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
                    f"There is already an active run for {active_ticket_id}. "
                    f"Ticket {ticket['id']} added to the queue (position {queue_position}).",
                    "warning",
                )
            return False

    _active_run_thread = AgentRunner(ticket, resume=resume)
    _active_run_thread.start()
    return True


def resume_run(ticket):
    """Resume a previously interrupted run for the given ticket."""
    global _active_run_thread
    if _active_run_thread and _active_run_thread.is_alive():
        return False, "There is already an active runner"
    state = load_run_state()
    if state.get("ticketId") != ticket["id"]:
        return False, "Ticket does not match run-state"
    started = start_automatic_run(ticket, resume=True)
    if not started:
        return False, "Could not start the runner"
    return True, "Run resumed"


def reset_run_state_to_idle():
    """Reset run-state to idle values while preserving the queue."""
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


def stop_active_run(reason="Stopped by user"):
    """Stop the active runner and clean run-state."""
    global _active_run_thread

    runner = _active_run_thread
    if runner and runner.is_alive():
        append_log(f"{reason}. Stopping runner {runner.ticket_id}...", "warning")
        runner.stop()
        # Wait briefly for the runner to acknowledge the signal.
        runner.join(timeout=3)

    with run_lock:
        state = load_run_state()
        state["active"] = False
        save_run_state(state)

    reset_run_state_to_idle()
    _active_run_thread = None


def _find_next_runnable_ticket(board=None, exclude_ids=None):
    """Find the next ticket that is ready to run on the board."""
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
    # Sort by updatedAt ascending (oldest first).
    candidates.sort(key=lambda t: t.get("updatedAt") or t.get("createdAt") or "")
    return candidates[0]


def process_next_in_queue():
    """Process the next ticket from the queue or board when a run finishes."""
    global _active_run_thread

    with run_lock:
        state = load_run_state()
        queue = state.get("queue", [])

    # First try the internal queue.
    next_ticket = None
    while queue:
        next_ticket_id = queue.pop(0)
        board = load_board()
        ticket = next((t for t in board["tickets"] if t["id"] == next_ticket_id), None)
        if ticket and ticket.get("status") in ["ready-for-work", "in-design"]:
            next_ticket = ticket
            break
        append_log(f"Queued ticket {next_ticket_id} no longer exists or is not ready. Skipping.", "warning")

    # If the queue is empty, find the next runnable ticket on the board.
    if not next_ticket:
        board = load_board()
        next_ticket = _find_next_runnable_ticket(board)
        if next_ticket:
            append_log(f"Next automatic board ticket: {next_ticket['id']}")

    if not next_ticket:
        append_log("No more queued or ready tickets.")
        reset_run_state_to_idle()
        _active_run_thread = None
        return False

    # Save the updated queue.
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
    with run_lock:
        state = load_run_state()
        if _reconcile_stale_qa_agents(state):
            save_run_state(state)
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
        return jsonify({"ok": False, "message": "This ticket is not running"}), 400
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
    """Return a concise description of the configured AI backend set."""
    try:
        from core.runners.registry import BackendRegistry

        registry = BackendRegistry.default()
        available = [backend.name for backend in registry.available_backends()]
        if available:
            return "Available AI backends: " + ", ".join(available)
    except Exception:
        pass
    return "No AI backend available"


@app.route("/api/system-info", methods=["GET"])
def api_system_info():
    return jsonify({"model": get_model_name()})


def _estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 4)


def _build_traces(state, limit=60):
    """Build traces by combining agent logs, bus events, and messages."""
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

    # Communication bus events.
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

    # Messages between agents.
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

    # Calculate task event duration using started/completed pairs.
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
    """Build nodes and edges for the agent graph."""
    nodes = []
    node_ids = set()
    for a in state.get("agents", []) or []:
        node_id = a.get("id")
        if not node_id:
            continue
        node_ids.add(node_id)
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
            key = (parent, a["id"], "parent")
            if key not in seen:
                edges.append({"source": parent, "target": a["id"], "type": "parent"})
                seen.add(key)

    communication_counts = {}
    for msg in state.get("messages", []) or []:
        key = (msg.get("from"), msg.get("to"))
        if key[0] in node_ids and key[1] in node_ids:
            communication_counts[key] = communication_counts.get(key, 0) + 1

    for entry in state.get("communication", {}).get("log", []) or []:
        if entry.get("type") != "message":
            continue
        source = entry.get("from")
        target = entry.get("to")
        if source in node_ids and target in node_ids and source != target:
            key = (source, target)
            communication_counts[key] = communication_counts.get(key, 0) + 1

    for (source, target), count in communication_counts.items():
        key = (source, target, "communication")
        if key not in seen:
            edges.append({
                "source": source,
                "target": target,
                "type": "communication",
                "count": count,
            })
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
    """The user chooses not to answer; the agent decides autonomously."""
    answer = "Decide autonomously (user skipped)"
    q = answer_user_question(question_id, answer)
    if not q:
        return jsonify({"error": "question not found or already answered"}), 404

    if not _write_answer_file(q, answer):
        return jsonify({"error": "could not write answer file"}), 500

    return jsonify({"ok": True, "question": q})


@app.route("/api/design-review", methods=["GET"])
def api_design_review():
    """Return the active design review (questions plus assumed answers)."""
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
    """Extend the design review timeout by 60 seconds."""
    with run_lock:
        state = load_run_state()
        review = state.get("designReview")
        if not review or review.get("answered"):
            return jsonify({"error": "No active review"}), 404
        extra = 60
        review["timeoutSeconds"] = review.get("timeoutSeconds", 60) + extra
        review["expiresAt"] = (datetime.now(timezone.utc) + timedelta(seconds=extra)).isoformat()
        review["extended"] = True
        state["designReview"] = review
        save_run_state(state)
    return jsonify({"ok": True, "review": review})


@app.route("/api/design-review/answer", methods=["POST"])
def api_design_review_answer():
    """Receive user answers and continue the loop."""
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        return jsonify({"error": "answers must be an object"}), 400

    with run_lock:
        state = load_run_state()
        review = state.get("designReview")
        if not review or review.get("answered"):
            return jsonify({"error": "No active review"}), 404

        # Save answers.
        review["answered"] = True
        review["finalAnswers"] = answers
        review["answeredAt"] = datetime.now(timezone.utc).isoformat()
        review["auto"] = False
        state["designReview"] = review
        state["status"] = "in-design"
        state["currentAgent"] = "project-manager"
        state["summary"] = "Design review completed by the user. Continuing..."
        save_run_state(state)

    # Notify the runner that answers are available.
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

    # If the active ticket is manually moved to backlog or done, stop execution.
    if old_status != new_status and new_status in ("backlog", "done"):
        state = load_run_state()
        if state.get("ticketId") == ticket_id:
            stop_active_run(
                f"Ticket {ticket_id} moved to {new_status}; stopping execution"
            )
            # If it was manually moved to done, continue with the next ticket.
            if new_status == "done":
                process_next_in_queue()

    if old_status != new_status and new_status == "ready-for-work":
        # Reset execution metrics so the ticket starts from zero.
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
            return jsonify({"error": "The ticket is in backlog"}), 409

    runner = _active_run_thread
    if runner and runner.is_alive() and runner.ticket_id == ticket_id:
        ok = runner._restart_agent(agent_id)
        if not ok:
            return jsonify({"error": "Agent not found"}), 404
        return jsonify({"ok": True, "agentId": agent_id})

    # No active runner: resume the loop if the agent is a phase coordinator.
    if agent_id in ("orchestrator", "engineer-squad", "project-manager"):
        ok, msg = resume_run(ticket)
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "agentId": agent_id, "resumed": True, "message": "Run resumed from the previous state."})

    # Point restart of one Engineer without an active runner.
    if agent_id.startswith("engineer-"):
        temp_runner = AgentRunner(ticket, resume=True)
        ok = temp_runner._restart_agent(agent_id)
        if not ok:
            return jsonify({"error": "Agent not found"}), 404
        return jsonify({"ok": True, "agentId": agent_id})

    return jsonify({"error": "No active runner is available to restart this agent"}), 409


@app.route("/api/open-path", methods=["POST"])
def api_open_path():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    open_folder = bool(data.get("folder", False))
    if not path:
        return jsonify({"error": "Path required"}), 400
    target = os.path.dirname(path) if open_folder else path
    if not os.path.exists(target):
        return jsonify({"error": "Path does not exist"}), 404
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
        return jsonify({"error": "File does not exist"}), 404
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        max_len = 100_000
        if len(content) > max_len:
            content = content[:max_len] + "\n\n[Content truncated; open the file to view it completely]"
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
    """Receive a human operator message directed to an agent.

    The message is saved in the communication log and, if a runner is active,
    the selected agent is asked for a response using the AI backend.
    """
    recipient = (data or {}).get("to", "orchestrator")
    text = ((data or {}).get("message") or "").strip()
    requested_ticket_id = (data or {}).get("ticketId")
    if not text:
        return

    with run_lock:
        state = load_run_state()
        ticket_id = requested_ticket_id or state.get("ticketId")
        bus.send_message(state, "user", recipient, "chat", {"text": text})
        save_run_state(state)
    emit_communication_update(state)

    runner = _active_run_thread
    active_runner = runner if runner and runner.is_alive() and (not ticket_id or runner.ticket_id == ticket_id) else None

    def respond():
        try:
            from core.chat_formatter import format_chat_response

            chat_runner = active_runner
            if chat_runner is None:
                ticket = _ticket_by_id(ticket_id) if ticket_id else None
                if not ticket:
                    payload = format_chat_response(
                        "No ticket is selected. Select a ticket before chatting with agents."
                    )
                else:
                    chat_runner = AgentRunner(ticket, resume=True)
                    answer = chat_runner.chat_with_agent(recipient, text)
                    payload = answer if isinstance(answer, dict) else format_chat_response(answer or "")
            else:
                answer = chat_runner.chat_with_agent(recipient, text)
                payload = answer if isinstance(answer, dict) else format_chat_response(answer or "")

            with run_lock:
                state = load_run_state()
                bus.send_message(state, recipient, "user", "chat", payload)
                save_run_state(state)
            emit_communication_update(state)
        except Exception as exc:
            append_log(f"Error in chat with {recipient}: {exc}", "error")
            with run_lock:
                state = load_run_state()
                bus.send_message(
                    state,
                    "system",
                    "user",
                    "chat",
                    {"text": f"Could not get a response from {recipient}: {exc}"},
                )
                save_run_state(state)
            emit_communication_update(state)

    threading.Thread(target=respond, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="AgentFlow Dashboard Server")
    parser.add_argument("--port", type=int, default=5050, help="Server port")
    parser.add_argument("--board", type=str, default=None, help="Path to board.json")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    args = parser.parse_args()

    if args.board:
        set_board_path(args.board)
        # Derive run-state and log files from the same directory.
        board_path = Path(args.board)
        global RUN_STATE_FILE, LOG_FILE
        RUN_STATE_FILE = board_path.parent / "run-state.json"
        LOG_FILE = board_path.parent / "run.log"

    # Ensure board.json exists and has the new structure.
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
            # Save a snapshot so the run can be resumed after restart.
            save_ticket_snapshot(ticket_id, state)
            append_log(
                f"Run {ticket_id} interrupted by server restart. "
                "Snapshot saved; you can resume it from the dashboard.",
                "warning",
            )
            reset_run_state_to_idle()
            state = load_run_state()
        else:
            state["active"] = False
    save_run_state(state)

    # Reschedule timers for pending questions.
    schedule_pending_question_timers()

    # Process pending queue on startup.
    if not state.get("active") and state.get("queue"):
        threading.Thread(target=process_next_in_queue, daemon=True).start()

    # Auto-resume runs interrupted by a server restart.
    state = load_run_state()
    if not state.get("active") and state.get("status") == "failed" and state.get("ticketId") and state.get("interruptedByRestart"):
        board = load_board()
        ticket = next((t for t in board.get("tickets", []) if t.get("id") == state["ticketId"]), None)
        if ticket and ticket.get("status") not in ("backlog", "done"):
            append_log(
                f"[AUTO-RESUME] Resuming {ticket['id']} after server restart.",
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

    print(f"AgentFlow Dashboard running at http://localhost:{args.port}")
    print(f"Board: {get_board_path()}")
    print(f"Run state: {get_run_state_path()}")
    socketio.run(app, host="0.0.0.0", port=args.port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
