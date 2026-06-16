from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


class Context:
    """Shared context object passed to roles and actions.

    Inspired by MetaGPT's ``Context`` / ``RoleContext``, this object holds the
    global state of a ticket execution so that roles and actions do not need
    to reconstruct it from scattered kwargs.
    """

    def __init__(
        self,
        ticket: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        callbacks: Optional[Dict[str, Any]] = None,
        backend_registry: Optional[Any] = None,
        skills_registry: Optional[Any] = None,
        prd_path: Optional[Path] = None,
        architecture_path: Optional[Path] = None,
        tasks_path: Optional[Path] = None,
        repo_path: Optional[str] = None,
        branch: Optional[str] = None,
    ):
        self.ticket = dict(ticket) if ticket else {}
        self.config = dict(config) if config else {}
        self.callbacks = dict(callbacks) if callbacks else {}
        self.backend_registry = backend_registry
        self.skills_registry = skills_registry

        self.prd_path = prd_path
        self.architecture_path = architecture_path
        self.tasks_path = tasks_path
        self.repo_path = repo_path
        self.branch = branch

        # Mutable shared state that roles/actions can read/write.
        self.shared: Dict[str, Any] = {}

    @property
    def ticket_id(self) -> str:
        return self.ticket.get("id", "")

    @property
    def ticket_title(self) -> str:
        return self.ticket.get("title", "")

    @property
    def ticket_description(self) -> str:
        return self.ticket.get("description", "")

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from the mutable shared state."""
        return self.shared.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a value to the mutable shared state."""
        self.shared[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        """Merge a dictionary into the mutable shared state."""
        self.shared.update(values)

    def callback(self, name: str, *args, **kwargs) -> Any:
        """Invoke a dashboard callback if present."""
        fn = self.callbacks.get(name)
        if fn is None:
            return None
        return fn(*args, **kwargs)

    def log(self, message: str, level: str = "info") -> None:
        """Convenience helper for the ``log`` callback."""
        self.callback("log", message, level)

    def run_ai(self, prompt: str, phase_name: str, timeout_seconds: int, agent_id: Optional[str] = None) -> Optional[str]:
        """Run a prompt through the configured backend registry.

        Falls back to the ``run_ai`` callback if no backend registry is
        configured, preserving legacy/local testing hooks.
        """
        callback_run = self.callbacks.get("run_ai")
        if callback_run:
            return callback_run(prompt, phase_name, timeout_seconds, agent_id)
        if self.backend_registry is None:
            return None
        return self.backend_registry.run_prompt(
            prompt,
            phase_name=phase_name,
            timeout_seconds=timeout_seconds,
            agent_id=agent_id,
        )
