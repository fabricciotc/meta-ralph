from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Set

from core.actions.plan_action import PlanAction
from core.models import Message
from core.roles.base import Role


class PlannerRole(Role):
    """Planner role that creates a task plan from PRD and architecture."""

    role_id = "planner"
    addresses = {"planner"}

    def __init__(
        self,
        actions: Optional[List[Any]] = None,
        run_ai: Optional[Any] = None,
        ticket_id: str = "",
        ticket_title: str = "",
        ticket_description: str = "",
        prd_path: Optional[Any] = None,
        tasks_path: Optional[Any] = None,
        build_plan_prompt: Optional[Any] = None,
        parse_tasks_json: Optional[Any] = None,
        write_fallback_plan: Optional[Any] = None,
        phase_name: str = "planning",
        timeout_seconds: int = 600,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="Planner",
            goal="Create a task plan from PRD and architecture.",
            actions=actions,
            addresses=self.addresses,
        )
        self.run_ai = run_ai
        self.ticket_id = ticket_id
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self.prd_path = Path(prd_path) if prd_path else None
        self.tasks_path = Path(tasks_path) if tasks_path else None
        self.build_plan_prompt = build_plan_prompt
        self.parse_tasks_json = parse_tasks_json
        self.write_fallback_plan = write_fallback_plan
        self.phase_name = phase_name
        self.timeout_seconds = timeout_seconds

        self._processed_message_ids: Set[str] = set()

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        """Return the most recent unprocessed architecture_ready or prd_ready message.

        architecture_ready messages take precedence so the planner does not act
        prematurely on a prd_ready when an architect is part of the flow.
        """
        prd_trigger: Optional[Message] = None
        for msg in reversed(context):
            if msg.cause_by not in {"architecture_ready", "prd_ready"}:
                continue
            if msg.sent_from == self.role_id:
                continue
            if msg.id in self._processed_message_ids:
                continue
            if msg.cause_by == "architecture_ready":
                return msg
            if prd_trigger is None:
                prd_trigger = msg
        return prd_trigger

    def _artifact_path(self, msg: Message) -> Optional[Path]:
        for key in ("path", "file"):
            value = msg.metadata.get(key)
            if value:
                return Path(value)
        return None

    def _has_architect_role(self, env: Any) -> bool:
        roles = getattr(env, "roles", {})
        return any(
            rid == "architect" or rid.startswith("architect-")
            for rid in roles.keys()
        )

    async def think(self, context: List[Message]) -> Optional[PlanAction]:
        trigger = self._find_trigger(context)
        if trigger is None:
            return None
        return PlanAction(
            action_id="create-plan",
            name="Create Task Plan",
            desc="Generate tasks-<ticket>.json from PRD and architecture.",
        )

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        action = await self.think(context)
        if not action:
            return None

        trigger = self._find_trigger(context)
        if trigger is None:
            return None

        # If an architect role is present, wait for architecture_ready instead of
        # acting on prd_ready. Do not mark the prd_ready as processed yet.
        if trigger.cause_by == "prd_ready" and self._has_architect_role(env):
            return None

        self._processed_message_ids.add(trigger.id)

        # Resolve PRD path.
        if trigger.cause_by == "prd_ready":
            prd_path = self._artifact_path(trigger)
        else:
            prd_path = None
            for msg in reversed(context):
                if msg.cause_by == "prd_ready" and msg.sent_from != self.role_id:
                    prd_path = self._artifact_path(msg)
                    if prd_path:
                        break
        if prd_path is None:
            prd_path = self.prd_path

        if not prd_path:
            return None

        # Resolve architecture path when available.
        architecture_path: Optional[Path] = None
        if trigger.cause_by == "architecture_ready":
            architecture_path = self._artifact_path(trigger)
        else:
            for msg in reversed(context):
                if msg.cause_by == "architecture_ready" and msg.sent_from != self.role_id:
                    architecture_path = self._artifact_path(msg)
                    if architecture_path:
                        break

        tasks_path = self.tasks_path or self._default_tasks_path(prd_path, self.ticket_id)

        action_kwargs = {
            "run_ai": self.run_ai,
            "ticket_id": self.ticket_id,
            "ticket_title": self.ticket_title,
            "ticket_description": self.ticket_description,
            "prd_path": prd_path,
            "architecture_path": architecture_path,
            "tasks_path": tasks_path,
            "build_plan_prompt": self.build_plan_prompt,
            "parse_tasks_json": self.parse_tasks_json,
            "write_fallback_plan": self.write_fallback_plan,
            "phase_name": self.phase_name,
            "timeout_seconds": self.timeout_seconds,
        }
        action_kwargs.update(kwargs)

        response = await self.act(action, context, **action_kwargs)
        response.sent_from = self.role_id
        env.publish_message(response)
        return response

    def _default_tasks_path(self, prd_path: Path, ticket_id: str) -> Path:
        parent = Path(prd_path).parent
        if ticket_id:
            return parent / f"tasks-{ticket_id}.json"
        return parent / "tasks.json"
