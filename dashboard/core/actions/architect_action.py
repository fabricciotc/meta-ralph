from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, List, Optional

from core.actions.base import Action
from core.models import Message


class ArchitectAction(Action):
    """Generates an architecture.md artifact from a PRD via the configured runner."""

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "prd_path",
            "architecture_path",
            "ticket_title",
            "ticket_description",
            "ticket_id",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"ArchitectAction missing required kwargs: {missing}")

        prd_path: Path = Path(kwargs["prd_path"])
        architecture_path: Path = Path(kwargs["architecture_path"])
        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        ticket_id: str = kwargs["ticket_id"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]
        review_answers: Optional[str] = kwargs.get("review_answers")

        build_prompt: Callable[..., str] = kwargs.get("build_architect_prompt") or self._build_default_prompt
        extract_architecture: Callable[..., str] = kwargs.get("extract_architecture") or self._extract_architecture

        architecture_path.parent.mkdir(parents=True, exist_ok=True)

        prd_content = prd_path.read_text(encoding="utf-8")

        if run_ai is None:
            content = self._write_fallback_architecture(
                architecture_path,
                ticket_title,
                ticket_description,
                prd_content,
            )
            return Message(
                content=content,
                sent_from="architect",
                cause_by="architecture_ready",
                send_to={"orchestrator"},
                metadata={
                    "artifact": "architecture",
                    "path": str(architecture_path),
                    "fallback": True,
                    "ticket_id": ticket_id,
                    "ticket_title": ticket_title,
                    "ticket_description": ticket_description,
                },
            )

        prompt = build_prompt(
            ticket_title,
            ticket_description,
            prd_content,
            architecture_path,
            review_answers,
        )

        raw = run_ai(prompt, phase_name, timeout_seconds, agent_id="architect")
        if inspect.isawaitable(raw):
            output = await raw
        else:
            output = raw

        if not output:
            content = self._write_fallback_architecture(
                architecture_path,
                ticket_title,
                ticket_description,
                prd_content,
            )
            fallback = True
        else:
            content = extract_architecture(output, ticket_title, ticket_description)
            fallback = False

        architecture_path.write_text(content, encoding="utf-8")

        return Message(
            content=content,
            sent_from="architect",
            cause_by="architecture_ready",
            send_to={"orchestrator"},
            metadata={
                "artifact": "architecture",
                "path": str(architecture_path),
                "fallback": fallback,
                "ticket_id": ticket_id,
                "ticket_title": ticket_title,
                "ticket_description": ticket_description,
            },
        )

    def _build_default_prompt(
        self,
        title: str,
        description: str,
        prd_content: str,
        architecture_path: Path,
        review_answers: Optional[str] = None,
    ) -> str:
        review_section = ""
        if review_answers:
            review_section = (
                "\n\nDESIGN REVIEW ANSWERS (apply these decisions):\n"
                f"{review_answers}\n"
            )

        return (
            "You are the AgentFlow Architect in a MetaGPT-style software factory. "
            "Design the global technical architecture for the following ticket. "
            "Do NOT implement code; define patterns, APIs, directory structure, "
            "conventions, and technical decisions that Engineers must follow.\n\n"
            f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}\n\n"
            f"PRD:\n{prd_content}\n\n"
            "Generate a markdown architecture document with these sections:\n"
            "1. Architecture summary\n"
            "2. Key technical decisions\n"
            "3. Recommended directories and modules\n"
            "4. APIs, interfaces, and contracts\n"
            "5. Code patterns and conventions\n"
            "6. Risks and mitigations\n\n"
            f"Write the complete markdown document to this file: {architecture_path}\n\n"
            "Respond in English. At the end, briefly confirm that you saved the architecture. "
            "If you detect pending design decisions, list them clearly under the heading "
            "'PENDING DECISIONS:'."
            + review_section
        )

    def _extract_architecture(
        self,
        output: str,
        title: str,
        description: str,
    ) -> str:
        lines = output.splitlines()
        arch_lines: List[str] = []
        capture = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# Architecture") or stripped.startswith("# 1."):
                capture = True
            if capture:
                arch_lines.append(line)
        if arch_lines:
            return "\n".join(arch_lines)

        filtered: List[str] = []
        for line in lines:
            if any(
                skip in line
                for skip in [
                    "context:",
                    "MCP server",
                    "thinking...",
                    "working...",
                ]
            ):
                continue
            filtered.append(line)
        return f"# Architecture: {title}\n\n**Description:**\n\n{description}\n\n---\n\n" + "\n".join(filtered[-200:])

    def _write_fallback_architecture(
        self,
        architecture_path: Path,
        title: str,
        description: str,
        prd_content: str,
    ) -> str:
        content = (
            f"# Architecture: {title}\n\n"
            f"**Description:** {description}\n\n"
            "## Technical Decisions\n"
            "- Preserve the project's existing stack and patterns.\n\n"
            "## Suggested Structure\n"
            "- Reuse existing modules; add components only when the PRD requires them.\n\n"
            "## Conventions\n"
            "- Follow project conventions and established patterns.\n\n"
            "## PRD Notes\n"
            f"{prd_content[:500]}\n"
        )
        architecture_path.write_text(content, encoding="utf-8")
        return content
