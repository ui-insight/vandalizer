"""Celery tasks for KB validation and auto-generation of test queries.

Routes via the ``tasks.kb.*`` namespace. The async path is optional — sync
endpoints (``POST /knowledge/{uuid}/validate`` etc.) keep the inline behaviour
for short runs; these tasks are used when the request body sets ``async=true``.
"""

from __future__ import annotations

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
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
)
def generate_test_queries_task(self, kb_uuid: str, user_id: str, coverage: str = "standard"):
    """Auto-generate KBTestQuery records via LLM in the background.

    Retries transient connection blips on a fresh attempt with backoff — this
    includes pydantic-ai's ``ModelAPIError`` ("Connection error.", the oauthdev
    outbound-socket blip), which the generator's tight in-process retries can
    miss when the blip outlasts their ~6s window. ``ModelHTTPError`` (an HTTP
    *status* error, and a ModelAPIError subclass) is deliberately not retried —
    a 4xx won't improve on retry — so it's caught and re-raised first.
    """
    from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
    retry_on = (ModelAPIError, *TRANSIENT_EXCEPTIONS)
    try:
        return _run_async(_generate_test_queries_async(kb_uuid, user_id, coverage))
    except ModelHTTPError:
        raise
    except retry_on as exc:
        raise self.retry(exc=exc)


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
# KB URL ingestion task.
#
# Fetching a URL (httpx + Playwright browser fallback) and, when crawl is
# enabled, walking up to 50 child pages serially can take many minutes — far
# longer than nginx's proxy_read_timeout. Running it inline in the request
# handler is what produced the 502 on POST /knowledge/{uuid}/add_urls. The
# frontend already drives this as a background flow (it sets status="building"
# and polls source status), so we dispatch here and return immediately.
# ---------------------------------------------------------------------------


@celery.task(
    bind=True,
    name="tasks.kb.add_urls",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
    soft_time_limit=1800,  # 30 min — accommodates a full 50-page crawl
    time_limit=1860,
)
def add_urls_task(
    self,
    kb_uuid: str,
    urls: list[str],
    crawl_enabled: bool = False,
    max_crawl_pages: int = 5,
    allowed_domains: str = "",
):
    """Fetch, crawl, chunk and embed URLs into a KB in the background."""
    return _run_async(_add_urls_async(
        kb_uuid, urls, crawl_enabled, max_crawl_pages, allowed_domains,
    ))


async def _add_urls_async(
    kb_uuid: str,
    urls: list[str],
    crawl_enabled: bool,
    max_crawl_pages: int,
    allowed_domains: str,
):
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.models.knowledge import KnowledgeBase
    from app.services import knowledge_service as svc

    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        logger.warning("KB %s not found for add_urls; skipping.", kb_uuid)
        return {"kb_uuid": kb_uuid, "added": 0}

    added = await svc.add_urls(
        kb, urls,
        crawl_enabled=crawl_enabled,
        max_crawl_pages=max_crawl_pages,
        allowed_domains=allowed_domains,
    )
    return {"kb_uuid": kb_uuid, "added": added}


@celery.task(
    bind=True,
    name="tasks.kb.refresh_url_source",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
    soft_time_limit=900,  # 15 min — one page (or one large PDF) fetch + embed
    time_limit=960,
)
def refresh_url_source_task(self, kb_uuid: str, source_uuid: str):
    """Re-fetch one URL source in place. See knowledge_service.refresh_url_source."""
    return _run_async(_refresh_url_source_async(kb_uuid, source_uuid))


