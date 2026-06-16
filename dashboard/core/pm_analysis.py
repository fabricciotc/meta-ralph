#!/usr/bin/env python3
"""Product Management Analysis phase for meta-ralph.

Self-contained PM research/consolidation logic that can be used both by the
legacy AgentRunner and by the new MetaGPT-style Orchestrator. It depends only
on the stdlib plus the core Message/Memory/Environment/Role/Action classes.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.context import Context
from core.environment import Environment
from core.models import Message
from core.roles.pm_lead_role import PMLeadRole
from core.roles.pm_research_role import PMResearchRole


# Default subagents used during PM Analysis.
DEFAULT_SUBAGENTS: List[tuple[str, str, str]] = [
    ("pm-domain", "Domain Analyst", "business domain, entities, rules, and main flows"),
    ("pm-ux", "UX Researcher", "user experience, views, screen flows, and frontend validation"),
    ("pm-technical", "Technical Analyst", "technical stack, architecture, patterns, and technical decisions"),
    ("pm-integration", "Integration Analyst", "third-party APIs, databases, and external services"),
    ("pm-risk", "Risk Analyst", "risks, security, compliance, permissions, and error handling"),
]


def get_meta_dir(cwd: Optional[Path] = None) -> Path:
    """Return the meta-ralph scripts directory relative to the project."""
    return (cwd or Path.cwd()) / "scripts" / "meta-ralph"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences."""
    import re

    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def run_ai_prompt(
    prompt: str,
    phase_name: str = "Agent",
    timeout_seconds: int = 120,
    agent_id: Optional[str] = None,
    ticket_id: str = "",
    repo_path: Optional[str] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Optional[str]:
    """Execute a prompt through the configured AI backend registry.

    Mirrors the server runner behaviour without depending on server.py state helpers.
    """
    import os
    from core.runners.registry import BackendRegistry

    safe_phase = phase_name.lower().replace(" ", "-")
    meta_dir = get_meta_dir()
    output_path = meta_dir / "state" / f"output-{ticket_id}-{safe_phase}.txt"
    prompt_path = meta_dir / "state" / f"prompt-{ticket_id}-{safe_phase}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    prompt_path.write_text(prompt, encoding="utf-8")

    def log(message: str, level: str = "info"):
        if log_callback:
            log_callback(message, level)

    registry = BackendRegistry.default()
    available = registry.available_backends()
    if not available:
        log("No AI backend executable or API credentials were found.", "error")
        return None

    backend_names = ", ".join(backend.name for backend in available)
    log(f"Running AI backend for {phase_name} (available: {backend_names}; timeout {timeout_seconds}s)...")
    dotnet_prefix = (
        "Activate the 'dotnet' skill and apply its conventions and best practices "
        "to all .NET code you generate. "
    )
    full_prompt = dotnet_prefix + prompt

    cwd = repo_path or os.getcwd()
    try:
        previous_cwd = os.getcwd()
        try:
            os.chdir(cwd)
            output = registry.run_prompt(
                full_prompt,
                phase_name=phase_name,
                timeout_seconds=timeout_seconds,
                agent_id=agent_id,
            ) or ""
        finally:
            os.chdir(previous_cwd)

        output_path.write_text(output, encoding="utf-8")

        lines = [strip_ansi(l) for l in output.splitlines() if strip_ansi(l).strip()]
        for line in lines[-50:]:
            log(f"[{phase_name}] {line[:250]}")

        return "\n".join(lines)
    except Exception as exc:
        log(f"{phase_name} error: {exc}", "error")
        return None


def decision_request_instruction() -> str:
    """Return the standard instruction appended to PM prompts."""
    return (
        "\n\nIf you detect design decisions that require user confirmation, "
        "list the options clearly at the end under the heading 'PENDING DECISIONS:'."
    )


def build_pm_subagent_prompt(
    sub_id: str,
    focus: str,
    title: str,
    description: str,
    follow_up: Optional[str] = None,
) -> str:
    """Build the research prompt for a PM subagent."""
    role_name = {
        "pm-domain": "Domain Analyst",
        "pm-ux": "UX Researcher",
        "pm-technical": "Technical Analyst",
        "pm-integration": "Integration Analyst",
        "pm-risk": "Risk Analyst",
    }.get(sub_id, sub_id)

    follow_up_section = ""
    if follow_up:
        follow_up_section = (
            "\n\nTHE PM LEAD ASKED YOU TO EXPAND YOUR ANALYSIS WITH THIS QUESTION/CLARIFICATION:\n"
            f"{follow_up}\n\n"
            "Answer the PM Lead request directly while keeping the same output format."
        )

    return (
        f"You are the {role_name} for AgentFlow, a MetaGPT-style multi-agent software factory. "
        f"Your exclusive focus is: {focus}. "
        "Research the current project codebase ONLY from your assigned angle. "
        "Do NOT implement code; only research, analyze, and document findings. "
        "Be concise but complete; prioritize quality over length.\n\n"
        "Your output must be markdown with these sections:\n"
        "1. Key findings (maximum 10 bullets).\n"
        "2. Functional and non-functional requirements relevant to your area.\n"
        "3. Risks, assumptions, or open questions.\n"
        "4. Relevant codebase files or areas.\n\n"
        f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}"
        + follow_up_section
        + "\n\nRespond in English."
        + decision_request_instruction()
    )


