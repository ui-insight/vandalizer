"""Shared summaries of optimizer runs across KB / extraction / workflow surfaces.

Used by the optimizer-inbox router and the agentic chat tools so both speak
the same dialect: one dict shape per run regardless of surface, with
``applied_at`` normalized across the three models' different ways of
recording an apply.
"""

from __future__ import annotations

import datetime
from typing import Optional

from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.kb_optimization_run import KBOptimizationRun
from app.models.workflow_optimization_run import WorkflowOptimizationRun
from app.services.optimization_common import reported_baseline_score

# Inbox window: shadow runs older than this are considered stale and dropped
# from the inbox response (they're still in the per-surface history view).
INBOX_LOOKBACK = datetime.timedelta(days=14)


def summarize_kb_run(run: KBOptimizationRun) -> dict:
    return {
        "surface": "kb",
        "run_uuid": run.uuid,
        "item_id": run.kb_uuid,
        "status": run.status,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "score": run.optimized_score,
        "baseline_score": _reported_baseline(run),
        "compared_on_held_out_cases": (
            _held_out_headline(run) is not None
            and getattr(run, "holdout_default_score", None) is not None
        ),
        "trigger": (run.options or {}).get("shadow_trigger"),
        "trigger_detail": (run.options or {}).get("shadow_trigger_detail") or {},
        "tied_with_baseline": run.tied_with_baseline,
        "apply_preview": run.apply_preview,
        "applied_at": run.applied_at.isoformat() if run.applied_at else None,
        "reverted_at": run.reverted_at.isoformat() if run.reverted_at else None,
        # Direct link target for the UI to deep-link the autovalidate panel.
        "link": f"/?mode=knowledge&kb={run.kb_uuid}&run={run.uuid}",
    }


def _held_out_headline(run: KBOptimizationRun | ExtractionOptimizationRun | WorkflowOptimizationRun) -> Optional[float]:
    """The run's headline score when it was measured on held-out cases.

    Runs from before ``holdout_optimized_score`` existed are recognised as the
    KB comparison card recognises them: a headline that differs from the
    training score can only be the held-out re-score.
    """
    held_out = run.holdout_optimized_score
    if held_out is not None:
        return held_out
    train = getattr(run, "optimized_score_train", None)
    if (
        getattr(run, "holdout_default_score", None) is not None
        and run.optimized_score is not None
        and train is not None
        and run.optimized_score != train
    ):
        return run.optimized_score
    return None


def _reported_baseline(run: KBOptimizationRun | ExtractionOptimizationRun | WorkflowOptimizationRun) -> Optional[float]:
    """Current settings' score, on the same cases as the run's headline."""
    return reported_baseline_score(
        holdout_optimized_score=_held_out_headline(run),
        holdout_default_score=getattr(run, "holdout_default_score", None),
        baseline_default_score=run.baseline_default_score,
    )


# What each winner_selection_reason means, in the editor's words.
_WINNER_REASON_TEXT = {
    "highest_score": "The best setup beat the runner-up by more than the scoring noise.",
    "default_in_cluster": (
        "Your current settings scored within the noise of the best setup, so the "
        "results don't justify changing them."
    ),
    "tied_with_baseline": (
        "The best setup scored within the noise of your current settings, so the "
        "results don't justify changing them."
    ),
    "tied_on_reported_score": (
        "The best setup led on the cases used to pick it, but re-scored on the "
        "held-out cases it came within the noise of your current settings. The "
        "lead didn't hold up."
    ),
    "closest_to_default": (
        "Several setups tied for the lead; this is the one that changes the "
        "fewest settings."
    ),
    "no_judge_variance": (
        "The scoring noise couldn't be measured, so a default noise level was "
        "used. Treat the difference as a rough estimate."
    ),
}


def winner_reason_text(reason: Optional[str]) -> Optional[str]:
    """A winner_selection_reason in plain words, never the raw code."""
    if not reason:
        return None
    return _WINNER_REASON_TEXT.get(reason, "The winner was picked by the optimizer's selection rule.")


