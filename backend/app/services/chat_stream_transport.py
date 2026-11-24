"""Keep long chat preparation and tool calls alive without inventing progress."""
import asyncio
from contextlib import aclosing
from collections.abc import AsyncGenerator
from typing import Literal

import anyio


async def with_heartbeats(source: AsyncGenerator[str, None], interval: float = 15.0) -> AsyncGenerator[str, None]:
    """Send a transport heartbeat during silence; preserve order and backpressure.

    A single producer owns the generator for its entire lifetime. Iterating each
    next() in a new task would break contextvars and cancel scopes spanning yields.
    Disconnecting closes that producer, including the source's cleanup handlers.
    """
    queue: asyncio.Queue[tuple[Literal["chunk"], str] | tuple[Literal["error"], Exception] | tuple[Literal["done"], None]] = asyncio.Queue(maxsize=1)

    async def produce() -> None:
        try:
            async with aclosing(source):
                async for chunk in source:
                    await queue.put(("chunk", chunk))
        except Exception as exc:
            await queue.put(("error", exc))
        else:
            await queue.put(("done", None))

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                if producer.done():
                    # A source canceled independently must not leave an endless heartbeat.
                    await producer
                    return
                yield '{"kind":"heartbeat","content":""}\n'
                continue
            if event[0] == "done":
                break
            if event[0] == "error":
                raise event[1]
            yield event[1]
    finally:
        producer.cancel()
        # Starlette cancels the response scope on disconnect. Shield cleanup so
        # the source can persist interruption state and reconcile its activity.
        with anyio.CancelScope(shield=True):
            await asyncio.gather(producer, return_exceptions=True)
