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


async def action(user, enrollment_id, *, payload=None, reference=None, kind='list'):
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Budget workflow assessment is not available')
    try:
        if kind in ('assess', 'retry'):
            service = AdvancedWorkflowAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        service = AdvancedWorkflowDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await service.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await service.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (AdvancedWorkflowUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/advanced_nodes/budget-workflows')
async def list_budget_work(user: User = Depends(get_current_user), *, enrollment_id: str):
    return await action(user, enrollment_id)


@router.post('/modules/advanced_nodes/budget-captures')
async def capture_budget_work(payload: AdvancedWorkflowCapture, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.post('/modules/advanced_nodes/budget-calculations')
async def save_budget_calculations(payload: AdvancedCalculationSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='calculation')


@router.get('/budget-calculations/{snapshot_id}')
async def read_budget_calculation(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=snapshot_id, kind='calculation')


@router.get('/budget-captures/{snapshot_id}')
async def read_budget_capture(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=snapshot_id, kind='capture')


@router.post('/modules/advanced_nodes/budget-runs')
async def prepare_budget_run(payload: AdvancedPlanRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.get('/budget-runs/{run_id}')
async def read_budget_run(run_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=run_id, kind='run')


@router.post('/budget-runs/scope')
async def save_budget_scope(payload: AdvancedScopeRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.get('/budget-scope-decisions/{decision_id}')
async def read_budget_scope(decision_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=decision_id, kind='scope')


@router.post('/budget-runs/execute')
async def execute_budget_run(payload: AdvancedExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/budget-runs/finalize')
async def finalize_budget_run(payload: AdvancedFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/modules/advanced_nodes/budget-reviews')
async def save_budget_review(payload: AdvancedReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/budget-reviews/{submission_id}')
async def read_budget_review(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=submission_id, kind='review')


@router.post('/budget-reviews/{submission_id}/automatic-reviews')
async def assess_budget_review(submission_id: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=submission_id, kind='assess')


@router.post('/budget-automatic-reviews/{attempt_id}/retry')
async def retry_budget_review(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=attempt_id, kind='retry')
