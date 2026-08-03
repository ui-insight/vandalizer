"""Optimizer Inbox  - unified tuning-suggestion triage (Phase 6 of loop closure).

Phases 5 + 6 trigger optimizer runs in *shadow* mode in response to quality
alerts and report-only signals. Those runs finish with a winning config and an
``apply_preview`` already computed, but nothing ever asked the user to look at
them — the candidates piled up invisibly, and so did the failures.

This router is the read/triage surface for all three optimizer families:

- ``GET  /inbox``                              — candidates + failures the caller can see
- ``GET  /inbox/count``                        — badge counts only (cheap)
- ``POST /inbox/{surface}/{run_uuid}/dismiss`` — reject a candidate
- ``POST /inbox/{surface}/{run_uuid}/restore`` — un-dismiss it

Applying a candidate deliberately stays on the per-surface endpoints
(``/api/workflows/{id}/optimize/{run}/apply`` and friends) so the inbox
inherits their governance gates — tied-with-baseline, cross-field thresholds,
previous-override snapshots and quality-timeline recording — instead of
growing a second, weaker apply path.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.kb_optimization_run import KBOptimizationRun
from app.models.user import User
from app.models.workflow_optimization_run import WorkflowOptimizationRun
from app.services import access_control, organization_service

logger = logging.getLogger(__name__)

router = APIRouter()


SurfaceKind = Literal["kb", "extraction", "workflow"]

# Inbox window: runs older than this drop out of the inbox (they're still in
# the per-surface history view and in the admin activity view).
INBOX_LOOKBACK = datetime.timedelta(days=14)

# Per-surface cap on the runs we pull before access filtering. The inbox is a
# triage list, not an archive — anything past this is reachable from history.
PER_SURFACE_LIMIT = 50

# Categories the UI groups rows by. ``needs_review`` is the only one that
# carries an action; the rest are informational.
InboxCategory = Literal[
    "needs_review",   # completed, has a config to promote, nobody has acted on it
    "no_change",      # completed but statistically tied with current settings
    "applied",        # winner is live on the item
    "failed",         # the tuning run itself blew up
    "in_flight",      # queued / running
    "cancelled",
    "dismissed",
]


class _AccessCache:
    """Per-request cache of the expensive access-control preamble.

    ``get_team_access_context`` and ``get_user_org_ancestry`` each cost queries,
    and the inbox resolves up to ``3 × PER_SURFACE_LIMIT`` runs that usually
    point at a much smaller set of distinct items. Resolve each item once.
    """

    def __init__(self, user: User) -> None:
        self.user = user
        self._team_access: Any = None
        # ``get_user_org_ancestry`` legitimately returns None, so track loaded
        # state separately rather than treating None as "not cached yet".
        self._org_ancestry: Optional[list[str]] = None
        self._org_loaded = False
        # (surface, item_id) -> (doc, can_manage) | None when not visible
        self._items: dict[tuple[str, str], Optional[tuple[Any, bool]]] = {}

    async def team_access(self) -> Any:
        if self._team_access is None:
            self._team_access = await access_control.get_team_access_context(self.user)
        return self._team_access

    async def org_ancestry(self) -> Optional[list[str]]:
        if not self._org_loaded:
            self._org_ancestry = await organization_service.get_user_org_ancestry(self.user)
            self._org_loaded = True
        return self._org_ancestry

    async def resolve(
        self, surface: SurfaceKind, item_id: str,
    ) -> Optional[tuple[Any, bool]]:
        """Return ``(parent_doc, can_manage)`` or ``None`` when not visible.

        Manage access is checked first because it's the common case for an
        owner and answers both questions in one lookup; the view-only fallback
        exists so a team member who can see (but not change) an item still
        learns that a candidate or failure exists.
        """
        key = (surface, item_id)
        if key in self._items:
            return self._items[key]
        resolved = await self._resolve_uncached(surface, item_id)
        self._items[key] = resolved
        return resolved

    async def _resolve_uncached(
        self, surface: SurfaceKind, item_id: str,
    ) -> Optional[tuple[Any, bool]]:
        if not item_id:
            return None
        try:
            if surface == "kb":
                ancestry = await self.org_ancestry()
                access = await self.team_access()
                doc = await access_control.get_authorized_knowledge_base(
                    item_id, self.user, manage=True,
                    user_org_ancestry=ancestry, team_access=access,
                )
                if doc is not None:
                    return (doc, True)
                doc = await access_control.get_authorized_knowledge_base(
                    item_id, self.user, user_org_ancestry=ancestry, team_access=access,
                )
                return (doc, False) if doc is not None else None

            if surface == "workflow":
                access = await self.team_access()
                doc = await access_control.get_authorized_workflow(
                    item_id, self.user, manage=True, team_access=access,
                )
                if doc is not None:
                    return (doc, True)
                doc = await access_control.get_authorized_workflow(
                    item_id, self.user, team_access=access,
                )
                return (doc, False) if doc is not None else None

            doc = await access_control.get_authorized_search_set(
                item_id, self.user, manage=True,
            )
            if doc is not None:
                return (doc, True)
            doc = await access_control.get_authorized_search_set(item_id, self.user)
            return (doc, False) if doc is not None else None
        except Exception:
            # A malformed id (e.g. a non-ObjectId workflow_id from an old run)
            # must not take down the whole inbox — just hide that row.
            logger.warning(
                "Inbox access resolution failed for %s/%s", surface, item_id, exc_info=True,
            )
            return None


def _item_name(surface: SurfaceKind, doc: Any) -> str:
    """Display name for the tuned item. KB/SearchSet use ``title``; Workflow ``name``."""
    if surface == "workflow":
        return getattr(doc, "name", None) or getattr(doc, "title", None) or "Untitled workflow"
    return getattr(doc, "title", None) or getattr(doc, "name", None) or "Untitled"


def _iso(value: Optional[datetime.datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _categorize(
    *, status: str, dismissed: bool, is_live: bool,
    tied: bool, has_config: bool,
) -> InboxCategory:
    if dismissed:
        return "dismissed"
    if status in ("queued", "running"):
        return "in_flight"
    if status == "failed":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if is_live:
        return "applied"
    if tied or not has_config:
        return "no_change"
    return "needs_review"


def _base_summary(
    *,
    surface: SurfaceKind,
    run: Any,
    item_id: str,
    item_name: str,
    can_manage: bool,
    is_live: bool,
    applied_at: Optional[str],
    reverted_at: Optional[str],
    link: str,
) -> dict:
    """Fields every surface reports identically, so the inbox UI is one table."""
    options = run.options or {}
    tied = bool(getattr(run, "tied_with_baseline", False))
    has_config = bool(getattr(run, "best_config", None)) or bool(
        getattr(run, "best_per_step_config", None)
    )
    dismissed_at = getattr(run, "dismissed_at", None)
    return {
        "surface": surface,
        "run_uuid": run.uuid,
        "item_id": item_id,
        "item_name": item_name,
        "status": run.status,
        "category": _categorize(
            status=run.status, dismissed=dismissed_at is not None,
            is_live=is_live, tied=tied, has_config=has_config,
        ),
        "started_at": _iso(getattr(run, "started_at", None)),
        "completed_at": _iso(getattr(run, "completed_at", None)),
        "score": getattr(run, "optimized_score", None),
        "baseline_score": getattr(run, "baseline_default_score", None),
        # Null for user-launched runs — the UI reads that as "you asked for this".
        "trigger": options.get("shadow_trigger"),
        "trigger_detail": options.get("shadow_trigger_detail") or {},
        "tied_with_baseline": tied,
        "apply_preview": getattr(run, "apply_preview", None),
        "suggestion_count": len(getattr(run, "suggestions", None) or []),
        "applied_at": applied_at,
        "reverted_at": reverted_at,
        "is_live": is_live,
        # Apply/dismiss are hidden without manage rights on the parent item.
        "can_manage": can_manage,
        "dismissed_at": _iso(dismissed_at),
        # Failure detail — the whole reason failed runs are in here.
        "error_message": getattr(run, "error_message", None),
        "error_code": getattr(run, "error_code", None),
        "error_context": getattr(run, "error_context", None),
        "stopped_reason": getattr(run, "stopped_reason", None),
        "phase": getattr(run, "phase", None),
        "progress_message": getattr(run, "progress_message", None),
        "judge_model": getattr(run, "judge_model", None),
        "overfitting_warning": bool(getattr(run, "overfitting_warning", False)),
        "link": link,
    }


def kb_run_is_live(run: Any) -> bool:
    """True when this run's winning config is the KB's current override."""
    return getattr(run, "applied_at", None) is not None and getattr(run, "reverted_at", None) is None


def extraction_run_is_live(run: Any, search_set: Any) -> bool:
    """True when the search set's live override is this run's winning config.

    SearchSet applies overwrite ``extraction_config_override`` outright without
    stamping a source run, so identity has to be established by comparison.
    """
    if not getattr(run, "best_config", None) or search_set is None:
        return False
    return bool(getattr(search_set, "extraction_config_override", None) == run.best_config)


def workflow_run_is_live(run: Any, workflow: Any) -> bool:
    """True when the workflow's ``config_override`` came from this run."""
    if workflow is None:
        return False
    override = getattr(workflow, "config_override", None) or {}
    return bool(override.get("from_run_uuid") == run.uuid)


