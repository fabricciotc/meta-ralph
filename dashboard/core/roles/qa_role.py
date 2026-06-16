from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from core.actions.correction_action import (
    CorrectionAction,
    default_build_correction_prompt,
    default_extract_correction_prompt,
)
from core.actions.review_action import (
    ReviewAction,
    default_build_review_prompt,
    default_extract_review_result,
)
from core.models import Message
from core.roles.base import Role


class QASubRole(Role):
    """Per-task QA subagent that executes ReviewAction for a single task."""

    def __init__(
        self,
        task_id: str,
        task: Dict[str, Any],
        run_ai: Optional[Any] = None,
        build_review_prompt: Optional[Callable[..., str]] = None,
        extract_review_result: Optional[Callable[..., Dict[str, Any]]] = None,
        build_correction_prompt: Optional[Callable[..., str]] = None,
        extract_correction_prompt: Optional[Callable[..., str]] = None,
    ):
        super().__init__(
            role_id=f"qa-{task_id}",
            profile=f"QA Engineer for {task_id}",
            goal=f"Review task {task_id} and approve or reject with feedback.",
            addresses={f"qa-{task_id}"},
        )
        self.task_id = task_id
        self.task = task
        self.run_ai = run_ai
        self.build_review_prompt = build_review_prompt or default_build_review_prompt
        self.extract_review_result = extract_review_result or default_extract_review_result
        self.build_correction_prompt = build_correction_prompt or default_build_correction_prompt
        self.extract_correction_prompt = extract_correction_prompt or default_extract_correction_prompt

    async def think(self, context: List[Message]) -> Optional[ReviewAction]:
        """Not used directly; QARole invokes review() instead."""
        return None

    async def review(self, context: List[Message], **kwargs) -> Message:
        """Run ReviewAction for this task and return the verdict message."""
        action = ReviewAction(
            action_id=f"review-{self.task_id}",
            name=f"Review {self.task_id}",
            desc=f"Review task {self.task_id}.",
        )
        action_kwargs = {
            "task": self.task,
            "task_id": self.task_id,
            "repo_path": kwargs.get("repo_path", "."),
            "branch": kwargs.get("branch"),
            "diff": kwargs.get("diff", ""),
            "build_output": kwargs.get("build_output", ""),
            "test_output": kwargs.get("test_output", ""),
            "build_review_prompt": self.build_review_prompt,
            "extract_review_result": self.extract_review_result,
            "phase_name": kwargs.get("phase_name", "qa_review"),
            "timeout_seconds": kwargs.get("timeout_seconds", 120),
            "run_ai": self.run_ai,
            "shared_context": kwargs.get("shared_context"),
        }
        return await action.run(context, **action_kwargs)

    async def generate_correction_prompt(
        self,
        context: List[Message],
        reason: str,
        suggested_fix: str,
        **kwargs,
    ) -> Message:
        """Run CorrectionAction for this task and return the correction prompt."""
        action = CorrectionAction(
            action_id=f"correction-{self.task_id}",
            name=f"Correction prompt for {self.task_id}",
            desc=f"Generate correction prompt for task {self.task_id}.",
        )
        action_kwargs = {
            "task": self.task,
            "task_id": self.task_id,
            "reason": reason,
            "suggested_fix": suggested_fix,
            "repo_path": kwargs.get("repo_path", "."),
            "branch": kwargs.get("branch"),
            "build_correction_prompt": self.build_correction_prompt,
            "extract_correction_prompt": self.extract_correction_prompt,
            "phase_name": kwargs.get("phase_name", "qa_correction"),
            "timeout_seconds": kwargs.get("timeout_seconds", 120),
            "run_ai": self.run_ai,
            "shared_context": kwargs.get("shared_context"),
        }
        return await action.run(context, **action_kwargs)


