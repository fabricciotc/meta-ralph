from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.implement_action import ImplementAction
from core.context import Context
from core.environment import Environment
from core.models import Message
from core.roles.engineer_role import EngineerRole


class TestImplementAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_path = Path(self.tmpdir) / "repo"
        self.repo_path.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_task(self):
        return {
            "id": "T1",
            "title": "Add login endpoint",
            "description": "Implement POST /login",
            "files_to_touch": ["src/auth.py"],
            "dependencies": [],
        }

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "task": self._default_task(),
            "repo_path": self.repo_path,
            "branch": "feature/T1-login",
            "build_prompt": lambda **kw: f"PROMPT {kw['task']['id']} {kw['branch']}",
            "update_agent": lambda agent_id, **kw: None,
            "phase_name": "engineer_implement",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_implement_action_calls_ai_runner_and_returns_completed(self):
        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return "Implemented login endpoint with tests."

        action = ImplementAction("implement-T1", "Implement T1")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["phase_name"], "engineer_implement")
        self.assertEqual(ai_calls[0]["timeout_seconds"], 120)
        self.assertEqual(ai_calls[0]["agent_id"], "T1")
        self.assertIn("PROMPT T1", ai_calls[0]["prompt"])

        self.assertEqual(msg.sent_from, "T1")
        self.assertEqual(msg.cause_by, "task_completed")
        self.assertIn("orchestrator", msg.send_to)
        self.assertIn("qa", msg.send_to)
        self.assertEqual(msg.metadata["task_id"], "T1")
        self.assertEqual(msg.metadata["branch"], "feature/T1-login")
        self.assertEqual(msg.metadata["repo_path"], str(self.repo_path))
        self.assertFalse(msg.metadata.get("fallback"))

    def test_implement_action_fallback_when_no_runner(self):
        action = ImplementAction("implement-T1", "Implement T1")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=None,
            **self._default_kwargs(),
        ))

        expected_note = self.repo_path / ".meta-ralph" / "engineer-notes" / "T1-feature-T1-login.md"
        self.assertTrue(expected_note.exists())
        self.assertIn("Add login endpoint", expected_note.read_text(encoding="utf-8"))

        self.assertEqual(msg.cause_by, "task_completed")
        self.assertTrue(msg.metadata.get("fallback"))
        self.assertEqual(msg.metadata["task_id"], "T1")

    def test_implement_action_failure_returns_task_failed(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            raise RuntimeError("AI runner execution failed")

        action = ImplementAction("implement-T1", "Implement T1")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "task_failed")
        self.assertEqual(msg.sent_from, "T1")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertEqual(msg.metadata["task_id"], "T1")
        self.assertEqual(msg.metadata["reason"], "AI runner execution failed")

    def test_implement_action_missing_required_kwargs_raises(self):
        action = ImplementAction("implement-T1", "Implement T1")

        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], task=self._default_task()))

        self.assertIn("missing required kwargs", str(cm.exception).lower())

    def test_implement_action_async_run_ai(self):
        async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "Async implementation complete."

        action = ImplementAction("implement-T1", "Implement T1")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "task_completed")
        self.assertEqual(msg.content, "Async implementation complete.")

    def test_implement_action_includes_executable_feedback_metadata(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Implemented T1."

        action = ImplementAction("implement-T1", "Implement T1")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "task_completed")
        self.assertIn("build_output", msg.metadata)
        self.assertIn("test_output", msg.metadata)

    def test_implement_action_executable_feedback_failure(self):
        import shutil

        # Create a fake .NET project so the action attempts to build.
        csproj = self.repo_path / "Fake.csproj"
        csproj.write_text("<Project></Project>", encoding="utf-8")

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Implemented T1."

        action = ImplementAction("implement-T1", "Implement T1")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        if shutil.which("dotnet"):
            self.assertEqual(msg.cause_by, "task_failed")
            self.assertIn("build_output", msg.metadata)
        else:
            # Without dotnet the validation is skipped.
            self.assertEqual(msg.cause_by, "task_completed")


