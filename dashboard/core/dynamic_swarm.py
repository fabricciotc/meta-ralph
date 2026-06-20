from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.ai_execution import invoke_ai
from core.environment import Environment
from core.models import Message
from core.roles.pm_research_role import PMResearchRole


DEFAULT_SPECIALIST_ROLES: Dict[str, str] = {
    "security_specialist": "Security, authentication, secrets, injection, OWASP, data privacy.",
    "performance_specialist": "Performance, latency, throughput, caching, profiling, scalability.",
    "integrations_specialist": "Third-party APIs, webhooks, data exchange, external auth flows.",
    "accessibility_specialist": "Accessibility, WCAG, keyboard navigation, screen readers.",
    "data_architect": "Data modeling, schema design, migrations, persistence, data integrity.",
}

KEYWORD_SPECIALIST_MAP: Dict[str, List[str]] = {
    "security_specialist": [
        "security",
        "auth",
        "oauth",
        "sso",
        "secret",
        "credential",
        "password",
        "jwt",
        "encrypt",
        "owasp",
        "injection",
        "xss",
        "csrf",
        "gdpr",
        "privacy",
    ],
    "performance_specialist": [
        "performance",
        "latency",
        "throughput",
        "cache",
        "scaling",
        "scale",
        "optimize",
        "profil",
        "slow",
        "bottleneck",
        "memory leak",
    ],
    "integrations_specialist": [
        "integration",
        "api",
        "webhook",
        "third-party",
        "third party",
        "external service",
        "sync",
        "connector",
    ],
    "accessibility_specialist": [
        "accessibility",
        "a11y",
        "wcag",
        "screen reader",
        "keyboard",
        "contrast",
        "aria",
    ],
    "data_architect": [
        "database",
        "schema",
        "migration",
        "persist",
        "data model",
        "sql",
        "nosql",
        "entity",
        "relation",
    ],
}


def build_dynamic_specialist_prompt(
    role_id: str,
    focus: str,
    title: str,
    description: str,
    follow_up: Optional[str],
    context: Any,
) -> str:
    """Build a research prompt for a dynamic specialist subagent."""
    artifacts: List[str] = []
    if getattr(context, "prd_path", None) and context.prd_path.exists():
        artifacts.append(f"PRD:\n{context.prd_path.read_text(encoding='utf-8')[:2000]}")
    if getattr(context, "architecture_path", None) and context.architecture_path.exists():
        artifacts.append(
            f"ARCHITECTURE:\n{context.architecture_path.read_text(encoding='utf-8')[:2000]}"
        )
    if getattr(context, "tasks_path", None) and context.tasks_path.exists():
        try:
            artifacts.append(
                f"TASKS:\n{context.tasks_path.read_text(encoding='utf-8')[:2000]}"
            )
        except Exception:
            pass
    if getattr(context, "design_path", None) and context.design_path.exists():
        artifacts.append(
            f"DESIGN:\n{context.design_path.read_text(encoding='utf-8')[:2000]}"
        )

    artifacts_text = "\n\n---\n\n".join(artifacts) or "No artifacts available."

    follow_up_section = ""
    if follow_up:
        follow_up_section = (
            "\n\nFOLLOW-UP QUESTION:\n"
            f"{follow_up}\n\n"
            "Answer directly while keeping the same output format."
        )

    return (
        f"You are the {role_id.replace('_', ' ').title()} for a MetaGPT-style multi-agent software factory. "
        f"Your exclusive focus is: {focus}. "
        "Analyze the provided artifacts ONLY from your assigned angle. "
        "Do NOT implement code; only research, analyze, and document findings. "
        "Be concise but complete; prioritize quality over length.\n\n"
        "Your output must be markdown with these sections:\n"
        "1. Key findings (maximum 10 bullets).\n"
        "2. Risks or concerns relevant to your area.\n"
        "3. Concrete recommendations for the Engineer Squad.\n"
        "4. Open questions (if any).\n\n"
        f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}\n\n"
        f"ARTIFACTS:\n{artifacts_text}"
        + follow_up_section
        + "\n\nRespond in English."
    )


