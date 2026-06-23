"""Shared observability bootstrap (Sentry).

Both the FastAPI web app (`app.main`) and the Celery workers
(`celery_worker.py`) import and call `init_sentry()` so that errors are
captured in *every* process, not just the web tier. Celery workers boot via
`celery -A celery_worker.celery_app worker` and never import `app.main`, so
they need their own init call here — otherwise task crashes go unobserved.
"""

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def init_sentry(settings: Settings, *, with_celery: bool = False) -> None:
    """Initialize Sentry for the current process.

    No-ops when ``sentry_dsn`` is unset (e.g. local dev). Pass
    ``with_celery=True`` from the worker entrypoint to enable the Celery
    integration, which auto-captures unhandled task exceptions, soft
    time-limit kills, and retry context.
    """
    if not settings.sentry_dsn:
        return

    import sentry_sdk

    integrations = []
    if with_celery:
        from sentry_sdk.integrations.celery import CeleryIntegration

        # monitor_beat_tasks wires scheduled beat tasks into Sentry Crons so a
        # task that silently *stops* running (not just one that throws) alerts.
        integrations.append(CeleryIntegration(monitor_beat_tasks=True))

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        send_default_pii=False,
        integrations=integrations,
    )
    logger.info(
        "Sentry initialized (environment=%s, celery=%s)",
        settings.environment,
        with_celery,
    )
