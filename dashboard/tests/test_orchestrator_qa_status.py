from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("yaml", MagicMock())
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.environment import Environment
from core.models import Message
from core.orchestrator import Orchestrator


class TestOrchestratorQaStatus(unittest.TestCase):
    def test_finalize_qa_subagent_status_marks_done_and_failed(self):
        env = Environment()
        env.publish_message(Message(
            content="approved",
            sent_from="qa-lead",
            cause_by="review_approved",
            send_to={"orchestrator"},
            metadata={"task_id": "T1", "approved": True, "reason": "Looks good"},
        ))
        env._drain_queue_to_memory()
        env.publish_message(Message(
            content="rejected",
            sent_from="qa-lead",
            cause_by="reject_with_feedback",
            send_to={"orchestrator"},
            metadata={"task_id": "T2", "approved": False, "reason": "Tests missing"},
        ))
        env._drain_queue_to_memory()

        updates = []

        def update_agent(agent_id, **kwargs):
            updates.append((agent_id, kwargs))

        orchestrator = Orchestrator(
            ticket={"id": "TKT-1", "title": "Test"},
            callbacks={"update_agent": update_agent},
        )
        orchestrator.env = env
        orchestrator._finalize_qa_subagent_status(["T1", "T2", "T3"])

        by_id = {agent_id: kwargs for agent_id, kwargs in updates}
        self.assertEqual(by_id["qa-T1"]["status"], "done")
        self.assertEqual(by_id["qa-T2"]["status"], "failed")
        self.assertEqual(by_id["qa-T3"]["status"], "failed")

    def test_finalize_uses_latest_verdict_after_correction_round(self):
        env = Environment()
        env.publish_message(Message(
            content="first rejection",
            sent_from="qa-lead",
            cause_by="reject_with_feedback",
            send_to={"orchestrator"},
            metadata={"task_id": "T1", "approved": False, "reason": "First pass"},
        ))
        env.publish_message(Message(
            content="approved after fix",
            sent_from="qa-lead",
            cause_by="review_approved",
            send_to={"orchestrator"},
            metadata={"task_id": "T1", "approved": True, "reason": "Fixed"},
        ))
        env._drain_queue_to_memory()

        updates = []

        def update_agent(agent_id, **kwargs):
            updates.append((agent_id, kwargs))

        orchestrator = Orchestrator(
            ticket={"id": "TKT-1", "title": "Test"},
            callbacks={"update_agent": update_agent},
        )
        orchestrator.env = env
        orchestrator._finalize_qa_subagent_status(["T1"])

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][0], "qa-T1")
        self.assertEqual(updates[0][1]["status"], "done")


if __name__ == "__main__":
    unittest.main()
