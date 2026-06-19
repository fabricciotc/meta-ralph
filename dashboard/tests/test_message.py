import sys
import uuid
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from core.models import Message


class TestMessage(unittest.TestCase):
    def test_create_message(self):
        msg = Message(content="hello", sent_from="orchestrator", cause_by="start")
        self.assertEqual(msg.content, "hello")
        self.assertEqual(msg.sent_from, "orchestrator")
        self.assertEqual(msg.cause_by, "start")
        self.assertEqual(msg.role, "assistant")
        self.assertEqual(msg.send_to, {"all"})
        self.assertIsNotNone(msg.id)

    def test_to_dict_roundtrip(self):
        msg = Message(content="hello", sent_from="orchestrator", cause_by="start")
        d = msg.to_dict()
        self.assertEqual(d["content"], "hello")
        restored = Message.from_dict(d)
        self.assertEqual(restored.content, "hello")
        self.assertEqual(restored.sent_from, "orchestrator")

    def test_message_has_msg_type_and_routing_key(self):
        msg = Message(
            content="hello",
            sent_from="orchestrator",
            cause_by="start",
            msg_type="task_assigned",
            routing_key="engineer-1",
        )
        self.assertEqual(msg.msg_type, "task_assigned")
        self.assertEqual(msg.routing_key, "engineer-1")

    def test_message_defaults(self):
        msg = Message(content="hello", sent_from="orchestrator", cause_by="start")
        self.assertEqual(msg.msg_type, "event")
        self.assertIsNone(msg.routing_key)

    def test_message_is_for_recipient(self):
        msg = Message(
            content="hello", sent_from="orchestrator", cause_by="start", send_to={"role1"}
        )
        self.assertTrue(msg.is_for("role1"))
        self.assertFalse(msg.is_for("role2"))

    def test_message_broadcast_is_for_everyone(self):
        msg = Message(
            content="hello", sent_from="orchestrator", cause_by="start", send_to={"all"}
        )
        self.assertTrue(msg.is_for("role1"))
        self.assertTrue(msg.is_broadcast())

    def test_message_to_dict_roundtrips_new_fields(self):
        msg = Message(
            content="hello",
            sent_from="orchestrator",
            cause_by="start",
            msg_type="task_assigned",
            routing_key="engineer-1",
        )
        d = msg.to_dict()
        restored = Message.from_dict(d)
        self.assertEqual(restored.msg_type, "task_assigned")
        self.assertEqual(restored.routing_key, "engineer-1")


if __name__ == "__main__":
    unittest.main()
