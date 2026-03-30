"""Automation API routes."""

import asyncio
import logging
import uuid as _uuid
from pathlib import Path
from typing import Optional

from beanie import PydanticObjectId
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from starlette.responses import JSONResponse

from app.dependencies import get_api_key_user, get_current_user
from app.models.automation import Automation
from app.models.document import SmartDocument
from app.models.passive import ExtractionTriggerEvent, WorkflowTriggerEvent
from app.models.user import User
from app.models.workflow import WorkflowResult
from app.rate_limit import limiter
from app.schemas.automations import (
    AutomationResponse,
    CreateAutomationRequest,
    TriggerEventStatusResponse,
    UpdateAutomationRequest,
)
from app.services import access_control
from app.services.access_control import get_authorized_search_set, get_authorized_workflow
from app.services import automation_service as svc

logger = logging.getLogger(__name__)
router = APIRouter()


async def _validate_action_target(
    action_type: str | None,
    action_id: str | None,
    user: User,
) -> None:
    if not action_type or not action_id:
        return
    if action_type in ("workflow", "task"):
        workflow = await get_authorized_workflow(action_id, user)
        if not workflow:
            raise HTTPException(status_code=404, detail="Linked workflow not found")
    elif action_type == "extraction":
        search_set = await get_authorized_search_set(action_id, user)
        if not search_set:
            raise HTTPException(status_code=404, detail="Linked extraction not found")


async def _authorize_existing_documents(document_uuids: list[str], user: User) -> list[str]:
    team_access = await access_control.get_team_access_context(user)
    authorized_document_uuids: list[str] = []
    for doc_uuid in document_uuids:
        doc = await access_control.get_authorized_document(
            doc_uuid,
            user,
            team_access=team_access,
            allow_admin=True,
        )
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_uuid}")
        authorized_document_uuids.append(doc.uuid)
    return authorized_document_uuids


async def _resolve_action_name(action_type: str | None, action_id: str | None) -> str | None:
    """Look up the name/title of the linked workflow or search set."""
    if not action_id:
        return None
    if action_type in ("workflow", "task"):
        from app.models.workflow import Workflow as WfModel
        try:
            wf = await WfModel.get(PydanticObjectId(action_id))
            return wf.name if wf else None
        except Exception:
            return None
    if action_type == "extraction":
        from app.models.search_set import SearchSet
        ss = await SearchSet.find_one(SearchSet.uuid == action_id)
        if not ss:
            # Fallback: action_id might be a MongoDB _id
            try:
                ss = await SearchSet.get(PydanticObjectId(action_id))
            except Exception:
                pass
        return ss.title if ss else None
    return None


async def _to_response(auto) -> AutomationResponse:
    action_name = await _resolve_action_name(auto.action_type, auto.action_id)
    return AutomationResponse(
        id=str(auto.id),
        name=auto.name,
        description=auto.description,
        enabled=auto.enabled,
        trigger_type=auto.trigger_type,
        trigger_config=auto.trigger_config,
        action_type=auto.action_type,
        action_id=auto.action_id,
        action_name=action_name,
        user_id=auto.user_id,
        team_id=auto.team_id,
        shared_with_team=auto.shared_with_team,
        output_config=auto.output_config,
        created_at=auto.created_at.isoformat(),
        updated_at=auto.updated_at.isoformat(),
    )


@router.post("", response_model=AutomationResponse)
async def create_automation(req: CreateAutomationRequest, user: User = Depends(get_current_user)):
    await _validate_action_target(req.action_type, req.action_id, user)
    team_id = str(user.current_team) if user.current_team else None
    auto = await svc.create_automation(
        req.name, user.user_id, req.description,
        req.trigger_type, trigger_config=req.trigger_config,
        action_type=req.action_type, action_id=req.action_id,
        team_id=team_id, shared_with_team=req.shared_with_team,
        output_config=req.output_config,
    )
    return await _to_response(auto)


