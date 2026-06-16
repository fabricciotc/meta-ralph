from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.actions.research_action import ResearchAction
from core.models import Message
from core.roles.base import Role


class PMResearchRole(Role):
    """Role for a PM research subagent that reacts to research requests."""

    def __init__(
        self,
        role_id: str,
        sub_name: str,
        focus: str,
        run_ai: Optional[Any] = None,
    ):
        super().__init__(
            role_id=role_id,
            profile=sub_name,
            goal=focus,
            addresses={role_id},
        )
        self.sub_name = sub_name
        self.focus = focus
        self.run_ai = run_ai
        self._processed_trigger_ids: set = set()
        self._base_metadata: Dict[str, Any] = {}

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        """Return the most recent relevant trigger message not from this role."""
        for msg in reversed(context):
            if msg.cause_by not in {"research_request", "request_clarification"}:
                continue
            if msg.sent_from == self.role_id:
                continue
            if msg.id in self._processed_trigger_ids:
                continue
            return msg
        return None

    async def think(self, context: List[Message]) -> Optional[ResearchAction]:
        trigger = self._find_trigger(context)
        if trigger is None:
            return None
        return ResearchAction(
            action_id=f"{self.role_id}-research",
            name=f"{self.sub_name} Research",
            desc=f"Research focus: {self.focus}",
        )

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        action = await self.think(context)
        if not action:
            return None

        trigger = self._find_trigger(context)

        action_kwargs = dict(kwargs)
        if trigger is not None:
            if trigger.cause_by == "research_request":
                # Persist the full request context for follow-up clarification rounds.
                self._base_metadata = dict(trigger.metadata)
                action_kwargs.update(self._base_metadata)
            elif trigger.cause_by == "request_clarification":
                # Use the persisted request context and add the follow-up question.
                action_kwargs.update(self._base_metadata)
                action_kwargs["follow_up"] = trigger.metadata.get("question") or trigger.content
            self._processed_trigger_ids.add(trigger.id)
        action_kwargs.setdefault("sub_id", self.role_id)
        action_kwargs.setdefault("sub_name", self.sub_name)
        action_kwargs.setdefault("focus", self.focus)
        action_kwargs.setdefault("run_ai", self.run_ai)

        response = await self.act(action, context, **action_kwargs)
        response.sent_from = self.role_id
        env.publish_message(response)
        return response
