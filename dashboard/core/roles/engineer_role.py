from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.implement_action import ImplementAction
from core.models import Message
from core.roles.base import Role


class EngineerRole(Role):
    """Engineer worker role that reacts to task assignments and implements them.

    Uses the MetaGPT-style ``_watch`` + ``set_actions`` pattern: it watches for
    ``task_assigned`` messages and executes its registered :class:`ImplementAction`.
    """

    _watch = ["task_assigned", "squad_instruction"]
    react_mode = "by_order"

    def __init__(
        self,
        role_id: str,
        focus: str,
        run_ai: Optional[Any] = None,
        repo_path: Optional[Any] = None,
        branch_prefix: str = "feature",
        update_agent: Optional[Any] = None,
        phase_name: str = "engineer_implement",
        timeout_seconds: int = 600,
    ):
        super().__init__(
            role_id=role_id,
            profile="Engineer",
            goal=f"Implement assigned tasks with focus: {focus}",
            addresses={role_id},
        )
        self.focus = focus
        self.run_ai = run_ai
        self.repo_path = Path(repo_path) if repo_path else None
        self.branch_prefix = branch_prefix
        self.update_agent = update_agent or self._default_update_agent
        self.phase_name = phase_name
        self.timeout_seconds = timeout_seconds

        # Register the single action this role performs. In the future an engineer
        # could have multiple actions (e.g. implement, test, fix) selected by react_mode.
        self.set_actions([
            ImplementAction(
                action_id=f"{role_id}-implement",
                name=f"Engineer {role_id} Implement",
                desc=f"Implement task with focus: {focus}",
            ),
        ])

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        """Return the most recent task_assigned or squad_instruction for this role."""
        # Delegate to the base trigger logic which uses _watch.
        trigger = super()._find_trigger(context)
        if trigger is not None:
            return trigger
        # Fallback for messages not yet observed by the base filter (legacy tests
        # sometimes call this method with a raw context).
        for msg in reversed(context):
            if msg.cause_by not in {"task_assigned", "squad_instruction"}:
                continue
            if msg.sent_from == self.role_id:
                continue
            if msg.id in self._processed_trigger_ids:
                continue
            if "all" in msg.send_to or self.role_id in msg.send_to:
                return msg
        return None

    async def think(self, context: List[Message]) -> Optional[ImplementAction]:
        """Select the implementation action when a task assignment is observed."""
        trigger = self._find_trigger(context)
        if trigger is None:
            self.todo = None
            return None
        # Use the action registered via set_actions.
        self.todo = self.actions[0] if self.actions else ImplementAction(
            action_id=f"{self.role_id}-implement",
            name=f"Engineer {self.role_id} Implement",
            desc=f"Implement task with focus: {self.focus}",
        )
        return self.todo

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
        self._mark_trigger_processed(trigger)

        is_squad_instruction = trigger.cause_by == "squad_instruction"
        task: Dict[str, Any] = dict(trigger.metadata.get("task", {}))
        ticket_id = trigger.metadata.get("ticket_id", "")
        ticket_title = trigger.metadata.get("ticket_title", "")
        ticket_description = trigger.metadata.get("ticket_description", "")

        repo_path = Path(trigger.metadata.get("repo_path", self.repo_path or "."))
        branch = str(
            trigger.metadata.get("branch")
            or kwargs.get("branch")
            or f"{self.branch_prefix}/{ticket_id}-{task.get('id', 'T')}".lower()
        )

        dependencies_context = trigger.metadata.get("dependencies_context", "")
        shared_context = kwargs.get("context")
        shared_reports = self._format_shared_engineer_reports(shared_context)
        if shared_reports:
            dependencies_context = (
                dependencies_context
                + ("\n\n" if dependencies_context else "")
                + "Shared engineer reports:\n"
                + shared_reports
            )
        if is_squad_instruction:
            feedback = trigger.metadata.get("instruction", "")
            extra_context = trigger.metadata.get("context", "")
            pm_answer = trigger.metadata.get("pm_answer", "")
            user_answer = trigger.metadata.get("user_answer", "")
            feedback_parts = [p for p in [feedback, extra_context, pm_answer, user_answer] if p]
            if feedback_parts:
                separator = "\n\n--- Squad Feedback ---\n\n"
                dependencies_context = dependencies_context + separator + "\n\n".join(feedback_parts)

        prd_path = trigger.metadata.get("prd_path") or kwargs.get("prd_path")
        architecture_path = trigger.metadata.get("architecture_path") or kwargs.get("architecture_path")

        action_kwargs = {
            "run_ai": self.run_ai,
            "task": task,
            "repo_path": repo_path,
            "branch": branch,
            "dependencies_context": dependencies_context,
            "prd_path": Path(prd_path) if prd_path else None,
            "architecture_path": Path(architecture_path) if architecture_path else None,
            "ticket_id": ticket_id,
            "ticket_title": ticket_title,
            "ticket_description": ticket_description,
            "agent_id": self.role_id,
            "build_prompt": kwargs.get("build_prompt") or self._default_build_prompt,
            "update_agent": kwargs.get("update_agent") or self.update_agent,
            "phase_name": kwargs.get("phase_name") or self.phase_name,
            "timeout_seconds": kwargs.get("timeout_seconds") or self.timeout_seconds,
            "shared_context": shared_context,
        }

        response = await self.act(action, context, **action_kwargs)
        response.sent_from = self.role_id
        env.publish_message(response)

        # Report back to the squad lead with the outcome.
        self._publish_task_report(env, response, task, repo_path, branch, shared_context)
        return response

    def _publish_task_report(
        self,
        env: Any,
        response: Message,
        task: Dict[str, Any],
        repo_path: Path,
        branch: str,
        shared_context: Any = None,
    ) -> None:
        task_id = str(task.get("id", ""))
        status = "completed" if response.cause_by == "task_completed" else "failed"
        self._store_shared_report(shared_context, task_id, self.role_id, status, response, repo_path, branch, task)
        report = Message(
            content=f"Report from {self.role_id}: task {task_id} {status}",
            sent_from=self.role_id,
            cause_by="task_report",
            send_to={"engineer-squad", "all"},
            metadata={
                "task_id": task_id,
                "engineer_id": self.role_id,
                "status": status,
                "summary": response.metadata.get("summary", ""),
                "repo_path": str(repo_path),
                "branch": branch,
                "build_output": response.metadata.get("build_output", ""),
                "test_output": response.metadata.get("test_output", ""),
                "fallback": response.metadata.get("fallback", False),
                "task": task,
            },
        )
        env.publish_message(report)

    def _default_build_prompt(
        self,
        *,
        task: Dict[str, Any],
        repo_path: Path,
        branch: str,
        dependencies_context: str,
        prd_path: Optional[Path],
        architecture_path: Optional[Path],
        ticket_title: str,
        ticket_description: str,
    ) -> str:
        files_section = ""
        files_to_touch = task.get("files_to_touch", []) or []
        if files_to_touch:
            files_section = "\nFiles to modify:\n" + "\n".join(f"- {f}" for f in files_to_touch)

        deps_section = ""
        if dependencies_context:
            deps_section = f"\n\nCompleted dependency context:\n{dependencies_context}"

        prd_section = ""
        if prd_path and prd_path.exists():
            prd_section = f"\n\nPRD: {prd_path}"

        arch_section = ""
        if architecture_path and architecture_path.exists():
            arch_section = f"\n\nArchitecture: {architecture_path}"

        return (
            "You are a senior software Engineer in a MetaGPT-style software factory. "
            f"Your identity is {self.role_id} and your focus is: {self.focus}.\n\n"
            "Implement the following task in the given repository and branch. "
            "Do not write explanations instead of code; generate real changes, tests when applicable, "
            "and respect project conventions.\n\n"
            f"TICKET: {ticket_title}\n"
            f"DESCRIPTION: {ticket_description}\n\n"
            f"TASK: {task.get('title', '')}\n"
            f"TASK ID: {task.get('id', '')}\n"
            f"TASK DESCRIPTION: {task.get('description', '')}\n"
            f"REPO: {repo_path}\n"
            f"BRANCH: {branch}{files_section}{deps_section}{prd_section}{arch_section}\n\n"
            "Respond with a brief summary of the changes made."
        )

    def _default_update_agent(self, agent_id: str, **kwargs) -> None:
        pass

    def _format_shared_engineer_reports(self, shared_context: Any) -> str:
        if shared_context is None or not hasattr(shared_context, "shared"):
            return ""
        reports = shared_context.shared.get("engineer_reports", {})
        if not reports:
            return ""
        lines = []
        for task_id, report in sorted(reports.items()):
            if not isinstance(report, dict):
                continue
            lines.append(
                f"- {task_id}: {report.get('status', 'unknown')} by "
                f"{report.get('engineer_id', 'unknown')} - {report.get('summary', '')[:300]}"
            )
        return "\n".join(lines)

    def _store_shared_report(
        self,
        shared_context: Any,
        task_id: str,
        engineer_id: str,
        status: str,
        response: Message,
        repo_path: Path,
        branch: str,
        task: Dict[str, Any],
    ) -> None:
        if shared_context is None or not hasattr(shared_context, "shared"):
            return
        reports = shared_context.shared.setdefault("engineer_reports", {})
        reports[task_id] = {
            "engineer_id": engineer_id,
            "status": status,
            "summary": response.metadata.get("summary", response.content[:500]),
            "repo_path": str(repo_path),
            "branch": branch,
            "build_output": response.metadata.get("build_output", ""),
            "test_output": response.metadata.get("test_output", ""),
            "fallback": response.metadata.get("fallback", False),
            "task": task,
        }
