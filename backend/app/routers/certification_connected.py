"""Explicit connected-workflow actions; GET requests never run or grade work."""
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_workflow_approval import ConnectedScopeRequest
from app.services.certification_versions.connected_workflow_delivery import ConnectedWorkflowDelivery, ConnectedWorkflowAssessment, ConnectedWorkflowUnavailable
from app.services.certification_versions.connected_workflow_execution import ConnectedExecutionRequest
from app.services.certification_versions.connected_workflow_inputs import ConnectedCaptureRequest
from app.services.certification_versions.connected_workflow_preparation import ConnectedPlanRequest
from app.services.certification_versions.connected_workflow_recovery import ConnectedFinalizationRequest
from app.services.certification_versions.connected_workflow_reviews import ConnectedReviewRequest
from app.services.certification_versions.connected_recovery_decisions import ConnectedRecoveryDecisionRequest
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_delivery import SavedReviewUnavailable

router = APIRouter()


async def action(user: User, enrollment_id: str, *, payload: object | None=None, reference: str | None=None, kind: str='list') -> dict:
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Connected-workflow assessment is not available')
    try:
        if kind in ('assess', 'retry'):
            if reference is None or not isinstance(payload, (AssessmentSubmission, AssessmentRetrySubmission)):
                raise HTTPException(status_code=422, detail='A saved record and assessment request are required')
            service = ConnectedWorkflowAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        delivery = ConnectedWorkflowDelivery()
        if payload is not None:
            return await delivery.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await delivery.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await delivery.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (ConnectedWorkflowUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/multi_step/connected-workflows', response_model=None)
async def list_connected_work(user: User = Depends(get_current_user), *, enrollment_id: str) -> dict:
    return await action(user, enrollment_id)


@router.post('/modules/multi_step/connected-captures', response_model=None)
async def capture_connected_work(payload: ConnectedCaptureRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.get('/connected-captures/{snapshot_id}', response_model=None)
async def read_connected_capture(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=snapshot_id, kind='capture')


@router.post('/modules/multi_step/connected-runs', response_model=None)
async def prepare_connected_run(payload: ConnectedPlanRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.get('/connected-runs/{run_id}', response_model=None)
async def read_connected_run(run_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=run_id, kind='run')


@router.post('/connected-runs/scope', response_model=None)
async def save_connected_scope(payload: ConnectedScopeRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.get('/connected-scope-decisions/{decision_id}', response_model=None)
async def read_connected_scope(decision_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=decision_id, kind='scope')


@router.post('/connected-runs/execute', response_model=None)
async def execute_connected_run(payload: ConnectedExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/connected-runs/finalize', response_model=None)
async def finalize_connected_run(payload: ConnectedFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/modules/multi_step/connected-reviews', response_model=None)
async def save_connected_review(payload: ConnectedReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/connected-reviews/{submission_id}', response_model=None)
async def read_connected_review(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=submission_id, kind='review')


@router.post('/connected-reviews/{submission_id}/automatic-reviews', response_model=None)
async def assess_connected_review(submission_id: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, reference=submission_id, kind='assess')


@router.post('/modules/multi_step/connected-recovery-decisions', response_model=None)
async def save_connected_recovery_choices(payload: ConnectedRecoveryDecisionRequest, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, kind='recovery')


@router.get('/connected-recovery-decisions/{submission_id}', response_model=None)
async def read_connected_recovery_choices(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, reference=submission_id, kind='recovery')


@router.post('/connected-automatic-reviews/{attempt_id}/retry', response_model=None)
async def retry_connected_review(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)) -> dict:
    return await action(user, enrollment_id, payload=payload, reference=attempt_id, kind='retry')
