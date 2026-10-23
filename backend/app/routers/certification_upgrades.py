"""Optional learner choices; publication never automatically selects a course."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import versioning_enabled
from app.services.certification_versions.saved_course_selection import Action, SavedCourseSelectionRequest
from app.services.certification_versions.upgrade_activation import UpgradeActivationRequest
from app.services.certification_versions.upgrade_comparison import UpgradeUnavailable
from app.services.certification_versions.upgrade_decisions import UpgradeDecisionRequest
from app.services.certification_versions.upgrade_delivery import UpgradeDelivery
from app.services.certification_versions.credit_transfer import CreditTransfer, CreditTransferRequest

router = APIRouter()
RequestId = Annotated[str, Path(pattern=r'^[a-f0-9]{32}$')]
EnrollmentId = Annotated[str, Query(pattern=r'^[a-f0-9]{32}$')]


async def transfer_delivery(user, method, value, *, enabled=True):
    if enabled and not versioning_enabled():
        raise HTTPException(status_code=404, detail='Credit transfer is not available')
    try:
        return await getattr(CreditTransfer(), method)(user.user_id, value)
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpgradeUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/credit-transfer-preview')
async def preview_credit_transfer(enrollment_id: EnrollmentId, user: User = Depends(get_current_user)):
    return await transfer_delivery(user, 'preview', enrollment_id)


@router.post('/credit-transfers')
async def apply_credit_transfer(payload: CreditTransferRequest, user: User = Depends(get_current_user)):
    return await transfer_delivery(user, 'apply', payload)


@router.get('/credit-transfers/{request_id}')
async def saved_credit_transfer(request_id: RequestId, user: User = Depends(get_current_user)):
    return await transfer_delivery(user, 'saved', request_id, enabled=False)


async def deliver(user, method, *args, enabled=True, **kwargs):
    if enabled and not versioning_enabled():
        raise HTTPException(status_code=404, detail='Optional course selection is not available')
    try:
        return await getattr(UpgradeDelivery(), method)(user.user_id, *args, **kwargs)
    except UpgradeUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/upgrade-choice-preview')
async def preview_choice(enrollment_id: EnrollmentId, target_version: str, user: User = Depends(get_current_user)):
    return await deliver(user, 'preview', enrollment_id, target_version)


@router.post('/upgrade-choices')
async def accept_choice(payload: UpgradeDecisionRequest, user: User = Depends(get_current_user)):
    return await deliver(user, 'accept', payload)


@router.get('/upgrade-choices/{request_id}')
async def saved_choice(request_id: RequestId, user: User = Depends(get_current_user)):
    return await deliver(user, 'decision', request_id, enabled=False)


@router.post('/upgrade-activations')
async def activate_choice(payload: UpgradeActivationRequest, user: User = Depends(get_current_user)):
    return await deliver(user, 'activate', payload)


@router.get('/upgrade-activations/{request_id}')
async def saved_activation(request_id: RequestId, user: User = Depends(get_current_user)):
    return await deliver(user, 'activation', request_id, enabled=False)


@router.get('/saved-course-options')
async def saved_course_options(user: User = Depends(get_current_user), cursor: Annotated[str | None, Query(pattern=r'^[a-f0-9]{24}$')] = None):
    return await deliver(user, 'saved_options', cursor=cursor, enabled=False)


@router.get('/saved-course-preview')
async def saved_course_preview(activation_id: EnrollmentId, action: Action, user: User = Depends(get_current_user)):
    return await deliver(user, 'saved_preview', activation_id, action)


@router.post('/saved-course-selections')
async def select_saved_course(payload: SavedCourseSelectionRequest, user: User = Depends(get_current_user)):
    return await deliver(user, 'select_saved', payload)


@router.get('/saved-course-selections/{request_id}')
async def saved_selection_result(request_id: RequestId, user: User = Depends(get_current_user)):
    return await deliver(user, 'saved_selection', request_id, enabled=False)
