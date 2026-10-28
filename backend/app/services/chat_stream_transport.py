"""Keep long chat preparation and tool calls alive without inventing progress."""
import asyncio
from contextlib import aclosing
from collections.abc import AsyncIterator

import anyio


async def with_heartbeats(source: AsyncIterator[str], interval: float = 15.0) -> AsyncIterator[str]:
    """Send a transport heartbeat during silence; preserve order and backpressure.

    A single producer owns the generator for its entire lifetime. Iterating each
    next() in a new task would break contextvars and cancel scopes spanning yields.
    Disconnecting closes that producer, including the source's cleanup handlers.
    """
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue(maxsize=1)

    async def produce():
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
                kind, value = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                if producer.done():
                    # A source canceled independently must not leave an endless heartbeat.
                    await producer
                    return
                yield '{"kind":"heartbeat","content":""}\n'
                continue
            if kind == "done":
                break
            if kind == "error":
                raise value
            yield value
    finally:
        producer.cancel()
        # Starlette cancels the response scope on disconnect. Shield cleanup so
        # the source can persist interruption state and reconcile its activity.
        with anyio.CancelScope(shield=True):
            await asyncio.gather(producer, return_exceptions=True)
