import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.actions.base import Action
from core.environment import Environment
from core.models import Message
from core.roles.base import Role


class AckAction(Action):
    async def run(self, context, **kwargs):
        return Message(
            content="ack",
            sent_from="",
            cause_by="ack",
            send_to={"all"},
        )


class WatcherRole(Role):
    _watch = ["trigger"]

    def __init__(self):
        super().__init__("watcher", "Watcher")
        self.set_actions([AckAction("ack", "Ack")])


class MultiActionRole(Role):
    _watch = ["trigger"]
    react_mode = "by_order"

    def __init__(self):
        super().__init__("multi", "Multi")
        self.set_actions([
            AckAction("first", "First"),
            AckAction("second", "Second"),
        ])


def test_base_role_uses_watch_and_actions():
    env = Environment()
    role = WatcherRole()
    env.add_role(role)
    env.publish_message(Message(
        content="go",
        sent_from="user",
        cause_by="trigger",
        send_to={"watcher"},
    ))
    active = asyncio.run(env.run_round())
    assert active is True
    history = env.memory.get()
    assert any(m.cause_by == "ack" for m in history)


def test_base_role_ignores_unwatched_messages():
    env = Environment()
    role = WatcherRole()
    env.add_role(role)
    env.publish_message(Message(
        content="go",
        sent_from="user",
        cause_by="other_event",
        send_to={"watcher"},
    ))
    asyncio.run(env.run_round())
    assert not any(m.sent_from == "watcher" for m in env.memory.get())


def test_base_role_by_order_selects_first_action():
    env = Environment()
    role = MultiActionRole()
    env.add_role(role)
    env.publish_message(Message(
        content="go",
        sent_from="user",
        cause_by="trigger",
        send_to={"multi"},
    ))
    asyncio.run(env.run_round())
    assert any(m.cause_by == "ack" for m in env.memory.get())
