from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from core.models import Message


class Action(ABC):
    def __init__(self, action_id: str, name: str, desc: str = ""):
        self.action_id = action_id
        self.name = name
        self.desc = desc

    @abstractmethod
    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        """Execute the action and return a Message with the result."""
        ...
