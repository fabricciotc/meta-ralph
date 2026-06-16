import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

import communication_bus as bus


class TestCommunicationBus(unittest.TestCase):
    def test_send_chat_message(self):
        state = {}
        msg = bus.send_message(state, "user", "orchestrator", "chat", {"text": "Hello"})
        self.assertEqual(msg["from"], "user")
        self.assertEqual(msg["to"], "orchestrator")
        self.assertEqual(msg["messageType"], "chat")
        self.assertEqual(msg["payload"]["text"], "Hello")
        self.assertFalse(msg["handled"])
        self.assertIn("id", msg)

    def test_get_log_filters_chat(self):
        state = {}
        bus.send_message(state, "user", "orchestrator", "chat", {"text": "Hello"})
        bus.publish_event(state, "orchestrator", "status_changed", {"status": "running"})
        log = bus.get_log(state, type_filter="message", message_type="chat")
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["messageType"], "chat")

    def test_get_messages_for_participant(self):
        state = {}
        bus.send_message(state, "user", "engineer-T1", "chat", {"text": "Review"})
        bus.send_message(state, "engineer-T1", "user", "chat", {"text": "OK"})
        msgs = bus.get_messages_for(state, "user", message_type="chat")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["from"], "engineer-T1")

    def test_mark_handled(self):
        state = {}
        msg = bus.send_message(state, "user", "orchestrator", "chat", {"text": "Hello"})
        found = bus.mark_handled(state, msg["id"], {"answer": "Hello back"})
        self.assertTrue(found)
        log = bus.get_log(state)
        self.assertTrue(log[0]["handled"])
        self.assertEqual(log[0]["result"]["answer"], "Hello back")

    def test_send_mirrored_message_without_pending_action(self):
        state = {}
        msg = bus.send_message(
            state,
            "engineer-T1",
            "all",
            "task_report",
            {"text": "Task completed."},
            add_pending=False,
        )
        self.assertEqual(msg["messageType"], "task_report")
        self.assertEqual(bus.get_pending_actions(state), [])


if __name__ == "__main__":
    unittest.main()
