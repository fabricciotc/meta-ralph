import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.environment import Environment
from core.models import Message
from core.roles.aggregator_role import AggregatorRole


def test_aggregator_waits_for_all_subtasks():
    env = Environment()
    role = AggregatorRole(parent_task_id="T5", subtask_ids={"T5a", "T5b"})
    env.add_role(role)

    env.publish_message(Message(
        content="done",
        sent_from="engineer-T5a",
        cause_by="task_completed",
        send_to={"aggregator-T5"},
        metadata={"task_id": "T5a", "parent_task_id": "T5", "summary": "setup done"},
    ))
    asyncio.run(env.run_round())
    # Only one subtask done: aggregator should not emit yet.
    assert len([m for m in env.history() if m.cause_by == "task_completed" and m.metadata.get("task_id") == "T5"]) == 0

    env.publish_message(Message(
        content="done",
        sent_from="engineer-T5b",
        cause_by="task_completed",
        send_to={"aggregator-T5"},
        metadata={"task_id": "T5b", "parent_task_id": "T5", "summary": "api done"},
    ))
    asyncio.run(env.run_round())

    parent_completed = [m for m in env.history() if m.cause_by == "task_completed" and m.metadata.get("task_id") == "T5"]
    assert len(parent_completed) == 1
    assert parent_completed[0].sent_from == "aggregator-T5"
