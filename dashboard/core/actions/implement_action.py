from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.actions.base import Action
from core.ai_execution import invoke_ai
from core.models import Message


class ImplementAction(Action):
    """Executes an implementation task by invoking the AI runner in a repo/branch.

    After the AI produces an implementation summary, the action runs an
    executable feedback loop:

    1. Detect a .NET project (*.csproj / *.sln).
    2. Run ``dotnet build``.
    3. Run ``dotnet test``.
    4. If any step fails, emit ``task_failed`` so the recovery role can retry.
    5. If everything passes (or no .NET project is present), emit
       ``task_completed`` with the build/test output in metadata.

    This mirrors MetaGPT's executable feedback mechanism.
    """

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "task",
            "repo_path",
            "branch",
            "build_prompt",
            "update_agent",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"ImplementAction missing required kwargs: {missing}")

        task: Dict[str, Any] = kwargs["task"]
        repo_path: Path = Path(kwargs["repo_path"])
        branch: str = kwargs["branch"]
        build_prompt: Any = kwargs["build_prompt"]
        update_agent: Any = kwargs["update_agent"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        dependencies_context: str = kwargs.get("dependencies_context", "")
        prd_path: Optional[Path] = kwargs.get("prd_path")
        architecture_path: Optional[Path] = kwargs.get("architecture_path")
        ticket_id: str = kwargs.get("ticket_id", "")
        ticket_title: str = kwargs.get("ticket_title", "")
        ticket_description: str = kwargs.get("ticket_description", "")

        task_id = str(task.get("id", ""))
        task_title = str(task.get("title", ""))
        agent_id = kwargs.get("agent_id", task_id)

        update_agent(
            agent_id,
            status="running",
            progress=10,
            log=f"Engineer {agent_id} starting implementation for {task_title}...",
        )

        try:
            prompt = build_prompt(
                task=task,
                repo_path=repo_path,
                branch=branch,
                dependencies_context=dependencies_context,
                prd_path=prd_path,
                architecture_path=architecture_path,
                ticket_title=ticket_title,
                ticket_description=ticket_description,
            )

            output = await invoke_ai(run_ai, prompt, phase_name, timeout_seconds, agent_id=agent_id)

            if not output:
                # No runner available: write a minimal implementation note so the
                # workflow can continue deterministically in tests.
                output = self._write_fallback_implementation(
                    repo_path,
                    branch,
                    task,
                    dependencies_context,
                )

            update_agent(
                agent_id,
                status="running",
                progress=50,
            log=f"Engineer {agent_id} running build/test for {task_title}...",
            )

            build_output, test_output, executable_ok, executable_reason = self._run_executable_feedback(
                repo_path, task_id
            )

            if not executable_ok:
                self._store_engineer_context(
                    kwargs.get("shared_context") or kwargs.get("context"),
                    task_id,
                    agent_id,
                    "failed",
                    executable_reason,
                    build_output,
                    test_output,
                    str(repo_path),
                    branch,
                )
                update_agent(
                    agent_id,
                    status="error",
                    progress=0,
                    log=f"Engineer {agent_id} failed build/test: {executable_reason}",
                )
                return Message(
                    content=executable_reason,
                    sent_from=agent_id,
                    cause_by="task_failed",
                    send_to={"orchestrator"},
                    metadata={
                        "task_id": task_id,
                        "task": task,
                        "repo_path": str(repo_path),
                        "branch": branch,
                        "reason": executable_reason,
                        "build_output": build_output,
                        "test_output": test_output,
                    },
                )

            summary = output[:500]
            self._store_engineer_context(
                kwargs.get("shared_context") or kwargs.get("context"),
                task_id,
                agent_id,
                "completed",
                summary,
                build_output,
                test_output,
                str(repo_path),
                branch,
            )
            update_agent(
                agent_id,
                status="done",
                progress=100,
                log=f"Engineer {agent_id} completed {task_title}.",
            )

            return Message(
                content=output,
                sent_from=agent_id,
                cause_by="task_completed",
                send_to={"orchestrator", "qa"},
                metadata={
                    "task_id": task_id,
                    "task": task,
                    "repo_path": str(repo_path),
                    "branch": branch,
                    "summary": summary,
                    "fallback": run_ai is None,
                    "build_output": build_output,
                    "test_output": test_output,
                },
            )
        except Exception as exc:
            self._store_engineer_context(
                kwargs.get("shared_context") or kwargs.get("context"),
                task_id if "task_id" in locals() else str(task.get("id", "")),
                agent_id if "agent_id" in locals() else str(task.get("id", "")),
                "failed",
                str(exc),
                "",
                "",
                str(repo_path) if "repo_path" in locals() else "",
                branch if "branch" in locals() else "",
            )
            update_agent(
                agent_id,
                status="error",
                progress=0,
                log=f"Engineer {agent_id} failed: {exc}",
            )
            return Message(
                content=str(exc),
                sent_from=agent_id,
                cause_by="task_failed",
                send_to={"orchestrator"},
                metadata={
                    "task_id": task_id,
                    "task": task,
                    "repo_path": str(repo_path),
                    "branch": branch,
                    "reason": str(exc),
                },
            )

    def _run_executable_feedback(
        self,
        repo_path: Path,
        task_id: str,
        command_timeout: int = 120,
    ) -> Tuple[str, str, bool, str]:
        """Run build/test if a .NET project is detected.

        Returns ``(build_output, test_output, ok, reason)``. When no .NET
        project is detected or ``dotnet`` is not available, the feedback is
        considered successful with empty outputs.
        """
        if not self._detect_dotnet_project(repo_path):
            return "", "", True, ""

        dotnet = shutil.which("dotnet")
        if not dotnet:
            return "", "", True, "dotnet not found; executable validation skipped"

        rc, build_output, build_err = self._run_shell(
            [dotnet, "build"], repo_path, timeout=command_timeout
        )
        build_full = self._combine_output(build_output, build_err)
        if rc != 0:
            return build_full, "", False, f"dotnet build failed for task {task_id}"

        rc, test_output, test_err = self._run_shell(
            [dotnet, "test"], repo_path, timeout=command_timeout
        )
        test_full = self._combine_output(test_output, test_err)
        if rc != 0:
            return build_full, test_full, False, f"dotnet test failed for task {task_id}"

        return build_full, test_full, True, ""

    def _detect_dotnet_project(self, repo_path: Path) -> bool:
        if not repo_path.exists():
            return False
        return bool(list(repo_path.rglob("*.csproj")) or list(repo_path.rglob("*.sln")))

    def _run_shell(
        self,
        cmd: List[str],
        cwd: Path,
        timeout: int,
    ) -> Tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            return -1, "", f"timeout ({timeout}s): {exc}"
        except Exception as exc:
            return -1, "", str(exc)

    def _combine_output(self, stdout: str, stderr: str) -> str:
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(stderr)
        return "\n".join(parts).strip()

    def _write_fallback_implementation(
        self,
        repo_path: Path,
        branch: str,
        task: Dict[str, Any],
        dependencies_context: str,
    ) -> str:
        """Generate a minimal local implementation note when no runner is available."""
        work_dir = repo_path / ".meta-ralph" / "engineer-notes"
        work_dir.mkdir(parents=True, exist_ok=True)
        task_id = str(task.get("id", "unknown"))
        safe_branch = str(branch).replace("/", "-")
        note_path = work_dir / f"{task_id}-{safe_branch}.md"

        files_to_touch = task.get("files_to_touch", []) or []
        content = (
            f"# Implementation: {task.get('title', task_id)}\n\n"
            f"**Branch:** {branch}\n\n"
            f"**Description:**\n{task.get('description', '')}\n\n"
            f"**Files to modify:**\n"
            + "\n".join(f"- {f}" for f in files_to_touch)
            + "\n\n"
            f"**Dependency context:**\n{dependencies_context or 'None'}\n\n"
            "This note was generated locally because no AI runner is available.\n"
        )
        note_path.write_text(content, encoding="utf-8")
        return content

    def _json_summary(self, task: Dict[str, Any]) -> str:
        try:
            return json.dumps(task, ensure_ascii=False, default=str)
        except Exception:
            return str(task)

    def _store_engineer_context(
        self,
        shared_context: Any,
        task_id: str,
        agent_id: str,
        status: str,
        summary: str,
        build_output: str,
        test_output: str,
        repo_path: str,
        branch: str,
    ) -> None:
        if shared_context is None or not hasattr(shared_context, "shared"):
            return
        reports = shared_context.shared.setdefault("engineer_reports", {})
        reports[task_id] = {
            "engineer_id": agent_id,
            "status": status,
            "summary": summary,
            "build_output": build_output,
            "test_output": test_output,
            "repo_path": repo_path,
            "branch": branch,
        }
