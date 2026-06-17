from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import Context
from core.environment import Environment
from core.models import Message
from core.roles.engineer_role import EngineerRole
from core.roles.engineer_squad_role import EngineerSquadRole
from core.roles.qa_role import QARole


class TestQAEngineerCorrectionLoop(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_task(self) -> dict:
        return {
            "id": "T1",
            "title": "Add login",
            "description": "Allow users to log in",
            "files_to_touch": ["src/auth.py"],
        }

    def _publish_task_assigned(self, env: Environment, task: dict) -> None:
        env.publish_message(Message(
            content="Implement this task",
            sent_from="orchestrator",
            cause_by="task_assigned",
            send_to={"engineer-T1"},
            metadata={
                "task": task,
                "ticket_id": "TKT-LOOP",
                "ticket_title": "Loop test",
                "ticket_description": "Test QA->engineer loop",
                "repo_path": self.tmpdir,
                "branch": "feature/tkt-loop-t1",
            },
        ))

    def _publish_review_request(self, env: Environment, task: dict, build_output: str = "", test_output: str = "") -> None:
        env.publish_message(Message(
            content="Please review T1",
            sent_from="orchestrator",
            cause_by="request_review",
            send_to={"qa-lead"},
            metadata={
                "task_id": "T1",
                "task": task,
                "repo_path": self.tmpdir,
                "branch": "feature/tkt-loop-t1",
                "diff": "+ def login(): pass",
                "build_output": build_output,
                "test_output": test_output,
            },
        ))

    def _publish_qa_rejection(self, env: Environment, task: dict, reason: str, suggested_fix: str) -> None:
        """Mimic what Orchestrator._apply_qa_corrections publishes."""
        env.publish_message(Message(
            content=f"QA rejected T1: {reason}",
            sent_from="qa-T1",
            cause_by="reject_with_feedback",
            send_to={"engineer-T1", "engineer-squad"},
            metadata={
                "task_id": "T1",
                "task": task,
                "engineer_id": "engineer-T1",
                "reason": reason,
                "suggested_fix": suggested_fix,
                "correction_prompt": "Add validation and tests.",
                "report_path": "",
                "repo_path": self.tmpdir,
                "branch": "feature/tkt-loop-t1",
            },
        ))

    def test_rejection_triggers_correction_and_approval(self):
        env = Environment()
        shared_context = Context(ticket={"id": "TKT-LOOP", "title": "Loop test", "description": ""})
        task = self._make_task()

        engineer_calls: list[str] = []

        def engineer_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            engineer_calls.append(prompt)
            if len(engineer_calls) == 1:
                return "Initial implementation"
            return "Fixed implementation after QA feedback"

        qa_calls: list[str] = []

        def qa_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            qa_calls.append(prompt)
            if len(qa_calls) == 1:
                return (
                    "VERDICT: REJECTED\n"
                    "REASON: Missing input validation.\n"
                    "SUGGESTION: Add email validation."
                )
            return (
                "VERDICT: APPROVED\n"
                "REASON: Validation added correctly."
            )

        squad = EngineerSquadRole(
            run_ai=lambda *a, **kw: {
                "action": "ack",
                "message": "Ack",
            },
            ticket_id="TKT-LOOP",
            ticket_title="Loop test",
            ticket_description="",
            tasks=[task],
        )
        engineer = EngineerRole(
            role_id="engineer-T1",
            focus="Add login",
            run_ai=engineer_run_ai,
            repo_path=self.tmpdir,
            branch_prefix="feature",
            phase_name="engineer-T1",
        )
        qa = QARole(run_ai=qa_run_ai)

        env.add_role(squad)
        env.add_role(engineer)
        env.add_role(qa)

        # Phase 1: engineer implements the task.
        self._publish_task_assigned(env, task)
        for _ in range(10):
            if not asyncio.run(env.run_round(context=shared_context)):
                break

        task_completed = [m for m in env.history() if m.cause_by == "task_completed"]
        self.assertEqual(len(task_completed), 1, "Engineer should complete the task once")

        # Phase 2: QA rejects.
        self._publish_review_request(env, task)
        for _ in range(10):
            if not asyncio.run(env.run_round(context=shared_context)):
                break

        rejections = [m for m in env.history() if m.cause_by == "reject_with_feedback"]
        self.assertEqual(len(rejections), 1, "QA should reject once")

        # Orchestrator would forward the rejection to the squad and engineer.
        self._publish_qa_rejection(env, task, "Missing input validation.", "Add email validation.")
        for _ in range(10):
            if not asyncio.run(env.run_round(context=shared_context)):
                break

        squad_instructions = [m for m in env.history() if m.cause_by == "squad_instruction"]
        self.assertEqual(len(squad_instructions), 1, "Squad should send one correction instruction")
        self.assertIn("engineer-T1", squad_instructions[0].send_to)

        # Phase 3: engineer corrects and QA re-reviews.
        self._publish_review_request(env, task)
        for _ in range(10):
            if not asyncio.run(env.run_round(context=shared_context)):
                break

        approvals = [m for m in env.history() if m.cause_by == "review_approved"]
        self.assertEqual(len(approvals), 1, "QA should approve after correction")

        # The engineer should have been invoked twice: initial + correction.
        self.assertEqual(len(engineer_calls), 2, "Engineer should run twice")


if __name__ == "__main__":
    unittest.main()
