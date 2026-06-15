from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from core.environment import Environment


class Orchestrator(threading.Thread):
    """MetaGPT-style orchestrator.

    Fase transitoria: actualmente envuelve el AgentRunner existente para
    mantener compatibilidad mientras se migran las fases a roles/actions.
    """

    def __init__(
        self,
        ticket: Dict[str, Any],
        resume: bool = False,
        runner_factory: Optional[Callable] = None,
    ):
        super().__init__(daemon=True)
        self.ticket = ticket
        self.ticket_id = ticket["id"]
        self.resume = bool(resume)
        self.runner_factory = runner_factory
        self.env = Environment()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._resume_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        self._resume_event.set()
        runner = getattr(self, "runner", None)
        if runner and hasattr(runner, "stop"):
            runner.stop()

    def pause(self) -> None:
        self._pause_event.set()
        self._resume_event.clear()
        runner = getattr(self, "runner", None)
        if runner and hasattr(runner, "pause"):
            runner.pause()

    def resume(self) -> None:
        self._pause_event.clear()
        self._resume_event.set()
        runner = getattr(self, "runner", None)
        if runner and hasattr(runner, "resume"):
            runner.resume()

    def run(self) -> None:
        """Execute the ticket pipeline."""
        # During the transition, instantiate the legacy runner and forward
        # lifecycle events. Future iterations will replace this with a full
        # Role/Action/Environment loop.
        if not self.runner_factory:
            raise RuntimeError("No runner_factory provided")
        self.runner = self.runner_factory(self.ticket, self.resume)
        self.runner.start()
        self.runner.join()