async def _refresh_url_source_async(kb_uuid: str, source_uuid: str):
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
    from app.services import knowledge_service as svc

    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        logger.warning("KB %s not found for refresh_url_source; skipping.", kb_uuid)
        return {"kb_uuid": kb_uuid, "refreshed": False}
    source = await KnowledgeBaseSource.find_one(
        KnowledgeBaseSource.uuid == source_uuid,
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    )
    if not source:
        logger.warning("Source %s not found in KB %s for refresh; skipping.", source_uuid, kb_uuid)
        # The router flipped the KB to "building"; restore its real status.
        await svc.recalculate_stats(kb)
        return {"kb_uuid": kb_uuid, "refreshed": False}

    reason = await svc.refresh_url_source(source, kb)
    # Unconditional: the router set status="building" before dispatching.
    await svc.recalculate_stats(kb)
    return {"kb_uuid": kb_uuid, "source_uuid": source_uuid, "refreshed": reason is None, "reason": reason}


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
# If a worker crashes mid-run (or is SIGKILLed at the hard time limit), an
# optimization run document is left in status="running" forever — which both
# confuses the UI (perpetual progress spinner) and blocks new optimizations on
# the same subject (the start paths return 409 because an "active" run already
# exists). This task sweeps all three optimizer run collections — KB,
# workflow, extraction — and marks stuck docs failed. Extraction also reaps
# on start and from its read endpoints, and workflow reaps on start; the
# janitor adds the time dimension so a run nobody polls or restarts still
# heals instead of spinning until someone edits the database.
#
# 2× the optimizer tasks' soft_time_limit (5400s) is the cutoff. Anything
# older than that hasn't legitimately been running this whole time — the
# worker would have raised SoftTimeLimitExceeded and we'd see status="failed"
# already. So 3h is a safe floor.
# ---------------------------------------------------------------------------


ORPHAN_RUN_AGE_SECONDS = 5400 * 2  # 3 hours


