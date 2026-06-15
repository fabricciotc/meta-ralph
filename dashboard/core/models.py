from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Set


@dataclass
class Message:
    content: str
    sent_from: str
    cause_by: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    role: str = "assistant"
    send_to: Set[str] = field(default_factory=lambda: {"all"})
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["send_to"] = list(data["send_to"])
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        data = dict(data)
        data["send_to"] = set(data.get("send_to", ["all"]))
        return cls(**data)
