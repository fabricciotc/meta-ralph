from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from core.actions.base import Action
from core.ai_execution import invoke_ai
from core.models import Message


class ResearchAction(Action):
    """Executes a research request by invoking the configured runner and writing results to disk."""

    async def run(
        self,
        context: List[Message],
        run_ai: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "sub_id",
            "sub_name",
            "focus",
            "ticket_title",
            "ticket_description",
            "ticket_id",
            "output_dir",
            "build_prompt",
            "update_agent",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"ResearchAction missing required kwargs: {missing}")

        sub_id: str = kwargs["sub_id"]
        sub_name: str = kwargs["sub_name"]
        focus: str = kwargs["focus"]
        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        ticket_id: str = kwargs["ticket_id"]
        follow_up: Optional[str] = kwargs.get("follow_up")
        output_dir: Path = kwargs["output_dir"]
        build_prompt: Any = kwargs["build_prompt"]
        update_agent: Any = kwargs["update_agent"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        update_agent(
            sub_id,
            status="running",
            progress=10,
            log=f"{sub_name} analyzing...",
        )

        try:
            prompt = build_prompt(sub_id, focus, ticket_title, ticket_description, follow_up)

            output = await invoke_ai(run_ai, prompt, phase_name, timeout_seconds, agent_id=sub_id)

            if not output:
                return Message(
                    content="",
                    sent_from=sub_id,
                    cause_by="research",
                    send_to={"pm-research-agents"},
                    metadata={"sub_id": sub_id},
                )

            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{ticket_id}-{sub_id}.md"
            path.write_text(output, encoding="utf-8")

            shared_context = kwargs.get("shared_context") or kwargs.get("context")
            if shared_context is not None and hasattr(shared_context, "shared"):
                findings = shared_context.shared.setdefault("pm_findings", {})
                findings[sub_id] = {
                    "agent": sub_name,
                    "focus": focus,
                    "file": str(path),
                    "summary": output[:1000],
                    "follow_up": bool(follow_up),
                }

            update_agent(
                sub_id,
                status="done",
                progress=100,
                log=f"{sub_name} finished analysis.",
            )

            return Message(
                content=output,
                sent_from=sub_id,
                cause_by="research",
                send_to={"pm-research-agents", "all"},
                metadata={
                    "file": str(path),
                    "sub_id": sub_id,
                    "follow_up": bool(follow_up),
                },
            )
        except Exception as exc:
            update_agent(
                sub_id,
                status="error",
                progress=0,
                log=f"{sub_name} failed: {exc}",
            )
            raise