class DynamicSwarmDetector:
    """Detects which pre-defined specialist roles are relevant for a ticket."""

    def __init__(
        self,
        run_ai: Optional[Callable] = None,
        skills_registry: Optional[Any] = None,
        timeout_seconds: int = 120,
    ):
        self.run_ai = run_ai
        self.skills_registry = skills_registry
        self.timeout_seconds = timeout_seconds

    async def detect(self, ticket: Dict[str, Any], context_text: str) -> List[str]:
        """Return a list of relevant specialist role IDs."""
        keyword_roles = self._keyword_detect(context_text)
        ai_roles = await self._ai_detect(ticket, context_text)
        seen: set = set()
        result: List[str] = []
        for role in keyword_roles + ai_roles:
            if role in DEFAULT_SPECIALIST_ROLES and role not in seen:
                result.append(role)
                seen.add(role)
        return result

    def _keyword_detect(self, text: str) -> List[str]:
        text_lower = text.lower()
        found: List[str] = []
        for role, keywords in KEYWORD_SPECIALIST_MAP.items():
            if any(kw in text_lower for kw in keywords):
                found.append(role)
        return found

    async def _ai_detect(self, ticket: Dict[str, Any], context_text: str) -> List[str]:
        if not self.run_ai:
            return []
        prompt = self._build_detect_prompt(ticket, context_text)
        try:
            raw = await invoke_ai(
                self.run_ai,
                prompt,
                "dynamic_swarm_detect",
                self.timeout_seconds,
                agent_id="dynamic-swarm-detector",
            )
            return self._parse_detect_response(raw or "")
        except Exception:
            return []

    def _build_detect_prompt(self, ticket: Dict[str, Any], context_text: str) -> str:
        role_list = "\n".join(
            f"- {rid}: {focus}" for rid, focus in DEFAULT_SPECIALIST_ROLES.items()
        )
        return (
            "You are a Dynamic Swarm Detector for a multi-agent software factory. "
            "Given a ticket and its generated artifacts, decide which pre-defined specialist roles "
            "should be added to the pipeline to improve quality. Only return roles that are truly relevant.\n\n"
            f"AVAILABLE ROLES:\n{role_list}\n\n"
            f"TICKET TITLE: {ticket.get('title', '')}\n"
            f"TICKET DESCRIPTION: {ticket.get('description', '')}\n\n"
            f"ARTIFACTS CONTEXT:\n{context_text[:4000]}\n\n"
            "Respond EXACTLY with JSON in this shape:\n"
            '{"specialists": ["security_specialist", "performance_specialist"]}\n'
            'If no specialists are needed, return {"specialists": []}.'
        )

    def _parse_detect_response(self, raw: str) -> List[str]:
        text = raw.strip()
        if "```" in text:
            blocks = text.split("```")
            for block in blocks:
                candidate = block.strip()
                if candidate.startswith("{"):
                    text = candidate
                    break
        try:
            data = json.loads(text)
            return [r for r in data.get("specialists", []) if r in DEFAULT_SPECIALIST_ROLES]
        except Exception:
            return []


