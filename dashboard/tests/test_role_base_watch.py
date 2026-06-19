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


def test_role_is_idle_when_no_pending_work():
    env = Environment()
    role = WatcherRole()
    env.add_role(role)
    assert role.is_idle() is True
    assert role.should_run(env) is False


def test_role_should_run_when_inbox_has_trigger():
    env = Environment()
    role = WatcherRole()
    env.add_role(role)
    env.publish_message(Message(
        content="go",
        sent_from="user",
        cause_by="trigger",
        send_to={"watcher"},
    ))
    assert role.is_idle() is True  # has not observed yet
    assert role.should_run(env) is True
    asyncio.run(env.run_round())
    assert role.should_run(env) is False
    assert role.is_idle() is True


def test_role_is_idle_false_when_todo_set():
    role = WatcherRole()
    assert role.is_idle() is True
    role.todo = AckAction("ack", "Ack")
    assert role.is_idle() is False


def test_role_is_idle_false_with_unprocessed_trigger():
    role = WatcherRole()
    trigger = Message(content="go", sent_from="user", cause_by="trigger", send_to={"watcher"})
    role.memory.add(trigger)
    assert role.is_idle() is False
    role._mark_trigger_processed(trigger)
    assert role.is_idle() is True
