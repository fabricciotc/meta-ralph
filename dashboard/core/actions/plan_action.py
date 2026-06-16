from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.models import Message


class PlanAction(Action):
    """Creates a task plan (tasks-<ticket>.json) from PRD and architecture.md."""

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "ticket_id",
            "ticket_title",
            "ticket_description",
            "prd_path",
            "tasks_path",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"PlanAction missing required kwargs: {missing}")

        ticket_id: str = kwargs["ticket_id"]
        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        prd_path: Path = Path(kwargs["prd_path"])
        architecture_path: Optional[Path] = kwargs.get("architecture_path")
        tasks_path: Path = Path(kwargs["tasks_path"])
        build_plan_prompt: Optional[Callable[..., str]] = kwargs.get("build_plan_prompt")
        parse_tasks_json: Optional[Callable[[str], List[Dict[str, Any]]]] = kwargs.get("parse_tasks_json")
        write_fallback_plan: Optional[Callable[..., Any]] = kwargs.get("write_fallback_plan")
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        prd_content = self._read_file(prd_path)
        architecture_content = self._read_file(architecture_path) if architecture_path else ""

        # No runner available: emit a fallback plan immediately.
        if run_ai is None:
            tasks = self._write_fallback_plan(
                write_fallback_plan,
                tasks_path,
                ticket_id,
                ticket_title,
                ticket_description,
            )
            return self._plan_ready_message(tasks, tasks_path, ticket_id, fallback=True)

        if build_plan_prompt is None:
            prompt = self._default_build_plan_prompt(
                ticket_id,
                ticket_title,
                ticket_description,
                prd_content,
                architecture_content,
                tasks_path,
            )
        else:
            prompt = build_plan_prompt(
                ticket_id,
                ticket_title,
                ticket_description,
                prd_content,
                architecture_content,
                tasks_path,
            )

        raw = run_ai(prompt, phase_name, timeout_seconds, agent_id="planner")
        if inspect.isawaitable(raw):
            output = await raw
        else:
            output = raw

        if not output:
            tasks = self._write_fallback_plan(
                write_fallback_plan,
                tasks_path,
                ticket_id,
                ticket_title,
                ticket_description,
            )
            return self._plan_ready_message(tasks, tasks_path, ticket_id, fallback=True)

        if parse_tasks_json is None:
            tasks = self._default_parse_tasks_json(output)
        else:
            tasks = parse_tasks_json(output)

        if not tasks:
            tasks = self._write_fallback_plan(
                write_fallback_plan,
                tasks_path,
                ticket_id,
                ticket_title,
                ticket_description,
            )
            fallback = True
        else:
            fallback = False

        tasks_path.parent.mkdir(parents=True, exist_ok=True)
        tasks_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

        return self._plan_ready_message(tasks, tasks_path, ticket_id, fallback=fallback)

    def _plan_ready_message(
        self,
        tasks: List[Dict[str, Any]],
        tasks_path: Path,
        ticket_id: str,
        fallback: bool,
    ) -> Message:
        content = json.dumps(tasks, indent=2)
        return Message(
            content=content,
            sent_from="planner",
            cause_by="plan_ready",
            send_to={"orchestrator"},
            metadata={
                "artifact": "tasks",
                "path": str(tasks_path),
                "ticket_id": ticket_id,
                "fallback": fallback,
            },
        )

    def _read_file(self, path: Optional[Path]) -> str:
        if path is None:
            return ""
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            return f"[Error reading {path}: {exc}]"

    def _write_fallback_plan(
        self,
        write_fallback_plan: Optional[Callable[..., Any]],
        tasks_path: Path,
        ticket_id: str,
        title: str,
        description: str,
    ) -> List[Dict[str, Any]]:
        if write_fallback_plan is not None:
            result = write_fallback_plan(tasks_path, ticket_id, title, description)
            if isinstance(result, list):
                tasks_path.parent.mkdir(parents=True, exist_ok=True)
                tasks_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                return result
            result_path = Path(result) if isinstance(result, (str, Path)) else None
            if result_path is not None and result_path.exists() and result_path.is_file():
                try:
                    content = result_path.read_text(encoding="utf-8")
                    tasks = json.loads(content)
                    if isinstance(tasks, list):
                        tasks_path.parent.mkdir(parents=True, exist_ok=True)
                        tasks_path.write_text(content, encoding="utf-8")
                        return tasks
                except Exception:
                    pass

        tasks = self._default_fallback_plan(ticket_id, title, description)
        tasks_path.parent.mkdir(parents=True, exist_ok=True)
        tasks_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
        return tasks

    def _default_fallback_plan(
        self,
        ticket_id: str,
        title: str,
        description: str,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "id": f"{ticket_id}-T1",
                "title": f"Implement: {title}",
                "description": description,
                "dependencies": [],
                "files_to_touch": [],
                "complexity": "M",
                "qa_checklist": ["Validate that it satisfies the ticket description."],
            },
            {
                "id": f"{ticket_id}-T2",
                "title": "Add unit tests",
                "description": "Minimum coverage for the implemented change.",
                "dependencies": [f"{ticket_id}-T1"],
                "files_to_touch": [],
                "complexity": "S",
                "qa_checklist": ["Tests pass locally."],
            },
        ]

    def _default_parse_tasks_json(self, output: str) -> List[Dict[str, Any]]:
        """Extract a JSON array of tasks from raw output, with tolerant parsing."""
        candidates: List[str] = []

        start = output.find("[")
        if start != -1:
            depth = 0
            end = start
            in_string = False
            escape = False
            for i in range(start, len(output)):
                ch = output[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            candidates.append(output[start:end])

        candidates.append(output)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    if "tasks" in parsed and isinstance(parsed["tasks"], list):
                        return parsed["tasks"]
            except Exception:
                continue

        return []

    def _default_build_plan_prompt(
        self,
        ticket_id: str,
        title: str,
        description: str,
        prd_content: str,
        architecture_content: str,
        tasks_path: Path,
    ) -> str:
        architecture_section = ""
        if architecture_content:
            architecture_section = f"\n\nARCHITECTURE:\n{architecture_content}"
        return (
            "You are the Planner for AgentFlow, a MetaGPT-style software factory. "
            "Your job is to generate a technical task plan from the provided PRD and architecture.\n\n"
            f"TICKET:\nID: {ticket_id}\nTITLE: {title}\nDESCRIPTION: {description}\n\n"
            f"PRD:\n{prd_content}"
            f"{architecture_section}\n\n"
            "Generate JSON with an array of tasks. Each task must include these fields:\n"
            "- id: unique string\n"
            "- title: string\n"
            "- description: string\n"
            "- dependencies: array of strings (previous task IDs)\n"
            "- files_to_touch: array of strings (relative file paths)\n"
            "- complexity: 'S', 'M', or 'L'\n"
            "- qa_checklist: array of strings\n\n"
            f"The plan must be saved at: {tasks_path}\n\n"
            "Respond ONLY with valid JSON, without additional text."
        )
