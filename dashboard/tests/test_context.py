import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import Context


def test_context_exposes_ticket_fields():
    ctx = Context(ticket={"id": "TKT-001", "title": "Login", "description": "Allow login"})
    assert ctx.ticket_id == "TKT-001"
    assert ctx.ticket_title == "Login"
    assert ctx.ticket_description == "Allow login"


def test_context_shared_state():
    ctx = Context(ticket={})
    ctx.set("phase", "architecture")
    ctx.update({"architect_ready": True})
    assert ctx.get("phase") == "architecture"
    assert ctx.get("architect_ready") is True
    assert ctx.get("missing", "default") == "default"


def test_context_callback():
    calls = []
    ctx = Context(ticket={}, callbacks={"custom": lambda *a, **kw: calls.append((a, kw))})
    ctx.callback("custom", 1, 2, key="value")
    assert calls == [((1, 2), {"key": "value"})]


def test_context_run_ai_uses_callback():
    calls = []

    def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
        calls.append((prompt, phase_name, timeout_seconds, agent_id))
        return "ok"

    ctx = Context(ticket={}, callbacks={"run_ai": mock_run_ai})
    assert ctx.run_ai("p", "phase", 5, "agent") == "ok"
    assert calls == [("p", "phase", 5, "agent")]


def test_context_paths_optional():
    ctx = Context(ticket={})
    assert ctx.prd_path is None
    assert ctx.architecture_path is None
    assert ctx.tasks_path is None
    assert ctx.repo_path is None
    assert ctx.branch is None
