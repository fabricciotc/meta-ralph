from __future__ import annotations

from typing import Any, List, Optional

from core.models import Message
from core.roles.base import Role


class RecoveryRole(Role):
    """Coordinator that decides retries, replanning or escalation on failures."""

    role_id = "recovery"
    addresses = {"recovery"}

    def __init__(self, max_retries: int = 2):
        super().__init__(
            role_id=self.role_id,
            profile="Recovery",
            goal="Decide retries, replanning or escalation on failures.",
            addresses=self.addresses,
        )
        self.max_retries = max_retries
        self._failures: dict = {}

    async def think(self, context: List[Message]) -> Optional[Any]:
        return None

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        for msg in reversed(context):
            if msg.cause_by in {"task_failed", "reject_with_feedback", "health_check"}:
                return msg
        return None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None

        if trigger.cause_by == "task_failed":
            task_id = trigger.metadata.get("task_id", "unknown")
            count = self._failures.get(task_id, 0) + 1
            self._failures[task_id] = count
            if count <= self.max_retries:
                msg = Message(
                    content=f"Retry task {task_id}",
                    sent_from=self.role_id,
                    cause_by="task_assigned",
                    send_to={f"engineer-{task_id}"},
                    metadata=trigger.metadata,
                )
                env.publish_message(msg)
                return msg
            else:
                msg = Message(
                    content=f"Task {task_id} exceeded retries",
                    sent_from=self.role_id,
                    cause_by="run_failed",
                    send_to={"orchestrator"},
                    metadata={"task_id": task_id},
                )
                env.publish_message(msg)
                return msg
        return None
