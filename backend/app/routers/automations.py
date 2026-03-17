"""Automation API routes."""

import logging
import uuid as _uuid
from pathlib import Path
from typing import Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import get_api_key_user, get_current_user
from app.models.automation import Automation
from app.models.passive import WorkflowTriggerEvent
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.automations import (
    AutomationResponse,
    CreateAutomationRequest,
    UpdateAutomationRequest,
)
from app.services import automation_service as svc

logger = logging.getLogger(__name__)
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
        req.trigger_type, trigger_config=req.trigger_config,
        action_type=req.action_type, action_id=req.action_id,
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
    """Return IDs of automations whose linked workflows/extractions/tasks are currently running,
    plus recently completed automations (within the last 30 seconds) for toast notifications."""
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    recent_cutoff = now - datetime.timedelta(seconds=30)

    active_events = await WorkflowTriggerEvent.find(
        {"status": {"$in": ["pending", "queued", "running"]}}
    ).to_list()

    # Also find recently completed/failed events for toast notifications
    recent_events = await WorkflowTriggerEvent.find(
        {"status": {"$in": ["completed", "failed"]}, "completed_at": {"$gte": recent_cutoff}}
    ).to_list()

    active_workflow_ids = {e.workflow for e in active_events if e.workflow}
    recent_workflow_map: dict[str, dict] = {}
    for e in recent_events:
        if e.workflow:
            wf_id_str = str(e.workflow)
            recent_workflow_map[wf_id_str] = {
                "status": e.status,
                "documents": [str(d) for d in e.documents],
            }

    team_id = str(user.current_team) if user.current_team else None
    user_query: dict = {"user_id": user.user_id, "enabled": True}
    if team_id:
        team_query: dict = {"shared_with_team": True, "team_id": team_id, "enabled": True}
        automations = await Automation.find({"$or": [user_query, team_query]}).to_list()
    else:
        automations = await Automation.find(user_query).to_list()

    active_ids = []
    recently_completed: list[dict] = []

    for a in automations:
        if not a.action_id:
            continue
        a_id_str = str(a.id)

        if a.action_type in ("workflow", "task"):
            try:
                oid = PydanticObjectId(a.action_id)
                if oid in active_workflow_ids:
                    active_ids.append(a_id_str)
                elif a.action_id in recent_workflow_map:
                    info = recent_workflow_map[a.action_id]
                    recently_completed.append({
                        "id": a_id_str,
                        "name": a.name,
                        "status": info["status"],
                        "document_oids": info["documents"],
                    })
            except Exception:
                pass
        elif a.action_type == "extraction":
            raw = await Automation.get_motor_collection().find_one(
                {"_id": a.id}, {"_running": 1}
            )
            if raw and raw.get("_running"):
                active_ids.append(a_id_str)

    # Resolve document ObjectIds to uuid+title for recently completed
    all_doc_oids: list[PydanticObjectId] = []
    for rc in recently_completed:
        for d_oid_str in rc.get("document_oids", []):
            try:
                all_doc_oids.append(PydanticObjectId(d_oid_str))
            except Exception:
                pass

    doc_info_map: dict[str, dict] = {}  # oid_str -> {uuid, title}
    if all_doc_oids:
        from app.models.document import SmartDocument
        docs = await SmartDocument.find({"_id": {"$in": all_doc_oids}}).to_list()
        for d in docs:
            doc_info_map[str(d.id)] = {"uuid": d.uuid, "title": d.title}

    for rc in recently_completed:
        resolved = []
        for d_oid_str in rc.pop("document_oids", []):
            if d_oid_str in doc_info_map:
                resolved.append(doc_info_map[d_oid_str])
        rc["documents"] = resolved

    return {"active_automation_ids": active_ids, "recently_completed": recently_completed}


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


# ---------------------------------------------------------------------------
# API trigger endpoint (x-api-key auth)
# ---------------------------------------------------------------------------


