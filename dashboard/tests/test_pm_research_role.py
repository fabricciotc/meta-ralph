from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.research_action import ResearchAction
from core.environment import Environment
from core.models import Message
from core.roles.pm_research_role import PMResearchRole


class TestResearchAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_research_action_writes_file_and_calls_ai_runner(self):
        output_dir = Path(self.tmpdir) / "pm-research"
        output_dir.mkdir()

        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return "# Hallazgos\n- Punto clave"

        update_calls = []

        def mock_update_agent(agent_id, **kwargs):
            update_calls.append((agent_id, dict(kwargs)))

        def mock_build_prompt(sub_id, focus, title, description, follow_up):
            return f"PROMPT {sub_id} {focus} {title} {description} {follow_up}"

        action = ResearchAction("research-pm-domain", "PM Domain Research")

        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            sub_id="pm-domain",
            sub_name="Domain Analyst",
            focus="domain analysis",
            ticket_title="Login",
            ticket_description="Allow users to log in",
            ticket_id="TKT-001",
            follow_up="Check OAuth",
            output_dir=output_dir,
            build_prompt=mock_build_prompt,
            update_agent=mock_update_agent,
            phase_name="pm_research",
            timeout_seconds=120,
        ))

        expected_path = output_dir / "TKT-001-pm-domain.md"

        self.assertTrue(expected_path.exists())
        self.assertEqual(expected_path.read_text(encoding="utf-8"), "# Hallazgos\n- Punto clave")

        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["phase_name"], "pm_research")
        self.assertEqual(ai_calls[0]["timeout_seconds"], 120)
        self.assertEqual(ai_calls[0]["agent_id"], "pm-domain")
        self.assertEqual(ai_calls[0]["prompt"], "PROMPT pm-domain domain analysis Login Allow users to log in Check OAuth")

        self.assertEqual(len(update_calls), 2)
        self.assertEqual(update_calls[0][0], "pm-domain")
        self.assertEqual(update_calls[0][1]["status"], "running")
        self.assertEqual(update_calls[0][1]["progress"], 10)
        self.assertEqual(update_calls[1][0], "pm-domain")
        self.assertEqual(update_calls[1][1]["status"], "done")
        self.assertEqual(update_calls[1][1]["progress"], 100)

        self.assertEqual(msg.sent_from, "pm-domain")
        self.assertEqual(msg.cause_by, "research")
        self.assertEqual(msg.send_to, {"pm-research-agents", "all"})
        self.assertEqual(msg.content, "# Hallazgos\n- Punto clave")
        self.assertEqual(msg.metadata["file"], str(expected_path))
        self.assertEqual(msg.metadata["sub_id"], "pm-domain")
        self.assertTrue(msg.metadata["follow_up"])

    def test_research_action_handles_missing_output(self):
        output_dir = Path(self.tmpdir) / "pm-research"
        output_dir.mkdir()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return None

        def mock_update_agent(agent_id, **kwargs):
            pass

        def mock_build_prompt(sub_id, focus, title, description, follow_up):
            return "prompt"

        action = ResearchAction("research-pm-domain", "PM Domain Research")

        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            sub_id="pm-domain",
            sub_name="Domain Analyst",
            focus="domain analysis",
            ticket_title="Login",
            ticket_description="Allow users to log in",
            ticket_id="TKT-001",
            output_dir=output_dir,
            build_prompt=mock_build_prompt,
            update_agent=mock_update_agent,
            phase_name="pm_research",
            timeout_seconds=120,
        ))

        expected_path = output_dir / "TKT-001-pm-domain.md"
        self.assertFalse(expected_path.exists())

        self.assertEqual(msg.content, "")
        self.assertEqual(msg.sent_from, "pm-domain")
        self.assertEqual(msg.cause_by, "research")
        self.assertEqual(msg.send_to, {"pm-research-agents"})
        self.assertEqual(msg.metadata.get("sub_id"), "pm-domain")

    def test_research_action_async_run_ai(self):
        output_dir = Path(self.tmpdir) / "pm-research"
        output_dir.mkdir()

        async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "# Async findings"

        update_calls = []

        def mock_update_agent(agent_id, **kwargs):
            update_calls.append((agent_id, dict(kwargs)))

        def mock_build_prompt(sub_id, focus, title, description, follow_up):
            return f"PROMPT {sub_id} {focus}"

        action = ResearchAction("research-pm-domain", "PM Domain Research")

        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            sub_id="pm-domain",
            sub_name="Domain Analyst",
            focus="domain analysis",
            ticket_title="Login",
            ticket_description="Allow users to log in",
            ticket_id="TKT-001",
            output_dir=output_dir,
            build_prompt=mock_build_prompt,
            update_agent=mock_update_agent,
            phase_name="pm_research",
            timeout_seconds=120,
        ))

        expected_path = output_dir / "TKT-001-pm-domain.md"
        self.assertTrue(expected_path.exists())
        self.assertEqual(expected_path.read_text(encoding="utf-8"), "# Async findings")
        self.assertEqual(msg.content, "# Async findings")
        self.assertEqual(update_calls[-1][1]["status"], "done")
        self.assertEqual(update_calls[-1][1]["progress"], 100)

    def test_research_action_run_ai_exception_sets_error_and_propagates(self):
        output_dir = Path(self.tmpdir) / "pm-research"
        output_dir.mkdir()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            raise RuntimeError("AI runner exploded")

        update_calls = []

        def mock_update_agent(agent_id, **kwargs):
            update_calls.append((agent_id, dict(kwargs)))

        def mock_build_prompt(sub_id, focus, title, description, follow_up):
            return "prompt"

        action = ResearchAction("research-pm-domain", "PM Domain Research")

        with self.assertRaises(RuntimeError) as cm:
            asyncio.run(action.run(
                context=[],
                run_ai=mock_run_ai,
                sub_id="pm-domain",
                sub_name="Domain Analyst",
                focus="domain analysis",
                ticket_title="Login",
                ticket_description="Allow users to log in",
                ticket_id="TKT-001",
                output_dir=output_dir,
                build_prompt=mock_build_prompt,
                update_agent=mock_update_agent,
                phase_name="pm_research",
                timeout_seconds=120,
            ))

        self.assertEqual(str(cm.exception), "AI runner exploded")

        error_calls = [call for call in update_calls if call[1].get("status") == "error"]
        self.assertEqual(len(error_calls), 1)
        self.assertEqual(error_calls[0][0], "pm-domain")
        self.assertEqual(error_calls[0][1]["progress"], 0)
        self.assertIn("failed", error_calls[0][1]["log"])

    def test_research_action_missing_required_kwargs_raises(self):
        action = ResearchAction("research-pm-domain", "PM Domain Research")

        with self.assertRaises(ValueError) as cm:
            asyncio.run(action.run(context=[], sub_id="pm-domain"))

        self.assertIn("missing required kwargs", str(cm.exception).lower())


