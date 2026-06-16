from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.plan_action import PlanAction
from core.environment import Environment
from core.models import Message
from core.roles.planner_role import PlannerRole


class TestPlanAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prd_path = Path(self.tmpdir) / "prd.md"
        self.architecture_path = Path(self.tmpdir) / "architecture.md"
        self.tasks_path = Path(self.tmpdir) / "tasks-TKT-001.json"

        self.prd_path.write_text("# PRD\n\nImplement login.", encoding="utf-8")
        self.architecture_path.write_text(
            "# Architecture\n\nUse a controller + service.", encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "ticket_id": "TKT-001",
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "prd_path": self.prd_path,
            "architecture_path": self.architecture_path,
            "tasks_path": self.tasks_path,
            "phase_name": "planning",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_plan_action_writes_tasks_json(self):
        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Add auth endpoint",
                    "description": "Create login API endpoint.",
                    "dependencies": [],
                    "files_to_touch": ["auth.py"],
                    "complexity": "M",
                    "qa_checklist": ["Endpoint returns token."],
                }
            ])

        action = PlanAction("create-plan", "Create Task Plan")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.tasks_path.exists())
        tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], "TKT-001-T1")

        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["phase_name"], "planning")
        self.assertEqual(ai_calls[0]["timeout_seconds"], 120)
        self.assertEqual(ai_calls[0]["agent_id"], "planner")
        self.assertIn("PRD", ai_calls[0]["prompt"])
        self.assertIn("ARCHITECTURE", ai_calls[0]["prompt"])

        self.assertEqual(msg.sent_from, "planner")
        self.assertEqual(msg.cause_by, "plan_ready")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertEqual(msg.metadata.get("artifact"), "tasks")
        self.assertEqual(msg.metadata.get("path"), str(self.tasks_path))
        self.assertEqual(msg.metadata.get("ticket_id"), "TKT-001")
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_plan_action_uses_wrapped_tasks_key(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return json.dumps({
                "tasks": [
                    {
                        "id": "TKT-001-T1",
                        "title": "Task one",
                        "description": "Desc",
                        "dependencies": [],
                        "files_to_touch": [],
                        "complexity": "S",
                        "qa_checklist": [],
                    }
                ]
            })

        action = PlanAction("create-plan", "Create Task Plan")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], "TKT-001-T1")
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_plan_action_fallback_when_no_ai_runner(self):
        action = PlanAction("create-plan", "Create Task Plan")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=None,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.tasks_path.exists())
        tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["id"], "TKT-001-T1")
        self.assertEqual(tasks[1]["dependencies"], ["TKT-001-T1"])

        self.assertEqual(msg.cause_by, "plan_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_plan_action_fallback_on_invalid_json(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "No valid JSON here"

        action = PlanAction("create-plan", "Create Task Plan")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.tasks_path.exists())
        tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
        self.assertEqual(len(tasks), 2)

        self.assertEqual(msg.cause_by, "plan_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_plan_action_fallback_on_empty_output(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return None

        action = PlanAction("create-plan", "Create Task Plan")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.tasks_path.exists())
        self.assertEqual(msg.cause_by, "plan_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_plan_action_async_run_ai(self):
        async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Async task",
                    "description": "Desc",
                    "dependencies": [],
                    "files_to_touch": [],
                    "complexity": "S",
                    "qa_checklist": [],
                }
            ])

        action = PlanAction("create-plan", "Create Task Plan")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
        self.assertEqual(tasks[0]["title"], "Async task")
        self.assertEqual(msg.cause_by, "plan_ready")
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_plan_action_missing_required_kwargs_raises(self):
        action = PlanAction("create-plan", "Create Task Plan")

        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], ticket_id="TKT-001"))

        self.assertIn("missing required kwargs", str(cm.exception).lower())

    def test_plan_action_without_architecture_path(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            self.assertNotIn("ARQUITECTURA", prompt)
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Only PRD task",
                    "description": "Desc",
                    "dependencies": [],
                    "files_to_touch": [],
                    "complexity": "S",
                    "qa_checklist": [],
                }
            ])

        action = PlanAction("create-plan", "Create Task Plan")
        kwargs = self._default_kwargs()
        kwargs["architecture_path"] = None
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **kwargs,
        ))

        self.assertEqual(msg.cause_by, "plan_ready")