def build_pm_consolidator_prompt(
    title: str,
    description: str,
    research_files: Dict[str, Path],
    prd_path: Path,
) -> str:
    """Build the prompt that consolidates PM research into a PRD."""
    research_content = ""
    for sid, path in research_files.items():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[:150]
            research_content += f"\n\n--- {sid} ---\n\n" + "\n".join(lines)
        except Exception as exc:
            research_content += f"\n\n--- {sid} ---\n\nError reading findings: {exc}"

    return (
        "You are the Lead Product Manager for AgentFlow. Five PM Research Agents investigated a ticket. "
        "Consolidate THEIR FINDINGS into a concise, actionable Product Requirements Document (PRD). "
        "Do NOT invent requirements that are not supported by the findings; synthesize what was researched.\n\n"
        f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}\n\n"
        "AGENT FINDINGS:\n" + research_content + "\n\n"
        "Generate a markdown PRD with these sections (concise, maximum 2 paragraphs per section):\n"
        "1. Executive summary\n"
        "2. Main functional requirements (numbered, with High/Medium/Low priority)\n"
        "3. Key non-functional requirements\n"
        "4. User stories and acceptance criteria\n"
        "5. Suggested technical tasks with dependencies and estimates (S/M/L)\n"
        "6. Risks, assumptions, and open questions\n\n"
        f"Write the complete markdown PRD to this file: {prd_path}\n\n"
        "Respond in English. At the end, briefly confirm that you saved the PRD."
        + decision_request_instruction()
    )


def parse_clarifications(output: str) -> Dict[str, str]:
    """Parse clarification requests from consolidator output."""
    clarifications: Dict[str, str] = {}
    marker = "PENDING CLARIFICATIONS:"
    idx = output.find(marker)
    if idx == -1:
        return clarifications
    block = output[idx + len(marker):]
    next_header = block.find("\n#")
    if next_header != -1:
        block = block[:next_header]
    valid_ids = {"pm-domain", "pm-ux", "pm-technical", "pm-integration", "pm-risk"}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("*"):
            continue
        if ":" in line:
            sub_id, question = line.split(":", 1)
            sub_id = sub_id.strip()
            question = question.strip()
            if sub_id in valid_ids and question:
                clarifications[sub_id] = question
    return clarifications


