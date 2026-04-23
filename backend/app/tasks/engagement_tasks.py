"""Celery tasks for user engagement — onboarding drip and inactivity nudges."""

import asyncio
import logging

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_onboarding_drips",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_onboarding_drips(self):
    """Send due onboarding drip emails."""
    from app.services.engagement_service import process_onboarding_drips as _run
    from app.database import init_db

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(init_db())
        count = loop.run_until_complete(_run())
        return {"sent": count}
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_inactivity_nudges",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_inactivity_nudges(self):
    """Send inactivity nudge emails to users who haven't logged in recently."""
    from app.services.engagement_service import process_inactivity_nudges as _run
    from app.database import init_db

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(init_db())
        count = loop.run_until_complete(_run())
        return {"sent": count}
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_v5_launch_announcement",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_v5_launch_announcement(self, batch_size: int = 200):
    """Send the v5.0 launch announcement to eligible existing users.

    Idempotent — each user receives the email at most once. Safe to schedule
    on a cron or trigger manually from the admin UI during rollout.
    """
    from app.services.engagement_service import process_v5_launch_announcement as _run
    from app.database import init_db

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(init_db())
        count = loop.run_until_complete(_run(batch_size=batch_size))
        return {"sent": count}
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_agentic_chat_drip",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_agentic_chat_drip(self):
    """Send due agentic-chat tutorial drip emails (5-step sequence)."""
    from app.services.engagement_service import process_agentic_chat_drip as _run
    from app.database import init_db

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(init_db())
        count = loop.run_until_complete(_run())
        return {"sent": count}
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tasks.engagement.process_powerup_milestones",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def process_powerup_milestones(self):
    """Send the power-user upsell to users who've crossed the workflow threshold."""
    from app.services.engagement_service import process_powerup_milestones as _run
    from app.database import init_db

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(init_db())
        count = loop.run_until_complete(_run())
        return {"sent": count}
    finally:
        loop.close()
