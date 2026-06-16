from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from core.models import Message
from core.roles.base import Role


class EngineerSquadRole(Role):
    """Lead engineer that coordinates the engineer squad.

    The squad leader receives ``task_report`` messages from every engineer,
    decides the next move and keeps the general context. It can:

    - give feedback to engineers (``squad_instruction``),
    - request more research from the PM (``request_info_from_pm``),
    - escalate a doubt to the user (``escalate_to_user``),
    - chat with engineers and other agents (``squad_chat``).

    This role is inspired by MetaGPT's team leads: it does not implement
    code itself, but organizes the workers and resolves blockers.
    """

    role_id = "engineer-squad"
    addresses = {"engineer-squad"}
    _watch = [
        "task_report",
        "request_info_from_pm_response",
        "escalate_to_user_response",
        "squad_chat",
    ]

    def __init__(
        self,
        run_ai: Optional[Any] = None,
        ticket_id: str = "",
        ticket_title: str = "",
        ticket_description: str = "",
        prd_path: Optional[Path] = None,
        tasks: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 2,
        phase_name: str = "engineer-squad",
        timeout_seconds: int = 300,
        request_clarification: Optional[Callable[[str, int], str]] = None,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="Engineer Squad Lead",
            goal="Coordinate engineer subagents, resolve blockers and keep context.",
            addresses=self.addresses,
        )
        self.run_ai = run_ai
        self.ticket_id = ticket_id
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self.prd_path = Path(prd_path) if prd_path else None
        self.tasks = list(tasks) if tasks else []
        self.max_retries = max(1, max_retries)
        self.phase_name = phase_name
        self.timeout_seconds = timeout_seconds
        self.request_clarification = request_clarification
        self._escalation_question: Optional[str] = None
        self._escalation_answer: Optional[str] = None

        self.task_reports: Dict[str, Dict[str, Any]] = {}
        self._processed_trigger_ids: Set[str] = set()
        self._pending_pm_requests: Set[str] = set()
        self._pending_user_escalations: Set[str] = set()

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        for msg in reversed(context):
            if msg.id in self._processed_trigger_ids:
                continue
            if msg.sent_from == self.role_id:
                continue
            if msg.cause_by in self._watch:
                return msg
        return None

    async def think(self, context: List[Message]) -> Optional[str]:
        return "coordinate" if self._find_trigger(context) else None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None
        self._processed_trigger_ids.add(trigger.id)

        if trigger.cause_by == "task_report":
            return await self._handle_task_report(trigger, env)
        if trigger.cause_by == "request_info_from_pm_response":
            return await self._handle_pm_response(trigger, env)
        if trigger.cause_by == "escalate_to_user_response":
            return await self._handle_user_response(trigger, env)
        if trigger.cause_by == "squad_chat":
            return await self._handle_squad_chat(trigger, env)
        return None

    async def _handle_task_report(self, trigger: Message, env: Any) -> Message:
        task_id = trigger.metadata.get("task_id", "unknown")
        engineer_id = trigger.metadata.get("engineer_id", trigger.sent_from)
        status = trigger.metadata.get("status", "unknown")
        summary = trigger.metadata.get("summary", "")
        build_output = trigger.metadata.get("build_output", "")
        test_output = trigger.metadata.get("test_output", "")
        retries = self.task_reports.get(task_id, {}).get("retries", 0)

        self.task_reports[task_id] = {
            "engineer_id": engineer_id,
            "status": status,
            "summary": summary,
            "retries": retries,
            "timestamp": trigger.created_at,
        }

        # Build squad context for the LLM decision.
        squad_context = self._build_squad_context()

        decision = await self._decide_next_move(
            event="task_report",
            task_id=task_id,
            status=status,
            summary=summary,
            build_output=build_output,
            test_output=test_output,
            retries=retries,
            squad_context=squad_context,
        )

        # Publish a visible chat message describing the squad's reaction.
        chat_msg = Message(
            content=decision.get("message", f"Reporte recibido de {engineer_id}: {status}"),
            sent_from=self.role_id,
            cause_by="squad_chat",
            send_to={"all"},
            metadata={
                "task_id": task_id,
                "status": status,
                "decision": decision.get("action"),
            },
        )
        env.publish_message(chat_msg)

        action = decision.get("action", "ack")

        if action == "retry" and status in ("failed", "needs_fix"):
            retry_count = retries + 1
            if retry_count > self.max_retries:
                env.publish_message(self._escalate_to_user(task_id, summary, retries=retry_count))
            else:
                self.task_reports[task_id]["retries"] = retry_count
                env.publish_message(self._instruction_to_engineer(
                    task_id=task_id,
                    engineer_id=engineer_id,
                    instruction=decision.get("instruction", "Review the error and try again."),
                    context=decision.get("context", ""),
                ))
            return chat_msg

        if action == "request_info_from_pm":
            question = decision.get("question", f"I need more context about {task_id}")
            pm_msg = self._request_info_from_pm(task_id, question)
            self._pending_pm_requests.add(pm_msg.metadata.get("request_id", task_id))
            env.publish_message(pm_msg)
            return chat_msg

        if action == "escalate_to_user":
            env.publish_message(self._escalate_to_user(task_id, summary))
            if self.request_clarification:
                await self._ask_user_and_forward(task_id, summary, env)
            return chat_msg

        # Check if the whole batch is done.
        if self._all_tasks_reported() and self._all_tasks_done():
            env.publish_message(Message(
                content="All squad tasks completed. Sending batch to QA.",
                sent_from=self.role_id,
                cause_by="batch_completed",
                send_to={"orchestrator"},
                metadata={"task_ids": list(self.task_reports.keys()), "status": "completed"},
            ))

        return chat_msg

    async def _handle_pm_response(self, trigger: Message, env: Any) -> Optional[Message]:
        request_id = trigger.metadata.get("request_id", "")
        self._pending_pm_requests.discard(request_id)
        task_id = trigger.metadata.get("task_id", "unknown")
        answer = trigger.metadata.get("answer", "")

        # Forward the PM answer to the interested engineer and the general chat.
        engineer_id = self._engineer_for_task(task_id)
        env.publish_message(Message(
            content=f"PM answered about {task_id}: {answer}",
            sent_from=self.role_id,
            cause_by="squad_chat",
            send_to={"all"},
            metadata={"task_id": task_id, "source": "pm_response"},
        ))
        if engineer_id:
            env.publish_message(Message(
                content=f"Additional PM information: {answer}",
                sent_from=self.role_id,
                cause_by="squad_instruction",
                send_to={engineer_id},
                metadata={
                    "task_id": task_id,
                    "instruction": "continue",
                    "pm_answer": answer,
                    "context": trigger.metadata.get("context", ""),
                },
            ))
        return None

    async def _handle_user_response(self, trigger: Message, env: Any) -> Optional[Message]:
        escalation_id = trigger.metadata.get("escalation_id", "")
        self._pending_user_escalations.discard(escalation_id)
        task_id = trigger.metadata.get("task_id", "unknown")
        answer = trigger.metadata.get("answer", "")
        engineer_id = self._engineer_for_task(task_id)

        env.publish_message(Message(
            content=f"User answered about {task_id}: {answer}",
            sent_from=self.role_id,
            cause_by="squad_chat",
            send_to={"all"},
            metadata={"task_id": task_id, "source": "user_response"},
        ))
        if engineer_id:
            env.publish_message(Message(
                content=f"User answer: {answer}",
                sent_from=self.role_id,
                cause_by="squad_instruction",
                send_to={engineer_id},
                metadata={
                    "task_id": task_id,
                    "instruction": "continue",
                    "user_answer": answer,
                },
            ))
        return None

    async def _handle_squad_chat(self, trigger: Message, env: Any) -> Optional[Message]:
        # Squad can be @mentioned. For now, just acknowledge and keep context.
        if trigger.sent_from == self.role_id:
            return None
        return Message(
            content=f"Squad received a message from {trigger.sent_from}. Processing...",
            sent_from=self.role_id,
            cause_by="squad_chat",
            send_to={trigger.sent_from, "all"},
            metadata={"original_message": trigger.content},
        )

    def _instruction_to_engineer(
        self,
        task_id: str,
        engineer_id: str,
        instruction: str,
        context: str,
    ) -> Message:
        return Message(
            content=f"Squad instruction for {engineer_id}: {instruction}",
            sent_from=self.role_id,
            cause_by="squad_instruction",
            send_to={engineer_id},
            metadata={
                "task_id": task_id,
                "instruction": instruction,
                "context": context,
                "target_role": "engineer",
            },
        )

    def _request_info_from_pm(self, task_id: str, question: str) -> Message:
        request_id = f"pm-req-{task_id}"
        self._pending_pm_requests.add(request_id)
        return Message(
            content=f"Squad requests more PM information about {task_id}: {question}",
            sent_from=self.role_id,
            cause_by="request_info_from_pm",
            send_to={"pm-research-agents", "product_manager"},
            metadata={
                "request_id": request_id,
                "task_id": task_id,
                "question": question,
            },
        )

    def _escalate_to_user(self, task_id: str, reason: str, retries: int = 0) -> Message:
        escalation_id = f"esc-{task_id}"
        self._pending_user_escalations.add(escalation_id)
        return Message(
            content=f"Squad escalates the question for {task_id} to the user: {reason}",
            sent_from=self.role_id,
            cause_by="escalate_to_user",
            send_to={"orchestrator"},
            metadata={
                "escalation_id": escalation_id,
                "task_id": task_id,
                "question": f"The squad needs clarification for task {task_id}: {reason}",
                "retries": retries,
            },
        )

    async def _ask_user_and_forward(self, task_id: str, reason: str, env: Any) -> None:
        """Block while the user answers the escalation, then forward it."""
        if not self.request_clarification:
            return
        question = f"The squad needs clarification for task {task_id}: {reason}"
        self._escalation_question = question
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(self.request_clarification, question, self.timeout_seconds),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            answer = "No user answer before the timeout."
        self._escalation_answer = answer
        synthetic = Message(
            content=f"User answered about {task_id}: {answer}",
            sent_from="user",
            cause_by="escalate_to_user_response",
            send_to={self.role_id},
            metadata={
                "escalation_id": f"esc-{task_id}",
                "task_id": task_id,
                "answer": answer,
            },
        )
        await self._handle_user_response(synthetic, env)

    def _engineer_for_task(self, task_id: str) -> Optional[str]:
        report = self.task_reports.get(task_id)
        if report:
            return report.get("engineer_id")
        return None

    def _all_tasks_reported(self) -> bool:
        if not self.tasks:
            return False
        task_ids = {str(t.get("id", "")) for t in self.tasks}
        return task_ids.issubset(set(self.task_reports.keys()))

    def _all_tasks_done(self) -> bool:
        return all(r.get("status") == "completed" for r in self.task_reports.values())

    def _build_squad_context(self) -> str:
        parts = [
            f"Ticket: {self.ticket_title}",
            f"Description: {self.ticket_description}",
        ]
        if self.prd_path and self.prd_path.exists():
            try:
                parts.append(f"PRD: {self.prd_path.read_text(encoding='utf-8')[:1000]}")
            except Exception:
                pass
        if self.tasks:
            tasks_summary = "\n".join(
                f"- {t.get('id')}: {t.get('title')}" for t in self.tasks
            )
            parts.append(f"Planned tasks:\n{tasks_summary}")
        reports_summary = "\n".join(
            f"- {tid}: {r.get('status')} (engineer {r.get('engineer_id')}, retries {r.get('retries', 0)})"
            for tid, r in self.task_reports.items()
        )
        parts.append(f"Received reports:\n{reports_summary}")
        return "\n\n".join(parts)

    async def _decide_next_move(self, **kwargs) -> Dict[str, Any]:
        """Use the configured AI backend to decide the squad's next move.

        Returns a dict with keys: action, message, instruction|question|reason.
        """
        if self.run_ai is None:
            return self._fallback_decision(kwargs)

        prompt = self._build_decision_prompt(kwargs)
        try:
            raw = self.run_ai(prompt, self.phase_name, self.timeout_seconds, self.role_id)
            if raw:
                return self._parse_decision(raw)
        except Exception:
            pass
        return self._fallback_decision(kwargs)

    def _build_decision_prompt(self, kwargs: Dict[str, Any]) -> str:
        event = kwargs.get("event")
        task_id = kwargs.get("task_id", "unknown")
        status = kwargs.get("status", "unknown")
        summary = kwargs.get("summary", "")
        build_output = kwargs.get("build_output", "")
        test_output = kwargs.get("test_output", "")
        retries = kwargs.get("retries", 0)
        squad_context = kwargs.get("squad_context", "")

        return (
            "You are the Engineering Squad Lead in a MetaGPT-style software factory. "
            "You receive Engineer reports and decide the next step.\n\n"
            f"EVENTO: {event}\n"
            f"TASK: {task_id}\n"
            f"STATUS: {status}\n"
            f"SUMMARY: {summary}\n"
            f"BUILD OUTPUT:\n{build_output}\n\n"
            f"TEST OUTPUT:\n{test_output}\n\n"
            f"PREVIOUS RETRIES: {retries}\n\n"
            f"SQUAD CONTEXT:\n{squad_context}\n\n"
            "Respond EXACTLY with JSON in this shape:\n"
            '{\n'
            '  "action": "retry" | "request_info_from_pm" | "escalate_to_user" | "ack",\n'
            '  "message": "message visible in the general chat",\n'
            '  "instruction": "concrete instruction for the Engineer (only if action=retry)",\n'
            '  "question": "question for the PM (only if action=request_info_from_pm)",\n'
            '  "reason": "escalation reason (only if action=escalate_to_user)"\n'
            '}\n'
            "If status is failed and retries are available, prefer retry. "
            "Escalate to the user only if retries are exhausted or the question is business-related."
        )

    def _parse_decision(self, raw: str) -> Dict[str, Any]:
        text = raw.strip()
        # Try to extract JSON if wrapped in markdown fences.
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
        return self._fallback_decision({})

    def _fallback_decision(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        status = kwargs.get("status", "unknown")
        retries = kwargs.get("retries", 0)
        task_id = kwargs.get("task_id", "unknown")
        if status == "failed" and retries < self.max_retries:
            return {
                "action": "retry",
                "message": f"Task {task_id} failed; the Engineer will be instructed to retry.",
                "instruction": "Review the build/test error, fix it, and rerun the task.",
            }
        if status == "failed":
            return {
                "action": "escalate_to_user",
                "message": f"Task {task_id} is still failing after several attempts; it will be escalated to the user.",
                "reason": "The task failed repeatedly and the squad cannot resolve it automatically.",
            }
        return {
            "action": "ack",
            "message": f"Report for {task_id} received. Continuing follow-up.",
        }
