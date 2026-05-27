"""Optimizer Inbox  - unified shadow-run candidate list (Phase 6 of loop closure).

Phase 5 + 6 trigger optimizer runs in *shadow* mode in response to quality
alerts and report-only signals. These runs land in the user's inbox with
their winning config + ``apply_preview`` already computed — the user can
review, apply, dismiss, or re-tune from one place rather than checking
each KB / SearchSet / workflow individually.
"""

from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.kb_optimization_run import KBOptimizationRun
from app.models.user import User
from app.models.workflow_optimization_run import WorkflowOptimizationRun

router = APIRouter()


SurfaceKind = Literal["kb", "extraction", "workflow"]

# Inbox window: shadow runs older than this are considered stale and dropped
# from the inbox response (they're still in the per-surface history view).
INBOX_LOOKBACK = datetime.timedelta(days=14)


def _summarize_kb(run: KBOptimizationRun) -> dict:
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


def _summarize_extraction(run: ExtractionOptimizationRun) -> dict:
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


def _summarize_workflow(run: WorkflowOptimizationRun) -> dict:
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


@router.get("/inbox")
async def list_shadow_inbox(
    user: User = Depends(get_current_user),
) -> dict:
    """Return shadow optimizer runs across KB/extraction/workflow.

    Filters:
      - Triggered by a Phase 5 signal or Phase 6 alert (``options.shadow_trigger`` set)
      - Within ``INBOX_LOOKBACK`` (stale candidates drop out)
      - Owned by the current user (system-triggered runs use user_id="system",
        and are visible to everyone via the team scope of their parent item;
        for v1 we surface only the requester's own runs so the inbox stays
        focused — wider sharing is a Phase 7 concern).

    Sort: newest completed first; in-flight runs included so the user can
    see "tuning in progress" candidates too.
    """
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - INBOX_LOOKBACK

    # Each query is the same shape: shadow_trigger set AND started_at recent.
    # ``user_id`` filter is inclusive — surface both runs the user kicked off
    # and system-triggered runs they have access to. Access-control on the
    # parent item is the source of truth; this endpoint just gathers UUIDs.
    common_filter: dict = {
        "options.shadow_trigger": {"$exists": True},
        "started_at": {"$gte": cutoff},
    }

    kb_runs = await KBOptimizationRun.find(common_filter).sort("-started_at").limit(50).to_list()
    ex_runs = await ExtractionOptimizationRun.find(common_filter).sort("-started_at").limit(50).to_list()
    wf_runs = await WorkflowOptimizationRun.find(common_filter).sort("-started_at").limit(50).to_list()

    items: list[dict] = []
    items.extend(_summarize_kb(r) for r in kb_runs)
    items.extend(_summarize_extraction(r) for r in ex_runs)
    items.extend(_summarize_workflow(r) for r in wf_runs)

    # Newest first across surfaces; missing completed_at sorts last.
    items.sort(
        key=lambda d: d.get("completed_at") or "",
        reverse=True,
    )

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
