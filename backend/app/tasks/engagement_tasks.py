"""Celery tasks for user engagement — onboarding drip, inactivity nudges, morning briefings."""

import asyncio
import logging

from app.celery_app import celery_app
from app.config import Settings
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _init_and_run_onboarding_drips():
    from app.database import init_db
    from app.services.engagement_service import process_onboarding_drips as _run

    settings = Settings()
    await init_db(settings)
    return await _run(settings)


async def _init_and_run_inactivity_nudges():
    from app.database import init_db
    from app.services.engagement_service import process_inactivity_nudges as _run

    settings = Settings()
    await init_db(settings)
    return await _run(settings)


async def _init_and_run_morning_briefings():
    from app.database import init_db
    from app.services.briefing_service import send_morning_briefings as _run

    settings = Settings()
    await init_db(settings)
    return await _run(settings)


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_onboarding_drips",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_onboarding_drips(self):
    """Send due onboarding drip emails."""
    count = _run_async(_init_and_run_onboarding_drips())
    return {"sent": count}


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_inactivity_nudges",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_inactivity_nudges(self):
    """Send inactivity nudge emails to users who haven't logged in recently."""
    count = _run_async(_init_and_run_inactivity_nudges())
    return {"sent": count}


@celery_app.task(
    bind=True,
    name="tasks.engagement.send_morning_briefings",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def send_morning_briefings(self):
    """Compute + email the daily Morning Briefing to eligible users."""
    count = _run_async(_init_and_run_morning_briefings())
    return {"sent": count}