@router.get("", response_model=list[AutomationResponse])
async def list_automations(user: User = Depends(get_current_user)):
    team_id = str(user.current_team) if user.current_team else None
    automations = await svc.list_automations(
        user_id=user.user_id, team_id=team_id,
    )
    return [await _to_response(a) for a in automations]


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


# ---------------------------------------------------------------------------
# API trigger: polling endpoint for run status / results
# ---------------------------------------------------------------------------


@router.get("/runs/{trigger_event_id}", response_model=TriggerEventStatusResponse)
@limiter.limit("60/minute")
async def get_trigger_event_status(
    request: Request,
    trigger_event_id: str,
    user: User = Depends(get_api_key_user),
):
    """Poll the status and output of a triggered automation run.

    Works for both workflow and extraction trigger events.
    Returns output data once the run has completed.
    """
    # Try WorkflowTriggerEvent first
    try:
        oid = ObjectId(trigger_event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trigger_event_id")

    wf_event = await WorkflowTriggerEvent.find_one({"_id": oid})
    if wf_event:
        # Verify ownership via automation
        ctx = wf_event.trigger_context or {}
        auto_id = ctx.get("automation_id")
        if auto_id:
            try:
                auto = await Automation.get(PydanticObjectId(auto_id))
            except Exception:
                auto = None
            if not auto or auto.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Trigger event not found")
        output = None
        if wf_event.status == "completed" and wf_event.workflow_result:
            result = await WorkflowResult.get(wf_event.workflow_result)
            if result and result.final_output:
                output = result.final_output.get("output")
        resp = TriggerEventStatusResponse(
            trigger_event_id=trigger_event_id,
            status=wf_event.status,
            action_type="workflow",
            created_at=wf_event.created_at.isoformat() if wf_event.created_at else None,
            started_at=wf_event.started_at.isoformat() if wf_event.started_at else None,
            completed_at=wf_event.completed_at.isoformat() if wf_event.completed_at else None,
            output=output,
            error=wf_event.error,
        )
        if wf_event.status in ("pending", "queued", "running"):
            return JSONResponse(
                content=resp.model_dump(),
                headers={"Retry-After": "5"},
            )
        return resp

    # Try ExtractionTriggerEvent
    ext_event = await ExtractionTriggerEvent.find_one({"_id": oid})
    if ext_event:
        if ext_event.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Trigger event not found")
        resp = TriggerEventStatusResponse(
            trigger_event_id=trigger_event_id,
            status=ext_event.status,
            action_type="extraction",
            created_at=ext_event.created_at.isoformat() if ext_event.created_at else None,
            started_at=ext_event.started_at.isoformat() if ext_event.started_at else None,
            completed_at=ext_event.completed_at.isoformat() if ext_event.completed_at else None,
            output=ext_event.result,
            error=ext_event.error,
        )
        if ext_event.status in ("pending", "queued", "running"):
            return JSONResponse(
                content=resp.model_dump(),
                headers={"Retry-After": "5"},
            )
        return resp

    raise HTTPException(status_code=404, detail="Trigger event not found")


# ---------------------------------------------------------------------------
# CRUD endpoints with path params (must come after /runs, /active etc.)
# ---------------------------------------------------------------------------


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(automation_id: str, user: User = Depends(get_current_user)):
    auto = await svc.get_automation(automation_id, user=user)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    return await _to_response(auto)


@router.patch("/{automation_id}", response_model=AutomationResponse)
async def update_automation(automation_id: str, req: UpdateAutomationRequest, user: User = Depends(get_current_user)):
    current = await svc.get_automation(automation_id, user=user, manage=True)
    if not current:
        raise HTTPException(status_code=404, detail="Automation not found")

    action_type = req.action_type if req.action_type is not None else current.action_type
    action_id = req.action_id if req.action_id is not None else current.action_id
    await _validate_action_target(action_type, action_id, user)

    auto = await svc.update_automation(
        automation_id,
        user=user,
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
    return await _to_response(auto)


@router.delete("/{automation_id}")
async def delete_automation(automation_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_automation(automation_id, user=user)
    if not ok:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API trigger endpoint (x-api-key auth)
# ---------------------------------------------------------------------------


@router.post("/{automation_id}/trigger")
@limiter.limit("20/minute")
async def trigger_automation(
    request: Request,
    automation_id: str,
    files: list[UploadFile] = File(default=[]),
    document_uuids: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    callback_url: Optional[str] = Form(None),
    wait: bool = Query(False),
    timeout: int = Query(30, ge=5, le=120),
    user: User = Depends(get_api_key_user),
):
    """Trigger an automation via API. Accepts file uploads, existing document UUIDs, and/or plain text.

    Requires ``x-api-key`` header. The automation must be enabled and have an action configured.

    For workflow/task actions, creates a WorkflowTriggerEvent and dispatches
    execution through the passive pipeline (with budget/throttle checks, retry,
    and output delivery).
    """
    from app.config import Settings
    from app.tasks.upload_tasks import dispatch_upload_tasks

    auto = await svc.get_automation(automation_id, user=user)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    if not auto.enabled:
        raise HTTPException(status_code=400, detail="Automation is disabled")
    if not auto.action_id:
        raise HTTPException(status_code=400, detail="Automation has no action configured")

    # Validate callback_url if provided (SSRF protection)
    if callback_url:
        from app.utils.url_validation import validate_outbound_url
        try:
            validate_outbound_url(callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid callback_url: {e}")

    settings = Settings()
    team_id = str(user.current_team) if user.current_team else None
    existing_doc_uuids: list[str] = []
    all_doc_uuids: list[str] = []

    try:
        # Parse existing document UUIDs
        if document_uuids:
            existing_doc_uuids.extend(u.strip() for u in document_uuids.split(",") if u.strip())
            existing_doc_uuids = await _authorize_existing_documents(existing_doc_uuids, user)
            all_doc_uuids.extend(existing_doc_uuids)

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
                team_id=team_id,
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
                team_id=team_id,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error preparing trigger inputs for automation %s: %s", automation_id, e)
        raise HTTPException(status_code=500, detail=f"Error preparing inputs: {e}")

    if not all_doc_uuids:
        raise HTTPException(status_code=400, detail="No input provided. Send files, document_uuids, or text.")

    # Route to the appropriate action
    try:
        return await _dispatch_action(auto, user, all_doc_uuids, callback_url, wait, timeout)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error dispatching action for automation %s: %s", automation_id, e)
        raise HTTPException(status_code=500, detail=f"Error dispatching action: {e}")


async def _dispatch_action(auto, user, all_doc_uuids, callback_url, wait, timeout):
    from app.models.activity import ActivityType
    from app.services import activity_service
    if auto.action_type in ("workflow", "task"):
        # Resolve document UUIDs to ObjectIds for the trigger event
        doc_records = await SmartDocument.find(
            {"uuid": {"$in": all_doc_uuids}},
        ).to_list()
        doc_oids = [d.id for d in doc_records]

        # Create a WorkflowTriggerEvent so API triggers get the same
        # tracking, retry, and output delivery as other trigger types
        from app.services.passive_triggers import create_api_trigger

        auto_dict = {
            "_id": auto.id,
            "name": auto.name,
            "user_id": auto.user_id,
        }
        trigger_event = create_api_trigger(
            automation_doc=auto_dict,
            workflow_id=auto.action_id,
            document_oids=doc_oids,
            callback_url=callback_url,
        )

        # Also create an Activity for the UI activity feed
        activity = await activity_service.activity_start(
            type=ActivityType.WORKFLOW_RUN,
            title=f"API: {auto.name}",
            user_id=user.user_id,
            workflow=PydanticObjectId(auto.action_id),
        )

        # Dispatch to the passive execution pipeline
        from app.tasks.passive_tasks import execute_workflow_passive
        execute_workflow_passive.delay(str(trigger_event["_id"]))

        trigger_event_id = str(trigger_event["_id"])

        if wait:
            output = await _wait_for_workflow_event(trigger_event_id, timeout)
            if output is not None:
                return {
                    "status": "completed",
                    "trigger_event_id": trigger_event_id,
                    "activity_id": str(activity.id),
                    "action_type": auto.action_type,
                    "documents": all_doc_uuids,
                    "output": output,
                }
            # Timed out — return 202
            return JSONResponse(
                status_code=202,
                content={
                    "status": "running",
                    "trigger_event_id": trigger_event_id,
                    "activity_id": str(activity.id),
                    "action_type": auto.action_type,
                    "documents": all_doc_uuids,
                    "output": None,
                    "message": f"Still running. Poll GET /api/automations/runs/{trigger_event_id} for results.",
                },
            )

        return {
            "status": "queued",
            "trigger_event_id": trigger_event_id,
            "activity_id": str(activity.id),
            "action_type": auto.action_type,
            "documents": all_doc_uuids,
        }

    elif auto.action_type == "extraction":
        ss = await get_authorized_search_set(auto.action_id, user)
        if not ss:
            raise HTTPException(status_code=404, detail="Linked extraction not found")

        # Create tracking event for extractions
        ext_event = ExtractionTriggerEvent(
            automation_id=str(auto.id),
            search_set_uuid=auto.action_id,
            user_id=user.user_id,
            status="queued",
            document_uuids=all_doc_uuids,
            trigger_context={"callback_url": callback_url} if callback_url else {},
        )
        await ext_event.insert()

        activity = await activity_service.activity_start(
            type=ActivityType.SEARCH_SET_RUN,
            title=f"API: {auto.name}",
            user_id=user.user_id,
            search_set_uuid=auto.action_id,
        )

        # Dispatch extraction + output processing asynchronously via Celery
        from app.tasks.passive_tasks import process_extraction_outputs
        process_extraction_outputs.delay(
            automation_id=str(auto.id),
            search_set_uuid=auto.action_id,
            document_uuids=all_doc_uuids,
            user_id=user.user_id,
            extraction_event_id=str(ext_event.id),
        )

        trigger_event_id = str(ext_event.id)

        if wait:
            output = await _wait_for_extraction_event(trigger_event_id, timeout)
            if output is not None:
                return {
                    "status": "completed",
                    "trigger_event_id": trigger_event_id,
                    "activity_id": str(activity.id),
                    "action_type": "extraction",
                    "documents": all_doc_uuids,
                    "output": output,
                }
            return JSONResponse(
                status_code=202,
                content={
                    "status": "running",
                    "trigger_event_id": trigger_event_id,
                    "activity_id": str(activity.id),
                    "action_type": "extraction",
                    "documents": all_doc_uuids,
                    "output": None,
                    "message": f"Still running. Poll GET /api/automations/runs/{trigger_event_id} for results.",
                },
            )

        return {
            "status": "queued",
            "trigger_event_id": trigger_event_id,
            "activity_id": str(activity.id),
            "action_type": "extraction",
            "documents": all_doc_uuids,
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action type: {auto.action_type}")


# ---------------------------------------------------------------------------
# Sync-wait helpers
# ---------------------------------------------------------------------------


async def _wait_for_workflow_event(trigger_event_id: str, timeout: int):
    """Poll WorkflowTriggerEvent until completed/failed or timeout. Returns output or None."""
    oid = ObjectId(trigger_event_id)
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(2)
        elapsed += 2
        event = await WorkflowTriggerEvent.find_one({"_id": oid})
        if not event:
            return None
        if event.status == "completed" and event.workflow_result:
            result = await WorkflowResult.get(event.workflow_result)
            if result and result.final_output:
                return result.final_output.get("output")
            return {}
        if event.status == "failed":
            return None
    return None


async def _wait_for_extraction_event(trigger_event_id: str, timeout: int):
    """Poll ExtractionTriggerEvent until completed/failed or timeout. Returns output or None."""
    oid = ObjectId(trigger_event_id)
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(2)
        elapsed += 2
        event = await ExtractionTriggerEvent.find_one({"_id": oid})
        if not event:
            return None
        if event.status == "completed":
            return event.result
        if event.status == "failed":
            return None
    return None
