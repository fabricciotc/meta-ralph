from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.correction_action import CorrectionAction
from core.actions.review_action import ReviewAction
from core.environment import Environment
from core.models import Message
from core.roles.qa_role import QARole, QASubRole


class TestReviewAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "task": {
                "id": "T1",
                "title": "Add login",
                "description": "Allow users to log in",
                "complexity": "M",
                "files_to_touch": ["src/auth.py", "tests/test_auth.py"],
                "qa_checklist": ["Unit tests pass", "No hardcoded secrets"],
            },
            "task_id": "T1",
            "repo_path": self.tmpdir,
            "branch": "feature/T1",
            "diff": "+ def login(): pass",
            "build_output": "Build OK",
            "test_output": "Tests OK",
            "build_review_prompt": lambda **kw: f"PROMPT {kw['task']['id']} {kw['diff']}",
            "extract_review_result": lambda output: {
                "approved": "APROBADO" in output,
                "reason": "reviewed",
                "suggested_fix": "",
            },
            "phase_name": "qa_review",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_review_action_approves(self):
        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "VEREDICTO: APROBADO\nRAZÓN: Todo correcto.\nSUGERENCIA: "

        action = ReviewAction("review-T1", "Review T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "review_approved")
        self.assertEqual(msg.sent_from, "qa-T1")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertTrue(msg.metadata["approved"])
        self.assertEqual(msg.metadata["task_id"], "T1")
        self.assertEqual(msg.metadata["reason"], "reviewed")

    def test_review_action_rejects(self):
        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return (
                "VEREDICTO: RECHAZADO\n"
                "RAZÓN: Falta validación de email.\n"
                "SUGERENCIA: Agregar regex de email."
            )

        def extract(output):
            approved = "APROBADO" in output and "RECHAZADO" not in output
            reason = "Falta validación de email."
            suggested = "Agregar regex de email."
            return {"approved": approved, "reason": reason, "suggested_fix": suggested}

        action = ReviewAction("review-T1", "Review T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs({"extract_review_result": extract}),
        ))

        self.assertEqual(msg.cause_by, "reject_with_feedback")
        self.assertFalse(msg.metadata["approved"])
        self.assertEqual(msg.metadata["reason"], "Falta validación de email.")
        self.assertEqual(msg.metadata["suggested_fix"], "Agregar regex de email.")

    def test_review_action_async_run_kimi(self):
        async def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "VEREDICTO: APROBADO\nRAZÓN: Async OK."

        def extract(output):
            approved = "APROBADO" in output and "RECHAZADO" not in output
            reason = output.split("RAZÓN:", 1)[1].strip() if "RAZÓN:" in output else output[:300]
            return {"approved": approved, "reason": reason, "suggested_fix": ""}

        action = ReviewAction("review-T1", "Review T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs({"extract_review_result": extract}),
        ))

        self.assertEqual(msg.cause_by, "review_approved")
        self.assertIn("Async OK", msg.content)

    def test_review_action_fallback_when_no_runner(self):
        from core.actions.review_action import default_extract_review_result

        action = ReviewAction("review-T1", "Review T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=None,
            **self._default_kwargs({"extract_review_result": default_extract_review_result}),
        ))

        self.assertEqual(msg.cause_by, "review_approved")
        self.assertTrue(msg.metadata["approved"])
        self.assertIn("No output", msg.metadata["reason"])

    def test_review_action_missing_kwargs_raises(self):
        action = ReviewAction("review-T1", "Review T1")
        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], task={}))
        self.assertIn("missing required kwargs", str(cm.exception).lower())


class TestCorrectionAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "task": {
                "id": "T1",
                "title": "Add login",
                "description": "Allow users to log in",
                "files_to_touch": ["src/auth.py"],
            },
            "task_id": "T1",
            "reason": "Falta validación de email.",
            "suggested_fix": "Agregar regex de email.",
            "repo_path": self.tmpdir,
            "branch": "feature/T1",
            "build_correction_prompt": lambda **kw: (
                f"CORRECTION {kw['task']['id']} {kw['reason']} {kw['suggested_fix']}"
            ),
            "extract_correction_prompt": lambda output: output or "default correction",
            "phase_name": "qa_correction",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_correction_action_generates_prompt(self):
        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "1. Revisar regex\n2. Agregar tests"

        action = CorrectionAction("correction-T1", "Correction T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "correction_prompt_ready")
        self.assertEqual(msg.sent_from, "qa-T1")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertEqual(msg.content, "1. Revisar regex\n2. Agregar tests")
        self.assertEqual(msg.metadata["task_id"], "T1")
        self.assertEqual(msg.metadata["reason"], "Falta validación de email.")

    def test_correction_action_async_run_kimi(self):
        async def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "Async correction prompt"

        action = CorrectionAction("correction-T1", "Correction T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.content, "Async correction prompt")

    def test_correction_action_fallback_when_no_runner(self):
        from core.actions.correction_action import default_extract_correction_prompt

        action = CorrectionAction("correction-T1", "Correction T1")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=None,
            **self._default_kwargs({"extract_correction_prompt": default_extract_correction_prompt}),
        ))

        self.assertEqual(msg.cause_by, "correction_prompt_ready")
        self.assertIn("Corregir los problemas", msg.content)

    def test_correction_action_missing_kwargs_raises(self):
        action = CorrectionAction("correction-T1", "Correction T1")
        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], task={}))
        self.assertIn("missing required kwargs", str(cm.exception).lower())


class TestQASubRole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_sub_role_reviews_task(self):
        task = {
            "id": "T1",
            "title": "Add login",
            "description": "Allow users to log in",
        }

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "VEREDICTO: APROBADO\nRAZÓN: OK"

        sub = QASubRole("T1", task, run_kimi=mock_run_kimi)
        msg = asyncio.run(sub.review(context=[], repo_path=self.tmpdir))

        self.assertEqual(msg.cause_by, "review_approved")
        self.assertEqual(msg.metadata["task_id"], "T1")

    def test_sub_role_generates_correction_prompt(self):
        task = {"id": "T1", "title": "Add login"}

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Fix email validation"

        sub = QASubRole("T1", task, run_kimi=mock_run_kimi)
        msg = asyncio.run(sub.generate_correction_prompt(
            context=[],
            reason="Falta validación",
            suggested_fix="Agregar regex",
            repo_path=self.tmpdir,
        ))

        self.assertEqual(msg.cause_by, "correction_prompt_ready")
        self.assertEqual(msg.content, "Fix email validation")
        self.assertEqual(msg.metadata["reason"], "Falta validación")


