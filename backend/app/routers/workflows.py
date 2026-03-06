"""Workflow API routes."""

import asyncio
import base64
import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.dependencies import get_api_key_user, get_current_user
from app.models.user import User
from app.schemas.workflows import (
    AddStepRequest,
    AddTaskRequest,
    CreateTempDocumentsRequest,
    CreateWorkflowRequest,
    ReorderStepsRequest,
    RunWorkflowRequest,
    TestStepRequest,
    UpdateStepRequest,
    UpdateTaskRequest,
    UpdateValidationInputsRequest,
    UpdateValidationPlanRequest,
    UpdateWorkflowRequest,
    ValidateWorkflowResponse,
    ValidationInputsResponse,
    ValidationPlanResponse,
    WorkflowResponse,
    WorkflowStatusResponse,
)
from app.services import workflow_service as svc

router = APIRouter()


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=WorkflowResponse)
async def create_workflow(req: CreateWorkflowRequest, user: User = Depends(get_current_user)):
    wf = await svc.create_workflow(req.name, user.user_id, req.space, req.description)
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description,
        user_id=wf.user_id, space=wf.space, num_executions=wf.num_executions,
    )


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(space: str | None = None, user: User = Depends(get_current_user)):
    workflows = await svc.list_workflows(space=space)
    return [
        WorkflowResponse(
            id=str(wf.id), name=wf.name, description=wf.description,
            user_id=wf.user_id, space=wf.space, num_executions=wf.num_executions,
        )
        for wf in workflows
    ]


@router.get("/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(session_id: str, user: User = Depends(get_current_user)):
    status = await svc.get_workflow_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Workflow result not found")
    return WorkflowStatusResponse(**status)


@router.get("/status/stream")
async def stream_workflow_status(session_id: str, user: User = Depends(get_current_user)):
    """SSE endpoint that streams workflow status updates until completion."""

    async def event_generator():
        last_json = ""
        not_found_retries = 0
        while True:
            status = await svc.get_workflow_status(session_id)
            if not status:
                not_found_retries += 1
                # Allow a few retries for the workflow result to appear in the DB
                if not_found_retries > 10:
                    yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                    return
                await asyncio.sleep(1.0)
                continue

            current_json = json.dumps(status, default=str)
            # Only send if something changed
            if current_json != last_json:
                last_json = current_json
                yield f"data: {current_json}\n\n"

            if status.get("status") in ("completed", "error", "failed"):
                return

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/steps/test/{task_id}")
async def poll_step_test(task_id: str, user: User = Depends(get_current_user)):
    return svc.get_test_status(task_id)


@router.get("/download")
async def download_results(
    session_id: str,
    format: str = "json",
    user: User = Depends(get_current_user),
):
    """Download workflow results in specified format."""
    status = await svc.get_workflow_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Workflow result not found")

    final_output = status.get("final_output", {})
    output_data = final_output.get("output", "") if isinstance(final_output, dict) else final_output

    # Check for file_download type (e.g., from DataExport or DocumentRenderer)
    if isinstance(output_data, dict) and output_data.get("type") == "file_download":
        file_bytes = base64.b64decode(output_data["data_b64"])
        media_type_map = {"pdf": "application/pdf", "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "json": "application/json", "zip": "application/zip"}
        media_type = media_type_map.get(output_data.get("file_type", ""), "application/octet-stream")
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{output_data.get("filename", "output")}"'},
        )

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        if isinstance(output_data, list):
            if output_data and isinstance(output_data[0], dict):
                headers = list(output_data[0].keys())
                writer.writerow(headers)
                for row in output_data:
                    writer.writerow([row.get(h, "") for h in headers])
            else:
                writer.writerow(["Value"])
                for item in output_data:
                    writer.writerow([str(item)])
        elif isinstance(output_data, dict):
            writer.writerow(["Key", "Value"])
            for k, v in output_data.items():
                writer.writerow([k, str(v)])
        else:
            writer.writerow(["Output"])
            writer.writerow([str(output_data)])
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="results.csv"'},
        )

    # Default: JSON
    json_bytes = json.dumps(output_data, indent=2, default=str).encode()
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="results.json"'},
    )


