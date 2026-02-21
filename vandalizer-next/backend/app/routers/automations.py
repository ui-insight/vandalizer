"""Automation API routes."""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.automations import (
    AutomationResponse,
    CreateAutomationRequest,
    UpdateAutomationRequest,
)
from app.services import automation_service as svc

router = APIRouter()


def _to_response(auto) -> AutomationResponse:
    return AutomationResponse(
        id=str(auto.id),
        name=auto.name,
        description=auto.description,
        enabled=auto.enabled,
        trigger_type=auto.trigger_type,
        trigger_config=auto.trigger_config,
        action_type=auto.action_type,
        action_id=auto.action_id,
        user_id=auto.user_id,
        space=auto.space,
        created_at=auto.created_at.isoformat(),
        updated_at=auto.updated_at.isoformat(),
    )


@router.post("", response_model=AutomationResponse)
async def create_automation(req: CreateAutomationRequest, user: User = Depends(get_current_user)):
    auto = await svc.create_automation(
        req.name, user.user_id, req.space, req.description,
        req.trigger_type, req.action_type, req.action_id,
    )
    return _to_response(auto)


@router.get("", response_model=list[AutomationResponse])
async def list_automations(space: str | None = None, user: User = Depends(get_current_user)):
    automations = await svc.list_automations(space=space)
    return [_to_response(a) for a in automations]


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(automation_id: str, user: User = Depends(get_current_user)):
    auto = await svc.get_automation(automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    return _to_response(auto)


@router.patch("/{automation_id}", response_model=AutomationResponse)
async def update_automation(automation_id: str, req: UpdateAutomationRequest, user: User = Depends(get_current_user)):
    auto = await svc.update_automation(
        automation_id,
        name=req.name,
        description=req.description,
        enabled=req.enabled,
        trigger_type=req.trigger_type,
        trigger_config=req.trigger_config,
        action_type=req.action_type,
        action_id=req.action_id,
    )
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    return _to_response(auto)


@router.delete("/{automation_id}")
async def delete_automation(automation_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_automation(automation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"ok": True}