def _percent(score: Optional[float]) -> Optional[int]:
    """A 0..1 optimizer score as the whole percent the screens show."""
    return None if score is None else round(score * 100)


def with_percent_scores(summary: dict) -> dict:
    """Add ``score_percent`` / ``baseline_score_percent`` to a run summary.

    Run scores are on a 0..1 scale. Chat rounded 0.93 as if it were already
    out of 100 and showed "score 1/100 (was 1)"; these fields carry the number
    the optimizer screens show.
    """
    summary["score_percent"] = _percent(summary.get("score"))
    summary["baseline_score_percent"] = _percent(summary.get("baseline_score"))
    # The difference between the two numbers shown, not the rounded raw
    # difference: 94.6% vs 93.4% is "95% vs 93%", a 2-point difference.
    summary["difference_points"] = (
        summary["score_percent"] - summary["baseline_score_percent"]
        if summary["score_percent"] is not None and summary["baseline_score_percent"] is not None
        else None
    )
    return summary


def _extraction_winner_details(run: ExtractionOptimizationRun) -> dict:
    """Which trial the reported best configuration is, and the top scorer.

    When the best trial is statistically tied with the current settings, the
    reported configuration is the tied setup closest to the current one, not
    the highest-scoring trial; both are returned so neither is mistaken for
    the other.
    """
    completed = [t for t in (run.trials or []) if t.get("status") == "completed" and t.get("score") is not None]
    top = max(completed, key=lambda t: t["score"], default=None)
    best = next((t for t in completed if t.get("trial_id") == getattr(run, "best_trial_id", None)), None)
    if best is None and run.best_config is not None:
        best = next((t for t in completed if t.get("config") == run.best_config), None)
    return {
        "best_trial_score_percent": _percent(best.get("score")) if best else None,
        "top_trial_score_percent": _percent(top.get("score")) if top else None,
        "top_trial_is_best": bool(best and top and best.get("trial_id") == top.get("trial_id")),
        "measured_with_model": getattr(run, "baseline_model", None),
    }


def summarize_extraction_run(run: ExtractionOptimizationRun) -> dict:
    return {
        **_extraction_winner_details(run),
        "surface": "extraction",
        "run_uuid": run.uuid,
        "item_id": run.search_set_uuid,
        "status": run.status,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "score": run.optimized_score,
        "baseline_score": _reported_baseline(run),
        "compared_on_held_out_cases": (
            _held_out_headline(run) is not None
            and getattr(run, "holdout_default_score", None) is not None
        ),
        "trigger": (run.options or {}).get("shadow_trigger"),
        "trigger_detail": (run.options or {}).get("shadow_trigger_detail") or {},
        "tied_with_baseline": getattr(run, "tied_with_baseline", False),
        "apply_preview": getattr(run, "apply_preview", None),
        # Extraction tracks applied state via previous_override being non-null
        # rather than a dedicated applied_at column.
        "applied_at": (
            run.completed_at.isoformat()
            if run.previous_override is not None and run.completed_at
            else None
        ),
        "reverted_at": None,
        "link": f"/?mode=extractions&searchSet={run.search_set_uuid}&run={run.uuid}",
    }


def summarize_workflow_run(run: WorkflowOptimizationRun) -> dict:
    return {
        "surface": "workflow",
        "run_uuid": run.uuid,
        "item_id": run.workflow_id,
        "status": run.status,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "score": run.optimized_score,
        "baseline_score": _reported_baseline(run),
        "compared_on_held_out_cases": (
            _held_out_headline(run) is not None
            and getattr(run, "holdout_default_score", None) is not None
        ),
        "trigger": (run.options or {}).get("shadow_trigger"),
        "trigger_detail": (run.options or {}).get("shadow_trigger_detail") or {},
        "tied_with_baseline": run.tied_with_baseline,
        "apply_preview": getattr(run, "apply_preview", None),
        "applied_at": None,
        "reverted_at": None,
        "link": f"/?mode=workspace&workflow={run.workflow_id}&run={run.uuid}",
    }


