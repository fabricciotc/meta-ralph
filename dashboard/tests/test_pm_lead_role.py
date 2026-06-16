from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.consolidate_prd_action import ConsolidatePRDAction
from core.environment import Environment
from core.models import Message
from core.roles.pm_lead_role import PMLeadRole


class TestConsolidatePRDAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prd_path = Path(self.tmpdir) / "prd.md"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_kwargs(self, overrides=None):
        kwargs = {
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "research_files": {},
            "prd_path": self.prd_path,
            "build_consolidator_prompt": lambda title, description, research_files, prd_path: f"PROMPT {title} {description} {prd_path}",
            "extract_prd": lambda output, title, description: output,
            "parse_clarifications": lambda output: {},
            "write_fallback_prd": lambda prd_path, title, description: f"# Fallback PRD\n\n{title}\n\n{description}",
            "send_clarification": lambda sub_id, question: None,
            "send_completion": lambda prd_path, preview: None,
            "phase_name": "pm_consolidate",
            "timeout_seconds": 120,
        }
        if overrides:
            kwargs.update(overrides)
        return kwargs

    def test_consolidate_action_writes_prd(self):
        research_file = Path(self.tmpdir) / "research.md"
        research_file.write_text("# Findings\n- key point", encoding="utf-8")

        ai_calls = []

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            ai_calls.append({
                "prompt": prompt,
                "phase_name": phase_name,
                "timeout_seconds": timeout_seconds,
                "agent_id": agent_id,
            })
            return "# PRD\n\n1. Summary\n\nDetailed PRD content."

        completion_calls = []

        def mock_send_completion(prd_path, preview):
            completion_calls.append({"prd_path": prd_path, "preview": preview})

        action = ConsolidatePRDAction("consolidate-prd", "Consolidate PRD")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs({
                "research_files": {"pm-domain": research_file},
                "send_completion": mock_send_completion,
            }),
        ))

        self.assertTrue(self.prd_path.exists())
        self.assertEqual(
            self.prd_path.read_text(encoding="utf-8"),
            "# PRD\n\n1. Summary\n\nDetailed PRD content.",
        )

        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["phase_name"], "pm_consolidate")
        self.assertEqual(ai_calls[0]["timeout_seconds"], 120)
        self.assertEqual(ai_calls[0]["agent_id"], "pm-research-agents")
        self.assertIn("Login", ai_calls[0]["prompt"])

        self.assertEqual(len(completion_calls), 1)
        self.assertEqual(completion_calls[0]["prd_path"], self.prd_path)
        self.assertIn("Detailed PRD", completion_calls[0]["preview"])

        self.assertEqual(msg.sent_from, "pm-research-agents")
        self.assertEqual(msg.cause_by, "prd_ready")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertIn("Detailed PRD", msg.content)
        self.assertEqual(msg.metadata.get("artifact"), "PRD")
        self.assertEqual(msg.metadata.get("path"), str(self.prd_path))
        self.assertIn("Detailed PRD", msg.metadata.get("preview", ""))
        self.assertFalse(msg.metadata.get("fallback", True))

    def test_consolidate_action_requests_clarifications(self):
        research_file = Path(self.tmpdir) / "research.md"
        research_file.write_text("# Findings", encoding="utf-8")

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "PENDING CLARIFICATIONS:\npm-domain: What is the OAuth flow?\npm-technical: Which provider should be used?\n\n# PRD\n1. Summary"

        clarification_calls = []

        def mock_send_clarification(sub_id, question):
            clarification_calls.append({"sub_id": sub_id, "question": question})

        def mock_parse_clarifications(output):
            clarifications = {}
            marker = "PENDING CLARIFICATIONS:"
            idx = output.find(marker)
            if idx != -1:
                block = output[idx + len(marker):]
                for line in block.splitlines():
                    line = line.strip()
                    if ":" in line and not line.startswith("-"):
                        sid, question = line.split(":", 1)
                        clarifications[sid.strip()] = question.strip()
            return clarifications

        action = ConsolidatePRDAction("consolidate-prd", "Consolidate PRD")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs({
                "research_files": {"pm-domain": research_file, "pm-technical": research_file},
                "send_clarification": mock_send_clarification,
                "parse_clarifications": mock_parse_clarifications,
            }),
        ))

        self.assertFalse(self.prd_path.exists())
        self.assertEqual(len(clarification_calls), 2)
        self.assertEqual(clarification_calls[0]["sub_id"], "pm-domain")
        self.assertEqual(clarification_calls[1]["sub_id"], "pm-technical")

        self.assertEqual(msg.sent_from, "pm-research-agents")
        self.assertEqual(msg.cause_by, "clarifications_requested")
        self.assertEqual(msg.send_to, {"pm-research-agents"})
        self.assertEqual(msg.content, "")
        self.assertIn("pm-domain", msg.metadata.get("clarifications", {}))

    def test_consolidate_action_fallback_when_no_research(self):
        fallback_calls = []

        def mock_write_fallback_prd(prd_path, title, description):
            fallback_calls.append({"prd_path": prd_path, "title": title, "description": description})
            return f"# Fallback PRD\n\n{title}\n\n{description}"

        completion_calls = []

        def mock_send_completion(prd_path, preview):
            completion_calls.append({"prd_path": prd_path, "preview": preview})

        action = ConsolidatePRDAction("consolidate-prd", "Consolidate PRD")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=None,
            **self._default_kwargs({
                "research_files": {},
                "write_fallback_prd": mock_write_fallback_prd,
                "send_completion": mock_send_completion,
            }),
        ))

        self.assertEqual(len(fallback_calls), 1)
        self.assertEqual(fallback_calls[0]["prd_path"], self.prd_path)

        self.assertTrue(self.prd_path.exists())
        self.assertEqual(
            self.prd_path.read_text(encoding="utf-8"),
            "# Fallback PRD\n\nLogin\n\nAllow users to log in",
        )

        self.assertEqual(len(completion_calls), 1)
        self.assertEqual(completion_calls[0]["prd_path"], self.prd_path)

        self.assertEqual(msg.cause_by, "prd_ready")
        self.assertEqual(msg.send_to, {"orchestrator"})
        self.assertTrue(msg.metadata.get("fallback"))

    def test_consolidate_action_fallback_on_empty_ai_output(self):
        research_file = Path(self.tmpdir) / "research.md"
        research_file.write_text("# Findings", encoding="utf-8")

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return None

        fallback_calls = []

        def mock_write_fallback_prd(prd_path, title, description):
            fallback_calls.append({"prd_path": prd_path})
            return f"# Fallback PRD\n\n{title}"

        completion_calls = []

        def mock_send_completion(prd_path, preview):
            completion_calls.append({"prd_path": prd_path})

        action = ConsolidatePRDAction("consolidate-prd", "Consolidate PRD")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs({
                "research_files": {"pm-domain": research_file},
                "write_fallback_prd": mock_write_fallback_prd,
                "send_completion": mock_send_completion,
            }),
        ))

        self.assertEqual(len(fallback_calls), 1)
        self.assertEqual(len(completion_calls), 1)
        self.assertTrue(self.prd_path.exists())
        self.assertEqual(msg.cause_by, "prd_ready")
        self.assertTrue(msg.metadata.get("fallback"))

    def test_consolidate_action_async_run_ai(self):
        research_file = Path(self.tmpdir) / "research.md"
        research_file.write_text("# Findings", encoding="utf-8")

        async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            await asyncio.sleep(0)
            return "# Async PRD"

        action = ConsolidatePRDAction("consolidate-prd", "Consolidate PRD")
        msg = asyncio.run(action.run(
            context=[],
            run_ai=mock_run_ai,
            **self._default_kwargs({
                "research_files": {"pm-domain": research_file},
            }),
        ))

        self.assertEqual(self.prd_path.read_text(encoding="utf-8"), "# Async PRD")
        self.assertEqual(msg.cause_by, "prd_ready")


