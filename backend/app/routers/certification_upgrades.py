"""Optional learner choices; publication never automatically selects a course."""
from collections.abc import Awaitable, Callable
from typing import Annotated, Concatenate, ParamSpec

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

P = ParamSpec("P")

router = APIRouter()
RequestId = Annotated[str, Path(pattern=r'^[a-f0-9]{32}$')]
EnrollmentId = Annotated[str, Query(pattern=r'^[a-f0-9]{32}$')]


async def transfer_delivery(user: User, method: Callable[[], Callable[Concatenate[str, P], Awaitable[dict]]], enabled: bool, *args: P.args, **kwargs: P.kwargs) -> dict:
    if enabled and not versioning_enabled():
        raise HTTPException(status_code=404, detail='Credit transfer is not available')
    try:
        return await method()(user.user_id, *args, **kwargs)
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpgradeUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/credit-transfer-preview', response_model=None)
async def preview_credit_transfer(enrollment_id: EnrollmentId, user: User = Depends(get_current_user)) -> dict:
    return await transfer_delivery(user, lambda: CreditTransfer().preview, True, enrollment_id)


@router.post('/credit-transfers', response_model=None)
async def apply_credit_transfer(payload: CreditTransferRequest, user: User = Depends(get_current_user)) -> dict:
    return await transfer_delivery(user, lambda: CreditTransfer().apply, True, payload)


@router.get('/credit-transfers/{request_id}', response_model=None)
async def saved_credit_transfer(request_id: RequestId, user: User = Depends(get_current_user)) -> dict:
    return await transfer_delivery(user, lambda: CreditTransfer().saved, False, request_id)


async def deliver(user: User, method: Callable[[], Callable[Concatenate[str, P], Awaitable[dict]]], enabled: bool, *args: P.args, **kwargs: P.kwargs) -> dict:
    if enabled and not versioning_enabled():
        raise HTTPException(status_code=404, detail='Optional course selection is not available')
    try:
        return await method()(user.user_id, *args, **kwargs)
    except UpgradeUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/upgrade-choice-preview', response_model=None)
async def preview_choice(enrollment_id: EnrollmentId, target_version: str, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().preview, True, enrollment_id, target_version)


@router.post('/upgrade-choices', response_model=None)
async def accept_choice(payload: UpgradeDecisionRequest, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().accept, True, payload)


@router.get('/upgrade-choices/{request_id}', response_model=None)
async def saved_choice(request_id: RequestId, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().decision, False, request_id)


@router.post('/upgrade-activations', response_model=None)
async def activate_choice(payload: UpgradeActivationRequest, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().activate, True, payload)


@router.get('/upgrade-activations/{request_id}', response_model=None)
async def saved_activation(request_id: RequestId, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().activation, False, request_id)


@router.get('/saved-course-options', response_model=None)
async def saved_course_options(user: User = Depends(get_current_user), cursor: Annotated[str | None, Query(pattern=r'^[a-f0-9]{24}$')] = None) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().saved_options, False, cursor=cursor)


@router.get('/saved-course-preview', response_model=None)
async def saved_course_preview(activation_id: EnrollmentId, action: Action, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().saved_preview, True, activation_id, action)


@router.post('/saved-course-selections', response_model=None)
async def select_saved_course(payload: SavedCourseSelectionRequest, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().select_saved, True, payload)


@router.get('/saved-course-selections/{request_id}', response_model=None)
async def saved_selection_result(request_id: RequestId, user: User = Depends(get_current_user)) -> dict:
    return await deliver(user, lambda: UpgradeDelivery().saved_selection, False, request_id)
