"""Shared Celery task utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pymongo.database import Database

# Transient exceptions that are safe to retry with backoff.
# Permanent errors (ValueError, KeyError, TypeError, etc.) should NOT be retried.
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

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
