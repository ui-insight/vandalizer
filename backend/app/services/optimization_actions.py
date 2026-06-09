"""Start / apply actions for optimizer runs, shared by routers and chat tools.

The three per-surface routers (knowledge, extractions, workflows) own HTTP
concerns — auth lookups, body parsing, status-code mapping. The mutations
themselves live here so the agentic chat tools execute the exact same code
path instead of a drifting copy.

Callers are responsible for authorization (manage-level access to the parent
item) before invoking anything in this module.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.extraction_optimization_run import ExtractionOptimizationRun
    from app.models.kb_optimization_run import KBOptimizationRun
    from app.models.workflow_optimization_run import WorkflowOptimizationRun

logger = logging.getLogger(__name__)


class OptimizationActionError(Exception):
    """Raised when a start/apply action can't proceed.

    ``code`` is machine-readable; routers map it onto HTTP status codes and
    chat tools return it in their error payloads.
    """

    def __init__(self, code: str, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

async def start_kb_optimization(
    kb,
    user_id: str,
    token_budget: int,
    include_indexing_track: bool = False,
    apply_on_finish: bool = False,
    autogen_coverage: str = "standard",
    extra_options: Optional[dict] = None,
) -> KBOptimizationRun:
    # Function-local import so tests patching the source module still intercept.
    from app.models.kb_optimization_run import KBOptimizationRun

    if token_budget <= 0:
        raise OptimizationActionError("bad_budget", "token_budget must be > 0")
    if autogen_coverage not in ("quick", "standard", "exhaustive"):
        autogen_coverage = "standard"

    active = await KBOptimizationRun.find_one(
        KBOptimizationRun.kb_uuid == kb.uuid,
        {"status": {"$in": ["queued", "running"]}},
    )
    if active:
        raise OptimizationActionError(
            "active_run",
            f"Optimization already in progress for this KB (run {active.uuid})",
            {"run_uuid": active.uuid},
        )

    run = KBOptimizationRun(
        kb_uuid=kb.uuid,
        user_id=user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "include_indexing_track": include_indexing_track,
            "apply_on_finish": apply_on_finish,
            "autogen_coverage": autogen_coverage,
            **(extra_options or {}),
        },
    )
    await run.insert()

    from app.tasks.kb_validation_tasks import optimize_kb_task
    optimize_kb_task.delay(
        kb.uuid, user_id, run.uuid, token_budget,
        include_indexing_track, apply_on_finish,
    )
    return run


async def start_extraction_optimization(
    search_set,
    user_id: str,
    token_budget: int,
    apply_on_finish: bool = False,
    max_candidates: int = 10,
    include_judge: bool = True,
    test_case_uuids: Optional[list[str]] = None,
    extra_options: Optional[dict] = None,
) -> ExtractionOptimizationRun:
    import uuid as _uuid

    from app.models.extraction_optimization_run import ExtractionOptimizationRun
    from app.services.extraction_optimizer import reap_stale_runs

    # Recover any orphaned run first so a dead worker's "running" doc can't
    # permanently block new runs via the active check below.
    await reap_stale_runs(search_set.uuid)

    active = await ExtractionOptimizationRun.find_one(
        ExtractionOptimizationRun.search_set_uuid == search_set.uuid,
        {"status": {"$in": ["queued", "running"]}},
    )
    if active:
        raise OptimizationActionError(
            "active_run",
            f"Optimization already in progress (run {active.uuid})",
            {"run_uuid": active.uuid},
        )

    # Drop blanks/dupes; None means "use every test case" downstream.
    selected_case_uuids = list(dict.fromkeys(u for u in (test_case_uuids or []) if u)) or None

    # Generate the Celery task id up front so it's persisted before dispatch —
    # no race where the task finishes before we record the id. It's the handle
    # the cancel endpoint + stale-run watchdog use to hard-revoke a wedged run.
    celery_task_id = _uuid.uuid4().hex

    run = ExtractionOptimizationRun(
        search_set_uuid=search_set.uuid,
        user_id=user_id,
        status="queued",
        token_budget=max(0, int(token_budget)),
        celery_task_id=celery_task_id,
        options={
            "apply_on_finish": apply_on_finish,
            "max_candidates": max_candidates,
            "include_judge": include_judge,
            "test_case_uuids": selected_case_uuids,
            **(extra_options or {}),
        },
    )
    await run.insert()

    from app.tasks.extraction_tasks import optimize_extraction_task
    optimize_extraction_task.apply_async(
        args=[
            search_set.uuid, user_id, run.uuid,
            max(0, int(token_budget)),
            bool(apply_on_finish),
            max(1, int(max_candidates)),
            bool(include_judge),
            selected_case_uuids,
        ],
        task_id=celery_task_id,
    )
    return run


async def start_workflow_optimization(
    workflow_id: str,
    user_id: str,
    token_budget: int = 0,
    apply_on_finish: bool = False,
    max_candidates: int = 10,
    include_judge: bool = True,
    extra_options: Optional[dict] = None,
) -> WorkflowOptimizationRun:
    from app.models.workflow_optimization_run import WorkflowOptimizationRun

    if token_budget < 0:
        raise OptimizationActionError("bad_budget", "token_budget must be >= 0")
    if max_candidates < 1 or max_candidates > 50:
        raise OptimizationActionError("bad_candidates", "max_candidates must be in [1, 50]")

    active = await WorkflowOptimizationRun.find_one(
        WorkflowOptimizationRun.workflow_id == workflow_id,
        {"status": {"$in": ["queued", "running"]}},
    )
    if active:
        raise OptimizationActionError(
            "active_run",
            f"Optimization already in progress for this workflow (run {active.uuid})",
            {"run_uuid": active.uuid},
        )

    run = WorkflowOptimizationRun(
        workflow_id=workflow_id,
        user_id=user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "apply_on_finish": apply_on_finish,
            "include_judge": include_judge,
            "max_candidates": max_candidates,
            **(extra_options or {}),
        },
    )
    await run.insert()

    from app.tasks.workflow_optimization_tasks import optimize_workflow_task
    optimize_workflow_task.delay(
        workflow_id, user_id, run.uuid,
        token_budget, apply_on_finish, max_candidates, include_judge,
    )
    return run


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def _require_applyable(run) -> None:
    if run.status != "completed":
        raise OptimizationActionError(
            "not_completed",
            f"Cannot apply — run status is '{run.status}', expected 'completed'",
        )
    if not run.best_config:
        raise OptimizationActionError("no_best_config", "Run has no best_config to apply")


async def apply_kb_optimization(kb, run: KBOptimizationRun, user_id: str) -> dict:
    """Apply a completed optimization's best config to the KB's rag_config_override."""
    _require_applyable(run)

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    # Snapshot the prior override on the run so Revert can restore it.
    run.previous_override = dict(kb.rag_config_override) if kb.rag_config_override else None
    run.applied_at = now
    run.reverted_at = None
    kb.rag_config_override = dict(run.best_config)
    kb.rag_config_override_set_at = now
    kb.rag_config_override_run_uuid = run.uuid
    await kb.save()
    await run.save()
    # Phase 4: write a corresponding ValidationRun so this apply shows up on
    # the unified quality timeline. Best-effort — never block the apply on a
    # telemetry failure.
    try:
        from app.services import quality_service as _qs
        score_pct = float((run.optimized_score or 0.0) * 100.0)
        await _qs.record_optimizer_apply(
            item_kind="knowledge_base",
            item_id=kb.uuid,
            item_name=getattr(kb, "title", "") or "",
            run_type="kb_validation",
            score=score_pct,
            user_id=user_id,
            source_run_uuid=run.uuid,
            applied_config=kb.rag_config_override,
            judge_model=run.judge_model,
            judge_variance=run.judge_variance,
        )
    except Exception:
        logger.warning("Failed to record optimizer-apply ValidationRun for KB %s", kb.uuid)
    return {
        "ok": True,
        "applied_config": kb.rag_config_override,
        "previous_override": run.previous_override,
        "applied_at": now.isoformat(),
    }


async def apply_extraction_optimization(
    search_set,
    run: ExtractionOptimizationRun,
    user_id: str,
    min_cf_pass_rate: Optional[float] = None,
    force: bool = False,
) -> dict:
    """Apply a completed run's best_config to the SearchSet override.

    When ``min_cf_pass_rate`` is supplied and the winning config's cross-field
    pass rate falls below it, raises ``OptimizationActionError`` with code
    ``cross_field_below_threshold``. Resubmit with ``force=True`` to apply anyway.
    """
    _require_applyable(run)

    # Cross-field apply-gate. Only meaningful when the run actually evaluated
    # rules (winner_cross_field_summary populated and has a decisive pass_rate).
    if min_cf_pass_rate is not None and not force and run.winner_cross_field_summary:
        cf_pass_rate = run.winner_cross_field_summary.get("pass_rate")
        if cf_pass_rate is not None and cf_pass_rate < float(min_cf_pass_rate):
            failing = [
                {
                    "rule_id": r.get("rule_id"),
                    "type": r.get("type"),
                    "label": r.get("label"),
                    "pass": r.get("pass"),
                    "fail": r.get("fail"),
                    "pass_rate": r.get("pass_rate"),
                }
                for r in (run.winner_cross_field_rule_breakdown or [])
                if (r.get("fail") or 0) > 0
            ]
            raise OptimizationActionError(
                "cross_field_below_threshold",
                (
                    f"Winning config's cross-field pass rate is "
                    f"{cf_pass_rate:.0%}, below the requested minimum of "
                    f"{float(min_cf_pass_rate):.0%}. Re-submit with "
                    "force=true to apply anyway."
                ),
                {
                    "pass_rate": cf_pass_rate,
                    "min_required": float(min_cf_pass_rate),
                    "failing_rules": failing,
                },
            )

    # Persist previous override on the run so revert can restore it.
    run.previous_override = search_set.extraction_config_override
    search_set.extraction_config_override = dict(run.best_config)
    search_set.extraction_config_override_set_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await search_set.save()
    await run.save()

    # Close the loop: re-validate the test set with the applied config so the
    # completed-state panel can show "optimizer score → real post-apply score."
    # Synchronous so the UI's refetch sees post_apply_validation populated.
    from app.services.extraction_optimizer import run_post_apply_validation
    await run_post_apply_validation(
        run_doc=run,
        search_set_uuid=search_set.uuid,
        user_id=user_id,
        source="explicit_apply",
    )

    # Phase 4: record this apply on the unified quality timeline. Prefer the
    # authoritative post-apply score (0..1 unit, just stamped onto the run by
    # run_post_apply_validation) so the timeline marker agrees with the certified
    # quality tile; fall back to the optimizer's in-run headline only if the
    # post-apply validation didn't run.
    try:
        from app.services import quality_service as _qs
        _post = run.post_apply_validation or {}
        _post_unit = _post.get("score")
        score_pct = (
            float(_post_unit * 100.0) if _post_unit is not None
            else float((run.optimized_score or 0.0) * 100.0)
        )
        await _qs.record_optimizer_apply(
            item_kind="search_set",
            item_id=search_set.uuid,
            item_name=getattr(search_set, "title", "") or "",
            run_type="extraction",
            score=score_pct,
            user_id=user_id,
            source_run_uuid=run.uuid,
            applied_config=search_set.extraction_config_override,
            judge_model=run.judge_model,
            judge_variance=run.judge_variance,
        )
    except Exception:
        logger.warning("Failed to record optimizer-apply ValidationRun for SearchSet %s", search_set.uuid)

    return {"ok": True, "applied_config": search_set.extraction_config_override}


async def apply_workflow_optimization(
    wf,
    run: WorkflowOptimizationRun,
    user_id: str,
    step_ids: Optional[list[str]] = None,
) -> dict:
    """Apply a completed run's best config to ``Workflow.config_override``.

    ``step_ids`` promotes only those step overrides (Phase 3 per-step apply);
    None applies all winning step overrides.
    """
    _require_applyable(run)

    # Snapshot the previous override so revert is exact.
    run.previous_override = wf.config_override
    await run.save()

    winning_overrides: dict = (run.best_config or {}).get("step_overrides") or {}
    if step_ids is not None:
        # Validate: every requested step_id must exist in the winning config.
        unknown = [s for s in step_ids if s not in winning_overrides]
        if unknown:
            raise OptimizationActionError(
                "unknown_step_ids",
                f"Unknown step_ids in winning config: {unknown}",
            )
        # Subset apply: start from the currently-live step_overrides (so the
        # user's prior choices on other steps survive) and overlay only the
        # selected ones from this run's winner.
        live_overrides: dict = ((wf.config_override or {}).get("step_overrides") or {})
        merged = dict(live_overrides)
        for sid in step_ids:
            merged[sid] = winning_overrides[sid]
        applied_overrides = merged
    else:
        applied_overrides = dict(winning_overrides)

    wf.config_override = {
        "step_overrides": applied_overrides,
        "from_run_uuid": run.uuid,
        "partial": step_ids is not None,
    }
    wf.config_override_set_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()

    # Phase 4: record this apply on the unified quality timeline so workflow
    # applies show up alongside validation runs in the shared QualityTimeline.
    try:
        from app.services import quality_service as _qs
        score_pct = float((run.optimized_score or 0.0) * 100.0)
        wf_name = getattr(wf, "name", "") or getattr(wf, "title", "") or ""
        await _qs.record_optimizer_apply(
            item_kind="workflow",
            item_id=str(wf.id),
            item_name=wf_name,
            run_type="workflow",
            score=score_pct,
            user_id=user_id,
            source_run_uuid=run.uuid,
            applied_config=wf.config_override,
            judge_model=run.judge_model,
            judge_variance=run.judge_variance,
        )
    except Exception:
        logger.warning("Failed to record optimizer-apply ValidationRun for workflow %s", wf.id)

    return {
        "ok": True,
        "applied_config": wf.config_override,
        "applied_step_ids": list(applied_overrides.keys()),
        "partial": step_ids is not None,
    }
