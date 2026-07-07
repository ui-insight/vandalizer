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
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


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
