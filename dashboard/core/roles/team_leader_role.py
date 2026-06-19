from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from core.ai_execution import invoke_ai
from core.models import Message
from core.roles.base import Role


class TeamLeaderRole(Role):
    """Base class for MetaGPT-style team leaders.

    A team leader coordinates workers: it receives reports/rejections, decides
    the next move (retry, request info, escalate, acknowledge), and publishes
    instructions back to the team.

    Subclasses typically override:
      - ``_build_decision_prompt`` to tailor the LLM prompt.
      - ``_fallback_decision`` to provide domain-specific defaults.
    """

    _watch: List[str] = ["task_report", "reject_with_feedback", "squad_chat"]
    addresses: Set[str] = set()

    def __init__(
        self,
        role_id: str,
        profile: str,
        run_ai: Optional[Any] = None,
        max_retries: int = 2,
        phase_name: Optional[str] = None,
        timeout_seconds: int = 300,
        **kwargs,
    ):
        super().__init__(role_id=role_id, profile=profile, addresses=self.addresses or {role_id})
        self.run_ai = run_ai
        self.max_retries = max(1, max_retries)
        self.phase_name = phase_name or role_id
        self.timeout_seconds = timeout_seconds
        self._processed_trigger_ids: Set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def think(self, context: List[Message]) -> Optional[str]:
        return "coordinate" if self._find_trigger(context) else None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None
        self._mark_trigger_processed(trigger)

        decision = await self.mediate(trigger, context)
        return self._publish_decision(decision, trigger, env)

    # ------------------------------------------------------------------
    # Decision making
    # ------------------------------------------------------------------
    async def mediate(self, trigger: Message, context: List[Message]) -> Dict[str, Any]:
        """Decide the team's next move for ``trigger``."""
        if self.run_ai is None:
            return self._fallback_decision(trigger, context)

        prompt = self._build_decision_prompt(trigger, context)
        try:
            raw = await invoke_ai(self.run_ai, prompt, self.phase_name, self.timeout_seconds, self.role_id)
            if raw:
                return self._parse_decision(raw)
        except Exception:
            pass
        return self._fallback_decision(trigger, context)

    def _build_decision_prompt(self, trigger: Message, context: List[Message]) -> str:
        event = trigger.cause_by
        task_id = trigger.metadata.get("task_id", "unknown")
        status = trigger.metadata.get("status", "unknown")
        summary = trigger.metadata.get("summary", trigger.content)
        retries = trigger.metadata.get("retries", 0)

        return (
            "You are a team leader in a multi-agent software factory. "
            "You receive a report or rejection and decide the next step.\n\n"
            f"EVENT: {event}\n"
            f"TASK: {task_id}\n"
            f"STATUS: {status}\n"
            f"SUMMARY: {summary}\n"
            f"PREVIOUS RETRIES: {retries}\n\n"
            "Respond EXACTLY with JSON in this shape:\n"
            '{\n'
            '  "action": "retry" | "request_info" | "escalate_to_user" | "ack",\n'
            '  "message": "message visible in the general chat",\n'
            '  "instruction": "concrete instruction for the worker (only if action=retry)",\n'
            '  "question": "question for another agent (only if action=request_info)",\n'
            '  "reason": "escalation reason (only if action=escalate_to_user)"\n'
            '}\n'
            "Escalate to the user only if retries are exhausted or the question is business-related."
        )

    def _parse_decision(self, raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if "```" in text:
            blocks = text.split("```")
            for block in blocks:
                candidate = block.strip()
                if candidate.startswith("{"):
                    text = candidate
                    break
        try:
            data = json.loads(text)
            if "action" in data:
                return data
        except Exception:
            pass
        return {"action": "ack", "message": "Leader acknowledged the update."}

    def _fallback_decision(self, trigger: Message, context: List[Message]) -> Dict[str, Any]:
        status = trigger.metadata.get("status", "unknown")
        retries = trigger.metadata.get("retries", 0)
        task_id = trigger.metadata.get("task_id", "unknown")
        if status == "failed" and retries < self.max_retries:
            return {
                "action": "retry",
                "message": f"Task {task_id} failed; the worker will retry.",
                "instruction": "Review the failure, fix it, and report back.",
            }
        if status == "failed":
            return {
                "action": "escalate_to_user",
                "message": f"Task {task_id} keeps failing; escalating to user.",
                "reason": "The task failed repeatedly and the leader cannot resolve it automatically.",
            }
        return {
            "action": "ack",
            "message": f"Report for {task_id} received. Continuing follow-up.",
        }

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------
    def _publish_decision(
        self,
        decision: Dict[str, Any],
        trigger: Message,
        env: Any,
    ) -> Message:
        task_id = trigger.metadata.get("task_id", "unknown")
        action = decision.get("action", "ack")
        message = decision.get("message", f"Leader update for {task_id}.")

        # Always publish a visible coordination message.
        chat_msg = Message(
            content=message,
            sent_from=self.role_id,
            cause_by="squad_chat",
            msg_type="squad_chat",
            send_to={"all"},
            metadata={"task_id": task_id, "decision": action},
        )
        env.publish_message(chat_msg)

        engineer_id = trigger.metadata.get("engineer_id") or f"engineer-{task_id}"

        if action == "retry":
            env.publish_message(Message(
                content=decision.get("instruction", "Please retry."),
                sent_from=self.role_id,
                cause_by="squad_instruction",
                msg_type="squad_instruction",
                send_to={engineer_id},
                metadata={
                    "task_id": task_id,
                    "instruction": decision.get("instruction", "Please retry."),
                    "target_role": "engineer",
                },
            ))
        elif action == "request_info":
            env.publish_message(Message(
                content=decision.get("question", f"Need more info about {task_id}"),
                sent_from=self.role_id,
                cause_by="request_info",
                msg_type="request_info",
                send_to={"product_manager"},
                metadata={"task_id": task_id, "question": decision.get("question", "")},
            ))
        elif action == "escalate_to_user":
            env.publish_message(Message(
                content=decision.get("reason", f"Need user input for {task_id}"),
                sent_from=self.role_id,
                cause_by="escalate_to_user",
                msg_type="escalate_to_user",
                send_to={"orchestrator"},
                metadata={
                    "task_id": task_id,
                    "question": decision.get("reason", f"Need user input for {task_id}"),
                },
            ))

        return chat_msg
