from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.models import Message


class ConsolidatePRDAction(Action):
    """Consolidates PM research findings into a PRD via the configured AI runner."""

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "ticket_title",
            "ticket_description",
            "research_files",
            "prd_path",
            "build_consolidator_prompt",
            "extract_prd",
            "parse_clarifications",
            "write_fallback_prd",
            "send_clarification",
            "send_completion",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"ConsolidatePRDAction missing required kwargs: {missing}")

        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        research_files: Dict[str, Any] = kwargs["research_files"]
        prd_path: Path = kwargs["prd_path"]
        build_consolidator_prompt: Callable[..., str] = kwargs["build_consolidator_prompt"]
        extract_prd: Callable[..., str] = kwargs["extract_prd"]
        parse_clarifications: Callable[..., Dict[str, str]] = kwargs["parse_clarifications"]
        write_fallback_prd: Callable[..., Any] = kwargs["write_fallback_prd"]
        send_clarification: Callable[[str, str], None] = kwargs["send_clarification"]
        send_completion: Callable[[Path, str], None] = kwargs["send_completion"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        prd_path = Path(prd_path)

        # Fallback when there is no research or no runner available.
        if not research_files or run_ai is None:
            content = self._write_prd(
                write_fallback_prd,
                prd_path,
                ticket_title,
                ticket_description,
            )
            preview = content[:500]
            send_completion(prd_path, preview)
            return Message(
                content=content,
                sent_from="pm-research-agents",
                cause_by="prd_ready",
                send_to={"orchestrator"},
                metadata={
                    "artifact": "PRD",
                    "path": str(prd_path),
                    "preview": preview,
                    "fallback": True,
                },
            )

        prompt = build_consolidator_prompt(
            ticket_title,
            ticket_description,
            research_files,
            prd_path,
        )

        raw = run_ai(prompt, phase_name, timeout_seconds, agent_id="pm-research-agents")
        if inspect.isawaitable(raw):
            output = await raw
        else:
            output = raw

        # Fallback on empty output from the runner.
        if not output:
            content = self._write_prd(
                write_fallback_prd,
                prd_path,
                ticket_title,
                ticket_description,
            )
            preview = content[:500]
            send_completion(prd_path, preview)
            return Message(
                content=content,
                sent_from="pm-research-agents",
                cause_by="prd_ready",
                send_to={"orchestrator"},
                metadata={
                    "artifact": "PRD",
                    "path": str(prd_path),
                    "preview": preview,
                    "fallback": True,
                },
            )

        clarifications = parse_clarifications(output)
        if clarifications:
            for sub_id, question in clarifications.items():
                send_clarification(sub_id, question)
            return Message(
                content="",
                sent_from="pm-research-agents",
                cause_by="clarifications_requested",
                send_to={"pm-research-agents"},
                metadata={"clarifications": clarifications},
            )

        content = extract_prd(output, ticket_title, ticket_description)
        prd_path.write_text(content, encoding="utf-8")
        preview = content[:500]
        send_completion(prd_path, preview)
        return Message(
            content=content,
            sent_from="pm-research-agents",
            cause_by="prd_ready",
            send_to={"orchestrator"},
            metadata={
                "artifact": "PRD",
                "path": str(prd_path),
                "preview": preview,
                "fallback": False,
            },
        )

    def _write_prd(
        self,
        write_fallback_prd: Callable[..., Any],
        prd_path: Path,
        title: str,
        description: str,
    ) -> str:
        result = write_fallback_prd(prd_path, title, description)
        if isinstance(result, Path) or (isinstance(result, str) and Path(result).exists()):
            path = Path(result)
            if path.is_file():
                content = path.read_text(encoding="utf-8")
                if path != prd_path:
                    prd_path.write_text(content, encoding="utf-8")
                return content
        content = str(result)
        prd_path.write_text(content, encoding="utf-8")
        return content
