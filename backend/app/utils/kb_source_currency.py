"""Per-source refresh / ingestion provenance for knowledge bases.

An evaluator checking that a KB's sources are current needs, for each source:
when the app last *tried* to refresh it, when it last *got* the page or
document text, when that text was last *written into the index*, which text
is actually retained right now, a fingerprint of that text, and a one-word
status. ``KnowledgeBaseSource.processed_at`` used to carry all of that as a
single overloaded timestamp; these helpers write the distinct fields at every
ingest/refresh site and read them back with fallbacks for rows written before
the fields existed.

Kept free of model imports so the sync Celery tasks (pymongo dicts) and the
async service (Beanie documents) share one definition.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Optional

HASH_ALGORITHM = "sha256"

# ``last_refresh_outcome`` values written by refresh_url_source.
OUTCOME_REFRESHED = "refreshed"          # new text fetched and indexed
OUTCOME_UNCHANGED = "unchanged"          # fetched text identical to what is indexed; index left alone
OUTCOME_RETRIEVAL_FAILED = "retrieval_failed"   # fetch failed or page rejected; previous text kept
OUTCOME_INGESTION_FAILED = "ingestion_failed"   # fetched fine, index write failed

# ``currency.status`` values derived for the API / export.
STATUS_NEVER_INGESTED = "never_ingested"
STATUS_INGESTED = "ingested"             # indexed once, never refreshed since
STATUS_REFRESHED = "refreshed"
STATUS_UNCHANGED = "unchanged"
STATUS_RETAINED_PREVIOUS = "retained_previous"  # last refresh failed; a previous good version is still served
STATUS_RETRIEVAL_FAILED = "retrieval_failed"     # last refresh failed and there is no good version to serve
STATUS_INGESTION_FAILED = "ingestion_failed"


def content_fingerprint(text: str) -> str:
    """sha256 of the text handed to the indexer — the version identifier of
    what a source currently retrieves from. Same input, same hash, across
    exports and deployments."""
    return hashlib.sha256((text or "").encode("utf-8", "surrogatepass")).hexdigest()


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def ingestion_stamp(
    text: str,
    *,
    now: datetime.datetime | None = None,
    retrieved: bool = True,
    retrieved_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Fields to write on a source after its chunks were (re)written.

    ``retrieved=True`` (a fetch, a document read, imported/bundled text) also
    stamps the retrieval dates: the indexed text is what was just obtained.
    ``retrieved=False`` (``/reingest``, which re-embeds the stored snapshot)
    leaves them alone — the text is no newer than it was; pass
    ``retrieved_at`` to backfill a row that never recorded one.
    """
    now = now or utcnow()
    out: dict[str, Any] = {
        "content_hash": content_fingerprint(text),
        "last_ingested_at": now,
        # Kept for every reader that predates the split.
        "processed_at": now,
    }
    if retrieved:
        out["last_retrieved_at"] = now
        out["content_retrieved_at"] = now
    elif retrieved_at is not None:
        out["content_retrieved_at"] = retrieved_at
    return out


def stamp_ingested(source: Any, text: str, **kwargs: Any) -> None:
    """Apply :func:`ingestion_stamp` to a Beanie document / attribute object."""
    for key, value in ingestion_stamp(text, **kwargs).items():
        setattr(source, key, value)


def _get(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _text(source: Any, key: str) -> Optional[str]:
    """A string field, or None — a stand-in object (a test double, a row
    with a corrupt value) must not turn into a 500 on the source list."""
    value = _get(source, key)
    return value if isinstance(value, str) and value else None


def _dt(source: Any, key: str) -> Optional[datetime.datetime]:
    value = _get(source, key)
    return value if isinstance(value, datetime.datetime) else None


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime.datetime) else None


def derive_source_currency(source: Any) -> dict[str, Any]:
    """The per-source currency block for the API and the export.

    Works on a ``KnowledgeBaseSource`` or a raw pymongo dict. Rows written
    before the explicit fields existed fall back to ``processed_at`` for the
    ingestion and retrieval dates, and to a hash of the retained snapshot
    when one is stored in full — ``content_hash_recorded`` says which.
    """
    processed_at = _dt(source, "processed_at")
    ingested_at = _dt(source, "last_ingested_at") or processed_at
    retrieved_at = _dt(source, "last_retrieved_at") or processed_at
    content_retrieved_at = _dt(source, "content_retrieved_at") or processed_at
    attempted_at = _dt(source, "last_refresh_attempted_at")
    outcome = _text(source, "last_refresh_outcome")
    status = _text(source, "status") or "pending"

    content_hash = _text(source, "content_hash")
    recorded = bool(content_hash)
    if not content_hash:
        content = _text(source, "content")
        # A truncated snapshot is not the indexed text, so its hash would
        # identify the wrong thing; leave it blank until the next ingest.
        if content and _get(source, "truncated", False) is not True:
            content_hash = content_fingerprint(content)

    if outcome == OUTCOME_REFRESHED:
        currency = STATUS_REFRESHED
    elif outcome == OUTCOME_UNCHANGED:
        currency = STATUS_UNCHANGED
    elif outcome == OUTCOME_RETRIEVAL_FAILED:
        currency = (
            STATUS_RETAINED_PREVIOUS if status == "ready" and ingested_at
            else STATUS_RETRIEVAL_FAILED
        )
    elif outcome == OUTCOME_INGESTION_FAILED:
        currency = STATUS_INGESTION_FAILED
    else:
        currency = STATUS_INGESTED if ingested_at else STATUS_NEVER_INGESTED

    return {
        "status": currency,
        "last_refresh_attempted_at": _iso(attempted_at),
        "last_retrieved_at": _iso(retrieved_at),
        "last_ingested_at": _iso(ingested_at),
        "content_retrieved_at": _iso(content_retrieved_at),
        "content_hash": content_hash,
        "content_hash_algorithm": HASH_ALGORITHM,
        "content_hash_recorded": recorded,
        "last_refresh_outcome": outcome,
        "last_refresh_error": _text(source, "last_refresh_error"),
    }


def export_provenance(source: Any) -> dict[str, Any]:
    """The read-only per-source block added to a KB export: the currency
    fields plus the status/size facts an evaluator reads beside them. Every
    value is coerced to a JSON-safe type; the importer ignores all of it."""
    chunk_count = _get(source, "chunk_count")
    return {
        "source_reference": _text(source, "source_reference"),
        "status": _text(source, "status") or "pending",
        "chunk_count": chunk_count if isinstance(chunk_count, int) else 0,
        "truncated": _get(source, "truncated", False) is True,
        "created_at": _iso(_dt(source, "created_at")),
        "currency": derive_source_currency(source),
    }
