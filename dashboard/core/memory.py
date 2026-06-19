from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from core.models import Message


class Memory:
    def __init__(self):
        self.messages: List[Message] = []
        self._index_by_cause: Dict[str, List[Message]] = defaultdict(list)
        self._index_by_role: Dict[str, List[Message]] = defaultdict(list)
        self._index_by_type: Dict[str, List[Message]] = defaultdict(list)
        self._index_by_recipient: Dict[str, List[Message]] = defaultdict(list)

    def add(self, msg: Message) -> None:
        self.messages.append(msg)
        self._index_by_cause[msg.cause_by].append(msg)
        self._index_by_role[msg.sent_from].append(msg)
        self._index_by_type[msg.msg_type].append(msg)
        for recipient in msg.send_to:
            self._index_by_recipient[recipient].append(msg)

    def add_batch(self, msgs: List[Message]) -> None:
        for msg in msgs:
            self.add(msg)

    def get(self, k: int = 0) -> List[Message]:
        if k <= 0:
            return list(self.messages)
        return list(self.messages[-k:])

    def get_by_cause(self, cause: str) -> List[Message]:
        return list(self._index_by_cause.get(cause, []))

    def get_by_role(self, role: str) -> List[Message]:
        return list(self._index_by_role.get(role, []))

    def get_by_type(self, msg_type: str) -> List[Message]:
        """Return all messages with the given ``msg_type``."""
        return list(self._index_by_type.get(msg_type, []))

    def get_for_role(self, role_id: str) -> List[Message]:
        """Return messages addressed to ``role_id`` (including broadcasts)."""
        seen: set = set()
        result: List[Message] = []
        for key in (role_id, "all"):
            for m in self._index_by_recipient.get(key, []):
                if m.id not in seen and m.is_for(role_id):
                    seen.add(m.id)
                    result.append(m)
        return result

    def recent_context(self, n: int = 10) -> List[Message]:
        return self.get(k=n)

    def to_dict(self) -> Dict[str, Any]:
        return {"messages": [m.to_dict() for m in self.messages]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        mem = cls()
        for m in data.get("messages", []):
            mem.add(Message.from_dict(m))
        return mem