class TestPlannerRole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prd_path = Path(self.tmpdir) / "prd.md"
        self.architecture_path = Path(self.tmpdir) / "architecture.md"
        self.tasks_path = Path(self.tmpdir) / "tasks-TKT-001.json"

        self.prd_path.write_text("# PRD\n\nImplement login.", encoding="utf-8")
        self.architecture_path.write_text(
            "# Architecture\n\nUse a controller + service.", encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_role(self, env=None, run_ai=None, **kwargs):
        defaults = {
            "ticket_id": "TKT-001",
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "prd_path": self.prd_path,
            "tasks_path": self.tasks_path,
            "phase_name": "planning",
            "timeout_seconds": 120,
        }
        defaults.update(kwargs)
        role = PlannerRole(run_ai=run_ai, **defaults)
        if env is not None:
            env.add_role(role)
        return role

    def test_planner_role_triggers_on_architecture_ready(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Auth endpoint",
                    "description": "Create login API.",
                    "dependencies": [],
                    "files_to_touch": ["auth.py"],
                    "complexity": "M",
                    "qa_checklist": ["Returns token."],
                }
            ])

        role = self._create_role(env=env, run_ai=mock_run_ai)
        env.publish_message(Message(
            content="PRD ready",
            sent_from="pm-lead",
            cause_by="prd_ready",
            send_to={"orchestrator"},
            metadata={"path": str(self.prd_path)},
        ))
        env.publish_message(Message(
            content="Architecture ready",
            sent_from="architect",
            cause_by="architecture_ready",
            send_to={"planner"},
            metadata={"path": str(self.architecture_path)},
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertTrue(self.tasks_path.exists())
        self.assertEqual(response.sent_from, "planner")
        self.assertEqual(response.cause_by, "plan_ready")
        self.assertEqual(response.send_to, {"orchestrator"})

    def test_planner_role_triggers_on_prd_ready_when_no_architect(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Auth endpoint",
                    "description": "Create login API.",
                    "dependencies": [],
                    "files_to_touch": ["auth.py"],
                    "complexity": "M",
                    "qa_checklist": ["Returns token."],
                }
            ])

        role = self._create_role(env=env, run_ai=mock_run_ai)
        env.publish_message(Message(
            content="PRD ready",
            sent_from="pm-lead",
            cause_by="prd_ready",
            send_to={"planner"},
            metadata={"path": str(self.prd_path)},
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertTrue(self.tasks_path.exists())
        self.assertEqual(response.cause_by, "plan_ready")

    def test_planner_role_waits_on_prd_ready_when_architect_present(self):
        env = Environment()

        # Add a placeholder architect role so the planner knows to wait.
        class FakeArchitect:
            role_id = "architect"
        env.add_role(FakeArchitect())

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Auth endpoint",
                    "description": "Create login API.",
                    "dependencies": [],
                    "files_to_touch": ["auth.py"],
                    "complexity": "M",
                    "qa_checklist": ["Returns token."],
                }
            ])

        role = self._create_role(env=env, run_ai=mock_run_ai)
        env.publish_message(Message(
            content="PRD ready",
            sent_from="pm-lead",
            cause_by="prd_ready",
            send_to={"planner"},
            metadata={"path": str(self.prd_path)},
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNone(response)
        self.assertFalse(self.tasks_path.exists())

        # Now the architect publishes architecture_ready.
        env.publish_message(Message(
            content="Architecture ready",
            sent_from="architect",
            cause_by="architecture_ready",
            send_to={"planner"},
            metadata={"path": str(self.architecture_path)},
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertTrue(self.tasks_path.exists())
        self.assertEqual(response.cause_by, "plan_ready")

    def test_planner_role_does_not_reprocess_same_message(self):
        env = Environment()

        call_count = {"n": 0}

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            call_count["n"] += 1
            return json.dumps([
                {
                    "id": "TKT-001-T1",
                    "title": "Auth endpoint",
                    "description": "Create login API.",
                    "dependencies": [],
                    "files_to_touch": ["auth.py"],
                    "complexity": "M",
                    "qa_checklist": ["Returns token."],
                }
            ])

        role = self._create_role(env=env, run_ai=mock_run_ai)
        env.publish_message(Message(
            content="Architecture ready",
            sent_from="architect",
            cause_by="architecture_ready",
            send_to={"planner"},
            metadata={"path": str(self.architecture_path)},
        ))

        response1 = asyncio.run(role.run(env))
        response2 = asyncio.run(role.run(env))

        self.assertIsNotNone(response1)
        self.assertIsNone(response2)
        self.assertEqual(call_count["n"], 1)

    def test_think_returns_none_when_no_relevant_message(self):
        role = self._create_role()
        context = [
            Message(
                content=" unrelated",
                sent_from="orchestrator",
                cause_by="chat",
                send_to={"planner"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNone(action)

    def test_think_prefers_architecture_ready(self):
        role = self._create_role()
        context = [
            Message(
                content="PRD ready",
                sent_from="pm-lead",
                cause_by="prd_ready",
                send_to={"planner"},
                metadata={"path": str(self.prd_path)},
            ),
            Message(
                content="Architecture ready",
                sent_from="architect",
                cause_by="architecture_ready",
                send_to={"planner"},
                metadata={"path": str(self.architecture_path)},
            ),
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNotNone(action)


if __name__ == "__main__":
    unittest.main()
