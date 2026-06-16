from __future__ import annotations

import asyncio
from collections import deque
from typing import Dict, List

from core.models import Message
from core.memory import Memory


class Environment:
    def __init__(self):
        self.roles: Dict[str, any] = {}
        self.memory = Memory()
        self._queue: deque = deque()

    def add_role(self, role) -> None:
        self.roles[role.role_id] = role

    def publish_message(self, msg: Message) -> None:
        self._queue.append(msg)

    def get_messages_for(self, role_id: str) -> List[Message]:
        result = []
        for msg in list(self._queue):
            if "all" in msg.send_to or role_id in msg.send_to:
                result.append(msg)
        return result

    def _drain_queue_to_memory(self) -> None:
        while self._queue:
            self.memory.add(self._queue.popleft())

    async def run_round(self, **kwargs) -> bool:
        context = kwargs.get("context")
        tasks = []
        for role in self.roles.values():
            if hasattr(role, "run"):
                tasks.append(role.run(self, **kwargs))
        if not tasks:
            return False
        results = await asyncio.gather(*tasks, return_exceptions=True)
        had_activity = any(
            r is True or isinstance(r, Message)
            for r in results
            if not isinstance(r, Exception)
        )
        # Messages published during the round count as activity even if no role
        # explicitly returned True; otherwise clarification loops stall.
        had_messages = len(self._queue) > 0
        self._emit_visible_messages(context)
        self._drain_queue_to_memory()
        return had_activity or had_messages

    def is_idle(self) -> bool:
        return len(self._queue) == 0

    def history(self) -> List[Message]:
        return self.memory.get()

    def _emit_visible_messages(self, context) -> None:
        if context is None or not hasattr(context, "callback"):
            return
        for msg in list(self._queue):
            context.callback("publish_message", msg)
