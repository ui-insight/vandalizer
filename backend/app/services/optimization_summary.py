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
        "baseline_score": run.baseline_default_score,
        "trigger": (run.options or {}).get("shadow_trigger"),
        "trigger_detail": (run.options or {}).get("shadow_trigger_detail") or {},
        "tied_with_baseline": run.tied_with_baseline,
        "apply_preview": run.apply_preview,
        "applied_at": run.applied_at.isoformat() if run.applied_at else None,
        "reverted_at": run.reverted_at.isoformat() if run.reverted_at else None,
        # Direct link target for the UI to deep-link the autovalidate panel.
        "link": f"/?mode=knowledge&kb={run.kb_uuid}&run={run.uuid}",
    }


def summarize_extraction_run(run: ExtractionOptimizationRun) -> dict:
    return {
        "surface": "extraction",
        "run_uuid": run.uuid,
        "item_id": run.search_set_uuid,
        "status": run.status,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "score": run.optimized_score,
        "baseline_score": run.baseline_default_score,
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
        "baseline_score": run.baseline_default_score,
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
    return summarize(run) if run else None


async def get_run_by_uuid(surface: str, run_uuid: str):
    """Fetch a run document by its surface name ('kb'/'extraction'/'workflow')."""
    surface_to_kind = {"kb": "knowledge_base", "extraction": "search_set", "workflow": "workflow"}
    entry = _KIND_TO_MODEL.get(surface_to_kind.get(surface, ""))
    if not entry:
        return None
    model, _, _ = entry
    return await model.find_one(model.uuid == run_uuid)


def summarize_run(run) -> Optional[dict]:
    """Summarize any of the three run document types."""
    if isinstance(run, KBOptimizationRun):
        return summarize_kb_run(run)
    if isinstance(run, ExtractionOptimizationRun):
        return summarize_extraction_run(run)
    if isinstance(run, WorkflowOptimizationRun):
        return summarize_workflow_run(run)
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
