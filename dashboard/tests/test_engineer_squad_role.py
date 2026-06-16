from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.environment import Environment
from core.models import Message
from core.roles.engineer_squad_role import EngineerSquadRole


class TestEngineerSquadRole(unittest.TestCase):
    def _report_message(
        self,
        task_id: str = "T1",
        status: str = "completed",
        engineer_id: str = "engineer-T1",
    ) -> Message:
        return Message(
            content=f"Report from {engineer_id}: task {task_id} {status}",
            sent_from=engineer_id,
            cause_by="task_report",
            send_to={"engineer-squad"},
            metadata={
                "task_id": task_id,
                "engineer_id": engineer_id,
                "status": status,
                "summary": "implemented",
                "repo_path": "/tmp/repo",
                "branch": f"feature/{task_id}",
                "build_output": "",
                "test_output": "",
                "task": {"id": task_id, "title": f"Task {task_id}"},
            },
        )

    def test_squad_role_acknowledges_completed_task(self):
        env = Environment()
        role = EngineerSquadRole(
            run_ai=lambda *a, **kw: json.dumps({
                "action": "ack",
                "message": "Task completed. Continuing.",
            }),
            ticket_id="TKT-1",
            tasks=[{"id": "T1", "title": "Task 1"}],
        )
        env.add_role(role)
        env.publish_message(self._report_message())
        asyncio.run(env.run_round())

        history = env.memory.get()
        self.assertTrue(any(m.cause_by == "squad_chat" for m in history))
        self.assertTrue(any(m.cause_by == "batch_completed" for m in history))

    def test_squad_role_retries_failed_task(self):
        env = Environment()
        role = EngineerSquadRole(
            run_ai=lambda *a, **kw: json.dumps({
                "action": "retry",
                "message": "Retrying failed task.",
                "instruction": "Fix the build error.",
            }),
            ticket_id="TKT-1",
            max_retries=2,
        )
        env.add_role(role)
        env.publish_message(self._report_message(status="failed"))
        asyncio.run(env.run_round())

        instructions = [m for m in env.memory.get() if m.cause_by == "squad_instruction"]
        self.assertEqual(len(instructions), 1)
        self.assertEqual(instructions[0].send_to, {"engineer-T1"})
        self.assertEqual(instructions[0].metadata.get("instruction"), "Fix the build error.")

    def test_squad_role_escalates_to_user_and_forwards_answer(self):
        env = Environment()
        user_answer = {"value": ""}

        def fake_clarification(question, timeout):
            user_answer["value"] = "Use version 2 of the endpoint"
            return user_answer["value"]

        role = EngineerSquadRole(
            run_ai=lambda *a, **kw: json.dumps({
                "action": "escalate_to_user",
                "message": "Escalating question to the user.",
                "reason": "We do not know which version to use.",
            }),
            ticket_id="TKT-1",
            timeout_seconds=5,
            request_clarification=fake_clarification,
        )
        env.add_role(role)
        env.publish_message(self._report_message(status="needs_fix"))
        asyncio.run(env.run_round())

        history = env.memory.get()
        self.assertTrue(any(m.cause_by == "escalate_to_user" for m in history))
        self.assertTrue(any(
            m.cause_by == "squad_chat" and "User answered" in m.content
            for m in history
        ))
        instructions = [m for m in history if m.cause_by == "squad_instruction"]
        self.assertTrue(any(m.metadata.get("user_answer") == "Use version 2 of the endpoint" for m in instructions))

    def test_squad_role_requests_info_from_pm_and_handles_response(self):
        env = Environment()
        role = EngineerSquadRole(
            run_ai=lambda *a, **kw: json.dumps({
                "action": "request_info_from_pm",
                "message": "Requesting information from PM.",
                "question": "Does the endpoint require authentication?",
            }),
            ticket_id="TKT-1",
        )
        env.add_role(role)
        env.publish_message(self._report_message())
        asyncio.run(env.run_round())

        pm_requests = [m for m in env.memory.get() if m.cause_by == "request_info_from_pm"]
        self.assertEqual(len(pm_requests), 1)
        self.assertIn("pm-research-agents", pm_requests[0].send_to)

        request_id = pm_requests[0].metadata["request_id"]
        env.publish_message(Message(
            content="PM response",
            sent_from="pm-research-agents",
            cause_by="request_info_from_pm_response",
            send_to={"engineer-squad"},
            metadata={
                "request_id": request_id,
                "task_id": "T1",
                "answer": "Yes, it requires authentication.",
            },
        ))
        asyncio.run(env.run_round())

        instructions = [m for m in env.memory.get() if m.cause_by == "squad_instruction"]
        self.assertTrue(any(m.metadata.get("pm_answer") == "Yes, it requires authentication." for m in instructions))

    def test_squad_role_does_not_reprocess_same_report(self):
        env = Environment()
        call_count = {"n": 0}

        def counting_run_ai(*a, **kw):
            call_count["n"] += 1
            return json.dumps({"action": "ack", "message": "ok"})

        role = EngineerSquadRole(run_ai=counting_run_ai, ticket_id="TKT-1")
        env.add_role(role)
        report = self._report_message()
        env.publish_message(report)
        asyncio.run(env.run_round())
        env.publish_message(report)
        asyncio.run(env.run_round())

        self.assertEqual(call_count["n"], 1)


if __name__ == "__main__":
    unittest.main()
