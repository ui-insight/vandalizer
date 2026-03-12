"""Vandal Workflow Architect certification endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.services import certification_service as svc

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


@router.get("/levels")
async def get_levels():
    """Return the level definitions and XP thresholds."""
    return {
        "levels": [{"name": name, "xp_threshold": xp} for name, xp in svc.LEVELS],
        "module_xp": svc.MODULE_XP,
        "module_order": svc.MODULE_ORDER,
    }
