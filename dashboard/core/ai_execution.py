from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional


async def invoke_ai(run_ai: Optional[Any], *args, **kwargs) -> Optional[str]:
    """Run an AI callback without blocking the event loop.

    Backends in this project can be either async callables or synchronous CLI/API
    wrappers. Synchronous wrappers are moved to a worker thread so multiple roles
    can make progress concurrently inside ``Environment.run_round``.
    """
    if run_ai is None:
        return None
    if inspect.iscoroutinefunction(run_ai):
        return await run_ai(*args, **kwargs)

    result = await asyncio.to_thread(run_ai, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
