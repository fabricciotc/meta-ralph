from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Dict, List

from core.models import Message
from core.memory import Memory


class Environment:
    def __init__(self):
        self.roles: Dict[str, any] = {}
        self.memory = Memory()
        self._queue: deque = deque()
        self.inboxes: Dict[str, deque] = defaultdict(deque)

    def add_role(self, role) -> None:
        self.roles[role.role_id] = role
        # Route any messages already waiting in the queue to the new role's inbox.
        for msg in list(self._queue):
            if msg.is_for(role.role_id):
                self.inboxes[role.role_id].append(msg)

    def publish_message(self, msg: Message) -> None:
        self._queue.append(msg)
        # Route to every known role that should receive this message.
        for role_id in self.roles:
            if msg.is_for(role_id):
                self.inboxes[role_id].append(msg)

    def get_messages_for(self, role_id: str) -> List[Message]:
        """Return pending messages for ``role_id`` from its inbox and the queue.

        The fallback to ``_queue`` preserves compatibility with messages published
        for roles that have not been registered yet (e.g. the orchestrator).
        """
        seen: set = set()
        result: List[Message] = []
        for msg in self.inboxes.get(role_id, deque()):
            seen.add(msg.id)
            result.append(msg)
        for msg in self._queue:
            if msg.id not in seen and msg.is_for(role_id):
                result.append(msg)
        return result

    def _drain_queue_to_memory(self) -> None:
        while self._queue:
            self.memory.add(self._queue.popleft())

    def _role_has_pending_work(self, role) -> bool:
        """Return True if ``role`` should be scheduled this round."""
        if hasattr(role, "should_run") and callable(getattr(role, "should_run")):
            return role.should_run(self)
        # Fallback for plain callable roles (e.g. test dummies).
        if getattr(role, "todo", None) is not None:
            return True
        if self.inboxes.get(role.role_id):
            return True
        return False

    async def run_round(self, **kwargs) -> bool:
        context = kwargs.get("context")
        tasks = []
        running_roles = []
        for role in self.roles.values():
            if hasattr(role, "run") and self._role_has_pending_work(role):
                tasks.append(role.run(self, **kwargs))
                running_roles.append(role)
        if not tasks:
            # No roles had pending work; drain orphan messages and finish.
            had_messages = len(self._queue) > 0
            self._emit_visible_messages(context)
            self._drain_queue_to_memory()
            return had_messages
        results = await asyncio.gather(*tasks, return_exceptions=True)
        had_activity = any(
            r is True or isinstance(r, Message)
            for r in results
            if not isinstance(r, Exception)
        )
        # Messages published during the round count as activity even if no role
        # explicitly returned True; otherwise clarification loops stall.
        had_messages = len(self._queue) > 0
        # Clear inboxes for roles that ran so the same messages don't re-trigger.
        for role in running_roles:
            self.inboxes[role.role_id].clear()
        self._emit_visible_messages(context)
        self._drain_queue_to_memory()
        return had_activity or had_messages

    def is_idle(self) -> bool:
        if len(self._queue) > 0:
            return False
        if any(self.inboxes.values()):
            return False
        return True

    def history(self) -> List[Message]:
        return self.memory.get()

    def _emit_visible_messages(self, context) -> None:
        if context is None or not hasattr(context, "callback"):
            return
        for msg in list(self._queue):
            context.callback("publish_message", msg)
