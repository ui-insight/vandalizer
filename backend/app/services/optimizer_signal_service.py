"""Signal-driven shadow optimizer enqueue.

Phase 5 of the loop-closure plan: report-only signals (cross-field validation
failures, chat thumbs-down rates) become *input* to the optimizers instead
of dying in a collection.

Every entry point here:
- Allocates an optimization run document with ``apply_on_finish=False`` (so
  results are advisory — a human reviews before any production mutation).
- Tags the run via ``options.shadow_trigger`` so the UI can surface "this
  run was auto-enqueued because X" and distinguish from user-launched runs.
- Enforces a per-item cooldown so a noisy signal can't fork hundreds of
  optimizer runs.
- Refuses to enqueue an item that can't be tuned yet (no validation plan, no
  test inputs / test cases with expected values). The optimizer raises on
  those and the manual start routes reject them with a 400 before a run doc
  exists; an auto-trigger that skipped the check spent a run document per
  signal and filled the Tuning suggestions page with failures nobody asked
  for and nobody could act on.

Phase 6 reuses these helpers from the ``QualityAlert.insert`` hook so that
the same alert → shadow-optimizer pipeline works for both report-only
signals (Phase 5) and graded quality alerts (Phase 6).
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal, Optional

from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.kb_optimization_run import KBOptimizationRun
from app.models.workflow_optimization_run import WorkflowOptimizationRun

logger = logging.getLogger(__name__)


# Cooldown — never enqueue a shadow run for the same item within this window.
# Prevents alert storms from spawning a backlog of optimization runs that
# would all converge on the same answer.
DEFAULT_SHADOW_COOLDOWN = datetime.timedelta(hours=6)

# Default token budget for shadow runs. Sized to fit the "quick" tier so the
# auto-triggered work doesn't surprise anyone with cost. Users can re-run at
# a higher tier from the inbox if the candidate looks promising.
DEFAULT_SHADOW_TOKEN_BUDGET = 200_000


ShadowTrigger = Literal[
    "cross_field_failure",      # Phase 5: workflow cross-field validation alert
    "chat_feedback_threshold",  # Phase 5: KB thumbs-down rate crossed
    "quality_alert",            # Phase 6: generic QualityAlert fired
]


async def _already_recent(
    *,
    kind: Literal["kb", "workflow"],
    item_id: str,
    trigger: ShadowTrigger,
    cooldown: datetime.timedelta,
) -> bool:
    """Return True if a shadow run with the same trigger fired recently."""
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - cooldown
    if kind == "kb":
        recent = await KBOptimizationRun.find_one(
            {
                "kb_uuid": item_id,
                "started_at": {"$gte": cutoff},
                "options.shadow_trigger": trigger,
            },
        )
    else:
        recent = await WorkflowOptimizationRun.find_one(
            {
                "workflow_id": item_id,
                "started_at": {"$gte": cutoff},
                "options.shadow_trigger": trigger,
            },
        )
    return recent is not None


async def _workflow_blocker(workflow_id: str) -> Optional[str]:
    """Why a workflow can't be tuned right now, or None when it can.

    The optimizer raises on these preconditions and the manual start route
    rejects them with a 400 before any run doc exists. Auto-triggered runs
    skipped the check entirely, so every signal on an un-testable workflow
    created a run that was dispatched, died in the worker, and landed on the
    Tuning suggestions page as a "Tuning failed" row — 49 of them on one
    deployment, with nothing a user could do about any of them.
    """
    from beanie import PydanticObjectId

    from app.models.workflow import Workflow

    try:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
    except Exception:
        wf = None
    if not wf:
        return "workflow not found"
    if not wf.validation_plan:
        return "workflow has no validation plan"

    from app.services.workflow_optimizer import _resolve_test_inputs

    if not await _resolve_test_inputs(wf):
        return "workflow has no test inputs (no run marked as expected output)"
    return None


async def _extraction_blocker(search_set_uuid: str) -> Optional[str]:
    """Why an extraction set can't be tuned right now, or None when it can.

    Mirrors ``_workflow_blocker`` for the preconditions
    ``run_extraction_optimization`` raises on.
    """
    from app.models.extraction_test_case import ExtractionTestCase
    from app.services.search_set_service import get_extraction_keys

    if not await get_extraction_keys(search_set_uuid):
        return "extraction set has no fields defined"

    test_cases = await ExtractionTestCase.find(
        {"search_set_uuid": search_set_uuid},
    ).to_list()
    if not any(
        tc.expected_values and any(v for v in tc.expected_values.values())
        for tc in test_cases
    ):
        return "extraction set has no test cases with expected values"
    return None


async def enqueue_kb_shadow_run(
    *,
    kb_uuid: str,
    user_id: str,
    trigger: ShadowTrigger,
    trigger_detail: Optional[dict] = None,
    token_budget: int = DEFAULT_SHADOW_TOKEN_BUDGET,
    cooldown: datetime.timedelta = DEFAULT_SHADOW_COOLDOWN,
) -> Optional[str]:
    """Enqueue a KB autovalidate run in shadow mode (apply_on_finish=False).

    Returns the new run uuid, or ``None`` when the cooldown blocked it.
    """
    if await _already_recent(
        kind="kb", item_id=kb_uuid, trigger=trigger, cooldown=cooldown,
    ):
        logger.info(
            "Suppressing shadow KB run for %s (trigger=%s in cooldown)",
            kb_uuid, trigger,
        )
        return None

    # Don't pile a shadow run on top of an in-flight one for the same KB.
    active = await KBOptimizationRun.find_one(
        {"kb_uuid": kb_uuid, "status": {"$in": ["queued", "running"]}},
    )
    if active:
        logger.info(
            "Skipping shadow KB run for %s — active run %s already in flight",
            kb_uuid, active.uuid,
        )
        return None

    run = KBOptimizationRun(
        kb_uuid=kb_uuid,
        user_id=user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "include_indexing_track": False,
            "apply_on_finish": False,
            "autogen_coverage": "quick",
            "shadow_trigger": trigger,
            "shadow_trigger_detail": trigger_detail or {},
        },
    )
    await run.insert()

    from app.tasks.kb_validation_tasks import optimize_kb_task
    optimize_kb_task.delay(
        kb_uuid, user_id, run.uuid, token_budget,
        False,  # include_indexing_track
        False,  # apply_on_finish — shadow
    )
    logger.info(
        "Enqueued shadow KB optimization %s for kb=%s (trigger=%s)",
        run.uuid, kb_uuid, trigger,
    )
    return run.uuid


async def enqueue_extraction_shadow_run(
    *,
    search_set_uuid: str,
    user_id: str,
    trigger: ShadowTrigger,
    trigger_detail: Optional[dict] = None,
    token_budget: int = DEFAULT_SHADOW_TOKEN_BUDGET,
    cooldown: datetime.timedelta = DEFAULT_SHADOW_COOLDOWN,
) -> Optional[str]:
    """Enqueue an extraction optimizer run in shadow mode (apply_on_finish=False)."""
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - cooldown
    recent = await ExtractionOptimizationRun.find_one(
        {
            "search_set_uuid": search_set_uuid,
            "started_at": {"$gte": cutoff},
            "options.shadow_trigger": trigger,
        },
    )
    if recent:
        logger.info(
            "Suppressing shadow extraction run for %s (trigger=%s in cooldown)",
            search_set_uuid, trigger,
        )
        return None

    active = await ExtractionOptimizationRun.find_one(
        {"search_set_uuid": search_set_uuid, "status": {"$in": ["queued", "running"]}},
    )
    if active:
        logger.info(
            "Skipping shadow extraction run for %s — active run %s in flight",
            search_set_uuid, active.uuid,
        )
        return None

    blocker = await _extraction_blocker(search_set_uuid)
    if blocker:
        logger.info(
            "Skipping shadow extraction run for %s — %s", search_set_uuid, blocker,
        )
        return None

    run = ExtractionOptimizationRun(
        search_set_uuid=search_set_uuid,
        user_id=user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "apply_on_finish": False,
            "include_judge": True,
            "shadow_trigger": trigger,
            "shadow_trigger_detail": trigger_detail or {},
        },
    )
    await run.insert()

    from app.tasks.extraction_tasks import optimize_extraction_task
    optimize_extraction_task.delay(
        search_set_uuid, user_id, run.uuid,
        token_budget,
        False,  # apply_on_finish — shadow
        8,      # max_candidates default
        True,   # include_judge
    )
    logger.info(
        "Enqueued shadow extraction optimization %s for search_set=%s (trigger=%s)",
        run.uuid, search_set_uuid, trigger,
    )
    return run.uuid


async def enqueue_workflow_shadow_run(
    *,
    workflow_id: str,
    user_id: str,
    trigger: ShadowTrigger,
    trigger_detail: Optional[dict] = None,
    token_budget: int = DEFAULT_SHADOW_TOKEN_BUDGET,
    cooldown: datetime.timedelta = DEFAULT_SHADOW_COOLDOWN,
) -> Optional[str]:
    """Enqueue a workflow optimizer run in shadow mode (apply_on_finish=False)."""
    if await _already_recent(
        kind="workflow", item_id=workflow_id, trigger=trigger, cooldown=cooldown,
    ):
        logger.info(
            "Suppressing shadow workflow run for %s (trigger=%s in cooldown)",
            workflow_id, trigger,
        )
        return None

    active = await WorkflowOptimizationRun.find_one(
        {"workflow_id": workflow_id, "status": {"$in": ["queued", "running"]}},
    )
    if active:
        logger.info(
            "Skipping shadow workflow run for %s — active run %s already in flight",
            workflow_id, active.uuid,
        )
        return None

    blocker = await _workflow_blocker(workflow_id)
    if blocker:
        logger.info(
            "Skipping shadow workflow run for %s — %s", workflow_id, blocker,
        )
        return None

    run = WorkflowOptimizationRun(
        workflow_id=workflow_id,
        user_id=user_id,
        status="queued",
        token_budget=token_budget,
        options={
            "apply_on_finish": False,
            "include_judge": True,
            "shadow_trigger": trigger,
            "shadow_trigger_detail": trigger_detail or {},
        },
    )
    await run.insert()

    from app.tasks.workflow_optimization_tasks import optimize_workflow_task
    optimize_workflow_task.delay(
        workflow_id, user_id, run.uuid,
        token_budget,
        False,  # apply_on_finish — shadow
        10,     # max_candidates — default
        True,   # include_judge
    )
    logger.info(
        "Enqueued shadow workflow optimization %s for workflow=%s (trigger=%s)",
        run.uuid, workflow_id, trigger,
    )
    return run.uuid