class TestPMLeadRole(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prd_path = Path(self.tmpdir) / "prd.md"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_role(self, run_ai=None, subagents=None, **kwargs):
        defaults = {
            "ticket_title": "Login",
            "ticket_description": "Allow users to log in",
            "prd_path": self.prd_path,
            "build_consolidator_prompt": lambda title, description, research_files, prd_path: f"PROMPT {title} {description} {prd_path}",
            "extract_prd": lambda output, title, description: output,
            "parse_clarifications": lambda output: {},
            "write_fallback_prd": lambda prd_path, title, description: f"# Fallback PRD\n\n{title}",
            "send_clarification": lambda sub_id, question: None,
            "send_completion": lambda prd_path, preview: None,
            "phase_name": "pm_consolidate",
            "timeout_seconds": 120,
        }
        defaults.update(kwargs)
        return PMLeadRole(
            run_ai=run_ai,
            subagents=subagents or ["pm-domain", "pm-ux", "pm-technical", "pm-integration", "pm-risk"],
            **defaults,
        )

    def test_pm_lead_role_collects_research_and_consolidates(self):
        env = Environment()

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return "# PRD\n\nConsolidated PRD content."

        role = self._create_role(run_ai=mock_run_ai)
        env.add_role(role)

        for sub_id in role.subagents:
            research_path = Path(self.tmpdir) / f"{sub_id}.md"
            research_path.write_text(f"# {sub_id} findings", encoding="utf-8")
            env.publish_message(Message(
                content=f"Research from {sub_id}",
                sent_from=sub_id,
                cause_by="research",
                send_to={"pm-research-agents"},
                metadata={"file": str(research_path), "sub_id": sub_id},
            ))

        response = asyncio.run(role.run(env))

        self.assertTrue(self.prd_path.exists())
        self.assertEqual(
            self.prd_path.read_text(encoding="utf-8"),
            "# PRD\n\nConsolidated PRD content.",
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.sent_from, "pm-research-agents")
        self.assertEqual(response.cause_by, "prd_ready")
        self.assertEqual(response.send_to, {"orchestrator"})
        self.assertTrue(role.prd_ready)

    def test_pm_lead_role_clarification_loop(self):
        env = Environment()

        outputs = [
            "PENDING CLARIFICATIONS:\npm-domain: What is the flow?\n\n# PRD\n1. Summary",
            "# PRD\n\nFinal consolidated PRD.",
        ]
        call_index = {"idx": 0}

        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            output = outputs[call_index["idx"]]
            call_index["idx"] += 1
            return output

        def mock_parse_clarifications(output):
            clarifications = {}
            marker = "PENDING CLARIFICATIONS:"
            idx = output.find(marker)
            if idx != -1:
                block = output[idx + len(marker):]
                for line in block.splitlines():
                    line = line.strip()
                    if ":" in line and not line.startswith("-"):
                        sid, question = line.split(":", 1)
                        clarifications[sid.strip()] = question.strip()
            return clarifications

        clarification_messages = []

        def mock_send_clarification(sub_id, question):
            clarification_messages.append({"sub_id": sub_id, "question": question})
            env.publish_message(Message(
                content=question,
                sent_from="pm-research-agents",
                cause_by="request_clarification",
                send_to={sub_id},
                metadata={"question": question},
            ))

        role = self._create_role(
            run_ai=mock_run_ai,
            parse_clarifications=mock_parse_clarifications,
            send_clarification=mock_send_clarification,
            subagents=["pm-domain", "pm-technical"],
        )
        env.add_role(role)

        for sub_id in role.subagents:
            research_path = Path(self.tmpdir) / f"{sub_id}.md"
            research_path.write_text(f"# {sub_id} findings", encoding="utf-8")
            env.publish_message(Message(
                content=f"Research from {sub_id}",
                sent_from=sub_id,
                cause_by="research",
                send_to={"pm-research-agents"},
                metadata={"file": str(research_path), "sub_id": sub_id},
            ))

        response = asyncio.run(role.run(env))

        self.assertIsNotNone(response)
        self.assertEqual(response.cause_by, "clarifications_requested")
        self.assertEqual(response.send_to, {"pm-research-agents"})
        self.assertEqual(len(clarification_messages), 1)
        self.assertEqual(clarification_messages[0]["sub_id"], "pm-domain")

        self.assertFalse(self.prd_path.exists())
        self.assertIn("pm-domain", role.pending_clarifications)

        # Simulate clarification response from pm-domain
        updated_path = Path(self.tmpdir) / "pm-domain-clarified.md"
        updated_path.write_text("# pm-domain clarified findings", encoding="utf-8")
        env.publish_message(Message(
            content="Clarified research from pm-domain",
            sent_from="pm-domain",
            cause_by="research",
            send_to={"pm-research-agents"},
            metadata={"file": str(updated_path), "sub_id": "pm-domain"},
        ))

        response = asyncio.run(role.run(env))

        self.assertTrue(self.prd_path.exists())
        self.assertEqual(
            self.prd_path.read_text(encoding="utf-8"),
            "# PRD\n\nFinal consolidated PRD.",
        )
        self.assertEqual(response.cause_by, "prd_ready")
        self.assertEqual(role.research_files["pm-domain"], updated_path)
        self.assertEqual(len(role.pending_clarifications), 0)


if __name__ == "__main__":
    unittest.main()
