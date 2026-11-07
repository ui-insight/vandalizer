"""Recover a learner's original committed selection without initiating one."""
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.selection_delivery import SelectionConfirmation, SelectionDelivery
from app.services.certification_versions.selection_preparation_recovery import PreparationRecoveryRequest, SelectionPreparationRecovery

router = APIRouter()


async def _deliver(user: User, payload: SelectionConfirmation | None=None) -> dict:
    try:
        service = SelectionDelivery()
        return await service.status(user.user_id) if payload is None else await service.confirm(user.user_id, payload)
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/selection-status', response_model=None)
async def selection_status(user: User = Depends(get_current_user)) -> dict:
    return await _deliver(user)


@router.post('/selection-confirmations', response_model=None)
async def confirm_selection(payload: SelectionConfirmation, user: User = Depends(get_current_user)) -> dict:
    return await _deliver(user, payload)


@router.post('/selection-preparation-recoveries', response_model=None)
async def stop_selection_preparation(payload: PreparationRecoveryRequest, user: User = Depends(get_current_user)) -> dict:
    try:
        return await SelectionPreparationRecovery().recover(user.user_id, payload)
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
