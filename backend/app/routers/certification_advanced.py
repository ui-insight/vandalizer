"""Explicit budget-workflow actions; GET requests never run or grade work."""
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.advanced_calculation_records import AdvancedCalculationSubmission
from app.services.certification_versions.advanced_workflow_approval import AdvancedScopeRequest
from app.services.certification_versions.advanced_workflow_delivery import AdvancedWorkflowDelivery, AdvancedWorkflowAssessment, AdvancedWorkflowUnavailable
from app.services.certification_versions.advanced_workflow_execution import AdvancedExecutionRequest
from app.services.certification_versions.advanced_workflow_inputs import AdvancedWorkflowCapture
from app.services.certification_versions.advanced_workflow_preparation import AdvancedPlanRequest
from app.services.certification_versions.advanced_workflow_recovery import AdvancedFinalizationRequest
from app.services.certification_versions.advanced_workflow_reviews import AdvancedReviewRequest
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_delivery import SavedReviewUnavailable

router = APIRouter()


async def action(user: User, enrollment_id: str, *, payload: object | None=None, reference: str | None=None, kind: str='list') -> dict:
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Budget workflow assessment is not available')
    try:
        if kind in ('assess', 'retry'):
            if reference is None or not isinstance(payload, (AssessmentSubmission, AssessmentRetrySubmission)):
                raise HTTPException(status_code=422, detail='A saved record and assessment request are required')
            service = AdvancedWorkflowAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        delivery = AdvancedWorkflowDelivery()
        if payload is not None:
            return await delivery.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await delivery.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await delivery.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (AdvancedWorkflowUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/advanced_nodes/budget-workflows', response_model=None)
async def list_budget_work(user: User = Depends(get_current_user), *, enrollment_id: str) -> dict:
    return await action(user, enrollment_id)


@router.post('/modules/advanced_nodes/budget-captures', response_model=None)
async def capture_budget_work(payload: AdvancedWorkflowCapture, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.post('/modules/advanced_nodes/budget-calculations', response_model=None)
async def save_budget_calculations(payload: AdvancedCalculationSubmission, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='calculation')


@router.get('/budget-calculations/{snapshot_id}', response_model=None)
async def read_budget_calculation(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=snapshot_id, kind='calculation')


@router.get('/budget-captures/{snapshot_id}', response_model=None)
async def read_budget_capture(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=snapshot_id, kind='capture')


@router.post('/modules/advanced_nodes/budget-runs', response_model=None)
async def prepare_budget_run(payload: AdvancedPlanRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.get('/budget-runs/{run_id}', response_model=None)
async def read_budget_run(run_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=run_id, kind='run')


@router.post('/budget-runs/scope', response_model=None)
async def save_budget_scope(payload: AdvancedScopeRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.get('/budget-scope-decisions/{decision_id}', response_model=None)
async def read_budget_scope(decision_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=decision_id, kind='scope')


@router.post('/budget-runs/execute', response_model=None)
async def execute_budget_run(payload: AdvancedExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/budget-runs/finalize', response_model=None)
async def finalize_budget_run(payload: AdvancedFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/modules/advanced_nodes/budget-reviews', response_model=None)
async def save_budget_review(payload: AdvancedReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/budget-reviews/{submission_id}', response_model=None)
async def read_budget_review(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=submission_id, kind='review')


@router.post('/budget-reviews/{submission_id}/automatic-reviews', response_model=None)
async def assess_budget_review(submission_id: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, reference=submission_id, kind='assess')


@router.post('/budget-automatic-reviews/{attempt_id}/retry', response_model=None)
async def retry_budget_review(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, reference=attempt_id, kind='retry')
