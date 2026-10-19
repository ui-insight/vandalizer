"""Dated version history for KB URL sources.

A URL source's ``content`` is the text it serves now, and a refresh that picks
up a revised page overwrites it. Without history there is no way to show what
the source said when an earlier answer was produced. Every distinct text a
source has served is kept as a ``KnowledgeBaseSourceVersion``. Each version
records when it was captured, when it took effect, when it was superseded,
and the last refresh that found the page still saying it.

Callers write the source first and then call :func:`record_current`, so a
version only ever describes text that was actually indexed. A source that
held text before this history existed has none of it; :func:`ensure_baseline`
keeps that text as version 1 the first time the source's text is about to
change or be re-checked. Neither function raises: losing a history row must
not fail a refresh that otherwise succeeded, so failures are logged.
"""

from __future__ import annotations

import asyncio
import datetime
import difflib
import logging
from typing import Any, Optional

from pydantic import BaseModel

from app.models.knowledge import KnowledgeBaseSource, KnowledgeBaseSourceVersion
from app.utils import kb_source_currency as currency

logger = logging.getLogger(__name__)

ORIGIN_INGEST = "ingest"
ORIGIN_REFRESH = "refresh"
ORIGIN_SUPPLIED_TEXT = "supplied_text"
ORIGIN_BASELINE = "baseline"

# Lines of unified diff returned by compare_versions. Two revisions of a long
# regulation can differ almost everywhere; past this the diff is cut off and
# flagged rather than shipped whole to the browser.
MAX_DIFF_LINES = 4000


def _tracked(source: Any) -> bool:
    return getattr(source, "source_type", None) == "url"


def _text_hash(source: Any) -> str:
    recorded = getattr(source, "content_hash", None)
    if isinstance(recorded, str) and recorded:
        return recorded
    return currency.content_fingerprint(getattr(source, "content", None) or "")


async def _latest(source_uuid: str) -> Optional[KnowledgeBaseSourceVersion]:
    rows = await KnowledgeBaseSourceVersion.find(
        {"source_uuid": source_uuid},
    ).sort("-number").limit(1).to_list()
    return rows[0] if rows else None


def _new_version(
    source: KnowledgeBaseSource, *, number: int, origin: str,
    captured_at: Optional[datetime.datetime], in_effect_from: Optional[datetime.datetime],
) -> KnowledgeBaseSourceVersion:
    content = source.content or ""
    return KnowledgeBaseSourceVersion(
        source_uuid=source.uuid,
        knowledge_base_uuid=source.knowledge_base_uuid,
        number=number,
        url=source.url,
        url_title=source.url_title,
        content=content,
        content_hash=_text_hash(source),
        char_count=len(content),
        truncated=bool(getattr(source, "truncated", False)),
        captured_at=captured_at,
        in_effect_from=in_effect_from,
        origin=origin,
    )


async def ensure_baseline(source: KnowledgeBaseSource) -> None:
    """Keep the text a source already holds as version 1, if it has no history.

    Call this before anything changes the source's text or currency fields:
    the baseline's dates come from them. The baseline's dates are the
    source's own: when its text was retrieved and when it was last indexed.
    For an older row these all fall back to ``processed_at``.
    """
    if not _tracked(source) or not (source.content or "").strip():
        return
    try:
        if await _latest(source.uuid) is not None:
            return
        processed_at = getattr(source, "processed_at", None)
        version = _new_version(
            source, number=1, origin=ORIGIN_BASELINE,
            captured_at=getattr(source, "content_retrieved_at", None) or processed_at,
            in_effect_from=getattr(source, "last_ingested_at", None) or processed_at,
        )
        await version.insert()
    except Exception:
        logger.exception("Could not record the baseline version of KB source %s", source.uuid)


async def record_current(source: KnowledgeBaseSource, *, origin: str) -> None:
    """Record the text the source now serves, after the source was saved.

    Text identical to the current version only moves its
    ``last_confirmed_at``: the page was checked and still said the same
    thing. New text closes the current version and opens the next one.
    """
    if not _tracked(source) or not (source.content or "").strip():
        return
    try:
        now = currency.utcnow()
        latest = await _latest(source.uuid)
        content_hash = _text_hash(source)
        retrieved_at = getattr(source, "last_retrieved_at", None) or now
        if latest is not None and latest.superseded_at is None and latest.content_hash == content_hash:
            latest.last_confirmed_at = retrieved_at
            await latest.save()
            return
        in_effect_from = getattr(source, "last_ingested_at", None) or now
        if latest is not None and latest.superseded_at is None:
            latest.superseded_at = in_effect_from
            await latest.save()
        version = _new_version(
            source,
            number=(latest.number + 1) if latest is not None else 1,
            origin=origin,
            captured_at=getattr(source, "content_retrieved_at", None) or retrieved_at,
            in_effect_from=in_effect_from,
        )
        await version.insert()
    except Exception:
        logger.exception("Could not record a version of KB source %s", source.uuid)


