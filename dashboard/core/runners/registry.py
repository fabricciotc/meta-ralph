from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from core.runners.base import AIBackend

logger = logging.getLogger(__name__)


class BackendRegistry:
    def __init__(self, backends: Iterable[AIBackend]):
        self.backends: List[AIBackend] = list(backends)

    @classmethod
    def default(cls) -> "BackendRegistry":
        from core.runners.kimi_cli import KimiCliBackend
        from core.runners.cursor_cli import CursorCliBackend
        from core.runners.claude_code import ClaudeCodeBackend
        from core.runners.codex_cli import CodexCliBackend
        from core.runners.openai_api import OpenAIApiBackend

        return cls([
            KimiCliBackend(),
            CursorCliBackend(),
            ClaudeCodeBackend(),
            CodexCliBackend(),
            OpenAIApiBackend(),
        ])

    def available_backends(self) -> List[AIBackend]:
        return [b for b in self.backends if b.is_available()]

    def supports_skill_activation(self) -> bool:
        """Return True if any available backend supports skill activation."""
        return any(b.supports_skill_activation for b in self.available_backends())

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        last_error = ""
        for backend in self.backends:
            if not backend.is_available():
                continue
            try:
                output = backend.run_prompt(
                    prompt,
                    phase_name=phase_name,
                    timeout_seconds=timeout_seconds,
                    agent_id=agent_id,
                    system_instructions=system_instructions,
                )
                if output:
                    return output
            except Exception as exc:
                last_error = str(exc)
                logger.warning("Backend %s failed: %s", backend.name, exc)
        if last_error:
            logger.error("All backends failed. Last error: %s", last_error)
        return None