class QARole(Role):
    """Lead QA role that coordinates per-task reviews and up to N correction rounds."""

    role_id = "qa-lead"
    addresses = {"qa-lead"}

    def __init__(
        self,
        run_ai: Optional[Any] = None,
        max_rounds: int = 3,
        force_approve_on_max_rounds: bool = False,
        build_review_prompt: Optional[Callable[..., str]] = None,
        extract_review_result: Optional[Callable[..., Dict[str, Any]]] = None,
        build_correction_prompt: Optional[Callable[..., str]] = None,
        extract_correction_prompt: Optional[Callable[..., str]] = None,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="QA Lead",
            goal="Coordinate QA reviews and enforce correction round limits.",
            addresses=self.addresses,
        )
        self.run_ai = run_ai
        self.max_rounds = max(1, max_rounds)
        self.force_approve_on_max_rounds = force_approve_on_max_rounds
        self.build_review_prompt = build_review_prompt or default_build_review_prompt
        self.extract_review_result = extract_review_result or default_extract_review_result
        self.build_correction_prompt = build_correction_prompt or default_build_correction_prompt
        self.extract_correction_prompt = extract_correction_prompt or default_extract_correction_prompt

        self._sub_roles: Dict[str, QASubRole] = {}
        self._review_state: Dict[str, Dict[str, Any]] = {}
        self._processed_message_ids: Set[str] = set()

    def _ensure_sub_role(self, task_id: str, task: Dict[str, Any]) -> QASubRole:
        if task_id not in self._sub_roles:
            self._sub_roles[task_id] = QASubRole(
                task_id=task_id,
                task=task,
                run_ai=self.run_ai,
                build_review_prompt=self.build_review_prompt,
                extract_review_result=self.extract_review_result,
                build_correction_prompt=self.build_correction_prompt,
                extract_correction_prompt=self.extract_correction_prompt,
            )
        return self._sub_roles[task_id]

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        """Return the most recent unprocessed request_review message."""
        for msg in reversed(context):
            if msg.cause_by != "request_review":
                continue
            if msg.id in self._processed_message_ids:
                continue
            return msg
        return None

    def _find_triggers(self, context: List[Message]) -> List[Message]:
        """Return all unprocessed review requests in observation order."""
        return [
            msg
            for msg in context
            if msg.cause_by == "request_review"
            and msg.id not in self._processed_message_ids
        ]

    async def think(self, context: List[Message]) -> Optional[Any]:
        """Not used directly; run() coordinates the full review flow."""
        return None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        """Observe, review, and publish approved/rejected messages."""
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)

        triggers = self._find_triggers(context)
        if not triggers:
            return None
        for trigger in triggers:
            self._processed_message_ids.add(trigger.id)

        results = await asyncio.gather(*[
            self._review_trigger(trigger, context, kwargs)
            for trigger in triggers
        ])
        for result in results:
            env.publish_message(result)

        if len(results) == 1:
            return results[0]

        approved = sum(1 for msg in results if msg.cause_by == "review_approved")
        rejected = sum(1 for msg in results if msg.cause_by == "reject_with_feedback")
        return Message(
            content=f"QA batch reviewed: {approved} approved, {rejected} rejected.",
            sent_from=self.role_id,
            cause_by="qa_batch_reviewed",
            send_to={"orchestrator"},
            metadata={"approved": approved, "rejected": rejected},
        )

    async def _review_trigger(
        self,
        trigger: Message,
        context: List[Message],
        kwargs: Dict[str, Any],
    ) -> Message:
        task = trigger.metadata.get("task") or {}
        task_id = trigger.metadata.get("task_id") or task.get("id") or "unknown"
        state = self._review_state.setdefault(task_id, {"rounds": 0, "history": []})

        if state["rounds"] >= self.max_rounds:
            if self.force_approve_on_max_rounds:
                msg = Message(
                    content=f"Task {task_id} approved after {self.max_rounds} correction rounds.",
                    sent_from=self.role_id,
                    cause_by="review_approved",
                    send_to={"orchestrator"},
                    metadata={
                        "task_id": task_id,
                        "task": task,
                        "approved": True,
                        "reason": f"Forced approval after {self.max_rounds} correction rounds.",
                        "suggested_fix": "",
                        "forced": True,
                    },
                )
                state["rounds"] = 0
                self._store_review_context(kwargs.get("context"), task_id, msg.metadata)
                return msg
            msg = Message(
                content=f"Task {task_id} still rejected after {self.max_rounds} review rounds.",
                sent_from=self.role_id,
                cause_by="reject_with_feedback",
                send_to={"orchestrator"},
                metadata={
                    "task_id": task_id,
                    "task": task,
                    "approved": False,
                    "reason": f"Task still failing after {self.max_rounds} QA review rounds.",
                    "suggested_fix": "Engineer must address all QA findings before the ticket can complete.",
                    "max_rounds_exceeded": True,
                },
            )
            self._store_review_context(kwargs.get("context"), task_id, msg.metadata)
            return msg

        sub_role = self._ensure_sub_role(task_id, task)
        action_kwargs = {
            "repo_path": trigger.metadata.get("repo_path", "."),
            "branch": trigger.metadata.get("branch"),
            "diff": trigger.metadata.get("diff", ""),
            "build_output": trigger.metadata.get("build_output", ""),
            "test_output": trigger.metadata.get("test_output", ""),
            "phase_name": kwargs.get("phase_name", "qa_review"),
            "timeout_seconds": kwargs.get("timeout_seconds", 120),
            "shared_context": kwargs.get("context"),
        }

        result = await sub_role.review(context, **action_kwargs)
        result.sent_from = self.role_id

        if result.cause_by == "review_approved":
            state["rounds"] = 0
        else:
            state["rounds"] += 1
        state["history"].append({
            "cause_by": result.cause_by,
            "reason": result.metadata.get("reason", ""),
        })
        self._store_review_context(kwargs.get("context"), task_id, result.metadata)
        return result

    def _store_review_context(self, shared_context: Any, task_id: str, metadata: Dict[str, Any]) -> None:
        if shared_context is None or not hasattr(shared_context, "shared"):
            return
        reviews = shared_context.shared.setdefault("qa_reviews", {})
        reviews[task_id] = {
            "approved": bool(metadata.get("approved", False)),
            "reason": metadata.get("reason", ""),
            "suggested_fix": metadata.get("suggested_fix", ""),
            "forced": metadata.get("forced", False),
        }

    async def generate_correction_prompt(
        self,
        context: List[Message],
        task_id: str,
        task: Dict[str, Any],
        reason: str,
        suggested_fix: str,
        **kwargs,
    ) -> Message:
        """Convenience helper to generate a correction prompt for a task."""
        sub_role = self._ensure_sub_role(task_id, task)
        return await sub_role.generate_correction_prompt(
            context,
            reason=reason,
            suggested_fix=suggested_fix,
            **kwargs,
        )
