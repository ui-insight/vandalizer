"""Refreshing a knowledge base's web sources — all at once, and on a schedule.

A URL source is a snapshot of a page taken when it was added. The per-source
Refresh (``knowledge_service.refresh_url_source``) re-fetches one in place; a
policy page that is revised needed someone to remember to click it, source by
source (support ticket: government and sponsor policy KBs quietly answering
from last year's text). This module queues that same refresh for every web
source in a KB, and — for a KB with ``url_refresh_interval`` set — for every
web source whose last check is older than the interval.

It adds no refresh logic of its own: a failed fetch still keeps the previous
text, an unchanged page is still not re-embedded, and each attempt is still
recorded on the source's currency fields that the source list shows.
"""

from __future__ import annotations

import datetime
import logging

from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource

logger = logging.getLogger(__name__)

INTERVALS: dict[str, datetime.timedelta] = {
    "daily": datetime.timedelta(days=1),
    "weekly": datetime.timedelta(days=7),
    "monthly": datetime.timedelta(days=30),
}

# A refresh is one page fetch + embed (the task's hard limit is about an hour,
# for a long page indexed in full). A source still "pending" or "processing"
# well past that — counted from when its task was due to start — lost its
# worker; it is refreshable again rather than stuck, which would otherwise
# exempt it from every later scheduled refresh.
STALE_IN_FLIGHT = datetime.timedelta(hours=2)

# Seconds between queued fetches for one KB — a crawl's children usually sit
# on the same site, which should not get them all in the same second.
STAGGER_SECONDS = 5


def _aware(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)


def last_checked(source: KnowledgeBaseSource) -> datetime.datetime | None:
    """When the page was last looked at — a refresh attempt, or first ingest."""
    stamps = [
        _aware(getattr(source, name, None))
        for name in ("last_refresh_attempted_at", "processed_at", "created_at")
    ]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def is_in_flight(source: KnowledgeBaseSource, now: datetime.datetime) -> bool:
    """Queued or running, and not abandoned: its latest stamp (queued,
    attempted, or created) is recent. One left pending or processing past
    ``STALE_IN_FLIGHT`` is refreshable again."""
    if source.status not in ("pending", "processing"):
        return False
    stamps = [
        _aware(getattr(source, name, None))
        for name in ("refresh_queued_at", "last_refresh_attempted_at", "created_at")
    ]
    stamps = [s for s in stamps if s is not None]
    return not stamps or now - max(stamps) < STALE_IN_FLIGHT


def is_refreshable(source: KnowledgeBaseSource, now: datetime.datetime) -> bool:
    return (
        source.source_type == "url"
        and bool(source.url)
        and source.status != "skipped"
        and not is_in_flight(source, now)
    )


def is_due(source: KnowledgeBaseSource, interval: datetime.timedelta, now: datetime.datetime) -> bool:
    checked = last_checked(source)
    return checked is None or now - checked >= interval


async def queue_refresh(kb: KnowledgeBase, sources: list[KnowledgeBaseSource]) -> int:
    """Mark each source pending and dispatch its refresh, staggered. Returns the count."""
    from app.tasks.kb_validation_tasks import refresh_url_source_task

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    for i, source in enumerate(sources):
        countdown = i * STAGGER_SECONDS
        # Stamped with when the task is due to start, so a long stagger is not
        # mistaken for an abandoned refresh; the task carries the stamp and
        # does nothing if a later queueing has replaced it.
        due = now + datetime.timedelta(seconds=countdown)
        source.status = "pending"
        source.refresh_queued_at = due
        await source.save()
        refresh_url_source_task.apply_async(
            args=(kb.uuid, source.uuid, due.isoformat()), countdown=countdown,
        )
    return len(sources)


async def refresh_all(kb: KnowledgeBase) -> dict[str, int]:
    """Queue a refresh of every web source in the KB not already in flight."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    sources = await KnowledgeBaseSource.find(
        {"knowledge_base_uuid": kb.uuid, "source_type": "url"},
    ).to_list()
    refreshable = [s for s in sources if is_refreshable(s, now)]
    # Counted before queuing marks the rest pending.
    in_progress = sum(1 for s in sources if is_in_flight(s, now))
    queued = await queue_refresh(kb, refreshable)
    if queued:
        kb.status = "building"
        await kb.save()
    return {"queued": queued, "in_progress": in_progress}


async def refresh_due_sources(now: datetime.datetime | None = None) -> dict[str, int]:
    """The scheduled pass: every KB with an interval, every web source due."""
    now = now or datetime.datetime.now(tz=datetime.timezone.utc)
    kbs = await KnowledgeBase.find({"url_refresh_interval": {"$in": list(INTERVALS)}}).to_list()
    kbs_touched = 0
    queued = 0
    for kb in kbs:
        try:
            interval = INTERVALS[kb.url_refresh_interval]
            sources = await KnowledgeBaseSource.find(
                {"knowledge_base_uuid": kb.uuid, "source_type": "url"},
            ).to_list()
            due = [s for s in sources if is_refreshable(s, now) and is_due(s, interval, now)]
            if due:
                queued += await queue_refresh(kb, due)
                kbs_touched += 1
        except Exception:
            # One KB's bad row must not stop every other KB's refresh.
            logger.exception("Scheduled web-source refresh failed for KB %s", kb.uuid)
    return {"knowledge_bases": kbs_touched, "queued": queued}
