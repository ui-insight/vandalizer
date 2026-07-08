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
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    # Register the web integrations explicitly rather than leaning on Sentry's
    # auto-enabling machinery. Auto-enable only fires when starlette/fastapi are
    # importable at init() time and silently captures *nothing* if that ordering
    # ever shifts — which is exactly how an unhandled 500 (e.g. /mgmt/v1/stats)
    # can fail to surface in Sentry. Listing them keeps capture deterministic.
    integrations = [StarletteIntegration(), FastApiIntegration()]
    if with_celery:
        from sentry_sdk.integrations.celery import CeleryIntegration

        # monitor_beat_tasks wires scheduled beat tasks into Sentry Crons so a
        # task that silently *stops* running (not just one that throws) alerts.
        integrations.append(CeleryIntegration(monitor_beat_tasks=True))

    # Turn off Sentry's auto-enabled LLM integrations. Each of these patches the
    # provider/agent call to capture *every* exception that escapes it as an
    # event with mechanism.handled=False — before our own code can catch it. But
    # the app handles LLM failures deliberately (transient blips are retried,
    # real errors are surfaced through their own channels), so these fire on
    # gracefully-handled errors too, mislabeling them "unhandled" and doubling
    # every genuine failure (once here, once at the real Celery/HTTP boundary).
    # Note pydantic_ai's integration deactivates openai/anthropic when active,
    # so all three must be disabled or the capture just moves to whichever is
    # left. We keep our own metering (MeteredModel) and don't use their spans.
    disabled_integrations = []
    for _mod, _cls in (
        ("sentry_sdk.integrations.pydantic_ai", "PydanticAIIntegration"),
        ("sentry_sdk.integrations.openai", "OpenAIIntegration"),
        ("sentry_sdk.integrations.anthropic", "AnthropicIntegration"),
    ):
        try:
            import importlib

            disabled_integrations.append(getattr(importlib.import_module(_mod), _cls))
        except Exception:
            # Integration/module unavailable (provider lib not installed) — it
            # wouldn't auto-enable anyway, so nothing to disable.
            pass

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        send_default_pii=False,
        integrations=integrations,
        disabled_integrations=disabled_integrations,
    )
    logger.info(
        "Sentry initialized (environment=%s, celery=%s)",
        settings.environment,
        with_celery,
    )
