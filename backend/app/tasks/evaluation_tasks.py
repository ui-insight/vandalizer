"""Celery tasks for workflow evaluation plan generation and validation runs.

Ported from Flask app/utilities/evaluation_tasks.py.
Uses pymongo (sync) for DB access.
"""

import logging
import os

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    client = MongoClient(mongo_host)
    return client[mongo_db]


@celery_app.task(
    bind=True,
    name="tasks.evaluation.generate_plan",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=5,
)
def generate_evaluation_plan_task(
    self,
    workflow_id: str,
    coverage_level: str = "standard",
    user_id: str | None = None,
) -> dict:
    """Generate an evaluation plan for a workflow."""
    from app.services.workflow_validator import PlanGenerator

    logger.info(
        "Generating evaluation plan for workflow %s (coverage=%s)",
        workflow_id, coverage_level,
    )

    generator = PlanGenerator()
    plan = generator.generate(workflow_id, coverage_level, user_id)

    return {
        "status": "completed",
        "plan_id": str(plan["_id"]),
        "plan_uuid": plan["uuid"],
        "num_checks": plan["num_checks"],
    }


@celery_app.task(
    bind=True,
    name="tasks.evaluation.run_validation",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=5,
)
def run_validation_task(
    self,
    plan_id: str,
    workflow_result_id: str,
    user_id: str | None = None,
) -> dict:
    """Run an evaluation plan against a completed workflow result."""
    from bson import ObjectId

    from app.services.workflow_validator import CheckRunner

    db = _get_db()
    plan = db.evaluation_plan.find_one({"_id": ObjectId(plan_id)})
    workflow_result = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})

    if not plan:
        return {"status": "error", "error": "Evaluation plan not found"}
    if not workflow_result:
        return {"status": "error", "error": "Workflow result not found"}

    logger.info(
        "Running validation: plan=%s, workflow_result=%s",
        plan.get("uuid"), workflow_result_id,
    )

    runner = CheckRunner()
    evaluation_run = runner.run(plan, workflow_result, user_id)

    return {
        "status": "completed",
        "run_id": str(evaluation_run["_id"]),
        "run_uuid": evaluation_run["uuid"],
        "overall_score": evaluation_run.get("overall_score"),
        "grade": evaluation_run.get("grade"),
        "num_passed": evaluation_run.get("num_passed"),
        "num_failed": evaluation_run.get("num_failed"),
        "num_warned": evaluation_run.get("num_warned"),
        "num_skipped": evaluation_run.get("num_skipped"),
    }
