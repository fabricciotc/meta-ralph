import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.environment import Environment
from core.models import Message
from core.roles.team_leader_role import TeamLeaderRole


class DummyTeamLeader(TeamLeaderRole):
    def __init__(self):
        super().__init__("test-lead", "Test Lead", max_retries=2)


def test_leader_is_not_idle_with_unprocessed_report():
    env = Environment()
    lead = DummyTeamLeader()
    env.add_role(lead)
    env.publish_message(Message(
        content="report",
        sent_from="engineer-T1",
        cause_by="task_report",
        send_to={"test-lead"},
        metadata={"task_id": "T1", "status": "completed"},
    ))
    assert lead.should_run(env) is True


def test_leader_run_acknowledges_completed_task():
    env = Environment()
    lead = DummyTeamLeader()
    env.add_role(lead)
    env.publish_message(Message(
        content="report",
        sent_from="engineer-T1",
        cause_by="task_report",
        send_to={"test-lead"},
        metadata={"task_id": "T1", "status": "completed"},
    ))
    response = asyncio.run(lead.run(env))
    assert response is not None
    assert response.cause_by == "squad_chat"


def test_leader_fallback_retries_failed_task():
    lead = DummyTeamLeader()
    trigger = Message(
        content="failed",
        sent_from="engineer-T1",
        cause_by="task_report",
        send_to={"test-lead"},
        metadata={"task_id": "T1", "status": "failed", "summary": "build broke"},
    )
    decision = asyncio.run(lead.mediate(trigger, []))
    assert decision["action"] == "retry"
    assert "T1" in decision.get("message", "")


def test_leader_fallback_escalates_after_max_retries():
    lead = DummyTeamLeader()
    trigger = Message(
        content="failed",
        sent_from="engineer-T1",
        cause_by="task_report",
        send_to={"test-lead"},
        metadata={"task_id": "T1", "status": "failed", "retries": 3, "summary": "build broke"},
    )
    decision = asyncio.run(lead.mediate(trigger, []))
    assert decision["action"] == "escalate_to_user"


def test_leader_run_publishes_instruction_on_retry():
    env = Environment()
    lead = DummyTeamLeader()
    env.add_role(lead)
    env.publish_message(Message(
        content="failed",
        sent_from="engineer-T1",
        cause_by="task_report",
        send_to={"test-lead"},
        metadata={
            "task_id": "T1",
            "status": "failed",
            "summary": "build broke",
            "engineer_id": "engineer-T1",
        },
    ))
    asyncio.run(env.run_round())
    instructions = [m for m in env.history() if m.cause_by == "squad_instruction"]
    assert len(instructions) == 1
    assert instructions[0].send_to == {"engineer-T1"}


def test_leader_parse_decision_extracts_json():
    lead = DummyTeamLeader()
    raw = '{"action": "ack", "message": "ok"}'
    decision = lead._parse_decision(raw)
    assert decision["action"] == "ack"
    assert decision["message"] == "ok"
