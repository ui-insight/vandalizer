"""Office/M365 API routes  - intake configs and work items."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.office import IntakeConfig, WorkItem
from app.models.user import User
from app.rate_limit import limiter
from app.services import access_control

router = APIRouter()


async def _get_owned_intake(intake_uuid: str, user: User) -> IntakeConfig | None:
    return await IntakeConfig.find_one(
        IntakeConfig.uuid == intake_uuid,
        IntakeConfig.owner_user_id == user.user_id,
    )


async def _get_owned_work_item(
    item_uuid: str,
    user: User,
    *,
    intake: IntakeConfig | None = None,
) -> WorkItem | None:
    filters = [
        WorkItem.uuid == item_uuid,
        WorkItem.owner_user_id == user.user_id,
    ]
    if intake is not None:
        filters.append(WorkItem.intake_config == intake.id)
    return await WorkItem.find_one(*filters)


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
@limiter.limit("30/minute")
async def create_intake(request: Request, req: CreateIntakeRequest, user: User = Depends(get_current_user)):
    from beanie import PydanticObjectId

    if req.default_workflow:
        workflow = await access_control.get_authorized_workflow(req.default_workflow, user)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

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
@limiter.limit("30/minute")
async def update_intake(
    request: Request,
    intake_uuid: str,
    req: UpdateIntakeRequest,
    user: User = Depends(get_current_user),
):
    intake = await _get_owned_intake(intake_uuid, user)
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
@limiter.limit("30/minute")
async def delete_intake(request: Request, intake_uuid: str, user: User = Depends(get_current_user)):
    intake = await _get_owned_intake(intake_uuid, user)
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
    item = await _get_owned_work_item(item_uuid, user)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return _work_item_to_dict(item)


@router.post("/workitems/{item_uuid}/approve")
@limiter.limit("30/minute")
async def approve_work_item(request: Request, item_uuid: str, user: User = Depends(get_current_user)):
    item = await _get_owned_work_item(item_uuid, user)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    if item.status != "awaiting_review":
        raise HTTPException(status_code=400, detail="Item is not awaiting review")
    item.status = "processing"
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await item.save()
    return _work_item_to_dict(item)


# ---------------------------------------------------------------------------
# Graph subscriptions
# ---------------------------------------------------------------------------


@router.post("/intakes/{intake_uuid}/subscribe")
@limiter.limit("10/minute")
async def create_graph_subscription(
    request: Request,
    intake_uuid: str,
    user: User = Depends(get_current_user),
):
    """Create a Graph subscription for an IntakeConfig."""
    from app.services.graph_client import GraphClient

    intake = await _get_owned_intake(intake_uuid, user)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    client = GraphClient(user.user_id)

    # Determine resource based on intake type
    if intake.intake_type in ("outlook", "outlook_shared"):
        if intake.mailbox_address:
            resource = f"users/{intake.mailbox_address}/mailFolders/inbox/messages"
        else:
            resource = "me/mailFolders/inbox/messages"
        if intake.outlook_folder_id:
            resource = resource.replace("inbox", intake.outlook_folder_id)
        change_type = "created"
    elif intake.intake_type == "onedrive":
        resource = "me/drive/root"
        if intake.folder_path:
            resource = f"me/drive/root:/{intake.folder_path.strip('/')}"
        change_type = "updated"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported intake type: {intake.intake_type}")

    import os
    base_url = os.environ.get("VANDALIZER_BASE_URL", "http://localhost:5173")
    notification_url = f"{base_url}/api/webhooks/graph"
    client_state = f"vandalizer:{user.user_id}:{intake.uuid}"

    sub = client.create_subscription(
        resource=resource,
        change_type=change_type,
        notification_url=notification_url,
        client_state=client_state,
    )

    # Store subscription record
    from app.models.passive import GraphSubscription
    gs = GraphSubscription(
        subscription_id=sub.get("id", ""),
        resource=resource,
        change_type=change_type,
        notification_url=notification_url,
        client_state=client_state,
        expiration=sub.get("expirationDateTime"),
        intake_config=intake.id,
        owner_user_id=user.user_id,
    )
    await gs.insert()

    return {"subscription_id": gs.subscription_id, "uuid": gs.uuid, "expiration": str(gs.expiration)}


@router.delete("/intakes/{intake_uuid}/subscribe")
async def delete_graph_subscription(
    intake_uuid: str,
    user: User = Depends(get_current_user),
):
    """Delete Graph subscriptions for an IntakeConfig."""
    from app.services.graph_client import GraphClient
    from app.models.passive import GraphSubscription

    intake = await _get_owned_intake(intake_uuid, user)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    subs = await GraphSubscription.find(
        GraphSubscription.intake_config == intake.id,
        GraphSubscription.active == True,
    ).to_list()

    client = GraphClient(user.user_id)
    deleted = 0

    for sub in subs:
        try:
            client.delete_subscription(sub.subscription_id)
        except Exception:
            pass
        sub.active = False
        await sub.save()
        deleted += 1

    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Manual triage & process
# ---------------------------------------------------------------------------


@router.post("/intakes/{intake_uuid}/triage/{item_uuid}")
@limiter.limit("20/minute")
async def manual_triage(
    request: Request,
    intake_uuid: str,
    item_uuid: str,
    user: User = Depends(get_current_user),
):
    """Manually trigger triage for a work item."""
    intake = await _get_owned_intake(intake_uuid, user)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    item = await _get_owned_work_item(item_uuid, user, intake=intake)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    from app.celery_app import celery_app
    celery_app.send_task(
        "tasks.passive.triage_work_item",
        args=[str(item.id)],
        queue="passive",
    )

    return {"status": "dispatched"}


@router.post("/intakes/{intake_uuid}/process/{item_uuid}")
@limiter.limit("20/minute")
async def manual_process(
    request: Request,
    intake_uuid: str,
    item_uuid: str,
    user: User = Depends(get_current_user),
):
    """Manually process a work item through its matched workflow."""
    intake = await _get_owned_intake(intake_uuid, user)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")

    item = await _get_owned_work_item(item_uuid, user, intake=intake)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    if not item.matched_workflow:
        raise HTTPException(status_code=400, detail="No matched workflow. Run triage first.")

    workflow = await access_control.get_authorized_workflow(str(item.matched_workflow), user)
    if not workflow:
        raise HTTPException(status_code=404, detail="Matched workflow not found")

    item.status = "processing"
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await item.save()

    from app.celery_app import celery_app
    celery_app.send_task(
        "tasks.passive.triage_work_item",
        args=[str(item.id)],
        queue="passive",
    )

    return {"status": "dispatched"}


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
