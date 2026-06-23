"""Celery tasks for workflow optimization.

Parallel to ``kb_validation_tasks`` and ``extraction_tasks``: the API route
pre-allocates a ``WorkflowOptimizationRun`` so it can return its UUID
immediately, then this task drives ``run_optimization`` in the background.
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.tasks import run_task_async

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context, releasing the
    loop's pooled LLM HTTP client on teardown (see ``run_task_async``)."""
    return run_task_async(coro)


@celery_app.task(
    bind=True,
    name="tasks.workflow.optimize",
    # No retries — partial optimization isn't safely resumable; the next run
    # starts a fresh trial set rather than picking up a half-finished one.
    autoretry_for=(),
    soft_time_limit=5400,  # 90 min — matches KB / extraction optimizer ceiling
    time_limit=5460,
)
def optimize_workflow_task(
    self,
    workflow_id: str,
    user_id: str,
    run_uuid: str,
    budget_tokens: int = 0,
    apply_on_finish: bool = False,
    max_candidates: int = 10,
    include_judge: bool = True,
):
    """Drive a WorkflowOptimizationRun. The pre-allocated run document is
    passed in so the API route can return its UUID immediately."""
    return _run_async(_optimize_workflow_async(
        workflow_id, user_id, run_uuid, budget_tokens, apply_on_finish,
        max_candidates, include_judge,
    ))


async def _optimize_workflow_async(
    workflow_id: str,
    user_id: str,
    run_uuid: str,
    budget_tokens: int,
    apply_on_finish: bool,
    max_candidates: int,
    include_judge: bool,
):
    from app.config import Settings
    from app.database import init_db

    await init_db(Settings())

    from app.services.workflow_optimizer import run_optimization
    run_doc = await run_optimization(
        workflow_id=workflow_id,
        user_id=user_id,
        run_uuid=run_uuid,
        budget_tokens=budget_tokens,
        apply_on_finish=apply_on_finish,
        max_candidates=max_candidates,
        include_judge=include_judge,
    )
    return {
        "run_uuid": run_uuid,
        "workflow_id": workflow_id,
        "status": run_doc.status,
        "optimized_score": run_doc.optimized_score,
        "baseline_no_workflow_score": run_doc.baseline_no_workflow_score,
        "baseline_default_score": run_doc.baseline_default_score,
        "best_config": run_doc.best_config,
    }
