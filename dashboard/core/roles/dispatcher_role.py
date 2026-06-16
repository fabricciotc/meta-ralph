from __future__ import annotations

from typing import Any, List, Optional

from core.models import Message
from core.roles.base import Role


class DispatcherRole(Role):
    """Coordinator that triggers phase transitions based on environment messages."""

    role_id = "dispatcher"
    addresses = {"dispatcher"}

    def __init__(self, ticket_id: str, ticket_title: str, ticket_description: str):
        super().__init__(
            role_id=self.role_id,
            profile="Dispatcher",
            goal="Coordinate the phases of the software factory loop.",
            addresses=self.addresses,
        )
        self.ticket_id = ticket_id
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self._processed_ids: set = set()

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        for msg in reversed(context):
            if msg.id in self._processed_ids:
                continue
            if msg.cause_by in {"ticket_ready", "architecture_ready", "plan_ready", "batch_completed"}:
                return msg
        return None

    async def think(self, context: List[Message]) -> Optional[str]:
        return "dispatch" if self._find_trigger(context) else None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None
        self._processed_ids.add(trigger.id)

        if trigger.cause_by == "ticket_ready":
            msg = Message(
                content=f"Start PM Analysis for {self.ticket_id}",
                sent_from=self.role_id,
                cause_by="prd_ready",
                send_to={"all"},
                metadata={
                    "ticket_id": self.ticket_id,
                    "ticket_title": self.ticket_title,
                    "ticket_description": self.ticket_description,
                },
            )
            env.publish_message(msg)
            return msg

        if trigger.cause_by == "architecture_ready":
            msg = Message(
                content="Architecture ready; plan tasks.",
                sent_from=self.role_id,
                cause_by="plan_ready_trigger",
                send_to={"planner"},
                metadata={"ticket_id": self.ticket_id},
            )
            env.publish_message(msg)
            return msg

        return None