class DynamicSwarmExecutor:
    """Runs selected specialist roles in parallel and writes their findings to disk."""

    def __init__(
        self,
        run_ai: Optional[Callable] = None,
        update_agent: Optional[Callable] = None,
        max_workers: int = 6,
        timeout_seconds: int = 600,
    ):
        self.run_ai = run_ai
        self.update_agent = update_agent
        self.max_workers = max(1, max_workers)
        self.timeout_seconds = timeout_seconds

    async def run(
        self,
        ticket: Dict[str, Any],
        role_ids: List[str],
        context: Any,
        output_dir: Path,
    ) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _run_one(role_id: str) -> Optional[Path]:
            async with semaphore:
                name = role_id.replace("_", " ").title()
                focus = DEFAULT_SPECIALIST_ROLES.get(role_id, "specialist analysis")
                role = PMResearchRole(
                    role_id=role_id,
                    sub_name=name,
                    focus=focus,
                    run_ai=self.run_ai,
                )
                env = Environment()
                env.add_role(role)

                def build_prompt(
                    sub_id: str,
                    focus: str,
                    title: str,
                    description: str,
                    follow_up: Optional[str],
                ) -> str:
                    return build_dynamic_specialist_prompt(
                        role_id, focus, title, description, follow_up, context
                    )

                def _update(agent_id: str, **kwargs: Any) -> None:
                    if self.update_agent:
                        self.update_agent(agent_id, **kwargs)

                env.publish_message(
                    Message(
                        content=f"Start {role_id}",
                        sent_from="orchestrator",
                        cause_by="research_request",
                        send_to={role_id},
                        metadata={
                            "ticket_title": ticket.get("title", ""),
                            "ticket_description": ticket.get("description", ""),
                            "ticket_id": ticket.get("id", ""),
                            "output_dir": output_dir,
                            "build_prompt": build_prompt,
                            "update_agent": _update,
                            "phase_name": role_id,
                            "timeout_seconds": self.timeout_seconds,
                        },
                    )
                )

                for _ in range(5):
                    active = await env.run_round(context=context)
                    if not active and env.is_idle():
                        break

                for msg in reversed(env.history()):
                    if msg.metadata.get("sub_id") == role_id and msg.metadata.get("file"):
                        return Path(msg.metadata["file"])
                return None

        results = await asyncio.gather(
            *[_run_one(r) for r in role_ids],
            return_exceptions=True,
        )
        files: Dict[str, Path] = {}
        for role_id, result in zip(role_ids, results):
            if isinstance(result, Path):
                files[role_id] = result
            elif isinstance(result, Exception):
                if hasattr(context, "log"):
                    context.log(f"Specialist {role_id} failed: {result}", "warning")
        return files


class DynamicSwarmSynthesizer:
    """Combines specialist findings into a single markdown report."""

    def __init__(
        self,
        run_ai: Optional[Callable] = None,
        timeout_seconds: int = 300,
    ):
        self.run_ai = run_ai
        self.timeout_seconds = timeout_seconds

    async def synthesize(
        self,
        ticket: Dict[str, Any],
        files: Dict[str, Path],
        output_path: Path,
    ) -> str:
        if not files:
            return ""

        findings: List[str] = []
        for role_id, path in files.items():
            try:
                text = path.read_text(encoding="utf-8")
                findings.append(f"--- {role_id} ---\n\n{text[:2000]}")
            except Exception as exc:
                findings.append(f"--- {role_id} ---\n\nError reading file: {exc}")

        prompt = (
            "You are a Swarm Synthesizer for a multi-agent software factory. "
            "Consolidate the findings of the specialist agents into an executive report for the Engineer Squad and QA.\n\n"
            f"TICKET:\nTITLE: {ticket.get('title', '')}\nDESCRIPTION: {ticket.get('description', '')}\n\n"
            "SPECIALIST FINDINGS:\n" + "\n\n".join(findings) + "\n\n"
            "Generate a concise markdown report with these sections:\n"
            "1. Executive summary\n"
            "2. Per-specialist highlights\n"
            "3. Actionable recommendations for implementation\n"
            "4. Open questions or risks to monitor"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            output = await invoke_ai(
                self.run_ai,
                prompt,
                "dynamic_swarm_synthesize",
                self.timeout_seconds,
                agent_id="dynamic-swarm-synthesizer",
            )
        except Exception:
            output = None

        if not output:
            output = "# Dynamic Swarm Report\n\n" + "\n\n".join(findings)

        output_path.write_text(output, encoding="utf-8")
        return output
