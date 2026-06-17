from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.ai_execution import invoke_ai
from core.models import Message


def default_build_review_prompt(
    task: Dict[str, Any],
    diff: str,
    build_output: str,
    test_output: str,
    repo_path: Any,
    branch: Optional[str],
) -> str:
    """Build the default QA review prompt."""
    checklist = task.get("qa_checklist", []) or []
    checklist_str = "\n".join(f"- {item}" for item in checklist) or "- No checklist provided."
    files = task.get("files_to_touch", []) or []
    files_str = ", ".join(str(f) for f in files) if files else "N/A"

    return (
        "You are an expert QA Engineer. Review this task's changes and decide whether to approve or reject them. "
        "Write the reason and suggestion as direct, actionable feedback to the implementing Engineer.\n\n"
        f"TASK: {task.get('id', '')} - {task.get('title', '')}\n"
        f"DESCRIPTION: {task.get('description', '')}\n"
        f"COMPLEXITY: {task.get('complexity', 'M')}\n"
        f"FILES: {files_str}\n"
        f"CHECKLIST QA:\n{checklist_str}\n\n"
        f"REPO: {repo_path}\n"
        f"BRANCH: {branch or 'N/A'}\n\n"
        f"DIFF:\n{diff or '(no diff provided)'}\n\n"
        f"BUILD OUTPUT:\n{build_output or '(no build output)'}\n\n"
        f"TEST OUTPUT:\n{test_output or '(no test output)'}\n\n"
        "Respond EXACTLY in this format. Choose ONE verdict only. Do not include both options or the pipe character.\n\n"
        "VERDICT: <APPROVED or REJECTED>\n"
        "REASON: <concise reason>\n"
        "SUGGESTION: <correction suggestion if applicable>"
    )


def default_extract_review_result(output: Optional[str]) -> Dict[str, Any]:
    """Extract the review verdict from runner output.

    The QA prompt asks for a strict format:
        VERDICT: <APPROVED or REJECTED>
        REASON: <concise reason>
        SUGGESTION: <correction suggestion if applicable>

    This parser first looks for an explicit, unambiguous ``VERDICT`` line.
    If the model repeated the placeholder ``APPROVED|REJECTED`` or omitted
    the verdict entirely, the review is rejected with a clear formatting
    error so the agent can recover on the next round.
    """
    if not output:
        return {
            "approved": False,
            "reason": "No output from QA reviewer.",
            "suggested_fix": "Re-run the review with build/test evidence.",
        }

    text = output.strip()
    lines = [line.strip() for line in text.splitlines()]

    approved: Optional[bool] = None
    # Look for an explicit, single-value verdict line first.
    for line in lines:
        upper = line.upper()
        if not upper.startswith("VERDICT:"):
            continue
        verdict_value = line.split(":", 1)[1].strip().upper()
        if verdict_value == "APPROVED":
            approved = True
            break
        if verdict_value == "REJECTED":
            approved = False
            break

    if approved is None:
        return {
            "approved": False,
            "reason": "QA response did not contain a clear APPROVED or REJECTED verdict.",
            "suggested_fix": (
                "Respond EXACTLY with one of these lines and nothing else for VERDICT:\n"
                "VERDICT: APPROVED\n"
                "VERDICT: REJECTED"
            ),
        }

    reason = ""
    suggested_fix = ""
    for line in lines:
        upper = line.upper()
        if upper.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
        elif upper.startswith("SUGGESTION:"):
            suggested_fix = line.split(":", 1)[1].strip()

    # Ignore placeholder remnants; fall back to the first 300 characters.
    if not reason or reason in ("<CONCISE REASON>", "<YOUR CONCISE REASON>"):
        reason = text[:300]

    return {
        "approved": approved,
        "reason": reason,
        "suggested_fix": suggested_fix,
    }


class ReviewAction(Action):
    """Reviews a completed task and returns approval or rejection."""

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "task",
            "task_id",
            "repo_path",
            "build_review_prompt",
            "extract_review_result",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"ReviewAction missing required kwargs: {missing}")

        task: Dict[str, Any] = kwargs["task"]
        task_id: str = kwargs["task_id"]
        repo_path: Any = kwargs["repo_path"]
        build_review_prompt: Callable[..., str] = kwargs["build_review_prompt"]
        extract_review_result: Callable[..., Dict[str, Any]] = kwargs["extract_review_result"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        branch: Optional[str] = kwargs.get("branch")
        diff: str = kwargs.get("diff", "")
        build_output: str = kwargs.get("build_output", "")
        test_output: str = kwargs.get("test_output", "")

        prompt = build_review_prompt(
            task=task,
            diff=diff,
            build_output=build_output,
            test_output=test_output,
            repo_path=repo_path,
            branch=branch,
        )

        result: Dict[str, Any]
        if run_ai is None:
            result = extract_review_result("")
        else:
            output = await invoke_ai(
                run_ai,
                prompt,
                phase_name,
                timeout_seconds,
                agent_id=f"qa-{task_id}",
            )
            result = extract_review_result(output)

        approved = bool(result.get("approved", False))
        reason = str(result.get("reason", ""))
        suggested_fix = str(result.get("suggested_fix", ""))

        cause_by = "review_approved" if approved else "reject_with_feedback"
        metadata: Dict[str, Any] = {
            "task_id": task_id,
            "task": task,
            "approved": approved,
            "reason": reason,
            "suggested_fix": suggested_fix,
        }
        shared_context = kwargs.get("shared_context") or kwargs.get("context")
        if shared_context is not None and hasattr(shared_context, "shared"):
            reviews = shared_context.shared.setdefault("qa_reviews", {})
            reviews[task_id] = {
                "approved": approved,
                "reason": reason,
                "suggested_fix": suggested_fix,
                "branch": branch,
            }

        return Message(
            content=reason,
            sent_from=f"qa-{task_id}",
            cause_by=cause_by,
            send_to={"orchestrator"},
            metadata=metadata,
        )
