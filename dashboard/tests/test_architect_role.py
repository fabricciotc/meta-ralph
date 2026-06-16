from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.architect_action import ArchitectAction
from core.actions.design_review_action import DesignReviewAction
from core.environment import Environment
from core.models import Message
from core.roles.architect_role import ArchitectRole


class TestArchitectAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prd_path = Path(self.tmpdir) / "prd.md"
        self.architecture_path = Path(self.tmpdir) / "architecture.md"
        self.prd_path.write_text("# PRD\n\nImplement login.", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "prd_path": self.prd_path,
            "architecture_path": self.architecture_path,
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "ticket_id": "TKT-001",
            "phase_name": "architect",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_architect_action_writes_architecture(self):
        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return "# Architecture\n\n## Decisions\nUse OAuth."

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.architecture_path.exists())
        self.assertEqual(
            self.architecture_path.read_text(encoding="utf-8"),
            "# Architecture\n\n## Decisions\nUse OAuth.",
        )

        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["phase_name"], "architect")
        self.assertEqual(ai_calls[0]["timeout_seconds"], 120)
        self.assertEqual(ai_calls[0]["agent_id"], "architect")
        self.assertIn("Architect", ai_calls[0]["prompt"])
        self.assertIn("PRD:", ai_calls[0]["prompt"])

        self.assertEqual(msg.sent_from, "architect")
        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertEqual(msg.metadata.get("artifact"), "architecture")
        self.assertEqual(msg.metadata.get("path"), str(self.architecture_path))
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_architect_action_uses_review_answers(self):
        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({"prompt": prompt})
            return "# Architecture\n\nUse JWT."

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs({"review_answers": "Use OAuth2 with Google"}),
        ))

        self.assertIn("DESIGN REVIEW ANSWERS", ai_calls[0]["prompt"])
        self.assertIn("Use OAuth2 with Google", ai_calls[0]["prompt"])
        self.assertEqual(msg.cause_by, "architecture_ready")

    def test_architect_action_fallback_when_no_runner(self):
        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=None,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.architecture_path.exists())
        content = self.architecture_path.read_text(encoding="utf-8")
        self.assertIn("Architecture: Login", content)
        self.assertIn("Preserve the project's existing stack", content)

        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_architect_action_fallback_on_empty_ai_output(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return None

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.architecture_path.exists())
        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_architect_action_async_run_ai(self):
        async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "# Architecture\n\nAsync arch."

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(self.architecture_path.read_text(encoding="utf-8"), "# Architecture\n\nAsync arch.")
        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_architect_action_missing_required_kwargs_raises(self):
        action = ArchitectAction("architect-generate", "Generate Architecture")

        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], prd_path=self.prd_path))

        self.assertIn("missing required kwargs", str(cm.exception).lower())


class TestDesignReviewAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "architecture_content": "# Architecture\n\n## Decisions\nPENDING DECISIONS:\n1. First-party OAuth or third-party OAuth?\n2. Relational database or NoSQL?",
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "ticket_id": "TKT-001",
            "phase_name": "design_review",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_design_review_action_requests_review(self):
        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({"prompt": prompt})
            return (
                "PENDING DECISIONS:\n"
                "1. First-party OAuth or third-party OAuth?\n"
                "2. Relational database or NoSQL?"
            )

        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(len(ai_calls), 1)
        self.assertIn("design decisions", ai_calls[0]["prompt"].lower())
        self.assertIn("TICKET:", ai_calls[0]["prompt"])

        self.assertEqual(msg.sent_from, "architect")
        self.assertEqual(msg.cause_by, "design_review_requested")
        self.assertEqual(msg.send_to, {"orchestrator"})
        questions = msg.metadata.get("questions", [])
        self.assertEqual(len(questions), 2)
        self.assertIn("OAuth", questions[0])
        self.assertIn("Relational database", questions[1])

    def test_design_review_action_returns_assumed_answers_without_runner(self):
        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=None,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "design_review_answered")
        self.assertTrue(msg.metadata.get("assumed"))
        self.assertIn("answers", msg.metadata)
        self.assertIn("current stack and patterns", str(msg.metadata["answers"]))
        self.assertIn("Assumed answers", msg.content)

    def test_design_review_action_answers_when_no_questions_extracted(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "NO_PENDING_DECISIONS"

        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "design_review_answered")
        self.assertTrue(msg.metadata.get("assumed"))
        self.assertIn("answers", msg.metadata)

    def test_design_review_action_async_run_ai(self):
        async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "1. Use cache?\n2. Rate limiting?"

        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "design_review_requested")
        self.assertEqual(len(msg.metadata.get("questions", [])), 2)

    def test_design_review_action_missing_required_kwargs_raises(self):
        action = DesignReviewAction("design-review", "Design Review")

        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], architecture_content="arch"))

        self.assertIn("missing required kwargs", str(cm.exception).lower())


