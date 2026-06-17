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
from core.orchestrator import Orchestrator
from core.roles.qa_role import QARole


class TestOrchestratorQACorrectionLoop(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()
        import os
        os.chdir(self.tmpdir)
        (self.tmpdir / "scripts" / "meta-ralph" / "state").mkdir(parents=True)

    def tearDown(self):
        import os
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_orchestrator(self, run_ai) -> Orchestrator:
        ticket = {
            "id": "TKT-LOOP",
            "title": "Loop test",
            "description": "Test QA correction loop",
            "repoPath": str(self.tmpdir),
        }
        callbacks = {
            "ensure_agent": lambda *a, **kw: None,
            "update_agent": lambda *a, **kw: None,
            "log": lambda *a, **kw: None,
            "collect_outputs": lambda *a, **kw: None,
            "set_phase": lambda *a, **kw: None,
            "run_ai": run_ai,
        }
        orch = Orchestrator(ticket, callbacks=callbacks)
        orch.env = Environment()
        return orch

    def test_apply_qa_corrections_sends_direct_instruction_to_engineer(self):
        """When QA rejects, the orchestrator should instruct the engineer directly."""

        calls: list[dict] = []

        def run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            calls.append({"phase": phase_name, "agent_id": agent_id})
            if phase_name == "qa_correction":
                return "Add input validation and unit tests."
            # engineer implementation
            return "Fixed implementation"

        orch = self._make_orchestrator(run_ai)
        qa_lead = QARole(run_ai=run_ai)
        orch.env.add_role(qa_lead)

        task = {"id": "T1", "title": "Add login"}
        rejections = [{
            "task_id": "T1",
            "task": task,
            "reason": "Missing input validation.",
            "suggested_fix": "Add email validation.",
        }]

        orch._apply_qa_corrections(
            rejections,
            repo_path=str(self.tmpdir),
            branch="feature/tkt-loop-t1",
            qa_lead=qa_lead,
            round_num=1,
        )

        # An instruction targeted at the engineer should exist in the environment history.
        instructions = [
            m for m in orch.env.history()
            if m.cause_by == "squad_instruction" and "engineer-T1" in m.send_to
        ]
        self.assertEqual(len(instructions), 1, "Orchestrator should send a squad_instruction to engineer-T1")
        self.assertIn("Add input validation", instructions[0].metadata.get("instruction", ""))


    def test_correction_loop_asks_user_after_repeated_failures(self):
        """When corrections keep failing, the orchestrator should ask the user."""

        questions: list[str] = []

        def run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            if phase_name == "qa_correction":
                return "Add input validation and unit tests."
            # Engineer always fails so the loop reaches the user-escalation threshold.
            raise RuntimeError("Simulated implementation failure")

        def request_clarification(question, timeout):
            questions.append(question)
            return "Add unit tests for email validation"

        orch = self._make_orchestrator(run_ai)
        orch.callbacks["request_clarification"] = request_clarification
        qa_lead = QARole(run_ai=run_ai)
        orch.env.add_role(qa_lead)

        task = {"id": "T1", "title": "Add login"}
        rejections = [{
            "task_id": "T1",
            "task": task,
            "reason": "Missing input validation.",
            "suggested_fix": "Add email validation.",
        }]

        orch._apply_qa_corrections(
            rejections,
            repo_path=str(self.tmpdir),
            branch="feature/tkt-loop-t1",
            qa_lead=qa_lead,
            round_num=1,
        )

        self.assertTrue(questions, "Orchestrator should ask the user after repeated correction failures")
        self.assertIn("Missing input validation", questions[0])

        instructions = [
            m for m in orch.env.history()
            if m.cause_by == "squad_instruction" and "engineer-T1" in m.send_to
        ]
        self.assertGreaterEqual(len(instructions), 2, "Should re-issue instructions after user guidance")

        # The final instruction should include the user's guidance.
        final_instruction = instructions[-1].metadata.get("instruction", "")
        self.assertIn("Add unit tests for email validation", final_instruction)


if __name__ == "__main__":
    unittest.main()
