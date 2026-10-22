"""Explicit validation-suite actions; GET requests never run or grade work."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.validation_approval import ValidationScopeRequest
from app.services.certification_versions.validation_delivery import ValidationDelivery, ValidationAssessment, ValidationUnavailable
from app.services.certification_versions.validation_execution import ValidationExecutionRequest
from app.services.certification_versions.validation_inputs import ValidationCaptureRequest
from app.services.certification_versions.validation_preparation import ValidationPlanRequest
from app.services.certification_versions.validation_recovery import ValidationFinalizationRequest
from app.services.certification_versions.validation_reviews import ValidationReviewRequest
from app.services.certification_versions.validation_suites import ValidationSuiteRequest
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_delivery import SavedReviewUnavailable

router = APIRouter()


async def action(user, enrollment_id, *, payload=None, reference=None, kind='list'):
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Validation suite assessment is not available')
    try:
        if kind in ('assess', 'retry'):
            service = ValidationAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        service = ValidationDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await service.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await service.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (ValidationUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/validation_qa/validation-suites')
async def list_validation_work(user: User = Depends(get_current_user), *, enrollment_id: str):
    return await action(user, enrollment_id)


@router.post('/modules/validation_qa/validation-captures')
async def save_validation_capture(payload: ValidationCaptureRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.post('/modules/validation_qa/validation-suites')
async def save_validation_suite(payload: ValidationSuiteRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='suite')


@router.post('/modules/validation_qa/validation-runs')
async def save_validation_prepare(payload: ValidationPlanRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.post('/validation-runs/scope')
async def save_validation_scope(payload: ValidationScopeRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.post('/validation-runs/execute')
async def save_validation_execute(payload: ValidationExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/validation-runs/finalize')
async def save_validation_finalize(payload: ValidationFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/modules/validation_qa/validation-reviews')
async def save_validation_review(payload: ValidationReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/validation-captures/{reference}')
async def read_validation_capture(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='capture')


@router.get('/validation-suites/{reference}')
async def read_validation_suite(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='suite')


@router.get('/validation-runs/{reference}')
async def read_validation_run(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='run')


@router.get('/validation-scope-decisions/{reference}')
async def read_validation_scope(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='scope')


@router.get('/validation-reviews/{reference}')
async def read_validation_review(reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind='review')


@router.post('/validation-reviews/{reference}/automatic-reviews')
async def assess_validation_review(reference: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=reference, kind='assess')


@router.post('/validation-automatic-reviews/{reference}/retry')
async def retry_validation_review(reference: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=reference, kind='retry')


@router.get('/validation-sources/{origin}/{reference}/{source_id}')
async def read_saved_validation_source(origin: Literal['capture', 'suite', 'run', 'review'], reference: str,
        source_id: Literal['nsf', 'nih'], enrollment_id: str, user: User = Depends(get_current_user)):
    try:
        data, filename = await ValidationDelivery().download(user.user_id, enrollment_id, reference,
            origin=origin, source_id=source_id)
        return Response(content=data, media_type='application/pdf', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe=''),
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    except (ValidationUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
