"""Celery tasks for workflow evaluation plan generation and validation runs."""

from devtools import debug

from app.celery_worker import celery_app
from app.models import EvaluationPlan, WorkflowResult


@celery_app.task(
    bind=True,
    name="tasks.evaluation.generate_plan",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=5,
)
def generate_evaluation_plan_task(
    self, workflow_id: str, coverage_level: str = "standard", user_id: str = None
):
    """Generate an evaluation plan for a workflow."""
    from app.utilities.workflow_validator import PlanGenerator

    debug(
        f"Generating evaluation plan for workflow {workflow_id} "
        f"(coverage={coverage_level})"
    )

    generator = PlanGenerator()
    plan = generator.generate(workflow_id, coverage_level, user_id)

    return {
        "status": "completed",
        "plan_id": str(plan.id),
        "plan_uuid": plan.uuid,
        "num_checks": plan.num_checks,
    }


@celery_app.task(
    bind=True,
    name="tasks.evaluation.run_validation",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=5,
)
def run_validation_task(
    self, plan_id: str, workflow_result_id: str, user_id: str = None
):
    """Run an evaluation plan against a completed workflow result."""
    from app.utilities.workflow_validator import CheckRunner

    plan = EvaluationPlan.objects(id=plan_id).first()
    workflow_result = WorkflowResult.objects(id=workflow_result_id).first()

    if not plan:
        return {"status": "error", "error": "Evaluation plan not found"}
    if not workflow_result:
        return {"status": "error", "error": "Workflow result not found"}

    debug(
        f"Running validation: plan={plan.uuid}, "
        f"workflow_result={workflow_result_id}"
    )

    runner = CheckRunner()
    evaluation_run = runner.run(plan, workflow_result, user_id)

    return {
        "status": "completed",
        "run_id": str(evaluation_run.id),
        "run_uuid": evaluation_run.uuid,
        "overall_score": evaluation_run.overall_score,
        "grade": evaluation_run.grade,
        "num_passed": evaluation_run.num_passed,
        "num_failed": evaluation_run.num_failed,
        "num_warned": evaluation_run.num_warned,
        "num_skipped": evaluation_run.num_skipped,
    }
