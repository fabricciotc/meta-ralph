from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

from core.actions.architect_action import ArchitectAction
from core.actions.design_review_action import DesignReviewAction
from core.models import Message
from core.roles.base import Role


class ArchitectRole(Role):
    """Architect role that turns a PRD into an architecture.md document.

    The role reacts to ``prd_ready`` by running :class:`ArchitectAction`. If
    the resulting architecture contains pending design decisions, it triggers
    :class:`DesignReviewAction` and publishes ``design_review_requested``.
    Once ``design_review_answered`` is received, it re-runs the architect
    action with the answers and publishes ``architecture_ready``.
    """

    role_id = "architect"
    addresses = {"architect"}

    def __init__(
        self,
        actions: Optional[List[Any]] = None,
        run_ai: Optional[Any] = None,
        prd_path: Optional[Any] = None,
        architecture_path: Optional[Any] = None,
        ticket_title: str = "",
        ticket_description: str = "",
        ticket_id: str = "",
        phase_name: str = "architect",
        timeout_seconds: int = 600,
        build_architect_prompt: Optional[Any] = None,
        extract_architecture: Optional[Any] = None,
        build_design_review_prompt: Optional[Any] = None,
        parse_pending_decisions: Optional[Any] = None,
        parse_design_questions: Optional[Any] = None,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="Architect",
            goal="Design the technical architecture for a ticket based on its PRD.",
            actions=actions,
            addresses=self.addresses,
        )
        self.run_ai = run_ai
        self.prd_path = Path(prd_path) if prd_path else None
        self.architecture_path = Path(architecture_path) if architecture_path else None
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self.ticket_id = ticket_id
        self.phase_name = phase_name
        self.timeout_seconds = timeout_seconds
        self.build_architect_prompt = build_architect_prompt
        self.extract_architecture = extract_architecture
        self.build_design_review_prompt = build_design_review_prompt
        self.parse_pending_decisions = parse_pending_decisions or self._default_parse_pending_decisions
        self.parse_design_questions = parse_design_questions

        self._processed_message_ids: Set[str] = set()
        self._pending_review: bool = False
        self._architecture_ready: bool = False

    def _find_trigger(self, context: List[Message]) -> Optional[Tuple[str, Message]]:
        """Return the most recent unprocessed trigger for this role."""
        for msg in reversed(context):
            if msg.id in self._processed_message_ids:
                continue
            if msg.sent_from == self.role_id:
                continue
            if msg.cause_by == "prd_ready":
                return ("prd_ready", msg)
            if msg.cause_by == "design_review_answered":
                return ("design_review_answered", msg)
        return None

    def _action_for_trigger(self, trigger_type: str) -> Optional[Any]:
        if trigger_type == "prd_ready":
            if self._pending_review:
                # Already generated architecture and waiting for review answers.
                return None
            return ArchitectAction(
                action_id="architect-generate",
                name="Generate Architecture",
                desc="Generate architecture.md from PRD.",
            )

        if trigger_type == "design_review_answered":
            return ArchitectAction(
                action_id="architect-refine",
                name="Refine Architecture",
                desc="Refine architecture.md with design review answers.",
            )

        return None

    async def think(self, context: List[Message]) -> Optional[Any]:
        if self._architecture_ready:
            return None

        trigger = self._find_trigger(context)
        if trigger is None:
            return None

        trigger_type, trigger_msg = trigger
        self._processed_message_ids.add(trigger_msg.id)
        return self._action_for_trigger(trigger_type)

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)

        trigger = self._find_trigger(context)
        if trigger is None:
            return None

        trigger_type, trigger_msg = trigger
        self._processed_message_ids.add(trigger_msg.id)

        action = self._action_for_trigger(trigger_type)
        if action is None:
            return None

        base_kwargs = {
            "run_ai": self.run_ai,
            "prd_path": self.prd_path,
            "architecture_path": self.architecture_path,
            "ticket_title": self.ticket_title,
            "ticket_description": self.ticket_description,
            "ticket_id": self.ticket_id,
            "phase_name": self.phase_name,
            "timeout_seconds": self.timeout_seconds,
            "build_architect_prompt": self.build_architect_prompt,
            "extract_architecture": self.extract_architecture,
        }
        action_kwargs = dict(kwargs)
        action_kwargs.update(base_kwargs)

        if trigger_type == "design_review_answered":
            answers = trigger_msg.metadata.get("answers") or trigger_msg.content
            action_kwargs["review_answers"] = answers

        response = await self.act(action, context, **action_kwargs)
        response.sent_from = self.role_id

        if isinstance(action, ArchitectAction):
            if response.cause_by == "architecture_ready" and self._has_pending_decisions(response.content):
                review_action = DesignReviewAction(
                    action_id="design-review",
                    name="Design Review",
                    desc="Generate design review questions from architecture.",
                )
                review_kwargs = {
                    "run_ai": self.run_ai,
                    "architecture_content": response.content,
                    "ticket_title": self.ticket_title,
                    "ticket_description": self.ticket_description,
                    "ticket_id": self.ticket_id,
                    "phase_name": self.phase_name,
                    "timeout_seconds": self.timeout_seconds,
                    "build_design_review_prompt": self.build_design_review_prompt,
                    "parse_design_questions": self.parse_design_questions,
                }
                review_response = await self.act(review_action, context, **review_kwargs)
                review_response.sent_from = self.role_id
                self._pending_review = True
                env.publish_message(review_response)
                return review_response

            self._pending_review = False
            self._architecture_ready = True
            env.publish_message(response)
            return response

        if isinstance(action, DesignReviewAction):
            if response.cause_by == "design_review_answered":
                # No external runner or runner reported no pending decisions:
                # answers are assumed; re-run architect immediately to finalize.
                review_answers = response.metadata.get("answers") or response.content
                refined_action = ArchitectAction(
                    action_id="architect-refine",
                    name="Refine Architecture",
                    desc="Refine architecture.md with assumed design review answers.",
                )
                refined_kwargs = dict(base_kwargs)
                refined_kwargs["review_answers"] = review_answers
                refined_response = await self.act(refined_action, context, **refined_kwargs)
                refined_response.sent_from = self.role_id
                self._pending_review = False
                self._architecture_ready = True
                env.publish_message(refined_response)
                return refined_response
            self._pending_review = True
            env.publish_message(response)
            return response

        env.publish_message(response)
        return response

    def _has_pending_decisions(self, content: str) -> bool:
        decisions = self.parse_pending_decisions(content)
        return len(decisions) > 0

    def _default_parse_pending_decisions(self, content: str) -> List[str]:
        decisions: List[str] = []
        if not content:
            return decisions
        marker = "PENDING DECISIONS:"
        idx = content.find(marker)
        if idx == -1:
            return decisions
        block = content[idx + len(marker) :]
        next_header = block.find("\n#")
        if next_header != -1:
            block = block[:next_header]
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("no pending decisions"):
                continue
            if line.startswith(("-", "*")) or (line[0].isdigit() and "." in line[:3]):
                decisions.append(line)
        return decisions
