import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.environment import Environment
from core.models import Message
from core.roles.swarm_leader_role import SwarmLeaderRole


def test_swarm_leader_fallback_decomposes_large_task():
    env = Environment()
    role = SwarmLeaderRole(max_workers=3)
    env.add_role(role)
    env.publish_message(Message(
        content="Implement full auth module",
        sent_from="orchestrator",
        cause_by="decompose_request",
        send_to={"swarm-leader"},
        metadata={
            "task_id": "T5",
            "title": "Auth module",
            "description": "Implement login, logout, and password reset.",
            "complexity": "L",
        },
    ))
    asyncio.run(env.run_round())

    subtasks_msgs = [m for m in env.history() if m.cause_by == "swarm_subtasks"]
    assert len(subtasks_msgs) == 1
    subtasks = subtasks_msgs[0].metadata.get("subtasks", [])
    assert len(subtasks) >= 2
    assert all(st.get("parent_task_id") == "T5" for st in subtasks)


def test_swarm_leader_uses_llm_when_available():
    env = Environment()

    def fake_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
        return json.dumps({
            "subtasks": [
                {"id": "T5a", "title": "Setup DB", "dependencies": []},
                {"id": "T5b", "title": "API endpoints", "dependencies": ["T5a"]},
            ]
        })

    role = SwarmLeaderRole(run_ai=fake_run_ai, max_workers=3)
    env.add_role(role)
    env.publish_message(Message(
        content="Big task",
        sent_from="orchestrator",
        cause_by="decompose_request",
        send_to={"swarm-leader"},
        metadata={"task_id": "T5", "title": "Big", "description": "Desc", "complexity": "L"},
    ))
    asyncio.run(env.run_round())

    subtasks_msgs = [m for m in env.history() if m.cause_by == "swarm_subtasks"]
    assert len(subtasks_msgs) == 1
    ids = [st["id"] for st in subtasks_msgs[0].metadata["subtasks"]]
    assert "T5a" in ids and "T5b" in ids


def test_swarm_leader_respects_max_workers():
    env = Environment()
    role = SwarmLeaderRole(max_workers=2)
    env.add_role(role)
    env.publish_message(Message(
        content="Huge task",
        sent_from="orchestrator",
        cause_by="decompose_request",
        send_to={"swarm-leader"},
        metadata={"task_id": "T6", "title": "Huge", "description": "Many things", "complexity": "L"},
    ))
    asyncio.run(env.run_round())

    subtasks = [m for m in env.history() if m.cause_by == "swarm_subtasks"][0].metadata["subtasks"]
    assert len(subtasks) <= 2
