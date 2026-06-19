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

    def test_inboxes_are_routed_by_recipient(self):
        env = Environment()
        env.add_role(DummyRole("role1"))
        env.add_role(DummyRole("role2"))
        env.publish_message(
            Message(content="hi", sent_from="user", cause_by="start", send_to={"role1"})
        )
        self.assertEqual(len(env.get_messages_for("role1")), 1)
        self.assertEqual(len(env.get_messages_for("role2")), 0)

    def test_broadcast_populates_all_inboxes(self):
        env = Environment()
        env.add_role(DummyRole("role1"))
        env.add_role(DummyRole("role2"))
        env.publish_message(
            Message(content="hi", sent_from="user", cause_by="start", send_to={"all"})
        )
        self.assertEqual(len(env.get_messages_for("role1")), 1)
        self.assertEqual(len(env.get_messages_for("role2")), 1)

    def test_run_round_skips_idle_roles(self):
        import asyncio

        class CountingRole:
            def __init__(self, role_id):
                self.role_id = role_id
                self.addresses = {role_id}
                self.runs = 0

            async def run(self, env, **kwargs):
                self.runs += 1
                return True

        env = Environment()
        active_role = CountingRole("active")
        idle_role = CountingRole("idle")
        env.add_role(active_role)
        env.add_role(idle_role)
        env.publish_message(
            Message(content="go", sent_from="user", cause_by="start", send_to={"active"})
        )
        asyncio.run(env.run_round())
        self.assertEqual(active_role.runs, 1)
        self.assertEqual(idle_role.runs, 0)

    def test_run_round_clears_inbox_after_run(self):
        import asyncio

        env = Environment()
        env.add_role(DummyRole("role1"))
        env.publish_message(
            Message(content="go", sent_from="user", cause_by="start", send_to={"role1"})
        )
        self.assertEqual(len(env.get_messages_for("role1")), 1)
        asyncio.run(env.run_round())
        self.assertEqual(len(env.get_messages_for("role1")), 0)

    def test_is_idle_false_when_inbox_has_messages(self):
        env = Environment()
        env.add_role(DummyRole("role1"))
        self.assertTrue(env.is_idle())
        env.publish_message(
            Message(content="go", sent_from="user", cause_by="start", send_to={"role1"})
        )
        self.assertFalse(env.is_idle())


if __name__ == "__main__":
    unittest.main()
