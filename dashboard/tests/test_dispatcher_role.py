import asyncio

from core.environment import Environment
from core.models import Message
from core.roles.dispatcher_role import DispatcherRole


def test_dispatcher_reacts_to_ticket_ready():
    env = Environment()
    role = DispatcherRole(ticket_id="T-1", ticket_title="Test", ticket_description="Desc")
    env.add_role(role)
    env.publish_message(Message(
        content="go",
        sent_from="orchestrator",
        cause_by="ticket_ready",
        send_to={"dispatcher"},
        metadata={},
    ))
    result = asyncio.run(role.run(env))
    assert result is not None
    assert result.cause_by == "prd_ready"


def test_dispatcher_reacts_to_architecture_ready():
    env = Environment()
    role = DispatcherRole(ticket_id="T-1", ticket_title="Test", ticket_description="Desc")
    env.add_role(role)
    env.publish_message(Message(
        content="architecture done",
        sent_from="architect",
        cause_by="architecture_ready",
        send_to={"dispatcher"},
        metadata={"path": "/tmp/arch.md"},
    ))
    result = asyncio.run(role.run(env))
    assert result is not None
    assert result.cause_by == "plan_ready_trigger"
