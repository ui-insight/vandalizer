"""Explicit capstone learner actions; authenticated GET requests only read saved work."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.governance_delivery import GovernanceDelivery, GovernanceAssessment, GovernanceUnavailable
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_delivery import SavedReviewUnavailable
from app.services.certification_versions.governance_inputs import GovernanceCaptureRequest
from app.services.certification_versions.governance_preparation import GovernancePlanRequest
from app.services.certification_versions.governance_approval import GovernanceApprovalRequest
from app.services.certification_versions.governance_execution import GovernanceExecutionRequest
from app.services.certification_versions.governance_recovery import GovernanceFinalizationRequest
from app.services.certification_versions.governance_scope import GovernanceScopeCorrectionRequest
from app.services.certification_versions.governance_findings import GovernanceFindingRequest
from app.services.certification_versions.governance_memos import GovernanceMemoRequest
from app.services.certification_versions.governance_release import GovernanceReleaseRequest
from app.services.certification_versions.governance_handoff import GovernanceHandoffRequest
from app.services.certification_versions.governance_reviews import GovernanceReviewRequest

router = APIRouter()


async def action(user, enrollment_id, *, payload=None, reference=None, kind='list'):
    enabled = runtime.versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Governance capstone is not available')
    try:
        if kind in ('assess', 'retry'):
            service = GovernanceAssessment()
            method = service.request if kind == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        service = GovernanceDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload, action=kind)
        if reference is not None:
            return await service.get(user.user_id, enrollment_id, reference, kind=kind, delivery_enabled=enabled)
        return await service.list(user.user_id, enrollment_id, delivery_enabled=enabled)
    except (GovernanceUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EnrollmentConflict, EvidenceAssemblyUnavailable) as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/governance/governance-work')
async def list_governance_work(user: User = Depends(get_current_user), *, enrollment_id: str):
    return await action(user, enrollment_id)


@router.post('/modules/governance/governance-captures')
async def save_governance_capture(payload: GovernanceCaptureRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='capture')


@router.post('/modules/governance/governance-runs')
async def save_governance_prepare(payload: GovernancePlanRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='prepare')


@router.post('/governance-runs/scope')
async def save_governance_scope(payload: GovernanceApprovalRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='scope')


@router.post('/governance-runs/execute')
async def save_governance_execute(payload: GovernanceExecutionRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='execute')


@router.post('/governance-runs/finalize')
async def save_governance_finalize(payload: GovernanceFinalizationRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='finalize')


@router.post('/governance/corrections')
async def save_governance_correction(payload: GovernanceScopeCorrectionRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='correction')


@router.post('/governance/findings')
async def save_governance_finding(payload: GovernanceFindingRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='finding')


@router.post('/governance/memos')
async def save_governance_memo(payload: GovernanceMemoRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='memo')


@router.post('/governance/releases')
async def save_governance_release(payload: GovernanceReleaseRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='release')


@router.post('/governance/handoffs')
async def save_governance_handoff(payload: GovernanceHandoffRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='handoff')


@router.post('/modules/governance/governance-reviews')
async def save_governance_review(payload: GovernanceReviewRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, kind='review')


@router.get('/governance/{kind}/{reference}')
async def read_governance_record(kind: Literal['capture', 'run', 'scope', 'correction', 'finding', 'memo', 'release', 'handoff', 'review'],
        reference: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, reference=reference, kind=kind)


@router.post('/governance-reviews/{reference}/automatic-reviews')
async def assess_governance_review(reference: str, payload: AssessmentSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=reference, kind='assess')


@router.post('/governance-automatic-reviews/{reference}/retry')
async def retry_governance_review(reference: str, payload: AssessmentRetrySubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await action(user, enrollment_id, payload=payload, reference=reference, kind='retry')


async def download(user, enrollment_id, reference, *, origin, source_id=None):
    try:
        data, filename, content_type = await GovernanceDelivery().download(user.user_id, enrollment_id, reference,
            origin=origin, source_id=source_id)
        return Response(content=data, media_type=content_type, headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe=''),
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    except (GovernanceUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/governance-sources/{origin}/{reference}/{source_id}')
async def download_governance_source(origin: Literal['capture', 'correction', 'run', 'finding', 'memo', 'release', 'handoff', 'review'], reference: str,
        source_id: Literal['award', 'amendment'], enrollment_id: str, user: User = Depends(get_current_user)):
    return await download(user, enrollment_id, reference, origin=origin, source_id=source_id)


@router.get('/governance-memo-files/{origin}/{reference}')
async def download_governance_memo(origin: Literal['memo', 'release', 'handoff', 'review'], reference: str,
        enrollment_id: str, user: User = Depends(get_current_user)):
    return await download(user, enrollment_id, reference, origin=origin)
