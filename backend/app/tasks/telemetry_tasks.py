"""Celery task for the anonymous deployment heartbeat.

Scheduled once a day via Celery Beat (see app/celery_app.py), but the beat
entry is only registered when telemetry_enabled is True, so an opt-out
deployment never even schedules the task. The task also re-checks the flag at
run time as a belt-and-suspenders guard.
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.config import Settings
from app.tasks import TRANSIENT_EXCEPTIONS, get_sync_db

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.telemetry.send_heartbeat",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=300,
)
def send_heartbeat(self) -> dict:
    """Send one anonymous deployment heartbeat (opt-in; no-op when disabled).

    The task is always scheduled; send_heartbeat resolves the effective decision
    from SystemConfig (DB) + env each run, so toggling the in-app opt-in takes
    effect on the next daily run without a worker restart.
    """
    from app.services.telemetry_service import send_heartbeat as _send

    return _send(get_sync_db(), Settings())
