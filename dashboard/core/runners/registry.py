from __future__ import annotations

import logging
import os
import shutil
from typing import Any, Dict, Iterable, List, Optional

from core.runners.base import AIBackend
from core.config import get_preferred_backend

logger = logging.getLogger(__name__)


# CLI executables to probe, in preference order, for each backend name.
_CLI_CANDIDATES: Dict[str, List[str]] = {
    "kimi": ["kimi"],
    "claude": ["claude"],
    "cursor": ["cursor-agent", "agent", "cursor"],
    "codex": ["codex"],
    "copilot": ["copilot", "gh"],
}

_BACKEND_DISPLAY_NAMES: Dict[str, str] = {
    "kimi": "Kimi Code",
    "claude": "Claude Code",
    "cursor": "Cursor Agent",
    "codex": "Codex CLI",
    "copilot": "GitHub Copilot CLI",
    "openai_api": "OpenAI API",
}


def _find_executable(name: str) -> Optional[str]:
    return shutil.which(name)


def discover_backends() -> List[Dict[str, Any]]:
    """Return a list of detected backends with availability metadata.

    Each item contains: name, displayName, type, available, executable, reason.
    """
    results: List[Dict[str, Any]] = []

    for name, candidates in _CLI_CANDIDATES.items():
        executable: Optional[str] = None
        for candidate in candidates:
            executable = _find_executable(candidate)
            if executable:
                break

        if executable:
            results.append({
                "name": name,
                "displayName": _BACKEND_DISPLAY_NAMES.get(name, name),
                "type": "cli",
                "available": True,
                "executable": executable,
                "reason": f"Found at {executable}",
            })
        else:
            results.append({
                "name": name,
                "displayName": _BACKEND_DISPLAY_NAMES.get(name, name),
                "type": "cli",
                "available": False,
                "executable": None,
                "reason": f"None of {candidates} found in PATH",
            })

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        results.append({
            "name": "openai_api",
            "displayName": _BACKEND_DISPLAY_NAMES.get("openai_api", "openai_api"),
            "type": "api",
            "available": True,
            "executable": None,
            "reason": "OPENAI_API_KEY is set",
        })
    else:
        results.append({
            "name": "openai_api",
            "displayName": _BACKEND_DISPLAY_NAMES.get("openai_api", "openai_api"),
            "type": "api",
            "available": False,
            "executable": None,
            "reason": "OPENAI_API_KEY is not set",
        })

    return results


def _resolve_preferred_backend(preferred: Optional[str]) -> Optional[str]:
    """Return the executable/path for the preferred backend if it is available."""
    if not preferred:
        return None

    if preferred == "openai_api":
        return preferred if os.environ.get("OPENAI_API_KEY") else None

    candidates = _CLI_CANDIDATES.get(preferred, [preferred])
    for candidate in candidates:
        executable = _find_executable(candidate)
        if executable:
            return executable
    return None


class BackendRegistry:
    def __init__(self, backends: Iterable[AIBackend]):
        self.backends: List[AIBackend] = list(backends)

    @classmethod
    def default(cls, preferred: Optional[str] = None) -> "BackendRegistry":
        from core.runners.kimi_cli import KimiCliBackend
        from core.runners.cursor_cli import CursorCliBackend
        from core.runners.claude_code import ClaudeCodeBackend
        from core.runners.codex_cli import CodexCliBackend
        from core.runners.copilot_cli import CopilotCliBackend
        from core.runners.openai_api import OpenAIApiBackend

        # If a preferred backend is configured and available, use only that one.
        if preferred:
            executable = _resolve_preferred_backend(preferred)
            if executable:
                backend_map = {
                    "kimi": KimiCliBackend(executable=executable),
                    "claude": ClaudeCodeBackend(executable=executable),
                    "cursor": CursorCliBackend(executable=executable),
                    "codex": CodexCliBackend(executable=executable),
                    "copilot": CopilotCliBackend(executable=executable),
                    "openai_api": OpenAIApiBackend(),
                }
                backend = backend_map.get(preferred)
                if backend and backend.is_available():
                    logger.info("Using preferred backend: %s", preferred)
                    return cls([backend])
            logger.warning(
                "Preferred backend '%s' is not available; falling back to all available backends.",
                preferred,
            )

        return cls([
            KimiCliBackend(),
            CursorCliBackend(),
            ClaudeCodeBackend(),
            CodexCliBackend(),
            CopilotCliBackend(),
            OpenAIApiBackend(),
        ])

    @classmethod
    def from_config(cls) -> "BackendRegistry":
        preferred = get_preferred_backend()
        return cls.default(preferred=preferred)

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