class TestArchitectRole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prd_path = Path(self.tmpdir) / "prd.md"
        self.architecture_path = Path(self.tmpdir) / "architecture.md"
        self.prd_path.write_text("# PRD\n\nLogin with OAuth.", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_role(self, run_ai=None, **kwargs):
        defaults = {
            "prd_path": self.prd_path,
            "architecture_path": self.architecture_path,
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "ticket_id": "TKT-001",
            "phase_name": "architect",
            "timeout_seconds": 120,
        }
        defaults.update(kwargs)
        return ArchitectRole(run_ai=run_ai, **defaults)

    def test_architect_role_triggers_on_prd_ready(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "# Architecture\n\nUse JWT for authentication."

        role = self._create_role(run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(Message(
            content="PRD ready",
            sent_from="pm-research-agents",
            cause_by="prd_ready",
            send_to={"architect"},
            metadata={
                "ticket_id": "TKT-001",
                "ticket_title": "Login",
                "ticket_description": "Allow users to log in",
                "path": str(self.prd_path),
            },
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertEqual(response.sent_from, "architect")
        self.assertEqual(response.cause_by, "architecture_ready")
        self.assertEqual(response.send_to, {"orchestrator"})
        self.assertTrue(self.architecture_path.exists())
        self.assertEqual(
            self.architecture_path.read_text(encoding="utf-8"),
            "# Architecture\n\nUse JWT for authentication.",
        )
        self.assertTrue(role._architecture_ready)

    def test_architect_role_requests_design_review_for_pending_decisions(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            if "design decisions" in prompt.lower():
                return "PENDING DECISIONS:\n1. First-party or third-party OAuth?\n2. SQL or NoSQL?"
            return (
                "# Architecture\n\n"
                "## Decisions\n"
                "PENDING DECISIONS:\n"
                "1. First-party or third-party OAuth?\n"
                "2. SQL or NoSQL?"
            )

        role = self._create_role(run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(Message(
            content="PRD ready",
            sent_from="pm-research-agents",
            cause_by="prd_ready",
            send_to={"architect"},
            metadata={
                "ticket_id": "TKT-001",
                "path": str(self.prd_path),
            },
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertEqual(response.cause_by, "design_review_requested")
        self.assertEqual(response.sent_from, "architect")
        self.assertTrue(role._pending_review)
        self.assertFalse(role._architecture_ready)
        questions = response.metadata.get("questions", [])
        self.assertEqual(len(questions), 2)

        queued = env.get_messages_for("orchestrator")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[-1].cause_by, "design_review_requested")

    def test_architect_role_completes_after_review_answers(self):
        env = Environment()

        outputs = [
            # First architect call: has pending decisions.
            "# Architecture\n\nPENDING DECISIONS:\n1. First-party or third-party OAuth?",
            # Design review questions.
            "PENDING DECISIONS:\n1. First-party or third-party OAuth?",
            # Second architect call: refined architecture.
            "# Architecture\n\nUse OAuth2 with Google. No pending decisions.",
        ]
        call_index = {"idx": 0}

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            output = outputs[call_index["idx"]]
            call_index["idx"] += 1
            return output

        role = self._create_role(run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(Message(
            content="PRD ready",
            sent_from="pm-research-agents",
            cause_by="prd_ready",
            send_to={"architect"},
            metadata={
                "ticket_id": "TKT-001",
                "path": str(self.prd_path),
            },
        ))

        response = asyncio.run(role.run(env))
        self.assertEqual(response.cause_by, "design_review_requested")

        # Simulate design review answers from orchestrator/user.
        env.publish_message(Message(
            content="Use OAuth2 with Google",
            sent_from="orchestrator",
            cause_by="design_review_answered",
            send_to={"architect"},
            metadata={
                "ticket_id": "TKT-001",
                "answers": {"First-party or third-party OAuth?": "Use OAuth2 with Google"},
            },
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertEqual(response.cause_by, "architecture_ready")
        self.assertTrue(role._architecture_ready)
        self.assertFalse(role._pending_review)
        self.assertIn("OAuth2 with Google", response.content)

    def test_architect_role_ignores_irrelevant_messages(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "# Architecture"

        role = self._create_role(run_ai=mock_run_ai)
        env.add_role(role)

        env.publish_message(Message(
            content=" unrelated",
            sent_from="orchestrator",
            cause_by="chat",
            send_to={"architect"},
        ))

        response = asyncio.run(role.run(env))
        self.assertIsNone(response)

    def test_think_returns_none_when_done(self):
        role = self._create_role()
        role._architecture_ready = True

        context = [
            Message(
                content="PRD ready",
                sent_from="pm-research-agents",
                cause_by="prd_ready",
                send_to={"architect"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNone(action)


if __name__ == "__main__":
    unittest.main()
