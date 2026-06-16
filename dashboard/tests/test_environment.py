import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from core.models import Message
from core.environment import Environment


class DummyRole:
    def __init__(self, role_id):
        self.role_id = role_id
        self.observed = []
        self.addresses = {role_id}

    def observe(self, env):
        self.observed = env.get_messages_for(self.role_id)
        return self.observed

    async def run(self, env, **kwargs):
        msgs = self.observe(env)
        if msgs:
            env.publish_message(
                Message(
                    content=f"ack from {self.role_id}",
                    sent_from=self.role_id,
                    cause_by="ack",
                    send_to={"all"},
                )
            )
            return True
        return False


class TestEnvironment(unittest.TestCase):
    def test_publish_and_observe(self):
        env = Environment()
        r1 = DummyRole("role1")
        r2 = DummyRole("role2")
        env.add_role(r1)
        env.add_role(r2)
        env.publish_message(
            Message(content="hello", sent_from="user", cause_by="start", send_to={"role1"})
        )
        self.assertEqual(len(env.get_messages_for("role1")), 1)
        self.assertEqual(len(env.get_messages_for("role2")), 0)

    def test_run_round(self):
        import asyncio

        env = Environment()
        r1 = DummyRole("role1")
        env.add_role(r1)
        env.publish_message(
            Message(content="hello", sent_from="user", cause_by="start", send_to={"role1"})
        )
        active = asyncio.run(env.run_round())
        self.assertTrue(active)
        self.assertEqual(len(env.memory.get()), 2)

    def test_run_round_publishes_visible_messages_to_context_callback(self):
        import asyncio

        class DummyContext:
            def __init__(self):
                self.messages = []

            def callback(self, name, *args, **kwargs):
                if name == "publish_message":
                    self.messages.append(args[0])

        env = Environment()
        context = DummyContext()
        role = DummyRole("role1")
        env.add_role(role)
        env.publish_message(
            Message(content="hello", sent_from="user", cause_by="start", send_to={"role1"})
        )

        active = asyncio.run(env.run_round(context=context))

        self.assertTrue(active)
        self.assertEqual([m.cause_by for m in context.messages], ["start", "ack"])


if __name__ == "__main__":
    unittest.main()
