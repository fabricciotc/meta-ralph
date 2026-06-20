from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

from core.actions.ux_design_action import UXDesignAction
from core.models import Message
from core.roles.base import Role


class UXDesignerRole(Role):
    """UX Designer role that turns a PRD (and optional architecture) into a
    design specification consumed by the PM and Engineer Squad.

    The role reacts to ``prd_ready`` or ``architecture_ready`` by running
    :class:`UXDesignAction` and publishing ``ux_design_ready``.
    """

    role_id = "ux-designer"
    addresses = {"ux-designer"}

    def __init__(
        self,
        actions: Optional[List[Any]] = None,
        run_ai: Optional[Any] = None,
        prd_path: Optional[Any] = None,
        design_path: Optional[Any] = None,
        ticket_title: str = "",
        ticket_description: str = "",
        ticket_id: str = "",
        phase_name: str = "ux_design",
        timeout_seconds: int = 600,
        build_ux_design_prompt: Optional[Any] = None,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="UX Designer",
            goal="Produce a developer-ready UX/UI design specification.",
            actions=actions,
            addresses=self.addresses,
        )
        self.run_ai = run_ai
        self.prd_path = Path(prd_path) if prd_path else None
        self.design_path = Path(design_path) if design_path else None
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self.ticket_id = ticket_id
        self.phase_name = phase_name
        self.timeout_seconds = timeout_seconds
        self.build_ux_design_prompt = build_ux_design_prompt

        self._processed_message_ids: Set[str] = set()
        self._design_ready: bool = False

    def _find_trigger(self, context: List[Message]) -> Optional[Tuple[str, Message]]:
        """Return the most recent unprocessed trigger for this role."""
        for msg in reversed(context):
            if msg.id in self._processed_message_ids:
                continue
            if msg.sent_from == self.role_id:
                continue
            if msg.cause_by in ("prd_ready", "architecture_ready"):
                return (msg.cause_by, msg)
        return None

    async def think(self, context: List[Message]) -> Optional[Any]:
        if self._design_ready:
            return None
        trigger = self._find_trigger(context)
        if trigger is None:
            return None
        return UXDesignAction(
            action_id="ux-design",
            name="Generate UX Design Spec",
            desc="Generate design-<ticket>.md from PRD and architecture.",
        )

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)

        trigger = self._find_trigger(context)
        if trigger is None:
            return None
        trigger_type, trigger_msg = trigger
        self._processed_message_ids.add(trigger_msg.id)

        action = UXDesignAction(
            action_id="ux-design",
            name="Generate UX Design Spec",
            desc="Generate design-<ticket>.md from PRD and architecture.",
        )

        architecture_path = kwargs.get("architecture_path")
        if architecture_path is None and trigger_type == "architecture_ready":
            architecture_path = trigger_msg.metadata.get("path")

        action_kwargs = {
            "run_ai": self.run_ai,
            "ticket_id": self.ticket_id,
            "ticket_title": self.ticket_title,
            "ticket_description": self.ticket_description,
            "prd_path": self.prd_path,
            "design_path": self.design_path,
            "architecture_path": Path(architecture_path) if architecture_path else None,
            "phase_name": self.phase_name,
            "timeout_seconds": self.timeout_seconds,
            "build_ux_design_prompt": self.build_ux_design_prompt,
        }

        response = await self.act(action, context, **action_kwargs)
        response.sent_from = self.role_id
        self._design_ready = True
        env.publish_message(response)
        return response
