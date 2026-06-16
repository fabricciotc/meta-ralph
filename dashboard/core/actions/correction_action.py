from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.ai_execution import invoke_ai
from core.models import Message


def default_build_correction_prompt(
    task: Dict[str, Any],
    reason: str,
    suggested_fix: str,
    repo_path: Any,
    branch: Optional[str],
) -> str:
    """Build the default correction prompt for an engineer."""
    files = task.get("files_to_touch", []) or []
    files_str = ", ".join(str(f) for f in files) if files else "N/A"

    return (
        "You are a Senior Engineer. Generate a clear, actionable correction prompt so "
        "another Engineer can fix the issues found by QA.\n\n"
        f"TASK: {task.get('id', '')} - {task.get('title', '')}\n"
        f"DESCRIPTION: {task.get('description', '')}\n"
        f"COMPLEXITY: {task.get('complexity', 'M')}\n"
        f"FILES: {files_str}\n\n"
        f"REPO: {repo_path}\n"
        f"BRANCH: {branch or 'N/A'}\n\n"
        f"REJECTION REASON:\n{reason}\n\n"
        f"QA SUGGESTION:\n{suggested_fix or '(none provided)'}\n\n"
        "The correction prompt must:\n"
        "1. Summarize the problem in one sentence.\n"
        "2. List concrete steps to fix it.\n"
        "3. Explain how to validate locally before requesting review again.\n\n"
        "Respond in English."
    )


def default_extract_correction_prompt(output: Optional[str]) -> str:
    """Return the correction prompt, falling back to a default message."""
    if output and output.strip():
        return output.strip()
    return (
        "Fix the issues flagged by QA and request review again. "
        "Verify build/tests locally before submitting."
    )


class CorrectionAction(Action):
    """Generates a correction prompt from a QA rejection."""

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "task",
            "task_id",
            "reason",
            "suggested_fix",
            "repo_path",
            "build_correction_prompt",
            "extract_correction_prompt",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"CorrectionAction missing required kwargs: {missing}")

        task: Dict[str, Any] = kwargs["task"]
        task_id: str = kwargs["task_id"]
        reason: str = kwargs["reason"]
        suggested_fix: str = kwargs["suggested_fix"]
        repo_path: Any = kwargs["repo_path"]
        build_correction_prompt: Callable[..., str] = kwargs["build_correction_prompt"]
        extract_correction_prompt: Callable[..., str] = kwargs["extract_correction_prompt"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        branch: Optional[str] = kwargs.get("branch")

        prompt = build_correction_prompt(
            task=task,
            reason=reason,
            suggested_fix=suggested_fix,
            repo_path=repo_path,
            branch=branch,
        )

        if run_ai is None:
            content = extract_correction_prompt("")
        else:
            output = await invoke_ai(
                run_ai,
                prompt,
                phase_name,
                timeout_seconds,
                agent_id=f"qa-{task_id}",
            )
            content = extract_correction_prompt(output)

        return Message(
            content=content,
            sent_from=f"qa-{task_id}",
            cause_by="correction_prompt_ready",
            send_to={"orchestrator"},
            metadata={
                "task_id": task_id,
                "task": task,
                "reason": reason,
                "suggested_fix": suggested_fix,
            },
        )