class TestEngineerRole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_path = Path(self.tmpdir) / "repo"
        self.repo_path.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _task_message(self, role_id, task_id="T1", send_to=None):
        return Message(
            content=f"Assign task {task_id} to {role_id}",
            sent_from="orchestrator",
            cause_by="task_assigned",
            send_to=send_to or {role_id},
            metadata={
                "ticket_id": "TKT-001",
                "ticket_title": "Login",
                "ticket_description": "Allow users to log in",
                "task": {
                    "id": task_id,
                    "title": f"Task {task_id}",
                    "description": f"Implement {task_id}",
                    "files_to_touch": [f"src/{task_id}.py"],
                },
                "repo_path": str(self.repo_path),
                "branch": f"feature/{task_id}",
                "dependencies_context": "Dependency D1 is ready.",
            },
        )

    def test_engineer_role_triggers_on_task_assigned(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Implemented T1."

        role = EngineerRole("engineer-T1", "authentication backend", run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(self._task_message("engineer-T1"))
        asyncio.run(env.run_round())

        history = env.memory.get()
        self.assertEqual(len(history), 3)

        response = [m for m in history if m.sent_from == "engineer-T1" and m.cause_by == "task_completed"][0]
        self.assertIn("orchestrator", response.send_to)
        self.assertIn("qa", response.send_to)
        self.assertEqual(response.metadata["task_id"], "T1")
        self.assertEqual(response.metadata["branch"], "feature/T1")

        report = [m for m in history if m.cause_by == "task_report"][0]
        self.assertEqual(report.send_to, {"engineer-squad", "all"})
        self.assertEqual(report.metadata["status"], "completed")

    def test_engineer_role_stores_report_in_shared_context(self):
        env = Environment()
        shared_context = Context(ticket={"id": "TKT-001", "title": "Login", "description": "Allow login"})

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Implemented with shared context."

        role = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(self._task_message("engineer-T1"))
        asyncio.run(env.run_round(context=shared_context))

        reports = shared_context.shared.get("engineer_reports", {})
        self.assertIn("T1", reports)
        self.assertEqual(reports["T1"]["status"], "completed")
        self.assertEqual(reports["T1"]["engineer_id"], "engineer-T1")

    def test_engineer_role_ignores_task_assigned_to_other_engineer(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Implemented."

        role_t1 = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        role_t2 = EngineerRole("engineer-T2", "frontend", run_ai=mock_run_ai)
        env.add_role(role_t1)
        env.add_role(role_t2)

        env.publish_message(self._task_message("engineer-T2", task_id="T2", send_to={"engineer-T2"}))
        asyncio.run(env.run_round())

        history = env.memory.get()
        self.assertEqual(len(history), 3)

        response = [m for m in history if m.sent_from == "engineer-T2" and m.cause_by == "task_completed"][0]
        self.assertEqual(response.metadata["task_id"], "T2")
        self.assertEqual(role_t1.memory.get(), [])

    def test_engineer_role_ignores_non_task_assigned_messages(self):
        env = Environment()

        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append(agent_id)
            return "Implemented."

        role = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(Message(
            content="Just chatting",
            sent_from="orchestrator",
            cause_by="chat",
            send_to={"engineer-T1"},
        ))
        asyncio.run(env.run_round())

        self.assertEqual(ai_calls, [])
        self.assertEqual(len([m for m in env.memory.get() if m.sent_from == "engineer-T1"]), 0)

    def test_engineer_role_supports_multiple_engineers(self):
        env = Environment()

        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append(agent_id)
            return f"Implemented by {agent_id}."

        role_t1 = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        role_t2 = EngineerRole("engineer-T2", "frontend", run_ai=mock_run_ai)
        env.add_role(role_t1)
        env.add_role(role_t2)

        env.publish_message(self._task_message("engineer-T1", task_id="T1", send_to={"engineer-T1"}))
        env.publish_message(self._task_message("engineer-T2", task_id="T2", send_to={"engineer-T2"}))
        asyncio.run(env.run_round())

        history = env.memory.get()
        completed = [m for m in history if m.cause_by == "task_completed"]
        self.assertEqual(len(completed), 2)
        self.assertEqual(sorted([m.sent_from for m in completed]), ["engineer-T1", "engineer-T2"])
        self.assertEqual(sorted(ai_calls), ["engineer-T1", "engineer-T2"])

    def test_engineer_role_task_failed_on_ai_exception(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            raise RuntimeError("AI runner unavailable")

        role = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(self._task_message("engineer-T1"))
        asyncio.run(env.run_round())

        history = env.memory.get()
        response = [m for m in history if m.sent_from == "engineer-T1" and m.cause_by == "task_failed"][0]
        self.assertEqual(response.metadata["reason"], "AI runner unavailable")
        report = [m for m in history if m.cause_by == "task_report"][0]
        self.assertEqual(report.metadata["status"], "failed")

    def test_engineer_role_does_not_reprocess_same_assignment(self):
        env = Environment()

        call_count = {"n": 0}

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            call_count["n"] += 1
            return "Implemented T1."

        role = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        env.add_role(role)

        assignment = self._task_message("engineer-T1")
        env.publish_message(assignment)
        asyncio.run(env.run_round())

        # Publish the same assignment again; it should not trigger re-execution.
        env.publish_message(assignment)
        asyncio.run(env.run_round())

        self.assertEqual(call_count["n"], 1)

    def test_engineer_role_uses_watch_and_set_actions(self):
        from core.actions.implement_action import ImplementAction

        role = EngineerRole("engineer-T1", "backend", run_ai=lambda *a, **kw: "x")
        self.assertEqual(role._watch, ["task_assigned", "squad_instruction"])
        self.assertEqual(len(role.actions), 1)
        self.assertIsInstance(role.actions[0], ImplementAction)

    def test_engineer_role_executable_feedback_metadata_on_completion(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "Implemented T1."

        role = EngineerRole("engineer-T1", "backend", run_ai=mock_run_ai)
        env.add_role(role)
        env.publish_message(self._task_message("engineer-T1"))
        asyncio.run(env.run_round())

        completed = [m for m in env.memory.get() if m.cause_by == "task_completed"]
        self.assertEqual(len(completed), 1)
        self.assertIn("build_output", completed[0].metadata)
        self.assertIn("test_output", completed[0].metadata)


if __name__ == "__main__":
    unittest.main()
