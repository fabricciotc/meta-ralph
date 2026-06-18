"""Communication bus for AgenticFlow agent collaboration.

Provides participant profiles, environment events and typed direct messages.
All state is persisted inside run-state["communication"].
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

MAX_LOG_SIZE = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_communication(state) -> dict:
    if "communication" not in state:
        state["communication"] = {
            "ticketId": state.get("ticketId"),
            "participants": {},
            "log": [],
            "pendingActions": [],
            "maxLogSize": MAX_LOG_SIZE,
        }
    comm = state["communication"]
    comm.setdefault("participants", {})
    comm.setdefault("log", [])
    comm.setdefault("pendingActions", [])
    comm.setdefault("maxLogSize", MAX_LOG_SIZE)
    return comm


def register_participant(state, profile: dict) -> dict:
    """Register a participant profile and emit participant_joined event."""
    if not isinstance(profile, dict) or "id" not in profile:
        raise ValueError("profile must be a dict containing 'id'")
    comm = _get_communication(state)
    participant_id = profile["id"]
    comm["participants"][participant_id] = profile
    event = {
        "type": "event",
        "eventType": "participant_joined",
        "participantId": participant_id,
        "payload": {"profile": profile},
        "timestamp": _now_iso(),
    }
    _append_log_entry(state, event)
    return event


def unregister_participant(state, participant_id: str) -> dict:
    """Emit participant_left event and remove from active participants."""
    comm = _get_communication(state)
    comm["participants"].pop(participant_id, None)
    event = {
        "type": "event",
        "eventType": "participant_left",
        "participantId": participant_id,
        "payload": {},
        "timestamp": _now_iso(),
    }
    _append_log_entry(state, event)
    return event


def publish_event(state, participant_id: str, event_type: str, payload: Optional[dict] = None) -> dict:
    """Publish an environment event."""
    event = {
        "type": "event",
        "eventType": event_type,
        "participantId": participant_id,
        "payload": payload or {},
        "timestamp": _now_iso(),
    }
    _append_log_entry(state, event)
    return event


def send_message(state, from_id: str, to_id: str, message_type: str, payload: dict, add_pending: bool = True) -> dict:
    """Send a typed direct message between participants."""
    comm = _get_communication(state)
    msg_id = f"msg-{uuid.uuid4().hex[:8]}"
    message = {
        "id": msg_id,
        "type": "message",
        "from": from_id,
        "to": to_id,
        "messageType": message_type,
        "payload": payload,
        "timestamp": _now_iso(),
        "handled": False,
    }
    _append_log_entry(state, message)
    if add_pending:
        comm["pendingActions"].append({
            "messageId": msg_id,
            "handlerId": to_id,
            "action": _action_for_message_type(message_type),
        })
    return message


def _action_for_message_type(message_type: str) -> str:
    return {
        "request_review": "review",
        "reject_with_feedback": "fix_and_resubmit",
        "request_clarification": "answer",
        "request_help": "assist",
        "notify_completion": "acknowledge",
        "replan": "replan",
    }.get(message_type, "handle")


def _append_log_entry(state, entry: dict) -> None:
    comm = _get_communication(state)
    max_size = comm.get("maxLogSize", MAX_LOG_SIZE)
    comm["log"].append(entry)
    if len(comm["log"]) > max_size:
        comm["log"] = comm["log"][-max_size:]


def mark_handled(state, message_id: str, result: Optional[dict] = None) -> bool:
    """Mark a message as handled and record optional result."""
    comm = _get_communication(state)
    found = False
    for entry in comm.get("log", []):
        if entry.get("id") == message_id and entry.get("type") == "message":
            entry["handled"] = True
            entry["handledAt"] = _now_iso()
            if result:
                entry["result"] = result
            found = True
            break
    comm["pendingActions"] = [
        a for a in comm.get("pendingActions", [])
        if a.get("messageId") != message_id
    ]
    return found


def get_participants(state) -> dict:
    return _get_communication(state).get("participants", {})


def get_pending_actions(state) -> list:
    return _get_communication(state).get("pendingActions", [])


def _sanitize_log_param(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def get_log(state, limit=50, offset=0, type_filter=None, participant_id=None, message_type=None) -> list:
    log = _get_communication(state).get("log", [])
    if type_filter:
        log = [e for e in log if e.get("type") == type_filter]
    if participant_id:
        log = [
            e for e in log
            if e.get("participantId") == participant_id
            or e.get("from") == participant_id
            or e.get("to") == participant_id
        ]
    if message_type:
        log = [e for e in log if e.get("messageType") == message_type]
    limit = _sanitize_log_param(limit)
    offset = _sanitize_log_param(offset)
    total = len(log)
    end = max(0, total - offset)
    start = max(0, end - limit)
    return log[start:end]


def get_messages_for(state, participant_id: str, message_type: Optional[str] = None, handled: Optional[bool] = False) -> list:
    """Return messages directed to participant_id, optionally filtered by type and handled state."""
    comm = _get_communication(state)
    messages = [e for e in comm.get("log", []) if e.get("type") == "message" and e.get("to") == participant_id]
    if message_type:
        messages = [m for m in messages if m.get("messageType") == message_type]
    if handled is not None:
        messages = [m for m in messages if bool(m.get("handled")) == handled]
    return messages
