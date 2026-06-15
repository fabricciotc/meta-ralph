from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Set

from core.models import Message
from core.memory import Memory
from core.actions.base import Action


class Role(ABC):
    def __init__(
        self,
        role_id: str,
        profile: str,
        goal: str = "",
        constraints: str = "",
        actions: Optional[List[Action]] = None,
        addresses: Optional[Set[str]] = None,
    ):
        self.role_id = role_id
        self.profile = profile
        self.goal = goal
        self.constraints = constraints
        self.actions = actions or []
        self.memory = Memory()
        self.addresses = addresses or {role_id}

    def observe(self, messages: List[Message]) -> List[Message]:
        """Filter messages addressed to this role."""
        relevant = []
        for msg in messages:
            if "all" in msg.send_to or self.role_id in msg.send_to:
                relevant.append(msg)
        self.memory.add_batch(relevant)
        return relevant

    @abstractmethod
    async def think(self, context: List[Message]) -> Optional[Action]:
        """Choose the next action based on observed context."""
        ...

    async def act(self, action: Action, context: List[Message], **kwargs) -> Message:
        """Execute the chosen action."""
        return await action.run(context, **kwargs)

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        """Observe, think, act."""
        messages = env.history() if hasattr(env, "history") else []
        context = self.observe(messages)
        action = await self.think(context)
        if not action:
            return None
        response = await self.act(action, context, **kwargs)
        response.sent_from = self.role_id
        return response
