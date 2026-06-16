from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import server
from core import pm_analysis


class TestServerPMAnalysisIntegration(unittest.TestCase):
    """Integration test: AgentRunner.run_pm_analysis uses the new role/action engine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = Path.cwd()

    def tearDown(self):
        import os
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_pm_analysis_uses_role_engine_and_writes_prd(self):
        import os
        os.chdir(self.tmpdir)
        (Path(self.tmpdir) / "scripts" / "meta-ralph" / "state").mkdir(parents=True)

        ticket = {
            "id": "INT-001",
            "title": "Login OAuth",
            "description": "Add OAuth login",
            "repoPath": str(self.tmpdir),
        }

        calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            calls.append({"phase": phase_name, "agent_id": agent_id})
            if agent_id == "pm-research-agents":
                return "# PRD\n\nConsolidated PRD content."
            return f"# {agent_id}\n\nResearch findings."

        runner = server.AgentRunner(ticket)
        with patch.object(runner, "_run_ai_prompt", side_effect=mock_run_ai):
            runner.run_pm_analysis()

        prd_path = Path(self.tmpdir) / "scripts" / "meta-ralph" / "state" / "prd-INT-001.md"
        self.assertTrue(prd_path.exists())
        self.assertIn("Consolidated PRD content", prd_path.read_text(encoding="utf-8"))

        # Verify parallel research happened: all 5 subagents + 1 consolidator.
        research_calls = [c for c in calls if c["agent_id"] != "pm-research-agents"]
        self.assertEqual(len(research_calls), 5)
        self.assertTrue(any(c["agent_id"] == "pm-domain" for c in research_calls))
        self.assertTrue(any(c["agent_id"] == "pm-technical" for c in research_calls))
        self.assertTrue(any(c["agent_id"] == "pm-research-agents" for c in calls))

    def test_run_pm_analysis_reuses_existing_prd(self):
        import os
        os.chdir(self.tmpdir)
        state_dir = Path(self.tmpdir) / "scripts" / "meta-ralph" / "state"
        state_dir.mkdir(parents=True)
        prd_path = state_dir / "prd-INT-002.md"
        prd_path.write_text("# Existing PRD\n\nAlready done. " + "x" * 200, encoding="utf-8")

        ticket = {"id": "INT-002", "title": "X", "description": "Y"}
        runner = server.AgentRunner(ticket)

        calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            calls.append({"phase": phase_name, "agent_id": agent_id})
            return "# PRD\n\nNew content."

        with patch.object(runner, "_run_ai_prompt", side_effect=mock_run_ai):
            runner.run_pm_analysis()

        self.assertEqual(len(calls), 0)
        content = prd_path.read_text(encoding="utf-8")
        self.assertIn("Already done.", content)
        self.assertEqual(len(calls), 0)


if __name__ == "__main__":
    unittest.main()
