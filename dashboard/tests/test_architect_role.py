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
        self.prd_path.write_text("# PRD\n\nImplementar login.", encoding="utf-8")

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
        kimi_calls = []

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            kimi_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return "# Arquitectura\n\n## Decisiones\nUsar OAuth."

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.architecture_path.exists())
        self.assertEqual(
            self.architecture_path.read_text(encoding="utf-8"),
            "# Arquitectura\n\n## Decisiones\nUsar OAuth.",
        )

        self.assertEqual(len(kimi_calls), 1)
        self.assertEqual(kimi_calls[0]["phase_name"], "architect")
        self.assertEqual(kimi_calls[0]["timeout_seconds"], 120)
        self.assertEqual(kimi_calls[0]["agent_id"], "architect")
        self.assertIn("Arquitecto", kimi_calls[0]["prompt"])
        self.assertIn("PRD:", kimi_calls[0]["prompt"])

        self.assertEqual(msg.sent_from, "architect")
        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertEqual(msg.metadata.get("artifact"), "architecture")
        self.assertEqual(msg.metadata.get("path"), str(self.architecture_path))
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_architect_action_uses_review_answers(self):
        kimi_calls = []

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            kimi_calls.append({"prompt": prompt})
            return "# Arquitectura\n\nUsar JWT."

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs({"review_answers": "Usar OAuth2 con Google"}),
        ))

        self.assertIn("RESPUESTAS DEL DESIGN REVIEW", kimi_calls[0]["prompt"])
        self.assertIn("Usar OAuth2 con Google", kimi_calls[0]["prompt"])
        self.assertEqual(msg.cause_by, "architecture_ready")

    def test_architect_action_fallback_when_no_runner(self):
        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=None,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.architecture_path.exists())
        content = self.architecture_path.read_text(encoding="utf-8")
        self.assertIn("Arquitectura: Login", content)
        self.assertIn("Mantener el stack", content)

        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_architect_action_fallback_on_empty_kimi_output(self):
        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return None

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertTrue(self.architecture_path.exists())
        self.assertEqual(msg.cause_by, "architecture_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_architect_action_async_run_kimi(self):
        async def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "# Arquitectura\n\nAsync arch."

        action = ArchitectAction("architect-generate", "Generate Architecture")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertEqual(self.architecture_path.read_text(encoding="utf-8"), "# Arquitectura\n\nAsync arch.")
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
            "architecture_content": "# Arquitectura\n\n## Decisiones\nDECISIONES PENDIENTES:\n1. ¿OAuth propio o de terceros?\n2. ¿Base de datos relacional o NoSQL?",
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
        kimi_calls = []

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            kimi_calls.append({"prompt": prompt})
            return (
                "DECISIONES PENDIENTES:\n"
                "1. ¿OAuth propio o de terceros?\n"
                "2. ¿Base de datos relacional o NoSQL?"
            )

        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertEqual(len(kimi_calls), 1)
        self.assertIn("decisiones de diseño", kimi_calls[0]["prompt"].lower())
        self.assertIn("TICKET:", kimi_calls[0]["prompt"])

        self.assertEqual(msg.sent_from, "architect")
        self.assertEqual(msg.cause_by, "design_review_requested")
        self.assertEqual(msg.send_to, {"orchestrator"})
        questions = msg.metadata.get("questions", [])
        self.assertEqual(len(questions), 2)
        self.assertIn("OAuth", questions[0])
        self.assertIn("Base de datos", questions[1])

    def test_design_review_action_returns_assumed_answers_without_runner(self):
        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=None,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "design_review_answered")
        self.assertTrue(msg.metadata.get("assumed"))
        self.assertIn("answers", msg.metadata)
        self.assertIn("stack/patrones existentes", str(msg.metadata["answers"]))
        self.assertIn("Respuestas asumidas", msg.content)

    def test_design_review_action_answers_when_no_questions_extracted(self):
        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "SIN_DECISIONES_PENDIENTES"

        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
            **self._default_kwargs(),
        ))

        self.assertEqual(msg.cause_by, "design_review_answered")
        self.assertTrue(msg.metadata.get("assumed"))
        self.assertIn("answers", msg.metadata)

    def test_design_review_action_async_run_kimi(self):
        async def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "1. ¿Usar cache?\n2. ¿Rate limiting?"

        action = DesignReviewAction("design-review", "Design Review")
        msg = asyncio.run(action.run(
            context=[],
            run_kimi=mock_run_kimi,
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
        self.prd_path.write_text("# PRD\n\nLogin con OAuth.", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_role(self, run_kimi=None, **kwargs):
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
        return ArchitectRole(run_kimi=run_kimi, **defaults)

    def test_architect_role_triggers_on_prd_ready(self):
        env = Environment()

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "# Arquitectura\n\nUsar JWT para autenticación."

        role = self._create_role(run_kimi=mock_run_kimi)
        env.add_role(role)

        env.publish_message(Message(
            content="PRD listo",
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
            "# Arquitectura\n\nUsar JWT para autenticación.",
        )
        self.assertTrue(role._architecture_ready)

    def test_architect_role_requests_design_review_for_pending_decisions(self):
        env = Environment()

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            if "decisiones de diseño" in prompt.lower():
                return "DECISIONES PENDIENTES:\n1. ¿OAuth propio o terceros?\n2. ¿SQL o NoSQL?"
            return (
                "# Arquitectura\n\n"
                "## Decisiones\n"
                "DECISIONES PENDIENTES:\n"
                "1. ¿OAuth propio o terceros?\n"
                "2. ¿SQL o NoSQL?"
            )

        role = self._create_role(run_kimi=mock_run_kimi)
        env.add_role(role)

        env.publish_message(Message(
            content="PRD listo",
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
            "# Arquitectura\n\nDECISIONES PENDIENTES:\n1. ¿OAuth propio o terceros?",
            # Design review questions.
            "DECISIONES PENDIENTES:\n1. ¿OAuth propio o terceros?",
            # Second architect call: refined architecture.
            "# Arquitectura\n\nUsar OAuth2 con Google. Sin decisiones pendientes.",
        ]
        call_index = {"idx": 0}

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            output = outputs[call_index["idx"]]
            call_index["idx"] += 1
            return output

        role = self._create_role(run_kimi=mock_run_kimi)
        env.add_role(role)

        env.publish_message(Message(
            content="PRD listo",
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
            content="Usar OAuth2 con Google",
            sent_from="orchestrator",
            cause_by="design_review_answered",
            send_to={"architect"},
            metadata={
                "ticket_id": "TKT-001",
                "answers": {"¿OAuth propio o terceros?": "Usar OAuth2 con Google"},
            },
        ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertEqual(response.cause_by, "architecture_ready")
        self.assertTrue(role._architecture_ready)
        self.assertFalse(role._pending_review)
        self.assertIn("OAuth2 con Google", response.content)

    def test_architect_role_ignores_irrelevant_messages(self):
        env = Environment()

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            return "# Arquitectura"

        role = self._create_role(run_kimi=mock_run_kimi)
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
                content="PRD listo",
                sent_from="pm-research-agents",
                cause_by="prd_ready",
                send_to={"architect"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNone(action)


if __name__ == "__main__":
    unittest.main()
