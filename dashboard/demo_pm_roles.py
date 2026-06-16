#!/usr/bin/env python3
"""Demo for the PM Analysis flow with MetaGPT-style roles.

Runs an end-to-end PM analysis using PMResearchRoles and PMLeadRole
inside an Environment. Runner calls are mocked so the demo does not
depend on an active AI session.

Usage:
    cd dashboard
    python demo_pm_roles.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.environment import Environment
from core.models import Message
from core.roles.pm_lead_role import PMLeadRole
from core.roles.pm_research_role import PMResearchRole


def main():
    tmpdir = tempfile.mkdtemp()
    try:
        output_dir = Path(tmpdir) / "pm-research"
        output_dir.mkdir(parents=True, exist_ok=True)
        prd_path = Path(tmpdir) / "prd.md"

        subagents = [
            ("pm-domain", "Domain Analyst", "business domain and rules"),
            ("pm-ux", "UX Researcher", "user experience and flows"),
            ("pm-technical", "Technical Analyst", "technical stack and architecture"),
            ("pm-integration", "Integration Analyst", "external integrations"),
            ("pm-risk", "Risk Analyst", "risks and security"),
        ]

        research_calls = {sid: 0 for sid, _, _ in subagents}
        consolidation_calls = 0

        def run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            if agent_id in research_calls:
                research_calls[agent_id] += 1
                return f"# Findings for {agent_id}\n\nKey point for {agent_id}."
            if agent_id == "pm-research-agents":
                nonlocal consolidation_calls
                consolidation_calls += 1
                return (
                    "# Consolidated PRD\n\n"
                    "## Summary\n"
                    "OAuth authentication module for Scord V3.\n\n"
                    "## User stories\n"
                    "- Login with Google\n"
                    "- Secure logout\n"
                    "- Token refresh\n"
                )
            return ""

        def update_agent(agent_id, **kwargs):
            status = kwargs.get("status", "")
            progress = kwargs.get("progress", "")
            log = kwargs.get("log", "")
            print(f"  [{agent_id}] {status} {progress}% - {log}")

        def build_prompt(sub_id, focus, title, description, follow_up):
            return f"Research {sub_id} ({focus}) for '{title}'"

        def build_consolidator_prompt(title, description, research_files, prd_path):
            return f"Consolidate {list(research_files.keys())} into a PRD for '{title}'"

        def extract_prd(output, title, description):
            return output

        def parse_clarifications(output):
            return {}

        def write_fallback_prd(prd_path, title, description):
            content = f"# Fallback PRD\n\n{title}\n\n{description}"
            Path(prd_path).write_text(content, encoding="utf-8")
            return content

        def send_completion(prd_path, preview):
            print(f"\n  OK: PRD saved at {prd_path}")
            print(f"     Preview: {preview[:120]}...")

        env = Environment()

        for sub_id, sub_name, focus in subagents:
            role = PMResearchRole(sub_id, sub_name, focus)
            role.run_ai = run_ai
            env.add_role(role)

        lead = PMLeadRole(
            run_ai=run_ai,
            ticket_title="Login OAuth",
            ticket_description="Add Google login to the system",
            prd_path=prd_path,
            build_consolidator_prompt=build_consolidator_prompt,
            extract_prd=extract_prd,
            parse_clarifications=parse_clarifications,
            write_fallback_prd=write_fallback_prd,
            send_clarification=lambda sid, q: print(f"  Clarification for {sid}: {q}"),
            send_completion=send_completion,
            subagents=[sid for sid, _, _ in subagents],
        )
        env.add_role(lead)

        env.publish_message(Message(
            content="Start PM analysis",
            sent_from="orchestrator",
            cause_by="research_request",
            send_to={"all"},
            metadata={
                "ticket_title": "Login OAuth",
                "ticket_description": "Add Google login to the system",
                "ticket_id": "DEMO-OAUTH",
                "output_dir": output_dir,
                "build_prompt": build_prompt,
                "update_agent": update_agent,
                "phase_name": "pm_research",
                "timeout_seconds": 120,
            },
        ))

        print("\nStarting PM Analysis demo with MetaGPT-style roles\n")

        for i in range(10):
            print(f"- Round {i} -")
            active = asyncio.run(env.run_round())
            if not active and env.is_idle():
                break

        print(f"\nSummary:")
        print(f"   Rounds executed: {i + 1}")
        print(f"   Research calls: {sum(research_calls.values())}")
        print(f"   Consolidation calls: {consolidation_calls}")
        print(f"   PRD ready: {lead.prd_ready}")
        print(f"   PRD path: {prd_path}")

        if prd_path.exists():
            print(f"\nPRD content:\n{prd_path.read_text(encoding='utf-8')[:500]}")
        else:
            print("\nWARN: The PRD was not generated.")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