def _summarize_kb(run: KBOptimizationRun, doc: Any, can_manage: bool) -> dict:
    is_live = kb_run_is_live(run)
    return _base_summary(
        surface="kb", run=run, item_id=run.kb_uuid, item_name=_item_name("kb", doc),
        can_manage=can_manage, is_live=is_live,
        applied_at=_iso(run.applied_at), reverted_at=_iso(run.reverted_at),
        link=f"/?mode=knowledge&kb={run.kb_uuid}",
    )


def _summarize_extraction(run: ExtractionOptimizationRun, doc: Any, can_manage: bool) -> dict:
    is_live = extraction_run_is_live(run, doc)
    # ``previous_override`` non-null means an apply happened at some point,
    # even if a later run has since replaced the live config.
    applied = run.previous_override is not None
    return _base_summary(
        surface="extraction", run=run, item_id=run.search_set_uuid,
        item_name=_item_name("extraction", doc),
        can_manage=can_manage, is_live=is_live,
        applied_at=_iso(getattr(doc, "extraction_config_override_set_at", None)) if applied else None,
        reverted_at=None,
        link=f"/?extraction={run.search_set_uuid}",
    )


def _summarize_workflow(run: WorkflowOptimizationRun, doc: Any, can_manage: bool) -> dict:
    is_live = workflow_run_is_live(run, doc)
    return _base_summary(
        surface="workflow", run=run, item_id=run.workflow_id,
        item_name=_item_name("workflow", doc),
        can_manage=can_manage, is_live=is_live,
        applied_at=_iso(getattr(doc, "config_override_set_at", None)) if is_live else None,
        reverted_at=None,
        link=f"/?workflow={run.workflow_id}",
    )


