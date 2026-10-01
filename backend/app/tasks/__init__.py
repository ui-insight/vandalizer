"""Shared Celery task utilities."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from pymongo.database import Database

logger = logging.getLogger(__name__)

# Transient exceptions that are safe to retry with backoff.
# Permanent errors (ValueError, KeyError, TypeError, etc.) should NOT be retried.
#
# The builtins alone are not enough: the failures that actually occur in
# production raise library exception types that do NOT inherit from them —
# httpx timeouts/transport errors (httpx.HTTPError → Exception), pymongo
# AutoReconnect (PyMongoError → Exception), redis connection errors
# (RedisError → Exception) — so ``autoretry_for=TRANSIENT_EXCEPTIONS``
# silently never fired for the most common blips. Each library is added
# under an import guard so a missing optional dependency can't break task
# module import.
#
# LLM-call errors are deliberately NOT here: pydantic-ai's ``ModelAPIError``
# is transient but its subclass ``ModelHTTPError`` (an HTTP *status* error —
# a 4xx won't improve on retry) is not, and an ``except autoretry_for``
# clause cannot express that exclusion. Tasks that make LLM calls handle it
# per-task with the catch/re-raise pattern in
# ``kb_validation_tasks.generate_test_queries_task``.
def _transient_exceptions() -> tuple[type[BaseException], ...]:
    excs: list[type[BaseException]] = [ConnectionError, TimeoutError, OSError]
    try:
        import httpx

        # TransportError covers ConnectError, ReadTimeout, WriteError, etc.
        # HTTPStatusError is intentionally excluded (4xx/5xx responses).
        excs.append(httpx.TransportError)
    except ImportError:  # pragma: no cover
        pass
    try:
        from pymongo.errors import AutoReconnect

        excs.append(AutoReconnect)
    except ImportError:  # pragma: no cover
        pass
    try:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        excs.extend([RedisConnectionError, RedisTimeoutError])
    except ImportError:  # pragma: no cover
        pass
    return tuple(excs)


TRANSIENT_EXCEPTIONS = _transient_exceptions()


def _cancel_leftover_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel and await every task the finished coroutine left running.

    Logged, because a leftover is work the task started and never waited
    for — the names say where to look.
    """
    try:
        leftover = [t for t in asyncio.all_tasks(loop) if not t.done()]
        if not leftover:
            return
        names: dict[str, int] = {}
        for t in leftover:
            coro_obj = t.get_coro()
            name = getattr(coro_obj, "__qualname__", None) or repr(coro_obj)
            names[name] = names.get(name, 0) + 1
        logger.warning(
            "Task finished with %d task(s) still running; cancelling: %s",
            len(leftover),
            ", ".join(f"{n} x{c}" if c > 1 else n for n, c in sorted(names.items())),
        )
        for t in leftover:
            t.cancel()
        loop.run_until_complete(asyncio.gather(*leftover, return_exceptions=True))
    except Exception as e:  # never mask the task's own result/error
        logger.warning("Failed to cancel leftover tasks after task: %s", e)


def run_task_async(coro: "Coroutine[Any, Any, Any]") -> Any:
    """Run an async coroutine to completion in a fresh event loop for a Celery
    task, then release the loop's pooled LLM HTTP client before tearing the
    loop down.

    Celery tasks run sync, so each builds its own event loop. ``loop.close()``
    does not close the per-loop ``httpx.AsyncClient`` that ``llm_service``
    caches, so without this every LLM-touching task would leak a client and its
    sockets — the recurring ``[Errno 24] Too many open files`` exhaustion that
    eventually makes outbound model calls fail with "Connection error." The
    cleanup is a no-op when the task made no LLM call (no client was created).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # What asyncio.run does and this hand-built runner skipped: anything
        # still running when the task's coroutine returns would be destroyed
        # mid-flight by loop.close(). An agent run left behind (e.g. a sibling
        # of a failed ``asyncio.gather``, which does not cancel the others)
        # surfaced as "Task was destroyed but it is pending! …
        # CombinedCapability.wrap_run()" (Sentry 7613426710). Cancel and drain
        # them first — they may still be using the HTTP client closed below —
        # then let async generators (pydantic-ai's agent.iter) finalize.
        _cancel_leftover_tasks(loop)
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:  # never mask the task's own result/error
            logger.warning("Failed to shut down async generators after task: %s", e)
        try:
            from app.services.llm_service import aclose_loop_http_client
            loop.run_until_complete(aclose_loop_http_client())
        except Exception as e:  # never mask the task's own result/error
            logger.warning("Failed to close loop HTTP client after task: %s", e)
        loop.close()
        # Unset the now-closed loop as the thread's current loop. Otherwise a
        # later sync task in the same worker that calls pydantic-ai's
        # ``run_sync`` (e.g. tasks.activity.generate_description) would inherit
        # this closed loop via ``asyncio.get_event_loop()`` and crash with
        # "Event loop is closed". With it cleared, ``get_event_loop`` raises and
        # the caller creates a fresh loop instead.
        asyncio.set_event_loop(None)

# ---------------------------------------------------------------------------
# Shared sync MongoDB client (reused across Celery worker processes)
# ---------------------------------------------------------------------------

_mongo_client: Any = None
_mongo_db_name: str | None = None


def get_sync_db() -> Database[dict]:
    """Return a pymongo database handle, reusing a single MongoClient per process."""
    global _mongo_client, _mongo_db_name
    if _mongo_client is None:
        from pymongo import MongoClient

        from app.config import Settings
        settings = Settings()
        _mongo_client = MongoClient(settings.mongo_host)
        _mongo_db_name = settings.mongo_db
    db: Database[dict] = _mongo_client[_mongo_db_name]
    return db
