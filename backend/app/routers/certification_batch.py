"""Explicit bounded batch actions; GET requests never run or grade work."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.batch_approval import BatchScopeRequest
from app.services.certification_versions.batch_delivery import BatchDelivery, BatchAssessment, BatchUnavailable
from app.services.certification_versions.batch_execution import BatchExecutionRequest
from app.services.certification_versions.batch_inputs import BatchCaptureRequest
from app.services.certification_versions.batch_preparation import BatchPlanRequest
from app.services.certification_versions.batch_recovery import BatchFinalizationRequest
from app.services.certification_versions.batch_reviews import BatchReviewRequest
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_delivery import SavedReviewUnavailable

router = APIRouter()


async def action(user, enrollment_id, *, payload=None, reference=None, kind='list'):
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Batch assessment is not available')
    try:
        if kind in ('assess', 'retry'):
            service = BatchAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        service = BatchDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await service.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await service.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (BatchUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/batch_processing/batch-work')
async def list_batch_work(user: User = Depends(get_current_user), *, enrollment_id: str):
    return await action(user, enrollment_id)


@router.post('/modules/batch_processing/batch-captures')
async def save_batch_capture(payload: BatchCaptureRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.post('/modules/batch_processing/batch-runs')
async def save_batch_prepare(payload: BatchPlanRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.post('/batch-runs/scope')
async def save_batch_scope(payload: BatchScopeRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.post('/batch-runs/execute')
async def save_batch_execute(payload: BatchExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/batch-runs/finalize')
async def save_batch_finalize(payload: BatchFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/modules/batch_processing/batch-reviews')
async def save_batch_review(payload: BatchReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/batch-captures/{reference}')
async def read_batch_capture(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='capture')


@router.get('/batch-runs/{reference}')
async def read_batch_run(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='run')


@router.get('/batch-scope-decisions/{reference}')
async def read_batch_scope(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='scope')


@router.get('/batch-reviews/{reference}')
async def read_batch_review(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='review')


@router.post('/batch-reviews/{reference}/automatic-reviews')
async def assess_batch_review(reference: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=reference, kind='assess')


@router.post('/batch-automatic-reviews/{reference}/retry')
async def retry_batch_review(reference: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=reference, kind='retry')


@router.get('/batch-sources/{origin}/{reference}/{source_id}')
async def read_saved_batch_source(origin: Literal['capture', 'run', 'review'], reference: str,
        source_id: Literal['proposal_1', 'proposal_2', 'proposal_3'], enrollment_id: str, user: User = Depends(get_current_user)):
    try:
        data, filename = await BatchDelivery().download(user.user_id, enrollment_id, reference,
            origin=origin, source_id=source_id)
        return Response(content=data, media_type='application/pdf', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe=''),
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    except (BatchUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