def _window_filter(cutoff: datetime.datetime) -> dict:
    """Runs the inbox cares about: auto-triggered candidates, plus failures.

    Auto-triggered (shadow) runs are in because nobody asked for them, so the
    inbox is the only place they can surface. Failed runs are in regardless of
    trigger because a run that died is invisible the moment the user navigates
    away from the panel that launched it. Completed *user-launched* runs stay
    out — those are already restored in the item's own Validate & improve tab,
    and folding them in would turn triage into a firehose.
    """
    return {
        "started_at": {"$gte": cutoff},
        "$or": [
            {"options.shadow_trigger": {"$exists": True}},
            {"status": "failed"},
        ],
    }


async def _collect(
    user: User, *, days: int, include_dismissed: bool,
) -> list[dict]:
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days)
    query = _window_filter(cutoff)

    kb_runs = await KBOptimizationRun.find(query).sort("-started_at").limit(PER_SURFACE_LIMIT).to_list()
    ex_runs = await ExtractionOptimizationRun.find(query).sort("-started_at").limit(PER_SURFACE_LIMIT).to_list()
    wf_runs = await WorkflowOptimizationRun.find(query).sort("-started_at").limit(PER_SURFACE_LIMIT).to_list()

    cache = _AccessCache(user)
    items: list[dict] = []

    per_surface: tuple[tuple[SurfaceKind, list, str, Any], ...] = (
        ("kb", kb_runs, "kb_uuid", _summarize_kb),
        ("extraction", ex_runs, "search_set_uuid", _summarize_extraction),
        ("workflow", wf_runs, "workflow_id", _summarize_workflow),
    )
    for surface, runs, item_attr, summarize in per_surface:
        for run in runs:
            if getattr(run, "dismissed_at", None) is not None and not include_dismissed:
                continue
            resolved = await cache.resolve(surface, getattr(run, item_attr, ""))
            if resolved is None:
                # Item deleted, or the caller has no access to it.
                continue
            doc, can_manage = resolved
            items.append(summarize(run, doc, can_manage))

    # Newest activity first; in-flight runs (no completed_at) sort by start.
    items.sort(key=lambda d: d.get("completed_at") or d.get("started_at") or "", reverse=True)
    return items


