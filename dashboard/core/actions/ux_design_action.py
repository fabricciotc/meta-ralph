from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.models import Message


class UXDesignAction(Action):
    """Generates a UX/UI design specification from a PRD and optional architecture.

    The output is a markdown file (design-<ticket_id>.md) with user flows,
    screen descriptions, component suggestions, and implementation guidance
    for the Engineer Squad.
    """

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
            "design_path",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"UXDesignAction missing required kwargs: {missing}")

        ticket_id: str = kwargs["ticket_id"]
        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        prd_path: Path = Path(kwargs["prd_path"])
        design_path: Path = Path(kwargs["design_path"])
        architecture_path: Optional[Path] = kwargs.get("architecture_path")
        phase_name: str = kwargs.get("phase_name", "ux_design")
        timeout_seconds: int = kwargs.get("timeout_seconds", 600)

        build_prompt: Callable[..., str] = kwargs.get("build_ux_design_prompt") or self._build_default_prompt

        if run_ai is None:
            design_path.parent.mkdir(parents=True, exist_ok=True)
            design_path.write_text(self._fallback_design(ticket_title, ticket_description), encoding="utf-8")
            return Message(
                content=f"UX design spec saved at {design_path}",
                sent_from="ux-designer",
                cause_by="ux_design_ready",
                send_to={"orchestrator", "pm-research-agents", "product_manager"},
                metadata={
                    "path": str(design_path),
                    "ticket_id": ticket_id,
                    "fallback": True,
                },
            )

        prompt = build_prompt(
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            prd_path=prd_path,
            architecture_path=architecture_path,
            design_path=design_path,
        )

        raw = run_ai(prompt, phase_name, timeout_seconds, agent_id="ux-designer")
        if inspect.isawaitable(raw):
            output = await raw
        else:
            output = raw

        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(output or self._fallback_design(ticket_title, ticket_description), encoding="utf-8")

        return Message(
            content=f"UX design spec saved at {design_path}",
            sent_from="ux-designer",
            cause_by="ux_design_ready",
            send_to={"orchestrator", "pm-research-agents", "product_manager"},
            metadata={
                "path": str(design_path),
                "ticket_id": ticket_id,
                "fallback": not output,
            },
        )

    def _build_default_prompt(
        self,
        ticket_title: str,
        ticket_description: str,
        prd_path: Path,
        architecture_path: Optional[Path],
        design_path: Path,
    ) -> str:
        prd_text = ""
        if prd_path.exists():
            try:
                prd_text = prd_path.read_text(encoding="utf-8")[:10000]
            except Exception:
                pass

        arch_text = ""
        if architecture_path and architecture_path.exists():
            try:
                arch_text = architecture_path.read_text(encoding="utf-8")[:6000]
            except Exception:
                pass

        arch_section = f"\n\nARCHITECTURE:\n{arch_text}" if arch_text else ""

        # Load the project's own DESIGN.md if it exists so the UX agent stays on-brand.
        project_root = prd_path.parent.parent if prd_path else Path.cwd()
        design_md_path = project_root / "DESIGN.md"
        design_md_text = ""
        if design_md_path.exists():
            try:
                design_md_text = design_md_path.read_text(encoding="utf-8")[:8000]
            except Exception:
                pass
        design_md_section = f"\n\nPROJECT DESIGN SYSTEM (DESIGN.md):\n{design_md_text}" if design_md_text else ""

        return (
            "You are a senior UX/UI Designer for AgenticFlow.\n\n"
            "Before proposing a design, gather inspiration from real product design systems:\n"
            "- Browse https://styles.refero.design/ and search for styles that match this ticket "
            "(e.g. 'dark SaaS dashboard', 'command center', 'developer tools', 'Linear', 'Mercury', 'Vercel').\n"
            "- Read the DESIGN.md examples of the best 2-3 matches. Use their tokens, spacing, "
            "component rules, and visual atmosphere as inspiration, but adapt them to the "
            "AgenticFlow identity described below.\n"
            "- Also look for public GitHub repositories that publish DESIGN.md templates "
            "(e.g. google-labs-code/design.md, voltagent/awesome-design-md) to ground your spec "
            "in the standard format.\n\n"
            "Read the PRD (and architecture if provided) and create a markdown UX/UI design spec "
            f"saved to: {design_path}\n\n"
            f"TICKET:\nTITLE: {ticket_title}\nDESCRIPTION: {ticket_description}\n\n"
            f"PRD:\n{prd_text}{arch_section}{design_md_section}\n\n"
            "Your design spec must include:\n"
            "1. Inspiration summary — which Refero styles / DESIGN.md examples you consulted and why.\n"
            "2. User flow(s) — step-by-step screens/actions.\n"
            "3. Screen inventory — name, purpose, and key elements per screen.\n"
            "4. Component recommendations — reusable UI components and where they belong.\n"
            "5. Visual direction — spacing, color, typography, radii, shadows (keep it concise but concrete).\n"
            "6. Accessibility & responsiveness notes.\n"
            "7. Implementation guidance for engineers — file structure, state management, and event handling hints.\n"
            "8. Open design questions (if any).\n\n"
            "Do NOT write implementation code. Write clear, actionable design guidance that a PM can turn into "
            "user stories and an Engineer can implement."
        )

    def _fallback_design(self, title: str, description: str) -> str:
        return (
            f"# UX/UI Design: {title}\n\n"
            f"**Description:** {description}\n\n"
            "## User Flow\n"
            "1. User opens the feature.\n"
            "2. User interacts with the main screen.\n"
            "3. System shows feedback/results.\n\n"
            "## Screen Inventory\n"
            "- Main screen: primary entry point.\n\n"
            "## Component Recommendations\n"
            "- Use existing components when possible.\n\n"
            "## Implementation Guidance\n"
            "- Follow project conventions and the architecture document.\n"
        )