class TestQARole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_task(self, task_id="T1"):
        return {
            "id": task_id,
            "title": "Add login",
            "description": "Allow users to log in",
            "files_to_touch": ["src/auth.py"],
        }

    def _publish_review_request(self, env, task_id, task, send_to=None):
        env.publish_message(Message(
            content=f"Please review {task_id}",
            sent_from="engineer-T1",
            cause_by="request_review",
            send_to=send_to or {"qa-lead"},
            metadata={
                "task_id": task_id,
                "task": task,
                "repo_path": self.tmpdir,
                "branch": "feature/T1",
                "diff": "+ def login(): pass",
            },
        ))

    def test_qa_role_approves_task(self):
        env = Environment()

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "VEREDICTO: APROBADO\nRAZÓN: Todo correcto."

        role = QARole(run_kimi=mock_run_kimi)
        env.add_role(role)

        self._publish_review_request(env, "T1", self._make_task())
        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertEqual(response.sent_from, "qa-lead")
        self.assertEqual(response.cause_by, "review_approved")
        self.assertTrue(response.metadata["approved"])

        env._drain_queue_to_memory()
        history = env.memory.get()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1].cause_by, "review_approved")

    def test_qa_role_rejects_and_tracks_rounds(self):
        env = Environment()

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "VEREDICTO: RECHAZADO\nRAZÓN: Falta validación.\nSUGERENCIA: Agregar regex."

        role = QARole(run_kimi=mock_run_kimi)
        env.add_role(role)

        self._publish_review_request(env, "T1", self._make_task())
        response = asyncio.run(role.run(env))

        self.assertEqual(response.cause_by, "reject_with_feedback")
        self.assertFalse(response.metadata["approved"])
        self.assertEqual(response.metadata["reason"], "Falta validación.")
        self.assertEqual(role._review_state["T1"]["rounds"], 1)

    def test_qa_role_forces_approval_after_max_rounds(self):
        env = Environment()

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "VEREDICTO: RECHAZADO\nRAZÓN: Sigue fallando."

        role = QARole(run_kimi=mock_run_kimi, max_rounds=2)
        env.add_role(role)

        task = self._make_task()

        # Round 1: rejected
        self._publish_review_request(env, "T1", task)
        asyncio.run(role.run(env))
        self.assertEqual(role._review_state["T1"]["rounds"], 1)

        # Round 2: rejected
        self._publish_review_request(env, "T1", task)
        asyncio.run(role.run(env))
        self.assertEqual(role._review_state["T1"]["rounds"], 2)

        # Round 3: should force approval because rounds == max_rounds
        self._publish_review_request(env, "T1", task)
        response = asyncio.run(role.run(env))

        self.assertEqual(response.cause_by, "review_approved")
        self.assertTrue(response.metadata["approved"])
        self.assertTrue(response.metadata.get("forced"))
        self.assertIn("after 2 correction rounds", response.content)

    def test_qa_role_ignores_duplicate_request(self):
        env = Environment()

        calls = []

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            calls.append(agent_id)
            return "VEREDICTO: APROBADO\nRAZÓN: OK"

        role = QARole(run_kimi=mock_run_kimi)
        env.add_role(role)

        self._publish_review_request(env, "T1", self._make_task())
        asyncio.run(role.run(env))
        asyncio.run(role.run(env))

        self.assertEqual(len(calls), 1)

    def test_qa_role_returns_none_when_no_request(self):
        env = Environment()
        role = QARole(run_kimi=lambda *a, **kw: "VEREDICTO: APROBADO")
        env.add_role(role)

        response = asyncio.run(role.run(env))
        self.assertIsNone(response)

    def test_qa_role_generate_correction_prompt(self):
        role = QARole(run_kimi=lambda *a, **kw: "Fix it")
        task = self._make_task()
        msg = asyncio.run(role.generate_correction_prompt(
            context=[],
            task_id="T1",
            task=task,
            reason="Falta validación",
            suggested_fix="Agregar regex",
            repo_path=self.tmpdir,
        ))

        self.assertEqual(msg.cause_by, "correction_prompt_ready")
        self.assertEqual(msg.content, "Fix it")

    def test_qa_role_multiple_tasks_isolated(self):
        env = Environment()

        prompts = []

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            if agent_id == "qa-T1":
                return "VEREDICTO: APROBADO\nRAZÓN: OK"
            return "VEREDICTO: RECHAZADO\nRAZÓN: Mal."

        role = QARole(run_kimi=mock_run_kimi)
        env.add_role(role)

        self._publish_review_request(env, "T1", self._make_task("T1"))
        r1 = asyncio.run(role.run(env))

        self._publish_review_request(env, "T2", self._make_task("T2"))
        r2 = asyncio.run(role.run(env))

        self.assertEqual(r1.cause_by, "review_approved")
        self.assertEqual(r2.cause_by, "reject_with_feedback")
        self.assertEqual(role._review_state["T1"]["rounds"], 0)
        self.assertEqual(role._review_state["T2"]["rounds"], 1)


if __name__ == "__main__":
    unittest.main()