# Chat tools speak ValidationRun's item_kind dialect; map it onto the run
# models and their per-surface item-id field.
_KIND_TO_MODEL = {
    "knowledge_base": (KBOptimizationRun, "kb_uuid", summarize_kb_run),
    "search_set": (ExtractionOptimizationRun, "search_set_uuid", summarize_extraction_run),
    "workflow": (WorkflowOptimizationRun, "workflow_id", summarize_workflow_run),
}


async def latest_optimization_summary(item_kind: str, item_id: str) -> Optional[dict]:
    """Latest optimizer run for an item, in the unified summary shape.

    Returns None when the kind is unknown or the item has never been optimized.
    """
    entry = _KIND_TO_MODEL.get(item_kind)
    if not entry:
        return None
    model, id_field, summarize = entry
    run = await model.find({id_field: item_id}).sort("-started_at").first_or_none()
    return with_percent_scores(summarize(run)) if run else None


async def get_run_by_uuid(surface: str, run_uuid: str) -> KBOptimizationRun | ExtractionOptimizationRun | WorkflowOptimizationRun | None:
    """Fetch a run document by its surface name ('kb'/'extraction'/'workflow')."""
    if surface == "kb":
        return await KBOptimizationRun.find_one(KBOptimizationRun.uuid == run_uuid)
    if surface == "extraction":
        return await ExtractionOptimizationRun.find_one(ExtractionOptimizationRun.uuid == run_uuid)
    if surface == "workflow":
        return await WorkflowOptimizationRun.find_one(WorkflowOptimizationRun.uuid == run_uuid)
    return None


def summarize_run(run: object) -> Optional[dict]:
    """Summarize any of the three run document types."""
    if isinstance(run, KBOptimizationRun):
        return with_percent_scores(summarize_kb_run(run))
    if isinstance(run, ExtractionOptimizationRun):
        return with_percent_scores(summarize_extraction_run(run))
    if isinstance(run, WorkflowOptimizationRun):
        return with_percent_scores(summarize_workflow_run(run))
    return None


async def shadow_inbox() -> dict:
    """Shadow optimizer runs across KB/extraction/workflow surfaces.

    Filters:
      - Triggered by a Phase 5 signal or Phase 6 alert (``options.shadow_trigger`` set)
      - Within ``INBOX_LOOKBACK`` (stale candidates drop out)

    Sort: newest completed first; in-flight runs included so the user can
    see "tuning in progress" candidates too.
    """
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - INBOX_LOOKBACK

    # Each query is the same shape: shadow_trigger set AND started_at recent.
    # Access-control on the parent item is the source of truth; this just
    # gathers UUIDs.
    common_filter: dict = {
        "options.shadow_trigger": {"$exists": True},
        "started_at": {"$gte": cutoff},
    }

    kb_runs = await KBOptimizationRun.find(common_filter).sort("-started_at").limit(50).to_list()
    ex_runs = await ExtractionOptimizationRun.find(common_filter).sort("-started_at").limit(50).to_list()
    wf_runs = await WorkflowOptimizationRun.find(common_filter).sort("-started_at").limit(50).to_list()

    items: list[dict] = []
    items.extend(summarize_kb_run(r) for r in kb_runs)
    items.extend(summarize_extraction_run(r) for r in ex_runs)
    items.extend(summarize_workflow_run(r) for r in wf_runs)

    # Newest first across surfaces; missing completed_at sorts last.
    items.sort(key=lambda d: d.get("completed_at") or "", reverse=True)

    pending = [
        it for it in items
        if it["status"] == "completed"
        and not it.get("applied_at")
        and not it.get("tied_with_baseline")
    ]

    return {
        "items": items,
        "counts": {
            "total": len(items),
            "pending_review": len(pending),
            "in_flight": sum(1 for it in items if it["status"] in ("queued", "running")),
            "applied": sum(1 for it in items if it.get("applied_at")),
        },
        # Quietly bubble up the lookback so the UI can render "showing last 14 days".
        "lookback_days": INBOX_LOOKBACK.days,
    }
