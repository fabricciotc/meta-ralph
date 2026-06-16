from __future__ import annotations

from typing import Any, List, Optional

from core.models import Message
from core.roles.base import Role


class MonitorRole(Role):
    """Coordinator that detects stalls and reports overall health."""

    role_id = "monitor"
    addresses = {"monitor"}

    def __init__(self, max_idle_rounds: int = 5):
        super().__init__(
            role_id=self.role_id,
            profile="Monitor",
            goal="Detect stalls and report progress.",
            addresses=self.addresses,
        )
        self.max_idle_rounds = max_idle_rounds
        self._idle_rounds = 0
        self._last_history_len = 0

    async def think(self, context: List[Message]) -> Optional[Any]:
        return None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        if len(history) == self._last_history_len:
            self._idle_rounds += 1
        else:
            self._idle_rounds = 0
        self._last_history_len = len(history)

        if self._idle_rounds >= self.max_idle_rounds:
            msg = Message(
                content="Stall detected",
                sent_from=self.role_id,
                cause_by="health_check",
                send_to={"recovery"},
                metadata={"status": "stalled", "idle_rounds": self._idle_rounds},
            )
            env.publish_message(msg)
            self._idle_rounds = 0
            return msg
        return None
