from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.environment import Environment
from core.models import Message
from core.roles.pm_lead_role import PMLeadRole
from core.roles.pm_research_role import PMResearchRole


class TestPMAnalysisEndToEnd(unittest.TestCase):
    """End-to-end test for the PM Analysis phase using MetaGPT-style roles."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_dir = Path(self.tmpdir) / "pm-research"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prd_path = Path(self.tmpdir) / "prd.md"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_research_prompt(self, sub_id, focus, title, description, follow_up):
        return f"RESEARCH {sub_id} {focus} {title} {description} follow_up={follow_up}"

    def _build_consolidator_prompt(self, title, description, research_files, prd_path):
        return f"CONSOLIDATE {title} {description} files={list(research_files.keys())} path={prd_path}"

    def _extract_prd(self, output, title, description):
        return output

    def _parse_clarifications(self, output):
        return {}

    def _write_fallback_prd(self, prd_path, title, description):
        content = f"# Fallback PRD\n\n{title}\n\n{description}"
        Path(prd_path).write_text(content, encoding="utf-8")
        return content

    def _send_clarification(self, sub_id, question):
        pass

    def _send_completion(self, prd_path, preview):
        pass

    def _update_agent(self, agent_id, **kwargs):
        pass

    def _make_ai_runner(self, responses):
        idx = {"i": 0}

        def run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            response = responses[idx["i"] % len(responses)]
            idx["i"] += 1
            if callable(response):
                return response(prompt, phase_name, timeout_seconds, agent_id)
            return response

        return run_ai

    def test_full_pm_analysis_flow_produces_prd(self):
        env = Environment()

        subagents = [
            ("pm-domain", "Domain Analyst", "business domain"),
            ("pm-ux", "UX Researcher", "user experience"),
            ("pm-technical", "Technical Analyst", "technical stack"),
            ("pm-integration", "Integration Analyst", "integrations"),
            ("pm-risk", "Risk Analyst", "risks"),
        ]

        run_ai = self._make_ai_runner([
            lambda prompt, phase, timeout, agent_id=None: f"# {agent_id} research\n\nFindings for {agent_id}",
            "# PRD\n\nConsolidated PRD content from research.",
        ])

        for sub_id, sub_name, focus in subagents:
            role = PMResearchRole(sub_id, sub_name, focus)
            role.run_ai = run_ai
            env.add_role(role)

        lead = PMLeadRole(
            run_ai=run_ai,
            ticket_title="Login Feature",
            ticket_description="Allow users to log in",
            prd_path=self.prd_path,
            build_consolidator_prompt=self._build_consolidator_prompt,
            extract_prd=self._extract_prd,
            parse_clarifications=self._parse_clarifications,
            write_fallback_prd=self._write_fallback_prd,
            send_clarification=self._send_clarification,
            send_completion=self._send_completion,
            subagents=[sub_id for sub_id, _, _ in subagents],
        )
        env.add_role(lead)

        # Seed the research request that triggers PMResearchRoles.
        env.publish_message(Message(
            content="Investigate login feature",
            sent_from="orchestrator",
            cause_by="research_request",
            send_to={"all"},
            metadata={
                "ticket_title": "Login Feature",
                "ticket_description": "Allow users to log in",
                "ticket_id": "TKT-LOGIN",
                "output_dir": self.output_dir,
                "build_prompt": self._build_research_prompt,
                "update_agent": self._update_agent,
                "phase_name": "pm_research",
                "timeout_seconds": 120,
            },
        ))

        max_rounds = 10
        for _ in range(max_rounds):
            active = asyncio.run(env.run_round())
            if not active and env.is_idle():
                break

        self.assertTrue(self.prd_path.exists())
        content = self.prd_path.read_text(encoding="utf-8")
        self.assertIn("Consolidated PRD content", content)
        self.assertTrue(lead.prd_ready)

        # Verify research artifacts were written.
        for sub_id, _, _ in subagents:
            research_path = self.output_dir / f"TKT-LOGIN-{sub_id}.md"
            self.assertTrue(research_path.exists(), f"Missing research file for {sub_id}")

    def test_pm_analysis_with_clarification_round(self):
        env = Environment()

        subagents = [
            ("pm-domain", "Domain Analyst", "business domain"),
            ("pm-technical", "Technical Analyst", "technical stack"),
        ]

        # Track research rounds per subagent so we can return initial vs clarified findings.
        research_rounds = {sub_id: 0 for sub_id, _, _ in subagents}
        consolidation_rounds = {"i": 0}

        def run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            if agent_id in research_rounds:
                research_rounds[agent_id] += 1
                if research_rounds[agent_id] == 1:
                    return f"# {agent_id} research\n\nInitial findings"
                return f"# {agent_id} clarified\n\nOAuth flow details"
            if agent_id == "pm-research-agents":
                consolidation_rounds["i"] += 1
                if consolidation_rounds["i"] == 1:
                    return "PENDING CLARIFICATIONS:\npm-domain: What is the OAuth flow?\n\n# PRD\n\n1. Summary"
                return "# PRD\n\nFinal consolidated PRD with OAuth flow."
            return ""

        for sub_id, sub_name, focus in subagents:
            role = PMResearchRole(sub_id, sub_name, focus)
            role.run_ai = run_ai
            env.add_role(role)

        lead = PMLeadRole(
            run_ai=run_ai,
            ticket_title="OAuth Login",
            ticket_description="Allow OAuth login",
            prd_path=self.prd_path,
            build_consolidator_prompt=self._build_consolidator_prompt,
            extract_prd=self._extract_prd,
            parse_clarifications=self._parse_clarifications_with_marker,
            write_fallback_prd=self._write_fallback_prd,
            send_clarification=self._send_clarification,
            send_completion=self._send_completion,
            subagents=[sub_id for sub_id, _, _ in subagents],
        )
        env.add_role(lead)

        env.publish_message(Message(
            content="Investigate OAuth login",
            sent_from="orchestrator",
            cause_by="research_request",
            send_to={"all"},
            metadata={
                "ticket_title": "OAuth Login",
                "ticket_description": "Allow OAuth login",
                "ticket_id": "TKT-OAUTH",
                "output_dir": self.output_dir,
                "build_prompt": self._build_research_prompt,
                "update_agent": self._update_agent,
                "phase_name": "pm_research",
                "timeout_seconds": 120,
            },
        ))

        max_rounds = 20
        for _ in range(max_rounds):
            active = asyncio.run(env.run_round())
            if not active and env.is_idle():
                break

        self.assertTrue(self.prd_path.exists())
        self.assertIn("Final consolidated PRD with OAuth flow", self.prd_path.read_text(encoding="utf-8"))

    def _parse_clarifications_with_marker(self, output):
        clarifications = {}
        marker = "PENDING CLARIFICATIONS:"
        idx = output.find(marker)
        if idx != -1:
            block = output[idx + len(marker):]
            for line in block.splitlines():
                line = line.strip()
                if ":" in line and not line.startswith("-") and not line.startswith("#"):
                    sid, question = line.split(":", 1)
                    clarifications[sid.strip()] = question.strip()
        return clarifications


if __name__ == "__main__":
    unittest.main()