@celery.task(
    bind=True,
    name="tasks.passive.optimization_janitor",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def optimization_janitor(self):
    """Hourly: mark abandoned KB/workflow/extraction optimization runs failed."""
    return _run_async(_optimization_janitor_async())


async def _optimization_janitor_async() -> dict:
    import datetime as _dt
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.models.kb_optimization_run import KBOptimizationRun
    from app.models.workflow_optimization_run import WorkflowOptimizationRun

    cutoff = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(seconds=ORPHAN_RUN_AGE_SECONDS)
    reaped = 0
    scanned = 0

    # KB runs are finalized inline: no Celery task id on the doc to revoke,
    # so finalizing it is the whole job. The query matches status in
    # {queued, running} so a never-picked-up run (broker dropped the task)
    # is also recovered.
    stuck = await KBOptimizationRun.find(
        {"status": {"$in": ["queued", "running"]}, "started_at": {"$lt": cutoff}},
    ).to_list()
    scanned += len(stuck)
    for run in stuck:
        run.status = "failed"
        run.phase = "failed"
        run.error_message = (
            "Optimization run abandoned — worker crashed or exceeded the "
            f"{ORPHAN_RUN_AGE_SECONDS // 60}-minute soft cap. Run was reaped "
            "by tasks.passive.optimization_janitor."
        )
        run.completed_at = _dt.datetime.now(tz=_dt.timezone.utc)
        try:
            await run.save()
            reaped += 1
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Janitor could not save run %s: %s", run.uuid, e)

    # Extraction and workflow runs each have their own reap_one — both revoke
    # the run's Celery task (so a still-queued copy can't resurrect the doc)
    # and honor a user-requested cancel — so delegate rather than duplicate
    # the finalization write in a second place. reap_one no-ops on a run
    # young enough to still be legitimately executing.
    from app.models.extraction_optimization_run import ExtractionOptimizationRun
    from app.services import extraction_optimizer, workflow_optimizer

    for model_cls, reap_one in (
        (ExtractionOptimizationRun, extraction_optimizer.reap_one),
        (WorkflowOptimizationRun, workflow_optimizer.reap_one),
    ):
        candidates = await model_cls.find(
            {"status": {"$in": ["queued", "running"]}},
        ).to_list()
        scanned += len(candidates)
        for run in candidates:
            try:
                updated = await reap_one(run)
                if updated is not None and updated.status not in ("queued", "running"):
                    reaped += 1
            except Exception as e:  # pragma: no cover — defensive
                logger.warning("Janitor could not reap run %s: %s", run.uuid, e)

    if reaped:
        logger.info("Optimization janitor reaped %d orphan run(s)", reaped)
    return {"reaped": reaped, "scanned": scanned}


# ---------------------------------------------------------------------------
# Passive monthly re-validation of applied KB tunings.
#
# Closes the feedback loop after Apply: once a config is live on a KB, no
# part of the system re-checks whether it still wins on fresh queries. KB
# content drifts and the applied config may quietly stop helping. This task
# re-runs the validation judge on every KB with a live ``rag_config_override``
# and emits a ``regression`` QualityAlert when the headline score has fallen
# more than 10pts vs the originally applied optimization run's optimized score.
# ---------------------------------------------------------------------------


# Regression detection thresholds for the passive sweep.
REGRESSION_DELTA_THRESHOLD = -0.10  # 10pts drop on 0..1 scale
CRITICAL_DELTA_THRESHOLD = -0.20    # 20pts drop → critical instead of warning
REGRESSION_MIN_QUERIES = 5          # require at least this many judged queries


@celery.task(
    bind=True,
    name="tasks.passive.kb_revalidate_applied",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=1,
)
def kb_revalidate_applied(self):
    """Monthly: re-judge KBs with live ``rag_config_override`` and alert on regressions."""
    return _run_async(_kb_revalidate_applied_async())


async def _kb_revalidate_applied_async() -> dict:
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.models.kb_optimization_run import KBOptimizationRun
    from app.models.knowledge import KnowledgeBase
    from app.models.quality_alert import QualityAlert
    from app.models.validation_run import ValidationRun
    from app.services.kb_validation_service import run_kb_validation

    tuned_kbs = await KnowledgeBase.find(
        {
            "rag_config_override": {"$ne": None},
            "rag_config_override_run_uuid": {"$ne": None},
        },
    ).to_list()

    rechecked = 0
    regressions = 0
    for kb in tuned_kbs:
        run = await KBOptimizationRun.find_one(
            {"uuid": kb.rag_config_override_run_uuid},
        )
        if run is None or run.optimized_score is None:
            continue
        try:
            result = await run_kb_validation(kb.uuid, kb.user_id, mode="judge")
        except Exception as e:
            logger.warning("Passive re-validate failed for KB %s: %s", kb.uuid, e)
            continue
        rechecked += 1
        # ``raw_score`` is 0..100 (validation header units); persist the same
        # scale on ValidationRun so the existing quality-timeline chart needs
        # no special-case branch for passive rows.
        current_score_pct = float(result.get("raw_score") or 0.0)
        current_score = current_score_pct / 100.0
        applied_score = float(run.optimized_score or 0.0)
        delta = current_score - applied_score
        retrieval = result.get("retrieval_precision") or {}
        n_judged = int(retrieval.get("num_queries_judged") or 0)

        try:
            await ValidationRun(
                item_kind="knowledge_base",
                item_id=kb.uuid,
                item_name=kb.title or "",
                run_type="kb_validation",
                score=current_score_pct,
                score_breakdown={
                    "applied_score": round(applied_score, 4),
                    "current_score": round(current_score, 4),
                    "delta": round(delta, 4),
                    "n_judged": n_judged,
                },
                result_snapshot={"raw_score": current_score_pct},
                num_test_cases=n_judged,
                user_id=kb.user_id,
                source="passive_monthly",
                source_run_uuid=run.uuid,
            ).insert()
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Could not persist ValidationRun for KB %s: %s", kb.uuid, e)

        if delta < REGRESSION_DELTA_THRESHOLD and n_judged >= REGRESSION_MIN_QUERIES:
            regressions += 1
            severity = "critical" if delta < CRITICAL_DELTA_THRESHOLD else "warning"
            try:
                await QualityAlert(
                    alert_type="regression",
                    item_kind="knowledge_base",
                    item_id=kb.uuid,
                    item_name=kb.title or "",
                    severity=severity,
                    message=(
                        f"Applied KB tuning dropped {abs(delta) * 100:.0f}pts since apply "
                        f"({applied_score * 100:.0f}% → {current_score * 100:.0f}%, "
                        f"n={n_judged} queries). Re-run Autovalidate to find a fresh winner."
                    ),
                    previous_score=round(applied_score * 100.0, 1),
                    current_score=round(current_score_pct, 1),
                ).insert()
            except Exception as e:  # pragma: no cover — defensive
                logger.warning("Could not persist QualityAlert for KB %s: %s", kb.uuid, e)

    if rechecked:
        logger.info(
            "Passive KB re-validation: rechecked %d, regressions %d, total tuned KBs %d",
            rechecked, regressions, len(tuned_kbs),
        )
    return {
        "rechecked": rechecked,
        "regressions": regressions,
        "scanned": len(tuned_kbs),
    }
