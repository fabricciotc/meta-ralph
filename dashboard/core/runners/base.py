from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class BackendResult:
    output: Optional[str]
    backend_name: str


class AIBackend(Protocol):
    name: str
    supports_skill_activation: bool

    def is_available(self) -> bool: ...

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]: ...
