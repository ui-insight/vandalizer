"""Cost governance for the optimization / "Validate & improve" runs.

Every optimization run (KB, extraction, or workflow) spends real LLM tokens,
so this module adds the cross-resource cost-control layer that the per-resource
"one active run" 409 guards in the routers don't cover:

  1. A per-user concurrency cap across all three run types combined, so a single
     user can't spin up an unbounded number of paid runs at once.
  2. An audit-log entry on every start, giving admins a who / what / when /
     how-much record via the existing audit trail.

The cap is configurable through ``SystemConfig.quality_config`` so admins can
tune it without a code change; it defaults to a sensible ceiling. Global
admins bypass the cap.
"""

import asyncio
import logging

from fastapi import HTTPException

from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.kb_optimization_run import KBOptimizationRun
from app.models.system_config import SystemConfig
from app.models.user import User
from app.models.workflow_optimization_run import WorkflowOptimizationRun
from app.services import audit_service

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ["queued", "running"]

# Max concurrent optimization runs a single (non-admin) user may have in flight
# across KBs, extractions, and workflows combined. Overridable via
# ``SystemConfig.quality_config["max_concurrent_optimizations_per_user"]``.
DEFAULT_MAX_CONCURRENT_PER_USER = 3


async def _count_active_user_runs(user_id: str) -> int:
    """Count queued/running optimization runs the user owns, across all three
    run collections."""

    async def _count(model) -> int:
        return await model.find(
            {"user_id": user_id, "status": {"$in": _ACTIVE_STATUSES}}
        ).count()

    kb, wf, ex = await asyncio.gather(
        _count(KBOptimizationRun),
        _count(WorkflowOptimizationRun),
        _count(ExtractionOptimizationRun),
    )
    return kb + wf + ex


async def _max_concurrent_per_user() -> int:
    try:
        cfg = await SystemConfig.get_config()
        raw = (cfg.quality_config or {}).get("max_concurrent_optimizations_per_user")
        if raw is not None:
            return max(1, int(raw))
    except Exception:
        logger.exception("Failed to read optimization concurrency cap; using default")
    return DEFAULT_MAX_CONCURRENT_PER_USER


async def enforce_and_record_start(
    user: User,
    *,
    resource_type: str,
    resource_id: str,
    resource_name: str | None = None,
    team_id: str | None = None,
    token_budget: int = 0,
) -> None:
    """Gate a new optimization run on the per-user concurrency cap, then write
    an ``optimization.start`` audit entry.

    Call this AFTER the per-resource active-run guard and BEFORE inserting the
    run document. Raises HTTP 429 if the user is already at the cap. Global
    admins bypass the cap (but are still audited).
    """
    if not user.is_admin:
        cap = await _max_concurrent_per_user()
        active = await _count_active_user_runs(user.user_id)
        if active >= cap:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You already have {active} optimization "
                    f"{'run' if active == 1 else 'runs'} in progress "
                    f"(limit {cap}). Wait for one to finish before starting another."
                ),
            )

    # Audit is best-effort — log_event swallows its own errors, but never let a
    # logging hiccup block a legitimate run.
    try:
        await audit_service.log_event(
            action="optimization.start",
            actor_user_id=user.user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            team_id=team_id,
            detail={"token_budget": int(token_budget or 0)},
        )
    except Exception:
        logger.exception("Failed to audit optimization.start for %s", resource_id)
