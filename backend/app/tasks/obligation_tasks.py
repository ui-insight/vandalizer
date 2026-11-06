"""Celery tasks for RA inbox deadline reminders (see app.services.deadline_reminders)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

if TYPE_CHECKING:
    from celery import Task

logger = logging.getLogger(__name__)


def _run(coro_factory):  # type: ignore[no-untyped-def]
    from app.config import Settings
    from app.database import init_db

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(init_db(Settings(), skip_indexes=True))
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tasks.obligations.send_deadline_reminders",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def send_deadline_reminders(self: Task) -> dict[str, int]:
    """Bell and email reminders that are due now. Hourly; idempotent."""
    from app.services.deadline_reminders import send_due_reminders

    result: dict[str, int] = _run(send_due_reminders)
    return result


@celery_app.task(
    bind=True,
    name="tasks.obligations.send_weekly_deadline_summaries",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def send_weekly_deadline_summaries(self: Task) -> dict[str, int]:
    """Monday email of overdue / this week / next 30 days, for opted-in users."""
    from app.services.deadline_reminders import send_weekly_summaries

    sent: int = _run(send_weekly_summaries)
    return {"sent": sent}


@celery_app.task(
    bind=True,
    name="tasks.obligations.remind_expiring_page_links",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def remind_expiring_page_links(self: Task) -> dict[str, int]:
    """Bell Page owners whose public links expire within three days. Idempotent."""
    from app.services.public_page_access import remind_expiring
    from app.tasks import get_sync_db

    return {"sent": remind_expiring(get_sync_db())}
