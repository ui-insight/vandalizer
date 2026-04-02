"""Celery periodic tasks for the demo waitlist system."""

import asyncio
import logging

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS
from app.config import Settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _init_and_process_waitlist():
    from app.database import init_db
    from app.services import demo_service

    settings = Settings()
    await init_db(settings)
    return await demo_service.process_waitlist(settings)


async def _init_and_check_expirations():
    from app.database import init_db
    from app.services import demo_service

    settings = Settings()
    await init_db(settings)
    return await demo_service.check_expirations(settings)


async def _init_and_send_warnings():
    from app.database import init_db
    from app.services import demo_service

    settings = Settings()
    await init_db(settings)
    return await demo_service.send_expiry_warnings(settings)


async def _init_and_process_recapture():
    from app.database import init_db
    from app.services import demo_service

    settings = Settings()
    await init_db(settings)
    return await demo_service.process_recapture_drips(settings)


async def _init_and_enqueue_recapture_all():
    from app.database import init_db
    from app.services import demo_service

    settings = Settings()
    await init_db(settings)
    return await demo_service.enqueue_recapture_all(settings)


@celery_app.task(
    bind=True,
    name="tasks.demo.process_waitlist",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_demo_waitlist(self):
    """Process the demo waitlist — activate eligible pending applications."""
    count = _run_async(_init_and_process_waitlist())
    return {"activated": count}


@celery_app.task(
    bind=True,
    name="tasks.demo.check_expirations",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=30,
)
def check_demo_expirations(self):
    """Check for expired demo accounts and lock them."""
    count = _run_async(_init_and_check_expirations())
    return {"expired": count}


@celery_app.task(
    bind=True,
    name="tasks.demo.send_expiry_warnings",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=30,
)
def send_demo_expiry_warnings(self):
    """Send warning emails to demos expiring within 2 days."""
    count = _run_async(_init_and_send_warnings())
    return {"warnings_sent": count}


@celery_app.task(
    bind=True,
    name="tasks.demo.process_recapture",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_demo_recapture(self):
    """Send recapture drip emails to activated users who haven't logged in."""
    count = _run_async(_init_and_process_recapture())
    return {"recapture_sent": count}


@celery_app.task(
    bind=True,
    name="tasks.demo.enqueue_recapture_all",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=30,
)
def enqueue_recapture_all(self):
    """Admin-triggered: enqueue recapture drips for all eligible active demo users."""
    count = _run_async(_init_and_enqueue_recapture_all())
    return {"enqueued": count}
