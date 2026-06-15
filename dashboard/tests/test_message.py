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


if __name__ == "__main__":
    unittest.main()
