"""Office/M365 API routes — intake configs and work items."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.office import IntakeConfig, WorkItem
from app.models.user import User

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateIntakeRequest(BaseModel):
    name: str
    intake_type: str
    mailbox_address: Optional[str] = None
    outlook_folder_id: Optional[str] = None
    drive_id: Optional[str] = None
    folder_path: Optional[str] = None
    default_workflow: Optional[str] = None
    triage_enabled: bool = False


class UpdateIntakeRequest(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    mailbox_address: Optional[str] = None
    outlook_folder_id: Optional[str] = None
    drive_id: Optional[str] = None
    folder_path: Optional[str] = None
    triage_enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------


@router.get("/status")
async def office_status(user: User = Depends(get_current_user)):
    """Check M365 connection status for current user."""
    return {
        "connected": getattr(user, "m365_enabled", False),
        "connected_at": getattr(user, "m365_connected_at", None),
    }


# ---------------------------------------------------------------------------
# Intake configs
# ---------------------------------------------------------------------------


@router.get("/intakes")
async def list_intakes(user: User = Depends(get_current_user)):
    intakes = await IntakeConfig.find(
        IntakeConfig.owner_user_id == user.user_id
    ).sort("-created_at").to_list()
    return {"intakes": [_intake_to_dict(i) for i in intakes]}


@router.post("/intakes")
async def create_intake(req: CreateIntakeRequest, user: User = Depends(get_current_user)):
    from beanie import PydanticObjectId

    intake = IntakeConfig(
        name=req.name,
        intake_type=req.intake_type,
        mailbox_address=req.mailbox_address,
        outlook_folder_id=req.outlook_folder_id,
        drive_id=req.drive_id,
        folder_path=req.folder_path,
        default_workflow=PydanticObjectId(req.default_workflow) if req.default_workflow else None,
        triage_enabled=req.triage_enabled,
        owner_user_id=user.user_id,
    )
    await intake.insert()
    return _intake_to_dict(intake)


@router.patch("/intakes/{intake_uuid}")
async def update_intake(
    intake_uuid: str,
    req: UpdateIntakeRequest,
    user: User = Depends(get_current_user),
):
    intake = await IntakeConfig.find_one(
        IntakeConfig.uuid == intake_uuid,
        IntakeConfig.owner_user_id == user.user_id,
    )
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    if req.name is not None:
        intake.name = req.name
    if req.enabled is not None:
        intake.enabled = req.enabled
    if req.mailbox_address is not None:
        intake.mailbox_address = req.mailbox_address
    if req.outlook_folder_id is not None:
        intake.outlook_folder_id = req.outlook_folder_id
    if req.drive_id is not None:
        intake.drive_id = req.drive_id
    if req.folder_path is not None:
        intake.folder_path = req.folder_path
    if req.triage_enabled is not None:
        intake.triage_enabled = req.triage_enabled
    intake.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await intake.save()
    return _intake_to_dict(intake)


@router.delete("/intakes/{intake_uuid}")
async def delete_intake(intake_uuid: str, user: User = Depends(get_current_user)):
    intake = await IntakeConfig.find_one(
        IntakeConfig.uuid == intake_uuid,
        IntakeConfig.owner_user_id == user.user_id,
    )
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")
    await intake.delete()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Work items
# ---------------------------------------------------------------------------


@router.get("/workitems")
async def list_work_items(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    query: dict = {"owner_user_id": user.user_id}
    if status:
        query["status"] = status
    items = await WorkItem.find(query).sort("-created_at").limit(limit).to_list()
    return {"items": [_work_item_to_dict(i) for i in items]}


@router.get("/workitems/{item_uuid}")
async def get_work_item(item_uuid: str, user: User = Depends(get_current_user)):
    item = await WorkItem.find_one(WorkItem.uuid == item_uuid)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return _work_item_to_dict(item)


@router.post("/workitems/{item_uuid}/approve")
async def approve_work_item(item_uuid: str, user: User = Depends(get_current_user)):
    item = await WorkItem.find_one(WorkItem.uuid == item_uuid)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    if item.status != "awaiting_review":
        raise HTTPException(status_code=400, detail="Item is not awaiting review")
    item.status = "processing"
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await item.save()
    return _work_item_to_dict(item)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _intake_to_dict(intake: IntakeConfig) -> dict:
    return {
        "id": str(intake.id),
        "uuid": intake.uuid,
        "name": intake.name,
        "intake_type": intake.intake_type,
        "enabled": intake.enabled,
        "mailbox_address": intake.mailbox_address,
        "folder_path": intake.folder_path,
        "triage_enabled": intake.triage_enabled,
        "default_workflow": str(intake.default_workflow) if intake.default_workflow else None,
        "created_at": intake.created_at.isoformat() if intake.created_at else None,
        "updated_at": intake.updated_at.isoformat() if intake.updated_at else None,
    }


def _work_item_to_dict(item: WorkItem) -> dict:
    return {
        "id": str(item.id),
        "uuid": item.uuid,
        "source": item.source,
        "status": item.status,
        "subject": item.subject,
        "sender_email": item.sender_email,
        "sender_name": item.sender_name,
        "received_at": item.received_at.isoformat() if item.received_at else None,
        "triage_category": item.triage_category,
        "triage_confidence": item.triage_confidence,
        "triage_tags": item.triage_tags,
        "triage_summary": item.triage_summary,
        "sensitivity_flags": item.sensitivity_flags,
        "feedback_action": item.feedback_action,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