def _counts(items: list[dict]) -> dict:
    by_category: dict[str, int] = {}
    for it in items:
        by_category[it["category"]] = by_category.get(it["category"], 0) + 1
    return {
        "total": len(items),
        "needs_review": by_category.get("needs_review", 0),
        "failed": by_category.get("failed", 0),
        "in_flight": by_category.get("in_flight", 0),
        "applied": by_category.get("applied", 0),
        "no_change": by_category.get("no_change", 0),
        "dismissed": by_category.get("dismissed", 0),
        # Retained for the pre-existing client contract.
        "pending_review": by_category.get("needs_review", 0),
    }


@router.get("/inbox")
async def list_optimizer_inbox(
    include_dismissed: bool = Query(
        False, description="Include candidates the user already dismissed.",
    ),
    days: int = Query(
        INBOX_LOOKBACK.days, ge=1, le=90,
        description="Lookback window in days.",
    ),
    user: User = Depends(get_current_user),
) -> dict:
    """Tuning suggestions and tuning failures for items the caller can see.

    Every row is access-filtered against the parent KB / search set / workflow,
    so this endpoint leaks nothing the caller couldn't already open, and rows
    carry ``can_manage`` so the UI only offers Apply where it would succeed.
    """
    items = await _collect(user, days=days, include_dismissed=include_dismissed)
    return {
        "items": items,
        "counts": _counts(items),
        "lookback_days": days,
    }


@router.get("/inbox/count")
async def optimizer_inbox_count(
    user: User = Depends(get_current_user),
) -> dict:
    """Badge counts for the nav entry point — same filtering, no row payload."""
    items = await _collect(user, days=INBOX_LOOKBACK.days, include_dismissed=False)
    return _counts(items)


async def _load_run_for_write(
    surface: str, run_uuid: str, user: User,
) -> tuple[Any, _AccessCache]:
    """Fetch a run by (surface, uuid) and assert manage rights on its item."""
    if surface == "kb":
        run = await KBOptimizationRun.find_one(KBOptimizationRun.uuid == run_uuid)
        item_id = getattr(run, "kb_uuid", "")
    elif surface == "extraction":
        run = await ExtractionOptimizationRun.find_one(
            ExtractionOptimizationRun.uuid == run_uuid,
        )
        item_id = getattr(run, "search_set_uuid", "")
    elif surface == "workflow":
        run = await WorkflowOptimizationRun.find_one(
            WorkflowOptimizationRun.uuid == run_uuid,
        )
        item_id = getattr(run, "workflow_id", "")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown surface '{surface}'")

    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    cache = _AccessCache(user)
    resolved = await cache.resolve(surface, item_id)  # type: ignore[arg-type]
    if resolved is None or not resolved[1]:
        # Same response for "not yours" and "view-only" — don't confirm existence
        # of items the caller can't manage.
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return run, cache


@router.post("/inbox/{surface}/{run_uuid}/dismiss")
async def dismiss_optimizer_candidate(
    surface: str, run_uuid: str, user: User = Depends(get_current_user),
) -> dict:
    """Drop a candidate out of the inbox without deleting the run.

    The run stays in the item's history and in the admin activity view, so a
    dismissal is a triage decision, not a cover-up.
    """
    run, _ = await _load_run_for_write(surface, run_uuid, user)
    run.dismissed_at = datetime.datetime.now(tz=datetime.timezone.utc)
    run.dismissed_by = user.user_id
    await run.save()
    logger.info("Optimizer candidate %s/%s dismissed by %s", surface, run_uuid, user.user_id)
    return {"ok": True, "dismissed_at": _iso(run.dismissed_at)}


@router.post("/inbox/{surface}/{run_uuid}/restore")
async def restore_optimizer_candidate(
    surface: str, run_uuid: str, user: User = Depends(get_current_user),
) -> dict:
    """Undo a dismissal (the row returns to its natural category)."""
    run, _ = await _load_run_for_write(surface, run_uuid, user)
    run.dismissed_at = None
    run.dismissed_by = None
    await run.save()
    return {"ok": True}
