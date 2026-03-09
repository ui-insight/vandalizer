"""Automation API routes."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.automation import Automation
from app.models.passive import WorkflowTriggerEvent
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
        team_id=auto.team_id,
        shared_with_team=auto.shared_with_team,
        space=auto.space,
        output_config=auto.output_config,
        created_at=auto.created_at.isoformat(),
        updated_at=auto.updated_at.isoformat(),
    )


@router.post("", response_model=AutomationResponse)
async def create_automation(req: CreateAutomationRequest, user: User = Depends(get_current_user)):
    team_id = str(user.current_team) if user.current_team else None
    auto = await svc.create_automation(
        req.name, user.user_id, req.space, req.description,
        req.trigger_type, req.action_type, req.action_id,
        team_id=team_id, shared_with_team=req.shared_with_team,
        output_config=req.output_config,
    )
    return _to_response(auto)


@router.get("", response_model=list[AutomationResponse])
async def list_automations(space: str | None = None, user: User = Depends(get_current_user)):
    team_id = str(user.current_team) if user.current_team else None
    automations = await svc.list_automations(
        user_id=user.user_id, team_id=team_id, space=space,
    )
    return [_to_response(a) for a in automations]


@router.get("/active")
async def get_active_automations(user: User = Depends(get_current_user)):
    """Return IDs of automations whose linked workflows are currently running."""
    active_events = await WorkflowTriggerEvent.find(
        {"status": {"$in": ["pending", "queued", "running"]}}
    ).to_list()

    if not active_events:
        return {"active_automation_ids": []}

    active_workflow_ids = {e.workflow for e in active_events if e.workflow}

    team_id = str(user.current_team) if user.current_team else None
    user_query: dict = {"user_id": user.user_id, "enabled": True}
    if team_id:
        team_query: dict = {"shared_with_team": True, "team_id": team_id, "enabled": True}
        automations = await Automation.find({"$or": [user_query, team_query]}).to_list()
    else:
        automations = await Automation.find(user_query).to_list()

    active_ids = [
        str(a.id)
        for a in automations
        if a.action_id and PydanticObjectId(a.action_id) in active_workflow_ids
    ]

    return {"active_automation_ids": active_ids}


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
        shared_with_team=req.shared_with_team,
        output_config=req.output_config,
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
