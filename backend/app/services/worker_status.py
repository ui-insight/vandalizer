"""Which Celery queues have a live worker consuming them.

Nothing else in the API can tell. Mongo, Redis and Chroma can all be healthy
while the worker container has been down for a day: every task is queued in
Redis and nothing runs it, so uploads sit at "extracting", workflows at
"Preparing" and URL previews never start (the 2026-10-20 dev outage).
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time

logger = logging.getLogger(__name__)

#: Seconds a worker has to answer the broadcast.
REPLY_TIMEOUT = 1.0
#: Upper bound on the whole check, connect included, so a slow broker can
#: never hold up a health probe or a poll.
CHECK_TIMEOUT = 3.0
#: Polling clients ask every couple of seconds; one broadcast serves them all.
CACHE_SECONDS = 15.0

_cache: tuple[float, frozenset[str] | None] | None = None


def expected_queues() -> frozenset[str]:
    """Every queue a task can be routed to."""
    from app.celery_app import celery_app

    routes = celery_app.conf.task_routes or {}
    queues = {route["queue"] for route in routes.values() if "queue" in route}
    queues.add(celery_app.conf.task_default_queue)
    return frozenset(queues)


def queue_for(task_name: str) -> str:
    """The queue ``task_name`` is routed to."""
    from app.celery_app import celery_app

    for pattern, route in (celery_app.conf.task_routes or {}).items():
        if fnmatch.fnmatchcase(task_name, pattern) and "queue" in route:
            queue: str = route["queue"]
            return queue
    default_queue: str = celery_app.conf.task_default_queue
    return default_queue


def _inspect_queues() -> frozenset[str]:
    from app.celery_app import celery_app

    # One connect attempt: the app's default is to retry a down broker for a
    # long time, which would block this thread far past CHECK_TIMEOUT.
    with celery_app.connection_for_write() as conn:
        conn.ensure_connection(max_retries=1)
        replies = celery_app.control.inspect(
            timeout=REPLY_TIMEOUT, connection=conn,
        ).active_queues() or {}
    return frozenset(
        q["name"] for queues in replies.values() for q in (queues or []) if q.get("name")
    )


async def consuming_queues() -> frozenset[str] | None:
    """Queues some live worker consumes; empty when no worker answered.

    None when the broker couldn't be asked, which says nothing about the
    workers. Cached for CACHE_SECONDS.
    """
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        result: frozenset[str] | None = await asyncio.wait_for(
            asyncio.to_thread(_inspect_queues), CHECK_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 — an unanswerable question, not an error
        logger.info("Could not ask the broker which queues have workers: %s", e)
        result = None
    _cache = (now, result)
    return result


async def queue_has_worker(queue: str) -> bool | None:
    """Whether a live worker consumes ``queue``; None when unknown."""
    queues = await consuming_queues()
    return None if queues is None else queue in queues


async def worker_summary() -> dict:
    """The health endpoint's view: ok, down (some queue unserved) or unknown."""
    queues = await consuming_queues()
    expected = expected_queues()
    if queues is None:
        return {"status": "unknown", "queues": [], "missing_queues": []}
    missing = sorted(expected - queues)
    return {
        "status": "down" if missing else "ok",
        "queues": sorted(queues),
        "missing_queues": missing,
    }
