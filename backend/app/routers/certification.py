"""Vandal Workflow Architect certification endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.user import User
from app.services import certification_service as svc


class AssessmentPayload(BaseModel):
    answers: dict

router = APIRouter()


@router.get("/progress")
async def get_progress(user: User = Depends(get_current_user)):
    return await svc.get_progress_dict(user.user_id)


@router.post("/modules/{module_id}/validate")
async def validate_module(module_id: str, user: User = Depends(get_current_user)):
    result = await svc.validate_module(user.user_id, module_id)
    return result


@router.post("/modules/{module_id}/complete")
async def complete_module(module_id: str, user: User = Depends(get_current_user)):
    result = await svc.complete_module(user.user_id, module_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/modules/{module_id}/assessment")
async def submit_assessment(
    module_id: str,
    payload: AssessmentPayload,
    user: User = Depends(get_current_user),
):
    """Store self-assessment answers for a module."""
    result = await svc.store_assessment(user.user_id, module_id, payload.answers)
    return result


@router.post("/modules/{module_id}/provision")
async def provision_module(
    module_id: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Provision sample documents for a certification module into the user's workspace."""
    result = await svc.provision_module_documents(user.user_id, module_id, settings)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/modules/{module_id}/exercise")
async def get_exercise(module_id: str, user: User = Depends(get_current_user)):
    """Return the exercise definition for a certification module."""
    exercise = svc.get_exercise(module_id)
    if not exercise:
        raise HTTPException(status_code=404, detail=f"No exercise for module {module_id}")
    return exercise


@router.get("/levels")
async def get_levels():
    """Return the level definitions and XP thresholds."""
    return {
        "levels": [{"name": name, "xp_threshold": xp} for name, xp in svc.LEVELS],
        "module_xp": svc.MODULE_XP,
        "module_order": svc.MODULE_ORDER,
    }