@router.post("/{automation_id}/trigger")
@limiter.limit("20/minute")
async def trigger_automation(
    request,
    automation_id: str,
    files: list[UploadFile] = File(default=[]),
    document_uuids: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    user: User = Depends(get_api_key_user),
):
    """Trigger an automation via API. Accepts file uploads, existing document UUIDs, and/or plain text.

    Requires `x-api-key` header. The automation must be enabled and have an action configured.
    """
    from app.config import Settings
    from app.models.activity import ActivityStatus, ActivityType
    from app.models.document import SmartDocument
    from app.services import activity_service
    from app.tasks.upload_tasks import dispatch_upload_tasks

    auto = await svc.get_automation(automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    if not auto.enabled:
        raise HTTPException(status_code=400, detail="Automation is disabled")
    if not auto.action_id:
        raise HTTPException(status_code=400, detail="Automation has no action configured")

    settings = Settings()
    all_doc_uuids: list[str] = []

    # Parse existing document UUIDs
    if document_uuids:
        all_doc_uuids.extend(u.strip() for u in document_uuids.split(",") if u.strip())

    # Handle plain text input — create a temporary document
    if text and text.strip():
        uid = _uuid.uuid4().hex.upper()
        doc = SmartDocument(
            title=f"API Input {uid[:8]}",
            processing=False,
            valid=True,
            raw_text=text.strip(),
            downloadpath="",
            path="",
            extension="txt",
            uuid=uid,
            user_id=user.user_id,
            space="default",
            folder="0",
        )
        await doc.insert()
        all_doc_uuids.append(uid)

    # Handle file uploads
    for upload in files:
        if not upload.filename:
            continue
        uid = _uuid.uuid4().hex.upper()
        ext = (upload.filename.rsplit(".", 1)[-1] if "." in upload.filename else "pdf").lower()
        relative_path = Path(user.user_id) / f"{uid}.{ext}"
        upload_dir = Path(settings.upload_dir) / user.user_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{uid}.{ext}"
        file_data = await upload.read()
        file_path.write_bytes(file_data)

        doc = SmartDocument(
            title=upload.filename,
            processing=True,
            valid=True,
            raw_text="",
            downloadpath=str(relative_path),
            path=str(relative_path),
            extension=ext,
            uuid=uid,
            user_id=user.user_id,
            space="default",
            folder="0",
        )
        await doc.insert()

        task_id = dispatch_upload_tasks(
            document_uuid=uid, extension=ext, document_path=str(file_path),
            user_id=user.user_id,
        )
        doc.task_id = task_id
        await doc.save()
        all_doc_uuids.append(uid)

    if not all_doc_uuids:
        raise HTTPException(status_code=400, detail="No input provided. Send files, document_uuids, or text.")

    # Route to the appropriate action
    if auto.action_type in ("workflow", "task"):
        from app.services import workflow_service

        activity = await activity_service.activity_start(
            type=ActivityType.WORKFLOW_RUN,
            title=f"API: {auto.name}",
            user_id=user.user_id,
        )
        try:
            session_id = await workflow_service.run_workflow(
                auto.action_id, all_doc_uuids, user.user_id,
                activity_id=str(activity.id),
            )
            return {
                "status": "queued",
                "activity_id": str(activity.id),
                "session_id": session_id,
                "action_type": auto.action_type,
                "documents": all_doc_uuids,
            }
        except ValueError as e:
            await activity_service.activity_finish(activity.id, ActivityStatus.FAILED, error=str(e))
            raise HTTPException(status_code=400, detail=str(e))

    elif auto.action_type == "extraction":
        from app.services import search_set_service

        ss = await search_set_service.get_search_set(auto.action_id)
        if not ss:
            raise HTTPException(status_code=404, detail="Linked extraction not found")

        activity = await activity_service.activity_start(
            type=ActivityType.SEARCH_SET_RUN,
            title=f"API: {auto.name}",
            user_id=user.user_id,
            search_set_uuid=auto.action_id,
        )
        try:
            results = await search_set_service.run_extraction_sync(
                search_set_uuid=auto.action_id,
                document_uuids=all_doc_uuids,
                user_id=user.user_id,
            )
            await activity_service.activity_finish(activity.id, ActivityStatus.COMPLETED)

            # Process output_config (storage, notifications, webhooks)
            output_config = auto.output_config or {}
            if output_config:
                _process_extraction_trigger_outputs(auto, results, output_config)

            return {
                "status": "completed",
                "activity_id": str(activity.id),
                "action_type": "extraction",
                "documents": all_doc_uuids,
                "results": results,
            }
        except Exception as e:
            await activity_service.activity_finish(activity.id, ActivityStatus.FAILED, error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action type: {auto.action_type}")


def _process_extraction_trigger_outputs(
    auto: Automation, results: dict, output_config: dict
) -> None:
    """Process output_config for an extraction triggered via API (sync helpers)."""
    from app.services.output_handlers import (
        call_webhook,
        save_extraction_results_to_folder,
        send_workflow_notification,
        should_send_notification,
    )

    automation_dict = {
        "name": auto.name,
        "user_id": auto.user_id,
        "trigger_type": auto.trigger_type,
        "_id": auto.id,
    }

    result_doc = {
        "status": "completed",
        "trigger_type": "api",
        "final_output": {"output": results},
    }

    # Storage
    storage_cfg = output_config.get("storage", {})
    if storage_cfg.get("enabled"):
        try:
            save_extraction_results_to_folder(results, automation_dict, storage_cfg)
        except Exception as e:
            logger.error("API trigger: failed to save extraction results: %s", e)

    # Notifications
    for notification in output_config.get("notifications", []):
        try:
            if should_send_notification(result_doc, notification):
                send_workflow_notification(result_doc, notification)
        except Exception as e:
            logger.error("API trigger: failed to send extraction notification: %s", e)

    # Webhooks
    for webhook_cfg in output_config.get("webhooks", []):
        try:
            call_webhook(result_doc, webhook_cfg)
        except Exception as e:
            logger.error("API trigger: failed to call extraction webhook: %s", e)