async def list_versions(source_uuid: str) -> list[KnowledgeBaseSourceVersion]:
    """Every version of a source, newest first."""
    return await KnowledgeBaseSourceVersion.find(
        {"source_uuid": source_uuid},
    ).sort("-number").to_list()


class VersionSummary(BaseModel):
    """A version without its text, for listings. A page that changes on
    every refresh accrues a version per pass, each up to the KB text cap, so
    a listing must not pull every version's full text into memory."""

    uuid: str
    number: int
    origin: str = ORIGIN_INGEST
    url: Optional[str] = None
    url_title: Optional[str] = None
    content_hash: str
    char_count: int = 0
    truncated: bool = False
    captured_at: Optional[datetime.datetime] = None
    in_effect_from: Optional[datetime.datetime] = None
    superseded_at: Optional[datetime.datetime] = None
    last_confirmed_at: Optional[datetime.datetime] = None


async def list_version_summaries(source_uuid: str) -> list[VersionSummary]:
    """Every version of a source without its text, newest first."""
    return await KnowledgeBaseSourceVersion.find(
        {"source_uuid": source_uuid},
    ).sort("-number").project(VersionSummary).to_list()


async def get_version(source_uuid: str, version_uuid: str) -> Optional[KnowledgeBaseSourceVersion]:
    return await KnowledgeBaseSourceVersion.find_one(
        {"source_uuid": source_uuid, "uuid": version_uuid},
    )


def as_utc(value: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    # Mongo hands back naive UTC datetimes.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def version_in_effect_at(
    versions: list[KnowledgeBaseSourceVersion], at: datetime.datetime,
) -> Optional[KnowledgeBaseSourceVersion]:
    """The version answers came from at ``at``, or None if the source had
    no recorded text then (before its first version took effect)."""
    at = as_utc(at)
    for version in sorted(versions, key=lambda v: v.number, reverse=True):
        start = as_utc(version.in_effect_from)
        end = as_utc(version.superseded_at)
        if start is not None and start > at:
            continue
        if end is not None and end <= at:
            # Versions are contiguous; one that ended before ``at`` means
            # every older one did too.
            return None
        return version
    return None


def _diff(old: str, new: str, old_label: str, new_label: str) -> dict[str, Any]:
    lines: list[dict[str, str]] = []
    added = removed = 0
    truncated = False
    for raw in difflib.unified_diff(
        old.splitlines(), new.splitlines(), fromfile=old_label, tofile=new_label, lineterm="",
    ):
        if raw.startswith("---") or raw.startswith("+++"):
            continue
        op = raw[:1] if raw[:1] in ("+", "-", "@") else " "
        if op == "+":
            added += 1
        elif op == "-":
            removed += 1
        if len(lines) < MAX_DIFF_LINES:
            lines.append({"op": op, "text": raw[1:] if op in ("+", "-", " ") else raw})
        else:
            truncated = True
    return {"lines": lines, "added": added, "removed": removed, "truncated": truncated}


async def compare_versions(
    base: KnowledgeBaseSourceVersion, target: KnowledgeBaseSourceVersion,
) -> dict[str, Any]:
    """A line diff from ``base`` to ``target``. difflib on two long pages is
    CPU-bound, so it runs off the event loop."""
    return await asyncio.to_thread(
        _diff, base.content, target.content, f"v{base.number}", f"v{target.number}",
    )


async def delete_for_sources(source_uuids: list[str]) -> None:
    """Drop the history of removed sources. Called after the source rows are
    gone, so a failure here only leaves unreachable rows; it is logged, not
    raised into the delete the user asked for."""
    if not source_uuids:
        return
    try:
        await KnowledgeBaseSourceVersion.find(
            {"source_uuid": {"$in": source_uuids}},
        ).delete()
    except Exception:
        logger.exception("Could not delete the version history of KB sources %s", source_uuids)


async def delete_for_kb(kb_uuid: str) -> None:
    try:
        await KnowledgeBaseSourceVersion.find(
            {"knowledge_base_uuid": kb_uuid},
        ).delete()
    except Exception:
        logger.exception("Could not delete the version history of KB %s", kb_uuid)