def extract_prd_from_output(output: str, title: str, description: str) -> str:
    """Extract the PRD markdown from raw AI output."""
    lines = output.splitlines()
    prd_lines: List[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# PRD") or stripped.startswith("# 1.") or stripped.startswith("## 1."):
            capture = True
        if capture:
            prd_lines.append(line)
    if prd_lines:
        return "\n".join(prd_lines)

    filtered: List[str] = []
    for line in lines:
        if any(skip in line for skip in ["context:", "MCP server", "thinking...", "working..."]):
            continue
        filtered.append(line)
    return f"# Detailed PRD: {title}\n\n**Original description:**\n\n{description}\n\n---\n\n" + "\n".join(filtered[-200:])


def write_fallback_prd(prd_path: Path, title: str, description: str) -> str:
    """Generate a minimal fallback PRD locally."""
    content = (
        f"# PRD: {title}\n\n"
        f"**Description:** {description}\n\n"
        "## Functional Requirements\n"
        "1. Implement the requested functionality.\n\n"
        "## Acceptance Criteria\n"
        "- The system satisfies the ticket description.\n\n"
        "## Suggested Technical Tasks\n"
        "- Analyze requirements.\n"
        "- Implement changes.\n"
        "- Validate with tests.\n"
    )
    prd_path.write_text(content, encoding="utf-8")
    return content


def run_pm_analysis(
    ticket: Dict[str, Any],
    run_ai: Optional[Callable[..., Optional[str]]] = None,
    max_rounds: int = 10,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Optional[Path]:
    """Execute PM Analysis using MetaGPT-style roles and return the PRD path.

    Args:
        ticket: Ticket dict with at least 'id', 'title', 'description' and optionally 'repoPath'.
        run_ai: Function to invoke the configured AI runner. Defaults to run_ai_prompt.
        max_rounds: Maximum environment rounds to avoid infinite loops.
        log_callback: Optional callback(message, level) for logging.

    Returns:
        Path to the generated PRD, or None if generation failed.
    """
    ticket_id = ticket.get("id", "")
    title = ticket.get("title", "")
    description = ticket.get("description", "")
    repo_path = ticket.get("repoPath")

    prd_path = get_meta_dir() / "state" / f"prd-{ticket_id}.md"
    prd_path.parent.mkdir(parents=True, exist_ok=True)

    pm_research_dir = get_meta_dir() / "state" / "pm-research"
    pm_research_dir.mkdir(parents=True, exist_ok=True)

    if prd_path.exists() and prd_path.stat().st_size > 100:
        if log_callback:
            log_callback(f"Pre-generated PRD found at {prd_path}; skipping PM Research.", "info")
        return prd_path

    env = Environment()
    shared_context = Context(ticket=ticket, prd_path=prd_path, repo_path=repo_path)

    ai_runner = run_ai or (
        lambda prompt, phase_name, timeout_seconds, agent_id=None: run_ai_prompt(
            prompt,
            phase_name=phase_name,
            timeout_seconds=timeout_seconds,
            agent_id=agent_id,
            ticket_id=ticket_id,
            repo_path=repo_path,
            log_callback=log_callback,
        )
    )

    subagents = DEFAULT_SUBAGENTS

    def update_agent(agent_id: str, **kwargs):
        status = kwargs.get("status", "")
        progress = kwargs.get("progress", "")
        log = kwargs.get("log", "")
        if log_callback:
            log_callback(f"[{agent_id}] {status} {progress}% — {log}", "info")

    def build_prompt(sub_id: str, focus: str, title: str, description: str, follow_up: Optional[str]) -> str:
        return build_pm_subagent_prompt(sub_id, focus, title, description, follow_up)

    def build_consolidator_prompt(title: str, description: str, research_files: Dict[str, Path], prd_path: Path) -> str:
        return build_pm_consolidator_prompt(title, description, research_files, prd_path)

    for sub_id, sub_name, focus in subagents:
        role = PMResearchRole(sub_id, sub_name, focus)
        role.run_ai = ai_runner
        env.add_role(role)

    lead = PMLeadRole(
        run_ai=ai_runner,
        ticket_title=title,
        ticket_description=description,
        prd_path=prd_path,
        build_consolidator_prompt=build_consolidator_prompt,
        extract_prd=extract_prd_from_output,
        parse_clarifications=parse_clarifications,
        write_fallback_prd=write_fallback_prd,
        send_clarification=lambda sid, q: None,
        send_completion=lambda path, preview: None,
        subagents=[sid for sid, _, _ in subagents],
    )
    env.add_role(lead)

    env.publish_message(Message(
        content="Start PM analysis",
        sent_from="orchestrator",
        cause_by="research_request",
        send_to={"all"},
        metadata={
            "ticket_title": title,
            "ticket_description": description,
            "ticket_id": ticket_id,
            "output_dir": pm_research_dir,
            "build_prompt": build_prompt,
            "update_agent": update_agent,
            "phase_name": "pm_research",
            "timeout_seconds": 600,
        },
    ))

    for _ in range(max_rounds):
        active = asyncio.run(env.run_round(context=shared_context))
        if not active and env.is_idle():
            break

    if prd_path.exists():
        return prd_path
    return None


if __name__ == "__main__":
    # Simple smoke test with a mocked AI runner.
    tmpdir = tempfile.mkdtemp()
    original_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmpdir)
        (Path(tmpdir) / "scripts" / "meta-ralph" / "state").mkdir(parents=True)

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            if agent_id == "pm-research-agents":
                return "# PRD\n\nConsolidated."
            return f"# {agent_id}\n\nFindings."

        prd = run_pm_analysis(
            {"id": "SMOKE-001", "title": "Test", "description": "Desc"},
            run_ai=mock_run_ai,
        )
        assert prd is not None
        print("Smoke OK:", prd)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmpdir, ignore_errors=True)
