"""Celery tasks for KB validation and auto-generation of test queries.

Routes via the ``tasks.kb.*`` namespace. The async path is optional — sync
endpoints (``POST /knowledge/{uuid}/validate`` etc.) keep the inline behaviour
for short runs; these tasks are used when the request body sets ``async=true``.
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(
    bind=True,
    name="tasks.kb.validate_kb",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
)
def validate_kb_task(self, kb_uuid: str, user_id: str, mode: str = "judge", skip_judge: bool = False):
    """Run a KB validation in the background and persist a ValidationRun."""
    return _run_async(_validate_kb_async(kb_uuid, user_id, mode, skip_judge))


async def _validate_kb_async(kb_uuid: str, user_id: str, mode: str, skip_judge: bool):
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.services.kb_validation_service import run_kb_validation
    result = await run_kb_validation(kb_uuid, user_id, mode=mode, skip_judge=skip_judge)
    # Compact return value — the full result is in the persisted ValidationRun.
    return {
        "kb_uuid": kb_uuid,
        "raw_score": result.get("raw_score"),
        "mode": result.get("mode"),
        "judge_model": result.get("judge_model"),
    }


@celery.task(
    bind=True,
    name="tasks.kb.generate_test_queries",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
)
def generate_test_queries_task(self, kb_uuid: str, user_id: str, coverage: str = "standard"):
    """Auto-generate KBTestQuery records via LLM in the background."""
    return _run_async(_generate_test_queries_async(kb_uuid, user_id, coverage))


async def _generate_test_queries_async(kb_uuid: str, user_id: str, coverage: str):
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.services.kb_question_generator import KBQuestionGenerator
    created = await KBQuestionGenerator().generate(
        kb_uuid, user_id, coverage=coverage, persist=True,
    )
    return {"created": len(created), "uuids": [q.uuid for q in created]}


# ---------------------------------------------------------------------------
# KB Autovalidate optimizer task — long-running, no auto-retry.
#
# Idempotency mid-trial is not safe: a retry would re-run trials that already
# spent tokens. If the worker crashes mid-run, the orphaned KBOptimizationRun
# is left in status="running" and a future janitor task can mark it failed.
# ---------------------------------------------------------------------------


@celery.task(
    bind=True,
    name="tasks.kb.optimize_kb",
    autoretry_for=(),  # explicit: no retries
    soft_time_limit=5400,  # 90 min — accommodates Thorough tier
    time_limit=5460,
)
def optimize_kb_task(
    self,
    kb_uuid: str,
    user_id: str,
    run_uuid: str,
    token_budget: int,
    include_indexing_track: bool = False,
    apply_on_finish: bool = False,
):
    """Drive a KBOptimizationRun. The pre-allocated run document is passed in
    so the API route can return its UUID before the worker picks up the job.
    """
    return _run_async(_optimize_kb_async(
        kb_uuid, user_id, run_uuid, token_budget,
        include_indexing_track, apply_on_finish,
    ))


async def _optimize_kb_async(
    kb_uuid: str,
    user_id: str,
    run_uuid: str,
    token_budget: int,
    include_indexing_track: bool,
    apply_on_finish: bool,
):
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.services.kb_optimizer import KBOptimizer
    run_doc = await KBOptimizer().run(
        kb_uuid=kb_uuid,
        user_id=user_id,
        run_uuid=run_uuid,
        token_budget=token_budget,
        include_indexing_track=include_indexing_track,
        apply_on_finish=apply_on_finish,
    )
    return {
        "run_uuid": run_uuid,
        "kb_uuid": kb_uuid,
        "status": run_doc.status,
        "optimized_score": run_doc.optimized_score,
        "baseline_no_kb_score": run_doc.baseline_no_kb_score,
        "baseline_default_score": run_doc.baseline_default_score,
        "best_config": run_doc.best_config,
    }


# ---------------------------------------------------------------------------
# Orphan-run janitor
#
# If a worker crashes mid-run, the KBOptimizationRun document is left in
# status="running" forever — which both confuses the UI (perpetual progress
# spinner) and blocks new optimizations on the same KB (POST /optimize returns
# 409 because an "active" run already exists). This task scans for
# stuck-in-running docs and marks them failed.
#
# 2× the optimize_kb_task soft_time_limit (5400s) is the cutoff. Anything
# older than that hasn't legitimately been running this whole time — the
# worker would have raised SoftTimeLimitExceeded and we'd see status="failed"
# already. So 3h is a safe floor.
# ---------------------------------------------------------------------------


ORPHAN_RUN_AGE_SECONDS = 5400 * 2  # 3 hours


@celery.task(
    bind=True,
    name="tasks.passive.kb_optimization_janitor",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def kb_optimization_janitor(self):
    """Hourly: mark abandoned KB optimization runs as failed."""
    return _run_async(_kb_optimization_janitor_async())


async def _kb_optimization_janitor_async() -> dict:
    import datetime as _dt
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.models.kb_optimization_run import KBOptimizationRun

    cutoff = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(seconds=ORPHAN_RUN_AGE_SECONDS)
    # Find runs that look stuck. We match status in {queued, running} so a
    # never-picked-up run (broker dropped the task) is also recovered.
    stuck = await KBOptimizationRun.find(
        {"status": {"$in": ["queued", "running"]}, "started_at": {"$lt": cutoff}},
    ).to_list()

    reaped = 0
    for run in stuck:
        run.status = "failed"
        run.phase = "failed"
        run.error_message = (
            "Optimization run abandoned — worker crashed or exceeded the "
            f"{ORPHAN_RUN_AGE_SECONDS // 60}-minute soft cap. Run was reaped "
            "by tasks.passive.kb_optimization_janitor."
        )
        run.completed_at = _dt.datetime.now(tz=_dt.timezone.utc)
        try:
            await run.save()
            reaped += 1
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Janitor could not save run %s: %s", run.uuid, e)
    if reaped:
        logger.info("KB optimization janitor reaped %d orphan run(s)", reaped)
    return {"reaped": reaped, "scanned": len(stuck)}
