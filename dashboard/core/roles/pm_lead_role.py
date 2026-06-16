from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.actions.consolidate_prd_action import ConsolidatePRDAction
from core.models import Message
from core.roles.base import Role


class PMLeadRole(Role):
    """Lead PM role that collects research from subagents and consolidates a PRD."""

    role_id = "pm-research-agents"
    addresses = {"pm-research-agents"}

    def __init__(
        self,
        actions: Optional[List[Any]] = None,
        run_ai: Optional[Any] = None,
        ticket_title: str = "",
        ticket_description: str = "",
        prd_path: Optional[Any] = None,
        build_consolidator_prompt: Optional[Any] = None,
        extract_prd: Optional[Any] = None,
        parse_clarifications: Optional[Any] = None,
        write_fallback_prd: Optional[Any] = None,
        send_clarification: Optional[Any] = None,
        send_completion: Optional[Any] = None,
        phase_name: str = "pm_consolidate",
        timeout_seconds: int = 600,
        subagents: Optional[List[str]] = None,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="PM Lead",
            goal="Consolidate PM research findings into a PRD.",
            actions=actions,
            addresses=self.addresses,
        )
        self.run_ai = run_ai
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self.prd_path = Path(prd_path) if prd_path else None
        self.build_consolidator_prompt = build_consolidator_prompt
        self.extract_prd = extract_prd
        self.parse_clarifications = parse_clarifications
        self.write_fallback_prd = write_fallback_prd
        self.send_clarification = send_clarification
        self.send_completion = send_completion
        self.phase_name = phase_name
        self.timeout_seconds = timeout_seconds
        self.subagents: List[str] = subagents or []

        self.research_files: Dict[str, Optional[Path]] = {}
        self.pending_clarifications: Dict[str, Any] = {}
        self.prd_ready: bool = False

        self._processed_message_ids: Set[str] = set()

    def _process_message(self, msg: Message) -> None:
        if msg.id in self._processed_message_ids:
            return
        self._processed_message_ids.add(msg.id)

        if msg.cause_by == "research" and msg.sent_from != self.role_id:
            sub_id = msg.sent_from
            file_path = msg.metadata.get("file")
            if file_path:
                self.research_files[sub_id] = Path(file_path)
            else:
                self.research_files[sub_id] = None

            if sub_id in self.pending_clarifications:
                del self.pending_clarifications[sub_id]

        elif msg.cause_by == "request_clarification" and msg.sent_from != self.role_id:
            sub_id = msg.sent_from
            file_path = msg.metadata.get("file")
            if file_path:
                self.research_files[sub_id] = Path(file_path)

    async def think(self, context: List[Message]) -> Optional[ConsolidatePRDAction]:
        if self.prd_ready:
            return None

        for msg in context:
            self._process_message(msg)

        if self.pending_clarifications:
            # Wait until every pending subagent has responded with new research.
            return None

        if self.subagents and all(
            sub_id in self.research_files for sub_id in self.subagents
        ):
            return ConsolidatePRDAction(
                action_id="consolidate-prd",
                name="Consolidate PRD",
                desc="Consolidate research findings into a PRD.",
            )

        return None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        action = await self.think(context)
        if not action:
            return None

        action_kwargs = {
            "run_ai": self.run_ai,
            "ticket_title": self.ticket_title,
            "ticket_description": self.ticket_description,
            "research_files": dict(self.research_files),
            "prd_path": self.prd_path,
            "build_consolidator_prompt": self.build_consolidator_prompt,
            "extract_prd": self.extract_prd,
            "parse_clarifications": self.parse_clarifications,
            "write_fallback_prd": self.write_fallback_prd,
            "send_clarification": self.send_clarification,
            "send_completion": self.send_completion,
            "phase_name": self.phase_name,
            "timeout_seconds": self.timeout_seconds,
        }
        action_kwargs.update(kwargs)

        response = await self.act(action, context, **action_kwargs)
        response.sent_from = self.role_id

        if response.cause_by == "clarifications_requested":
            clarifications = response.metadata.get("clarifications", {})
            self.pending_clarifications = dict(clarifications)
            for sub_id, question in clarifications.items():
                env.publish_message(
                    Message(
                        content=question,
                        sent_from=self.role_id,
                        cause_by="request_clarification",
                        send_to={sub_id},
                        metadata={"question": question, "round": 2},
                    )
                )

        if response.cause_by == "prd_ready":
            self.prd_ready = True
            self.prd_path = Path(response.metadata.get("path", self.prd_path)) if response.metadata.get("path") else self.prd_path

        env.publish_message(response)
        return response