class TestPMResearchRole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_pm_research_role_triggers_on_request(self):
        env = Environment()
        output_dir = Path(self.tmpdir) / "pm-research"
        output_dir.mkdir()

        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return "# Domain findings"

        def mock_update_agent(agent_id, **kwargs):
            pass

        def mock_build_prompt(sub_id, focus, title, description, follow_up):
            return f"PROMPT {sub_id} {focus}"

        role = PMResearchRole("pm-domain", "Domain Analyst", "domain analysis")
        role.run_ai = mock_run_ai
        env.add_role(role)

        request = Message(
            content="Investigate domain implications",
            sent_from="pm-lead",
            cause_by="research_request",
            send_to={"pm-domain"},
            metadata={
                "ticket_title": "Login",
                "ticket_description": "Allow users to log in",
                "ticket_id": "TKT-001",
                "focus": "domain analysis",
                "output_dir": output_dir,
                "build_prompt": mock_build_prompt,
                "update_agent": mock_update_agent,
                "phase_name": "pm_research",
                "timeout_seconds": 120,
            },
        )
        env.publish_message(request)

        asyncio.run(env.run_round())

        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["agent_id"], "pm-domain")

        expected_path = output_dir / "TKT-001-pm-domain.md"
        self.assertTrue(expected_path.exists())
        self.assertEqual(expected_path.read_text(encoding="utf-8"), "# Domain findings")

        history = env.memory.get()
        self.assertEqual(len(history), 2)

        response = history[-1]
        self.assertEqual(response.sent_from, "pm-domain")
        self.assertEqual(response.cause_by, "research")
        self.assertEqual(response.send_to, {"pm-research-agents", "all"})
        self.assertEqual(response.metadata["sub_id"], "pm-domain")
        self.assertEqual(response.metadata["file"], str(expected_path))

    def test_think_returns_none_when_no_relevant_message(self):
        role = PMResearchRole("pm-domain", "Domain Analyst", "domain analysis")
        context = [
            Message(
                content=" unrelated",
                sent_from="pm-lead",
                cause_by="chat",
                send_to={"pm-domain"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNone(action)

    def test_think_triggered_by_request_clarification(self):
        role = PMResearchRole("pm-domain", "Domain Analyst", "domain analysis")
        context = [
            Message(
                content="Please clarify",
                sent_from="pm-lead",
                cause_by="request_clarification",
                send_to={"pm-domain"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNotNone(action)
        self.assertEqual(action.action_id, "pm-domain-research")

    def test_think_ignores_messages_from_self(self):
        role = PMResearchRole("pm-domain", "Domain Analyst", "domain analysis")
        context = [
            Message(
                content="Self request",
                sent_from="pm-domain",
                cause_by="research_request",
                send_to={"pm-domain"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNone(action)

    def test_think_triggers_on_send_to_all(self):
        role = PMResearchRole("pm-domain", "Domain Analyst", "domain analysis")
        context = [
            Message(
                content="Broadcast request",
                sent_from="pm-lead",
                cause_by="research_request",
                send_to={"all"},
            )
        ]
        action = asyncio.run(role.think(context))
        self.assertIsNotNone(action)
        self.assertEqual(action.name, "Domain Analyst Research")


if __name__ == "__main__":
    unittest.main()
