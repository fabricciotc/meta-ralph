import asyncio

from core.environment import Environment
from core.roles.monitor_role import MonitorRole


def test_monitor_detects_stall():
    env = Environment()
    role = MonitorRole(max_idle_rounds=2)
    env.add_role(role)
    # First round: history length 0, no stall
    assert asyncio.run(role.run(env)) is None
    # Second round: still no new messages -> stall
    result = asyncio.run(role.run(env))
    assert result is not None
    assert result.cause_by == "health_check"
    assert result.metadata["status"] == "stalled"
