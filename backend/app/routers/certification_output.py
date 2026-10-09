"""Explicit output-workflow actions; GET requests never run or grade work."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.output_workflow_approval import OutputScopeRequest
from app.services.certification_versions.output_workflow_delivery import OutputWorkflowDelivery, OutputWorkflowAssessment, OutputWorkflowUnavailable
from app.services.certification_versions.output_workflow_execution import OutputExecutionRequest
from app.services.certification_versions.output_workflow_inputs import OutputCaptureRequest
from app.services.certification_versions.output_workflow_preparation import OutputPlanRequest
from app.services.certification_versions.output_workflow_recovery import OutputFinalizationRequest
from app.services.certification_versions.output_outcome_reviews import OutputOutcomeReviewRequest
from app.services.certification_versions.output_file_reviews import OutputFileReviewRequest
from app.services.certification_versions.output_private_handoff import OutputHandoffRequest
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_delivery import SavedReviewUnavailable

router = APIRouter()


async def action(user, enrollment_id, *, payload=None, reference=None, kind='list'):
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Output workflow assessment is not available')
    try:
        if kind in ('assess', 'retry'):
            service = OutputWorkflowAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        service = OutputWorkflowDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await service.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await service.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (OutputWorkflowUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/output_delivery/output-workflows')
async def list_output_work(user: User = Depends(get_current_user), *, enrollment_id: str):
    return await action(user, enrollment_id)


@router.post('/modules/output_delivery/output-captures')
async def capture_output_work(payload: OutputCaptureRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.get('/output-captures/{snapshot_id}')
async def read_output_capture(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=snapshot_id, kind='capture')


@router.post('/modules/output_delivery/output-runs')
async def prepare_output_run(payload: OutputPlanRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.get('/output-runs/{run_id}')
async def read_output_run(run_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=run_id, kind='run')


@router.post('/output-runs/scope')
async def save_output_scope(payload: OutputScopeRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.get('/output-scope-decisions/{decision_id}')
async def read_output_scope(decision_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=decision_id, kind='scope')


@router.post('/output-runs/execute')
async def execute_output_run(payload: OutputExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/output-runs/finalize')
async def finalize_output_run(payload: OutputFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/modules/output_delivery/output-reviews')
async def save_output_review(payload: OutputOutcomeReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/output-reviews/{submission_id}')
async def read_output_review(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=submission_id, kind='review')


@router.post('/output-reviews/{submission_id}/automatic-reviews')
async def assess_output_review(submission_id: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=submission_id, kind='assess')


@router.post('/output-automatic-reviews/{attempt_id}/retry')
async def retry_output_review(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=attempt_id, kind='retry')


@router.post('/modules/output_delivery/output-file-reviews')
async def inspect_output_files(payload: OutputFileReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='inspection')


@router.get('/output-file-reviews/{submission_id}')
async def read_output_file_review(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=submission_id, kind='inspection')


@router.post('/modules/output_delivery/output-handoffs')
async def send_private_output(payload: OutputHandoffRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='handoff')


@router.get('/output-handoffs/{request_id}')
async def read_private_output(request_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=request_id, kind='handoff')


@router.get('/output-files/{origin}/{reference}/{kind}')
async def read_saved_output_bytes(origin: Literal['run', 'inspection', 'review', 'handoff'], reference: str,
        kind: Literal['source', 'file', 'bundle'], enrollment_id: str, file_index: int = Query(default=0, ge=0, le=7),
        user: User = Depends(get_current_user)):
    try:
        data, media_type, filename = await OutputWorkflowDelivery().download(user.user_id, enrollment_id, reference,
            origin=origin, kind=kind, file_index=file_index)
        return Response(content=data, media_type=media_type, headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe=''),
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    except (OutputWorkflowUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