@router.get("/{workflow_id}/export")
async def export_workflow(workflow_id: str, user: User = Depends(get_current_user)):
    """Download workflow definition as a shareable JSON file."""
    from app.services import export_import_service as eis

    try:
        data = await eis.export_workflow(workflow_id, user.email or user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    json_bytes = json.dumps(data, indent=2, default=str).encode()
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in (data["items"][0]["name"] or "workflow")).strip() or "workflow"
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.vandalizer.json"'},
    )


@router.post("/import")
async def import_workflow(
    file: UploadFile = File(...),
    space: str = Form("default"),
    user: User = Depends(get_current_user),
):
    """Import a workflow from an exported JSON file."""
    from app.services import export_import_service as eis

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    try:
        wf = await eis.import_workflow(data, user.user_id, space)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return WorkflowResponse(**wf)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, user: User = Depends(get_current_user)):
    wf = await svc.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(**wf)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: str, req: UpdateWorkflowRequest, user: User = Depends(get_current_user)):
    wf = await svc.update_workflow(workflow_id, name=req.name, description=req.description)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(
        id=str(wf.id), name=wf.name, description=wf.description,
        user_id=wf.user_id, space=wf.space, num_executions=wf.num_executions,
    )


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_workflow(workflow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"ok": True}


@router.post("/{workflow_id}/duplicate", response_model=WorkflowResponse)
async def duplicate_workflow(workflow_id: str, user: User = Depends(get_current_user)):
    wf = await svc.duplicate_workflow(workflow_id, user.user_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(**wf)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

@router.post("/{workflow_id}/steps")
async def add_step(workflow_id: str, req: AddStepRequest, user: User = Depends(get_current_user)):
    step = await svc.add_step(workflow_id, req.name, req.data, req.is_output)
    if not step:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return step


@router.patch("/steps/{step_id}")
async def update_step(step_id: str, req: UpdateStepRequest, user: User = Depends(get_current_user)):
    step = await svc.update_step(step_id, name=req.name, data=req.data, is_output=req.is_output)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    return step


@router.delete("/steps/{step_id}")
async def delete_step(step_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_step(step_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Step not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.post("/steps/{step_id}/tasks")
async def add_task(step_id: str, req: AddTaskRequest, user: User = Depends(get_current_user)):
    task = await svc.add_task(step_id, req.name, req.data)
    if not task:
        raise HTTPException(status_code=404, detail="Step not found")
    return task


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, req: UpdateTaskRequest, user: User = Depends(get_current_user)):
    task = await svc.update_task(task_id, name=req.name, data=req.data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: User = Depends(get_current_user)):
    ok = await svc.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, req: RunWorkflowRequest, user: User = Depends(get_current_user)):
    from app.models.activity import ActivityType
    from app.models.workflow import Workflow
    from app.services import activity_service
    from beanie import PydanticObjectId

    # Look up workflow name for activity title
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    initial_title = wf.name if wf else "Workflow Run"

    activity = await activity_service.activity_start(
        type=ActivityType.WORKFLOW_RUN,
        title=initial_title,
        user_id=user.user_id,
        team_id=str(user.current_team) if user.current_team else None,
        workflow=PydanticObjectId(workflow_id),
    )

    try:
        session_id = await svc.run_workflow(
            workflow_id, req.document_uuids, user.user_id, req.model,
            activity_id=str(activity.id),
        )
        return {"session_id": session_id, "activity_id": str(activity.id)}
    except ValueError as e:
        from app.models.activity import ActivityStatus
        await activity_service.activity_finish(activity.id, ActivityStatus.FAILED, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/steps/test")
async def test_step(req: TestStepRequest, user: User = Depends(get_current_user)):
    task_id = await svc.test_step(
        req.task_name, req.task_data, req.document_uuids, user.user_id, req.model
    )
    return {"task_id": task_id}


@router.post("/{workflow_id}/reorder-steps")
async def reorder_steps(workflow_id: str, req: ReorderStepsRequest, user: User = Depends(get_current_user)):
    ok = await svc.reorder_steps(workflow_id, req.step_ids)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid step IDs or workflow not found")
    return {"ok": True}


@router.get("/{workflow_id}/quality-history")
async def get_workflow_quality_history(
    workflow_id: str, limit: int = 50, user: User = Depends(get_current_user),
):
    from app.services.quality_service import get_quality_history
    return {"runs": await get_quality_history("workflow", workflow_id, limit)}


@router.get("/{workflow_id}/quality-sparkline")
async def get_workflow_quality_sparkline(
    workflow_id: str, limit: int = 10, user: User = Depends(get_current_user),
):
    """Return compact score history for sparkline visualization."""
    from app.services.quality_service import get_quality_history
    runs = await get_quality_history("workflow", workflow_id, limit)
    scores = [{"score": r["score"], "created_at": r["created_at"]} for r in reversed(runs)]
    return {"scores": scores}


@router.post("/{workflow_id}/improvement-suggestions")
async def get_workflow_suggestions(
    workflow_id: str, user: User = Depends(get_current_user),
):
    """Use LLM to suggest improvements based on the latest validation run."""
    from app.services.quality_service import get_latest_validation, generate_improvement_suggestions

    latest = await get_latest_validation("workflow", workflow_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No validation runs found for this workflow")
    result_snapshot = latest.get("result_snapshot", latest)
    suggestions = await generate_improvement_suggestions("workflow", workflow_id, result_snapshot)
    return {"suggestions": suggestions}


@router.get("/{workflow_id}/validation-plan", response_model=ValidationPlanResponse)
async def get_validation_plan(workflow_id: str, user: User = Depends(get_current_user)):
    try:
        checks = await svc.get_validation_plan(workflow_id)
        return ValidationPlanResponse(checks=checks)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{workflow_id}/validation-plan", response_model=ValidationPlanResponse)
async def update_validation_plan(
    workflow_id: str, req: UpdateValidationPlanRequest, user: User = Depends(get_current_user),
):
    try:
        checks = await svc.update_validation_plan(workflow_id, [c.model_dump() for c in req.checks])
        return ValidationPlanResponse(checks=checks)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{workflow_id}/validation-plan/generate", response_model=ValidationPlanResponse)
async def generate_validation_plan(workflow_id: str, user: User = Depends(get_current_user)):
    try:
        checks = await svc.generate_validation_plan(workflow_id)
        return ValidationPlanResponse(checks=checks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/validation-inputs", response_model=ValidationInputsResponse)
async def get_validation_inputs(workflow_id: str, user: User = Depends(get_current_user)):
    try:
        inputs = await svc.get_validation_inputs(workflow_id)
        return ValidationInputsResponse(inputs=inputs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{workflow_id}/validation-inputs", response_model=ValidationInputsResponse)
async def update_validation_inputs(
    workflow_id: str, req: UpdateValidationInputsRequest, user: User = Depends(get_current_user),
):
    try:
        inputs = await svc.update_validation_inputs(workflow_id, [i.model_dump() for i in req.inputs])
        return ValidationInputsResponse(inputs=inputs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{workflow_id}/create-temp-documents")
async def create_temp_documents(
    workflow_id: str, req: CreateTempDocumentsRequest, user: User = Depends(get_current_user),
):
    uuids = await svc.create_temp_documents_from_text(req.texts, user.user_id)
    return {"document_uuids": uuids}


@router.post("/{workflow_id}/validate", response_model=ValidateWorkflowResponse)
async def validate_workflow(workflow_id: str, user: User = Depends(get_current_user)):
    try:
        result = await svc.validate_workflow(workflow_id)
        return ValidateWorkflowResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# External API integration endpoints (x-api-key auth)
# ---------------------------------------------------------------------------


@router.post("/run-integrated")
async def run_workflow_integrated(
    workflow_id: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_api_key_user),
):
    """Run a workflow via external API with file uploads."""
    import uuid as _uuid
    from pathlib import Path
    from app.config import Settings
    from app.models.document import SmartDocument
    from app.tasks.upload_tasks import dispatch_upload_tasks
    from app.models.activity import ActivityType
    from app.services import activity_service

    settings = Settings()
    doc_uuids: list[str] = []

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
        doc_uuids.append(uid)

    if not doc_uuids:
        raise HTTPException(status_code=400, detail="No files provided")

    # Create activity
    activity = await activity_service.activity_start(
        type=ActivityType.WORKFLOW_RUN,
        title=f"API Workflow {workflow_id}",
        user_id=user.user_id,
    )

    try:
        session_id = await svc.run_workflow(
            workflow_id, doc_uuids, user.user_id,
        )
        return {
            "status": "queued",
            "activity_id": str(activity.id),
            "session_id": session_id,
        }
    except ValueError as e:
        from app.models.activity import ActivityStatus
        await activity_service.activity_finish(activity.id, ActivityStatus.FAILED, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))
