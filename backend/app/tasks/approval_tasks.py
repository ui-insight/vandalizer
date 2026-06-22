"""Approval lifecycle Celery tasks (timeout sweeper)."""

import logging

from app.celery_app import celery
from app.tasks import TRANSIENT_EXCEPTIONS, run_task_async

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context, releasing the
    loop's pooled LLM HTTP client on teardown (see ``run_task_async``)."""
    return run_task_async(coro)


@celery.task(
    bind=True,
    name="tasks.approvals.expire_overdue",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
)
def expire_overdue_approvals_task(self):
    """Find overdue pending approvals and apply their configured timeout_action.

    Scheduled via Celery beat (see celery_app.py beat_schedule).
    """
    async def _run():
        from app.config import Settings
        from app.database import init_db
        from app.services.approval_service import expire_overdue_approvals

        await init_db(Settings())
        return await expire_overdue_approvals()

    return _run_async(_run())
