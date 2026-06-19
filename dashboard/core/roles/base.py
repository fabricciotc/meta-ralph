from __future__ import annotations

from abc import ABC
from typing import Any, List, Optional, Set

from core.models import Message
from core.memory import Memory
from core.actions.base import Action


class Role(ABC):
    """Base class for MetaGPT-style roles.

    A role has a profile, goal, constraints, memory, and a set of actions. It
    reacts to messages whose ``cause_by`` value appears in ``_watch``.

    Inspired by MetaGPT:
    - ``_watch`` declares the message types that activate the role.
    - ``set_actions`` registers the actions the role can perform.
    - ``todo`` holds the action selected for the current round.
    - ``react_mode`` decides how the next action is chosen.
    """

    _watch: List[str] = []
    react_mode: str = "by_order"

    def __init__(
        self,
        role_id: str,
        profile: str,
        goal: str = "",
        constraints: str = "",
        actions: Optional[List[Action]] = None,
        addresses: Optional[Set[str]] = None,
    ):
        self.role_id = role_id
        self.profile = profile
        self.goal = goal
        self.constraints = constraints
        self.actions: List[Action] = list(actions) if actions else []
        self.memory = Memory()
        self.addresses = addresses or {role_id}

        self.todo: Optional[Action] = None
        self._processed_trigger_ids: Set[str] = set()

    def set_actions(self, actions: List[Action]) -> None:
        """Register the actions this role can perform."""
        self.actions = list(actions)
        self.todo = None

    def observe(self, messages: List[Message]) -> List[Message]:
        """Filter messages addressed to this role and store them in memory."""
        relevant = []
        for msg in messages:
            if "all" in msg.send_to or self.role_id in msg.send_to:
                relevant.append(msg)
        self.memory.add_batch(relevant)
        return relevant

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        """Return the most recent unprocessed message matching ``_watch``.

        Subclasses can override this to implement more sophisticated triggering,
        but the default is sufficient for the common "react to cause_by" case.
        """
        watch_set = set(self._watch)
        for msg in reversed(context):
            if msg.id in self._processed_trigger_ids:
                continue
            if msg.sent_from == self.role_id:
                continue
            if not watch_set or msg.cause_by in watch_set:
                return msg
        return None

    def _mark_trigger_processed(self, msg: Optional[Message]) -> None:
        if msg is not None:
            self._processed_trigger_ids.add(msg.id)

    def is_idle(self) -> bool:
        """Return True if the role has no pending work in memory.

        A role is idle when it has no selected action (``todo``) and no
        unprocessed trigger message in its own memory.
        """
        if self.todo is not None:
            return False
        return self._find_trigger(self.memory.get()) is None

    def should_run(self, env: Any = None) -> bool:
        """Return True if the role should be scheduled this round.

        By default a role should run when it is not idle or when its environment
        inbox contains new messages. Subclasses may override this hook to add
        custom scheduling logic.
        """
        if not self.is_idle():
            return True
        if env is not None and hasattr(env, "get_messages_for"):
            if env.get_messages_for(self.role_id):
                return True
        return False

    async def _think(self, context: List[Message]) -> Optional[Action]:
        """Default decision logic: pick the next action from ``self.actions``.

        If ``react_mode`` is ``by_order`` (default), the first registered action
        is selected whenever a matching trigger is observed. More sophisticated
        modes (e.g. LLM-based selection) can be added later.
        """
        if self.todo:
            return self.todo

        trigger = self._find_trigger(context)
        if trigger is None:
            return None

        if not self.actions:
            return None

        if self.react_mode == "by_order":
            self.todo = self.actions[0]
        else:
            # Future: LLM-based action selection.
            self.todo = self.actions[0]

        return self.todo

    async def _act(self, context: List[Message], **kwargs) -> Message:
        """Execute the current ``todo`` action and clear it."""
        if self.todo is None:
            raise RuntimeError("No action selected; call _think first.")
        response = await self.todo.run(context, **kwargs)
        self.todo = None
        return response

    async def think(self, context: List[Message]) -> Optional[Action]:
        """Public hook for choosing the next action.

        Subclasses may override this for custom logic; by default it delegates
        to :meth:`_think`.
        """
        return await self._think(context)

    async def act(self, action: Optional[Action], context: List[Message], **kwargs) -> Message:
        """Execute an action.

        ``action`` may be ``None`` when the role is using the ``todo`` pattern;
        in that case the current ``todo`` is executed.
        """
        action = action or self.todo
        if not action:
            raise ValueError("No action to execute.")
        return await action.run(context, **kwargs)

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        """Observe, think, act, publish.

        Subclasses with complex multi-step behavior may override this method,
        but simple roles can rely on ``_watch`` + ``set_actions`` + ``_think``.
        """
        messages = env.history() if hasattr(env, "history") else []
        if hasattr(env, "get_messages_for"):
            messages = messages + env.get_messages_for(self.role_id)
        context = self.observe(messages)

        action = await self.think(context)
        if not action:
            return None

        trigger = self._find_trigger(context)
        self._mark_trigger_processed(trigger)

        response = await self.act(action, context, **kwargs)
        self.todo = None
        response.sent_from = self.role_id

        if hasattr(env, "publish_message"):
            env.publish_message(response)
        return response
