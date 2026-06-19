from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from core.models import Message
from core.roles.base import Role


class AggregatorRole(Role):
    """Collects subtask outputs and emits a single completion for the parent task.

    This is the final step of the Kimi Agent Swarm pattern: after child agents
    finish their subtasks, the aggregator merges the results and publishes a
    ``task_completed`` message for the parent task.
    """

    _watch = ["task_completed", "swarm_subtask_report"]

    def __init__(
        self,
        parent_task_id: str,
        subtask_ids: Set[str],
        role_id: Optional[str] = None,
    ):
        super().__init__(
            role_id=role_id or f"aggregator-{parent_task_id}",
            profile="Result Aggregator",
        )
        self.parent_task_id = parent_task_id
        self.subtask_ids = set(subtask_ids)
        self._completed_subtasks: Dict[str, Dict[str, Any]] = {}
        self._emitted = False

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)

        for msg in context:
            if msg.id in self._processed_trigger_ids:
                continue
            if msg.sent_from == self.role_id:
                continue
            task_id = msg.metadata.get("task_id")
            parent_id = msg.metadata.get("parent_task_id")
            if parent_id == self.parent_task_id and task_id in self.subtask_ids:
                self._processed_trigger_ids.add(msg.id)
                self._completed_subtasks[task_id] = {
                    "summary": msg.metadata.get("summary", msg.content),
                    "sent_from": msg.sent_from,
                }

        if self._emitted or self._completed_subtasks.keys() != self.subtask_ids:
            return None

        self._emitted = True
        summary_parts = [
            f"- {tid}: {data['summary']}"
            for tid, data in sorted(self._completed_subtasks.items())
        ]
        summary = "\n".join(summary_parts)

        msg = Message(
            content=f"Aggregated {len(self.subtask_ids)} subtasks for {self.parent_task_id}.",
            sent_from=self.role_id,
            cause_by="task_completed",
            msg_type="task_completed",
            send_to={"orchestrator"},
            metadata={
                "task_id": self.parent_task_id,
                "summary": summary,
                "subtasks": list(self.subtask_ids),
            },
        )
        env.publish_message(msg)
        return msg
