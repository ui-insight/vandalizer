"""Workflow CRUD service."""

from __future__ import annotations

import datetime
import logging
import re
import uuid as uuid_mod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from beanie import PydanticObjectId
from bson import ObjectId
from celery.result import AsyncResult

from app.celery_app import celery_app
from app.models.document import SmartDocument
from app.models.search_set import SearchSetItem
from app.models.workflow import (
    Workflow,
    WorkflowAttachment,
    WorkflowResult,
    WorkflowStep,
    WorkflowStepTask,
)
from app.services.access_control import (
    can_manage_workflow,
    get_authorized_document,
    get_authorized_workflow,
    get_team_access_context,
)
from app.services.config_service import get_user_model_name

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------


def _sanitize_for_json(value):
    """Recursively convert ObjectId → str so free-form dict fields serialize cleanly."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_for_json(v) for v in value)
    return value


async def create_workflow(name: str, user_id: str, description: str | None = None, team_id: str | None = None) -> Workflow:
    wf = Workflow(
        name=name,
        description=description,
        user_id=user_id,
        team_id=team_id,
        created_by_user_id=user_id,
    )
    await wf.insert()
    return wf


async def list_workflows(
    user: User,
    skip: int = 0,
    limit: int = 100,
    scope: str | None = None,
    search: str | None = None,
) -> list[Workflow]:
    # Scope queries to the user's current team (matches Library behavior)
    current_team = str(user.current_team) if user.current_team else None

    if scope == "mine":
        # User's own workflows within the current team
        query: dict = {"user_id": user.user_id}
        if current_team:
            query["team_id"] = {"$in": [current_team, None]}
    elif scope == "team":
        if not current_team:
            return []
        query = {"team_id": current_team, "user_id": {"$ne": user.user_id}}
    else:
        # Default: user's own (in current team) + all current team items
        if current_team:
            conditions: list[dict] = [
                {"user_id": user.user_id, "team_id": {"$in": [current_team, None]}},
                {"team_id": current_team},
            ]
            query = {"$or": conditions}
        else:
            query = {"user_id": user.user_id}

    # Add text search filter
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    return await Workflow.find(query).skip(skip).limit(limit).to_list()


async def get_workflow(
    workflow_id: str,
    user: User | None = None,
    share_token: str | None = None,
) -> dict | None:
    """Get workflow with dereferenced steps and tasks.

    If ``user`` lacks team/library access, a non-empty ``share_token`` that
    matches the workflow's stored token grants view-only access (manage=False).
    """
    if user is not None:
        wf = await get_authorized_workflow(workflow_id, user)
        if wf:
            team_access = await get_team_access_context(user)
            can_manage = can_manage_workflow(wf, user, team_access)
        elif share_token:
            try:
                wf = await Workflow.get(PydanticObjectId(workflow_id))
            except Exception:
                return None
            if not wf or not wf.share_token or wf.share_token != share_token:
                return None
            can_manage = False
        else:
            return None
    else:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
        if not wf:
            return None
        # Without a user (e.g. internal export), assume manage to preserve
        # existing behavior — callers that gate on this pass a user.
        can_manage = True

    steps = []
    for step_id in wf.steps:
        step = await WorkflowStep.get(step_id)
        if not step:
            continue
        tasks = []
        for task_id in step.tasks:
            task = await WorkflowStepTask.get(task_id)
            if task:
                tasks.append({
                    "id": str(task.id),
                    "name": task.name,
                    "data": _sanitize_for_json(task.data),
                })
        steps.append({
            "id": str(step.id),
            "name": step.name,
            "data": _sanitize_for_json(step.data),
            "is_output": step.is_output,
            "tasks": tasks,
        })

    return {
        "id": str(wf.id),
        "name": wf.name,
        "description": wf.description,
        "user_id": wf.user_id,
        "team_id": wf.team_id,
        "num_executions": wf.num_executions,
        "steps": steps,
        "input_config": _sanitize_for_json(wf.input_config),
        "output_config": _sanitize_for_json(wf.output_config),
        "validation_plan": _sanitize_for_json(wf.validation_plan),
        "validation_inputs": _sanitize_for_json(wf.validation_inputs),
        "can_manage": can_manage,
        "created_by_user_id": wf.created_by_user_id or wf.user_id,
    }


async def update_workflow(
    workflow_id: str,
    user: User,
    name: str | None = None,
    description: str | None = None,
    input_config: dict | None = None,
    output_config: dict | None = None,
) -> Workflow | None:
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        return None
    if name is not None:
        wf.name = name
    if description is not None:
        wf.description = description
    if input_config is not None:
        wf.input_config = input_config
    if output_config is not None:
        wf.output_config = output_config
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf


class WorkflowNotInTeam(Exception):
    """Raised when remove_workflow_from_team is called on a workflow with no team."""


async def remove_workflow_from_team(workflow_id: str, user: User) -> Workflow | None:
    """Unset ``team_id`` on a workflow so it no longer appears in the team library.

    The workflow itself is preserved — the creator (``user_id``) keeps access via
    their personal scope. Other team members lose access immediately because
    visibility joins on ``team_id``.

    Authorization mirrors ``can_manage_workflow``: only the creator or a team
    owner/admin can remove a workflow from its team. Returns the updated workflow,
    or ``None`` if the workflow doesn't exist or the caller isn't authorized.
    Raises ``WorkflowNotInTeam`` if the workflow has no team to remove from.
    """
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        return None
    if not wf.team_id:
        raise WorkflowNotInTeam("Workflow is not in a team")
    wf.team_id = None
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf


async def delete_workflow(workflow_id: str, user: User) -> bool:
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        return False
    # Delete steps and tasks
    for step_id in wf.steps:
        step = await WorkflowStep.get(step_id)
        if step:
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task:
                    await task.delete()
            await step.delete()
    for att_id in wf.attachments:
        att = await WorkflowAttachment.get(att_id)
        if att:
            await att.delete()
    await wf.delete()
    return True


async def duplicate_workflow(
    workflow_id: str,
    user: User,
    user_id: str,
    team_id: str | None = None,
    share_token: str | None = None,
) -> dict | None:
    # Authorize access to the original workflow before duplicating. A valid
    # share_token grants the recipient enough access to copy it into their
    # own workspace, since the share-link UX promises "anyone can use this".
    wf_check = await get_authorized_workflow(workflow_id, user)
    if not wf_check and share_token:
        try:
            wf_check = await Workflow.get(PydanticObjectId(workflow_id))
        except Exception:
            wf_check = None
        if not wf_check or not wf_check.share_token or wf_check.share_token != share_token:
            wf_check = None
    if not wf_check:
        return None

    original = await get_workflow(workflow_id)
    if not original:
        return None

    # Clone steps and tasks first so the workflow can be inserted in a
    # single write with all step references already populated.
    new_step_ids = []
    for step_data in original.get("steps", []):
        new_task_ids = []
        for task_data in step_data.get("tasks", []):
            new_task = WorkflowStepTask(name=task_data["name"], data=task_data.get("data", {}))
            await new_task.insert()
            new_task_ids.append(new_task.id)

        new_step = WorkflowStep(
            name=step_data["name"],
            tasks=new_task_ids,
            data=step_data.get("data", {}),
            is_output=step_data.get("is_output", False),
        )
        await new_step.insert()
        new_step_ids.append(new_step.id)

    # Copy validation plan and inputs from original
    original_wf = await Workflow.get(PydanticObjectId(workflow_id))
    validation_plan = []
    validation_inputs = []
    if original_wf:
        validation_plan = original_wf.validation_plan or []
        validation_inputs = original_wf.validation_inputs or []

    new_wf = Workflow(
        name=f"{original['name']} (Copy)",
        description=original.get("description"),
        user_id=user_id,
        team_id=team_id,
        created_by_user_id=user_id,
        steps=new_step_ids,
        validation_plan=validation_plan,
        validation_inputs=validation_inputs,
    )
    await new_wf.insert()

    return await get_workflow(str(new_wf.id))


# ---------------------------------------------------------------------------
# Authorization helpers for step / task lookups
# ---------------------------------------------------------------------------

async def _get_workflow_for_step(step_id: PydanticObjectId) -> Workflow | None:
    """Find the parent workflow that contains a given step."""
    return await Workflow.find_one(Workflow.steps == step_id)


async def _get_workflow_for_task(task_id: PydanticObjectId) -> Workflow | None:
    """Find the parent workflow that contains a given task (via its step)."""
    step = await WorkflowStep.find_one(WorkflowStep.tasks == task_id)
    if not step:
        return None
    return await Workflow.find_one(Workflow.steps == step.id)


# ---------------------------------------------------------------------------
# Step CRUD
# ---------------------------------------------------------------------------

async def add_step(workflow_id: str, name: str, user: User, data: dict = {}, is_output: bool = False) -> dict | None:
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        return None

    step = WorkflowStep(name=name, data=data, is_output=is_output)
    await step.insert()
    wf.steps.append(step.id)
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()

    return {"id": str(step.id), "name": step.name, "data": step.data, "is_output": step.is_output, "tasks": []}


async def update_step(step_id: str, user: User, name: str | None = None, data: dict | None = None, is_output: bool | None = None) -> dict | None:
    step = await WorkflowStep.get(PydanticObjectId(step_id))
    if not step:
        return None

    # Authorize via parent workflow
    parent_wf = await _get_workflow_for_step(step.id)
    if not parent_wf:
        return None
    from app.services.access_control import can_manage_workflow
    team_access = await get_team_access_context(user)
    if not can_manage_workflow(parent_wf, user, team_access):
        return None

    if name is not None:
        step.name = name
    if data is not None:
        step.data = data
    if is_output is not None:
        step.is_output = is_output
    await step.save()
    return {"id": str(step.id), "name": step.name, "data": step.data, "is_output": step.is_output}


async def delete_step(step_id: str, user: User) -> bool:
    step = await WorkflowStep.get(PydanticObjectId(step_id))
    if not step:
        return False

    # Authorize via parent workflow
    wf = await Workflow.find_one(Workflow.steps == step.id)
    if wf:
        from app.services.access_control import can_manage_workflow
        team_access = await get_team_access_context(user)
        if not can_manage_workflow(wf, user, team_access):
            return False
        wf.steps = [s for s in wf.steps if s != step.id]
        await wf.save()

    # Delete tasks
    for task_id in step.tasks:
        task = await WorkflowStepTask.get(task_id)
        if task:
            await task.delete()
    await step.delete()
    return True


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

async def add_task(step_id: str, name: str, user: User, data: dict = {}) -> dict | None:
    step = await WorkflowStep.get(PydanticObjectId(step_id))
    if not step:
        return None

    # Authorize via parent workflow
    parent_wf = await _get_workflow_for_step(step.id)
    if not parent_wf:
        return None
    from app.services.access_control import can_manage_workflow
    team_access = await get_team_access_context(user)
    if not can_manage_workflow(parent_wf, user, team_access):
        return None

    task = WorkflowStepTask(name=name, data=data)
    await task.insert()
    step.tasks.append(task.id)
    await step.save()

    return {"id": str(task.id), "name": task.name, "data": task.data}


async def update_task(task_id: str, user: User, name: str | None = None, data: dict | None = None) -> dict | None:
    task = await WorkflowStepTask.get(PydanticObjectId(task_id))
    if not task:
        return None

    # Authorize via parent workflow
    parent_wf = await _get_workflow_for_task(task.id)
    if not parent_wf:
        return None
    from app.services.access_control import can_manage_workflow
    team_access = await get_team_access_context(user)
    if not can_manage_workflow(parent_wf, user, team_access):
        return None

    if name is not None:
        task.name = name
    if data is not None:
        task.data = data
    await task.save()
    return {"id": str(task.id), "name": task.name, "data": task.data}


async def delete_task(task_id: str, user: User) -> bool:
    task = await WorkflowStepTask.get(PydanticObjectId(task_id))
    if not task:
        return False

    # Authorize via parent workflow
    parent_wf = await _get_workflow_for_task(task.id)
    if parent_wf:
        from app.services.access_control import can_manage_workflow
        team_access = await get_team_access_context(user)
        if not can_manage_workflow(parent_wf, user, team_access):
            return False

    # Remove from parent step
    step = await WorkflowStep.find_one(WorkflowStep.tasks == task.id)
    if step:
        step.tasks = [t for t in step.tasks if t != task.id]
        await step.save()
    await task.delete()
    return True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def run_workflow(
    workflow_id: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
    activity_id: str | None = None,
    user: User | None = None,
) -> str:
    """Start workflow execution. Returns session_id for polling."""
    if user is not None:
        wf = await get_authorized_workflow(workflow_id, user)
        if not wf:
            raise ValueError("Workflow not found")
        team_access = await get_team_access_context(user)
        authorized_document_uuids: list[str] = []
        for doc_uuid in document_uuids:
            document = await get_authorized_document(
                doc_uuid,
                user,
                team_access=team_access,
                allow_admin=True,
            )
            if not document:
                raise ValueError(f"Document not found: {doc_uuid}")
            authorized_document_uuids.append(document.uuid)
        document_uuids = authorized_document_uuids
    else:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
        if not wf:
            raise ValueError("Workflow not found")

    if not model:
        model = await get_user_model_name(user_id)

    session_id = str(uuid_mod.uuid4())[:8]
    # Generate the Celery task id up front so we can persist it before the task
    # is dispatched (no race where the task finishes before we record the id).
    # It is the handle the cancel endpoint uses to revoke/terminate the run.
    celery_task_id = str(uuid_mod.uuid4())

    result = WorkflowResult(
        workflow=wf.id,
        session_id=session_id,
        status="queued",
        num_steps_total=len(wf.steps),
        input_context={"doc_uuids": document_uuids},
        celery_task_id=celery_task_id,
    )
    await result.insert()

    trigger_step_data = {"doc_uuids": document_uuids}

    celery_app.send_task(
        "tasks.workflow_next.execution",
        kwargs={
            "workflow_result_id": str(result.id),
            "workflow_id": str(wf.id),
            "trigger_step_data": trigger_step_data,
            "model": model,
            "activity_id": activity_id,
        },
        queue="workflows",
        task_id=celery_task_id,
    )

    return session_id


async def _get_authorized_workflow_result(
    session_id: str,
    user: User,
) -> WorkflowResult | None:
    result = await WorkflowResult.find_one(WorkflowResult.session_id == session_id)
    if not result or not result.workflow:
        return None

    # Use the library-aware authorizer so users can poll status for verified
    # workflows they launched from the library but don't own / aren't on the team for.
    workflow = await get_authorized_workflow(str(result.workflow), user)
    if not workflow:
        return None

    return result


async def get_workflow_status(session_id: str, user: User | None = None) -> dict | None:
    if user is not None:
        result = await _get_authorized_workflow_result(session_id, user)
    else:
        result = await WorkflowResult.find_one(WorkflowResult.session_id == session_id)
    if not result:
        return None
    workflow_name: str | None = None
    if result.workflow:
        wf = await Workflow.get(result.workflow)
        if wf:
            workflow_name = wf.name
    return {
        "status": result.status,
        "num_steps_completed": result.num_steps_completed,
        "num_steps_total": result.num_steps_total,
        "current_step_name": result.current_step_name,
        "current_step_detail": result.current_step_detail,
        "current_step_preview": result.current_step_preview,
        "final_output": result.final_output,
        "steps_output": result.steps_output,
        "output_step_names": result.output_step_names,
        "approval_request_id": result.approval_request_id,
        "error": result.error,
        "error_payload": result.error_payload,
        "retrieved_sources": result.retrieved_sources,
        "workflow_name": workflow_name,
        "document_title": result.document_title,
    }


async def cancel_workflow(session_id: str, user: User) -> dict | None:
    """Cancel an in-flight workflow run.

    Flips the result to ``canceled`` (which the engine's between-steps check and
    the frontend poller both treat as terminal) and revokes the Celery task with
    ``terminate=True`` so a step that is mid-LLM-call is interrupted rather than
    running to completion. Idempotent: a run that already reached a terminal
    state is returned unchanged. Returns ``None`` when the run is not found or
    the user is not authorized for it.
    """
    result = await _get_authorized_workflow_result(session_id, user)
    if not result:
        return None

    terminal = {"completed", "error", "failed", "canceled"}
    if result.status in terminal:
        return {"session_id": session_id, "status": result.status}

    # Set the terminal state first so the UI reflects the stop immediately and
    # the engine's cooperative check (if it happens to be between steps) bails.
    result.status = "canceled"
    result.error = "Canceled by user"
    await result.save()

    # Interrupt the worker. revoke(terminate=True) kills the prefork child
    # running this task id; if the task is still queued it is dropped before it
    # starts. Best-effort — the DB flip above is the source of truth for the UI.
    if result.celery_task_id:
        try:
            celery_app.control.revoke(
                result.celery_task_id, terminate=True, signal="SIGTERM",
            )
        except Exception:
            logger.warning(
                "Failed to revoke Celery task %s for session %s",
                result.celery_task_id, session_id, exc_info=True,
            )

    # Best-effort: mark the matching activity-rail entry canceled too, so the
    # run doesn't linger as "running" in the activity feed.
    try:
        from app.models.activity import ActivityEvent, ActivityStatus

        act = await ActivityEvent.find_one(
            ActivityEvent.workflow_session_id == session_id,
        )
        if act and act.is_running:
            act.status = ActivityStatus.CANCELED.value
            act.error = "Canceled by user"
            act.finished_at = datetime.datetime.now(datetime.timezone.utc)
            await act.save()
    except Exception:
        logger.warning(
            "Failed to mark activity canceled for session %s",
            session_id, exc_info=True,
        )

    return {"session_id": session_id, "status": result.status}


async def run_workflow_batch(
    workflow_id: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
    activity_id: str | None = None,
    user: User | None = None,
) -> str:
    """Start a batched workflow execution — one run per document.

    Returns a ``batch_id`` that can be polled via ``get_batch_status``.
    """
    if user is not None:
        wf = await get_authorized_workflow(workflow_id, user)
        if not wf:
            raise ValueError("Workflow not found")
        team_access = await get_team_access_context(user)
        authorized_document_uuids: list[str] = []
        for doc_uuid in document_uuids:
            document = await get_authorized_document(
                doc_uuid,
                user,
                team_access=team_access,
                allow_admin=True,
            )
            if not document:
                raise ValueError(f"Document not found: {doc_uuid}")
            authorized_document_uuids.append(document.uuid)
        document_uuids = authorized_document_uuids
    else:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
        if not wf:
            raise ValueError("Workflow not found")

    if not model:
        model = await get_user_model_name(user_id)

    batch_id = str(uuid_mod.uuid4())[:8]

    for doc_uuid in document_uuids:
        # Look up title for display
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        doc_title = doc.title if doc else doc_uuid

        session_id = str(uuid_mod.uuid4())[:8]

        result = WorkflowResult(
            workflow=wf.id,
            session_id=session_id,
            status="queued",
            num_steps_total=len(wf.steps),
            batch_id=batch_id,
            document_title=doc_title,
        )
        await result.insert()

        trigger_step_data = {"doc_uuids": [doc_uuid]}

        celery_app.send_task(
            "tasks.workflow_next.execution",
            kwargs={
                "workflow_result_id": str(result.id),
                "workflow_id": str(wf.id),
                "trigger_step_data": trigger_step_data,
                "model": model,
                "activity_id": activity_id,
            },
            queue="workflows",
        )

    return batch_id


async def get_batch_status(batch_id: str, user: User | None = None) -> dict | None:
    """Return aggregated status for a batch run."""
    results = await WorkflowResult.find(
        WorkflowResult.batch_id == batch_id,
    ).to_list()

    if not results:
        return None

    if user is not None:
        first = results[0]
        if not first.workflow:
            return None
        # Library-aware: also allows batch status polling for verified workflows
        # launched from the library (matches /run authorization).
        workflow = await get_authorized_workflow(str(first.workflow), user)
        if not workflow:
            return None

    total = len(results)
    completed = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status in ("error", "failed"))
    running = sum(1 for r in results if r.status in ("running", "queued"))

    if running > 0:
        overall_status = "running"
    elif failed == total:
        overall_status = "failed"
    elif completed + failed == total:
        overall_status = "completed"
    else:
        overall_status = "running"

    items = []
    for r in results:
        items.append({
            "session_id": r.session_id,
            "document_title": r.document_title,
            "status": r.status,
            "num_steps_completed": r.num_steps_completed,
            "num_steps_total": r.num_steps_total,
            "current_step_name": r.current_step_name,
            "final_output": r.final_output,
        })

    return {
        "status": overall_status,
        "total": total,
        "completed": completed,
        "failed": failed,
        "items": items,
    }


async def test_step(task_name: str, task_data: dict, document_uuids: list[str], user_id: str, model: str | None = None) -> str:
    """Test a single step. Returns Celery task_id for polling."""
    if not model:
        model = await get_user_model_name(user_id)

    task_data["model"] = model
    task_data["user_id"] = user_id

    # Resolve extraction keys if needed
    if task_name == "Extraction" and task_data.get("search_set_uuid"):
        items = await SearchSetItem.find(
            SearchSetItem.searchset == task_data["search_set_uuid"],
            SearchSetItem.searchtype == "extraction",
        ).to_list()
        task_data["keys"] = [item.searchphrase for item in items]

    result = celery_app.send_task(
        "tasks.workflow_next.execution_step_test",
        kwargs={
            "task_name": task_name,
            "task_data": task_data,
            "doc_uuids": document_uuids,
        },
        queue="workflows",
    )
    return result.id


def get_test_status(task_id: str) -> dict:
    """Poll a step test Celery task."""
    result = AsyncResult(task_id, app=celery_app)
    if not result.ready():
        return {"status": result.state}
    if result.successful():
        return {"status": "completed", "result": result.result}
    payload = result.result
    if isinstance(payload, BaseException):
        error_text = f"{type(payload).__name__}: {payload}"
    else:
        error_text = str(payload) if payload else "Test failed"
    return {"status": "failed", "error": error_text}


# ---------------------------------------------------------------------------
# Step reordering
# ---------------------------------------------------------------------------

async def reorder_steps(workflow_id: str, step_ids: list[str], user: User) -> bool:
    """Reorder steps in a workflow by providing the full ordered list of step IDs."""
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        return False

    # Validate that all provided step_ids belong to this workflow
    existing_ids = {str(s) for s in wf.steps}
    provided_ids = set(step_ids)
    if existing_ids != provided_ids:
        return False

    wf.steps = [PydanticObjectId(sid) for sid in step_ids]
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return True


# ---------------------------------------------------------------------------
# Validation Plan
# ---------------------------------------------------------------------------

def compute_workflow_definition_hash(wf_data: dict | None) -> str:
    """Deterministic hash of the parts of a workflow that a validation plan depends on.

    Covers step names (checks' target_step references them), task names and
    data (prompts, extraction field definitions), is_output, and output_config.
    Deliberately excludes ids, the validation plan itself, validation inputs,
    metadata, and optimizer config_override (revertible runtime config, not
    authored definition).
    """
    from app.services.quality_service import compute_config_hash

    canonical = {
        "steps": [
            {
                "name": s.get("name", ""),
                "is_output": bool(s.get("is_output", False)),
                "tasks": [
                    {"name": t.get("name", ""), "data": t.get("data", {})}
                    for t in s.get("tasks", [])
                ],
            }
            for s in (wf_data or {}).get("steps", [])
        ],
        "output_config": (wf_data or {}).get("output_config", {}),
    }
    return compute_config_hash(canonical)


def _plan_staleness(
    plan: list[dict],
    stored_hash: str | None,
    wf_data: dict | None,
) -> tuple[bool, list[str], list[str]]:
    """Return (plan_stale, stale_reasons, orphaned_check_ids) for *plan*.

    Two independent signals:
    - "definition_changed": the stored definition hash no longer matches the
      current workflow definition (only computable when a hash was stamped).
    - "orphaned_checks": a check's target_step matches no current step name —
      catches plans that went stale before hash stamping existed.
    """
    if not plan:
        return False, [], []

    step_names = {
        str(s.get("name", "")).strip().lower()
        for s in (wf_data or {}).get("steps", [])
    }
    orphaned = [
        str(c.get("id", ""))
        for c in plan
        if str(c.get("target_step", "") or "").strip()
        and str(c["target_step"]).strip().lower() not in step_names
    ]

    reasons: list[str] = []
    if orphaned:
        reasons.append("orphaned_checks")
    if stored_hash and stored_hash != compute_workflow_definition_hash(wf_data):
        reasons.append("definition_changed")
    return bool(reasons), reasons, orphaned


async def get_validation_plan(workflow_id: str, user: User) -> dict:
    """Return the workflow's persisted validation plan plus staleness info."""
    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")

    plan = wf.validation_plan
    wf_data = await get_workflow(workflow_id)
    stale, reasons, orphaned = _plan_staleness(
        plan, wf.validation_plan_definition_hash, wf_data,
    )

    # Lazy bless: plans written before hash stamping existed have no stored
    # hash, so definition drift is undetectable. If the structural signal is
    # also clean (no orphaned checks), stamp the current definition so future
    # edits are detected. Deliberately does not bump updated_at — this is a
    # read, not an authored change.
    if plan and not wf.validation_plan_definition_hash and not orphaned:
        wf.validation_plan_definition_hash = compute_workflow_definition_hash(wf_data)
        await wf.save()

    return {
        "checks": plan,
        "plan_stale": stale,
        "stale_reasons": reasons,
        "orphaned_check_ids": orphaned,
    }


async def update_validation_plan(workflow_id: str, checks: list[dict], user: User) -> list[dict]:
    """Replace the workflow's validation plan with *checks*.

    A manual plan save means the user is looking at the current workflow, so
    it also re-stamps the definition hash (blessing the current definition).
    """
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        raise ValueError("Workflow not found")
    wf_data = await get_workflow(workflow_id)
    wf.validation_plan = checks
    wf.validation_plan_definition_hash = compute_workflow_definition_hash(wf_data)
    wf.validation_plan_updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf.validation_plan


# ---------------------------------------------------------------------------
# Validation report (downloadable)
# ---------------------------------------------------------------------------

def _slugify_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "workflow").strip()).strip("-").lower()
    return slug or "workflow"


def _format_validation_report(
    *,
    workflow_name: str,
    workflow_id: str,
    plan: list[dict],
    snapshot: dict,
    grade: str | None,
    score: float,
    checks_passed: int,
    checks_failed: int,
    generated_at: str,
    fmt: str,
) -> tuple[str, str, str]:
    """Render a downloadable validation report from a persisted run snapshot.

    Pure function (no I/O) so it is unit-testable. Returns
    (filename, content, media_type). fmt is 'md' (default) or 'json'.
    """
    import json as _json

    cat_lookup: dict[str, str] = {}
    for c in plan or []:
        cid = c.get("id") or c.get("check_id")
        if cid:
            cat_lookup[str(cid)] = c.get("category") or c.get("check_type") or "content"

    checks = snapshot.get("checks", []) or []
    num_checks = snapshot.get("num_checks", len(checks))
    slug = _slugify_filename(workflow_name)

    if fmt == "json":
        report = {
            "workflow": workflow_name,
            "workflow_id": workflow_id,
            "generated_at": generated_at,
            "grade": grade,
            "score": score,
            "summary": snapshot.get("summary"),
            "num_runs": snapshot.get("num_runs"),
            "num_checks": num_checks,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "stability_score": snapshot.get("stability_score"),
            "checks": [
                {
                    "name": c.get("name"),
                    "category": cat_lookup.get(str(c.get("check_id", "")), None),
                    "status": c.get("status"),
                    "detail": c.get("detail"),
                    "consistency": c.get("consistency"),
                    "run_statuses": c.get("run_statuses"),
                }
                for c in checks
            ],
            "stability_detail": snapshot.get("stability_detail"),
            "output_comparison": snapshot.get("output_comparison"),
        }
        return (
            f"{slug}-validation-report.json",
            _json.dumps(report, indent=2, default=str),
            "application/json",
        )

    # Markdown (default)
    try:
        score_str = str(round(float(score)))
    except (TypeError, ValueError):
        score_str = "?"

    lines = [
        f"# Validation Report — {workflow_name}",
        "",
        f"- **Generated:** {generated_at or 'unknown'}",
        f"- **Grade:** {grade or '?'} (score {score_str}/100)",
    ]
    if snapshot.get("summary"):
        lines.append(f"- **Summary:** {snapshot['summary']}")
    lines.append(f"- **Checks:** {checks_passed} passed / {checks_failed} failed of {num_checks}")
    if snapshot.get("num_runs"):
        lines.append(f"- **Runs evaluated:** {snapshot['num_runs']}")
    if snapshot.get("stability_score") is not None:
        try:
            lines.append(f"- **Output stability:** {round(float(snapshot['stability_score']))}%")
        except (TypeError, ValueError):
            pass
    lines += ["", "## Check Results", ""]

    if not checks:
        lines.append("_No check results recorded._")
    for c in checks:
        cat = cat_lookup.get(str(c.get("check_id", "")), "")
        cat_str = f" — _{cat}_" if cat else ""
        lines.append(f"### [{c.get('status', '?')}] {c.get('name', '(unnamed check)')}{cat_str}")
        detail = (c.get("detail") or "").strip()
        lines.append(detail if detail else "_No detail provided._")
        run_statuses = c.get("run_statuses") or []
        if len(set(run_statuses)) > 1:
            lines.append("")
            lines.append(f"_Per-run: {', '.join(str(s) for s in run_statuses)}_")
        lines.append("")

    lines += [
        "---",
        "_Generated by Vandalizer — for the RA's internal quality review, not for sponsor submission._",
        "",
    ]
    return (f"{slug}-validation-report.md", "\n".join(lines), "text/markdown; charset=utf-8")


async def build_validation_report(workflow_id: str, fmt: str, user: User) -> tuple[str, str, str]:
    """Fetch the latest persisted validation run and render a downloadable
    report. Returns (filename, content, media_type). Raises ValueError when the
    workflow is unknown or has no validation runs yet."""
    from app.services.quality_service import get_latest_validation_run

    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")
    run = await get_latest_validation_run("workflow", workflow_id)
    if not run:
        raise ValueError("No validation runs yet — run Validate first.")

    return _format_validation_report(
        workflow_name=wf.name or "Workflow",
        workflow_id=workflow_id,
        plan=wf.validation_plan or [],
        snapshot=run.result_snapshot or {},
        grade=run.grade,
        score=run.score,
        checks_passed=run.checks_passed,
        checks_failed=run.checks_failed,
        generated_at=run.created_at.isoformat() if run.created_at else "",
        fmt=fmt,
    )


# ---------------------------------------------------------------------------
# Validation Inputs
# ---------------------------------------------------------------------------

async def get_validation_inputs(workflow_id: str, user: User) -> list[dict]:
    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")
    return wf.validation_inputs


async def update_validation_inputs(workflow_id: str, inputs: list[dict], user: User) -> list[dict]:
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        raise ValueError("Workflow not found")
    wf.validation_inputs = inputs
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf.validation_inputs


async def create_temp_documents_from_text(texts: list[dict], user_id: str) -> list[str]:
    """Create temporary SmartDocument records with raw_text pre-filled.

    Each entry in *texts* should have ``text`` and optionally ``label``.
    Returns the list of generated UUIDs.
    """
    from app.models.document import SmartDocument

    uuids: list[str] = []
    for entry in texts:
        uid = uuid_mod.uuid4().hex.upper()
        label = entry.get("label") or "Validation text input"
        doc = SmartDocument(
            title=label,
            processing=False,
            valid=True,
            raw_text=entry.get("text", ""),
            path="",
            downloadpath="",
            extension="txt",
            uuid=uid,
            user_id=user_id,
            folder="0",
        )
        await doc.insert()
        uuids.append(uid)
    return uuids


# ---------------------------------------------------------------------------
# Expected Output (ground-truth storage for deterministic validation)
# ---------------------------------------------------------------------------

async def save_expected_output(
    workflow_id: str,
    session_id: str,
    user: User,
    label: str | None = None,
) -> dict:
    """Mark a completed workflow execution as the 'expected output' for validation.

    This is the workflow equivalent of extraction test cases — it stores
    ground truth that future validations can compare against deterministically.
    """
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        raise ValueError("Workflow not found")

    # Find the specified WorkflowResult
    wr = await WorkflowResult.find_one(
        WorkflowResult.session_id == session_id,
        WorkflowResult.workflow == wf.id,
        WorkflowResult.status == "completed",
    )
    if not wr:
        raise ValueError("Completed workflow result not found for this session")

    output_text = _serialize_output(wr.final_output)
    if output_text is None:
        raise ValueError("Binary outputs cannot be saved as expected output")

    # Store as a validation input with expected output
    expected_entry = {
        "id": str(uuid_mod.uuid4()),
        "type": "expected_output",
        "session_id": session_id,
        "label": label or f"Expected output from {session_id[:8]}",
        "output_text": output_text[:50_000],
        "output_snapshot": wr.final_output,
        "steps_output_snapshot": wr.steps_output,
    }

    # Append to validation_inputs
    wf.validation_inputs = [
        inp for inp in wf.validation_inputs
        if inp.get("type") != "expected_output" or inp.get("session_id") != session_id
    ]
    wf.validation_inputs.append(expected_entry)
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()

    return expected_entry


async def get_expected_outputs(workflow_id: str, user: User) -> list[dict]:
    """Return all stored expected outputs for a workflow."""
    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")
    return [inp for inp in wf.validation_inputs if inp.get("type") == "expected_output"]


async def delete_expected_output(workflow_id: str, expected_id: str, user: User) -> bool:
    """Remove a stored expected output."""
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        return False
    before = len(wf.validation_inputs)
    wf.validation_inputs = [
        inp for inp in wf.validation_inputs if inp.get("id") != expected_id
    ]
    if len(wf.validation_inputs) == before:
        return False
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return True


async def _extract_workflow_intents(wf_data: dict) -> list[str]:
    """Stage-1 of plan generation: enumerate end-user intents from name + description only.

    Deliberately excludes step config — the goal is to capture what a consumer
    of the output expects, not what the current implementation happens to
    produce. Returns a fallback intent list when name/description are too thin
    or the LLM fails (better than blocking plan generation entirely).
    """
    from app.services.llm_service import create_chat_agent
    from app.models.system_config import SystemConfig

    name = (wf_data.get("name") or "").strip()
    desc = (wf_data.get("description") or "").strip()
    user_id = wf_data.get("user_id") or ""

    # Fallback when there's nothing to reason about — emit a generic intent so
    # stage 2 still has something to anchor on.
    if not name and not desc:
        return [
            "The output should be coherent, complete, and faithfully derived from the input.",
            "Any extracted or computed values should appear in the final output.",
        ]

    intent_system_prompt = (
        "You are reasoning about what a consumer of an automated workflow's output expects "
        "from it — independent of how the workflow happens to produce that output today.\n\n"
        "Given ONLY a workflow's name and description, enumerate 3-6 concrete intents an "
        "end-user has when they read this workflow's output. Each intent should be:\n"
        "- USER-FACING: phrased as what the reader of the output expects\n"
        "- CONCRETE: name the kind of content, format, or fact that should be present\n"
        "- IMPLEMENTATION-INDEPENDENT: don't mention specific steps, fields, or models — "
        "those describe the current implementation, not the user's expectation\n\n"
        "Return ONLY a JSON object: {\"intents\": [\"intent 1\", \"intent 2\", ...]}. "
        "No markdown, no extra text."
    )

    user_prompt = (
        f"Workflow name: {name or '(unnamed)'}\n"
        f"Description: {desc or '(no description)'}\n\n"
        "Enumerate what an end-user expects from this output."
    )

    try:
        model = await get_user_model_name(user_id)
        sys_config = await SystemConfig.get_config()
        sys_config_doc = sys_config.model_dump() if sys_config else {}
        agent = create_chat_agent(
            model, system_prompt=intent_system_prompt, system_config_doc=sys_config_doc,
        )
        result = await agent.run(user_prompt)
    except Exception as e:
        logger.warning("Intent extraction LLM call failed: %s — using fallback intents", e)
        return _fallback_intents(name, desc)

    raw = _parse_json_object(result.output or "")
    if not raw or "intents" not in raw:
        return _fallback_intents(name, desc)

    items = raw.get("intents") or []
    if not isinstance(items, list):
        return _fallback_intents(name, desc)

    cleaned = [str(x).strip() for x in items if isinstance(x, (str, int, float)) and str(x).strip()]
    return cleaned[:6] if cleaned else _fallback_intents(name, desc)


def _fallback_intents(name: str, desc: str) -> list[str]:
    """Deterministic fallback when the intent extractor can't run.

    Keeps stage-2 anchored on *something* user-facing instead of letting it
    silently revert to "checks what the workflow already does."
    """
    parts: list[str] = []
    if name:
        parts.append(f"The output should fulfill the stated task: \"{name}\".")
    if desc:
        parts.append(f"The output should match the described purpose: \"{desc[:200]}\".")
    parts.append("All claims in the output should be grounded in the input — no hallucination.")
    parts.append("The output should be complete: nothing the description promises is missing.")
    return parts


def _parse_json_object(text: str) -> dict | None:
    """Best-effort JSON object extraction. Mirrors the helper in the test-case
    generator service; kept inline so this module stays self-contained."""
    import json as _json

    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```\w*\n?", "", stripped)
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

    try:
        parsed = _json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except _json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            parsed = _json.loads(stripped[start:end])
            if isinstance(parsed, dict):
                return parsed
        except _json.JSONDecodeError:
            pass
    return None


async def generate_validation_plan(workflow_id: str, user: User) -> list[dict]:
    """Use an LLM to auto-generate quality check definitions from the workflow structure."""
    from app.services.llm_service import create_chat_agent
    from app.models.system_config import SystemConfig

    # Authorize before proceeding (manage=True since this modifies the plan)
    wf_check = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf_check:
        raise ValueError("Workflow not found")

    wf_data = await get_workflow(workflow_id)
    if not wf_data:
        raise ValueError("Workflow not found")

    # Build a data-flow-aware analysis of the workflow for the LLM.
    # For each step, describe what it does, what data it produces, and what
    # the next step receives — so the LLM can reason about what must appear
    # in the final output.
    steps = wf_data.get("steps", [])
    all_extracted_fields: list[dict] = []  # accumulate across all extraction steps
    step_analyses = []
    for idx, step in enumerate(steps):
        is_output = step.get("is_output", False)
        is_last = idx == len(steps) - 1
        step_desc_parts = [f"### Step {idx + 1}: {step['name']}"]
        if is_output or is_last:
            step_desc_parts[0] += "  [FINAL OUTPUT STEP]"

        for task in step.get("tasks", []):
            data = task.get("data", {})
            task_name = task["name"]

            if task_name == "Extraction":
                extractions = data.get("extractions", [])
                fields_detail = []
                for ext in extractions[:30]:
                    if isinstance(ext, str):
                        field_info = {"key": ext.strip()}
                    else:
                        key = ext.get("key", "")
                        desc = ext.get("description", "")
                        is_optional = ext.get("is_optional", False)
                        enum_vals = ext.get("enum_values", [])
                        field_info = {"key": key, "description": desc}
                        if is_optional:
                            field_info["optional"] = True
                        if enum_vals:
                            field_info["allowed_values"] = enum_vals
                    fields_detail.append(field_info)
                    all_extracted_fields.append(field_info)

                step_desc_parts.append(
                    "**Extraction task** — extracts the following fields from the input:\n"
                    + "\n".join(
                        f"  - `{f['key']}`"
                        + (f": {f['description']}" if f.get('description') else "")
                        + (" (optional)" if f.get('optional') else "")
                        + (f" [allowed: {', '.join(f['allowed_values'])}]" if f.get('allowed_values') else "")
                        for f in fields_detail
                    )
                )
                step_desc_parts.append(
                    f"This step PRODUCES a structured object with these {len(fields_detail)} fields."
                )

            elif task_name == "Prompt":
                prompt_text = data.get("prompt", "")
                # Include the full prompt (up to 2000 chars) so the LLM can understand
                # what transformation is being applied
                truncated = prompt_text[:2000]
                if len(prompt_text) > 2000:
                    truncated += "..."
                step_desc_parts.append(
                    f"**Prompt task** — sends the previous step's output to an LLM with this instruction:\n"
                    f'"{truncated}"'
                )
                step_desc_parts.append(
                    "This step PRODUCES free-form text shaped by the prompt instruction."
                )

            elif task_name == "Formatter":
                format_template = data.get("format_template") or data.get("prompt", "")
                truncated = format_template[:2000]
                if len(format_template) > 2000:
                    truncated += "..."
                step_desc_parts.append(
                    f"**Formatter task** — reformats the previous step's output using this template/instruction:\n"
                    f'"{truncated}"'
                )
                step_desc_parts.append(
                    "This step PRODUCES reformatted text according to the template."
                )

            elif task_name == "DataExport":
                fmt = data.get("format", "json")
                step_desc_parts.append(
                    f"**Data Export task** — exports the data in `{fmt}` format."
                )
                step_desc_parts.append(
                    f"This step PRODUCES a {fmt.upper()} file/text as output."
                )

            elif task_name == "DocumentRenderer":
                tpl = data.get("template_type", "")
                step_desc_parts.append(
                    f"**Document Renderer task** — renders output using template: `{tpl}`."
                )

            elif task_name == "AddWebsite":
                url = data.get("url", "")
                step_desc_parts.append(
                    f"**Website task** — fetches content from `{url}` and passes text to next step."
                )

            elif task_name == "AddDocument":
                step_desc_parts.append(
                    "**Add Document task** — loads document text into the pipeline."
                )

            elif task_name == "CodeExecution":
                step_desc_parts.append(
                    "**Code Execution task** — runs custom code on the data."
                )

            else:
                step_desc_parts.append(f"**{task_name} task**")

        if idx < len(steps) - 1:
            next_step = steps[idx + 1]
            step_desc_parts.append(
                f"\n→ Output flows to Step {idx + 2}: {next_step['name']}"
            )

        step_analyses.append("\n".join(step_desc_parts))

    # Build the data flow summary
    data_flow_section = ""
    if all_extracted_fields:
        field_names = [f['key'] for f in all_extracted_fields]
        data_flow_section = (
            "\n\n## Data That Must Survive to Final Output\n"
            f"The workflow extracts these specific data points: {', '.join(f'`{n}`' for n in field_names)}.\n"
            "Each of these extracted values should be present (or clearly represented) "
            "in the final output unless a downstream step explicitly filters them out."
        )

    workflow_desc = (
        f"## Workflow: {wf_data.get('name', 'Unnamed')}\n"
        f"**Description**: {wf_data.get('description', 'No description')}\n"
        f"**Number of steps**: {len(steps)}\n\n"
        "## Step-by-Step Data Flow\n\n"
        + "\n\n".join(step_analyses)
        + data_flow_section
    )

    # ── Stage 1: intent extraction ──
    # Read ONLY name + description. The point is to capture what an end-user
    # expects from the output, independent of how the current implementation
    # tries to produce it. Without this separation, the model anchors on
    # "checks the workflow's existing fields appear" — which means a broken
    # workflow that outputs the same wrong shape every time would pass.
    intents = await _extract_workflow_intents(wf_data)

    # ── Stage 2: check drafting from intents + step structure ──
    # Step structure is provided as context (so target_step can be mapped) but
    # the intent list — not the step config — is the basis for what to check.
    model = await get_user_model_name(wf_data.get("user_id", ""))

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    system_prompt = (
        "You are a workflow output quality analyst. Generate validation checks that will be "
        "evaluated against the ACTUAL OUTPUT of a workflow.\n\n"
        "You will be given:\n"
        "1. A list of END-USER INTENTS — what someone consuming this workflow's output "
        "actually expects, derived independently of the workflow's implementation.\n"
        "2. A data-flow analysis — used to map each check to its responsible step, "
        "NOT as the basis for what to check.\n\n"
        "Generate 4-8 quality check DEFINITIONS, each grounded in one or more INTENTS. "
        "Each check must be verifiable by reading the workflow's output text.\n\n"
        "Categories:\n"
        "- **completeness**: every named field / data point the intent calls for is present.\n"
        "- **accuracy**: values are faithfully grounded in the source — no hallucination, "
        "no internal contradictions.\n"
        "- **content**: the output serves the intent's stated purpose (e.g. 'a human-readable "
        "summary' really reads like one).\n"
        "- **formatting**: the output matches the format the intent calls for.\n\n"
        "DO NOT generate checks about:\n"
        "- The workflow definition's structure (YAML, step headers)\n"
        "- Step naming conventions\n"
        "- Whether the workflow has a name/description\n\n"
        "Anchor each check to an intent. A good check description names the specific intent "
        "it serves AND the fields/values an evaluator would need to look for in the output. "
        "A bad check restates a step's role (\"checks Extraction step ran\").\n\n"
        "Return ONLY a JSON array of check definition objects. Each must have:\n"
        '- "name": short check name (string, max 60 chars)\n'
        '- "description": detailed description naming the intent + what to look for (string)\n'
        '- "category": one of "completeness", "formatting", "content", "accuracy" (string)\n'
        '- "target_step": EXACT name of the step this check covers — pick from the step '
        "headers in the data-flow analysis. Use the final step name for whole-output checks. "
        "NEVER omit (string).\n\n"
        "Return ONLY the JSON array, no other text."
    )

    intents_block = (
        "## End-User Intents (what consumers of this output actually expect)\n"
        + "\n".join(f"- {i}" for i in intents)
    )

    agent = create_chat_agent(
        model,
        system_prompt=system_prompt,
        system_config_doc=sys_config_doc,
    )

    try:
        from app.services.metering import metered_async
        async with metered_async("validation", user_id=wf_data.get("user_id")):
            result = await agent.run(
                f"{intents_block}\n\n## Workflow (data-flow context for target_step)\n{workflow_desc}"
            )
    except Exception:
        raise ValueError("LLM call failed - could not generate validation plan")

    parsed = _parse_json_array(result.output)
    if parsed is None:
        raise ValueError("Could not parse LLM response into a validation plan")

    # Normalize into check definitions with UUIDs.
    # target_step is normalized against the workflow's actual step names so a
    # typo or paraphrase in the LLM output still produces a valid breakdown
    # bucket — we fall back to the final step (the most useful default for
    # output-shape checks) rather than "Unassigned", which suppresses the
    # step_breakdown diagnostic downstream.
    actual_step_names = [s["name"] for s in steps if isinstance(s, dict) and s.get("name")]
    final_step_name = actual_step_names[-1] if actual_step_names else ""
    norm_lookup = {n.lower().strip(): n for n in actual_step_names}

    checks: list[dict] = []
    valid_categories = {"completeness", "formatting", "content", "accuracy"}
    for item in parsed:
        if not isinstance(item, dict) or "name" not in item:
            continue
        cat = str(item.get("category", "content")).lower()
        if cat not in valid_categories:
            cat = "content"
        raw_target = str(item.get("target_step", "") or "").strip()
        target_step = norm_lookup.get(raw_target.lower(), "") or final_step_name
        checks.append({
            "id": str(uuid_mod.uuid4()),
            "name": str(item["name"])[:60],
            "description": str(item.get("description", "")),
            "category": cat,
            "target_step": target_step,
            "source": "auto",
        })

    # ── Meta-check filter ──
    # Discard checks that would pass even on a broken output. Reason: a check
    # like "the output contains text" passes for any non-empty workflow result,
    # so it doesn't actually distinguish good from bad. Best-effort — if the
    # meta-check LLM call fails, keep all checks (we'd rather over-include than
    # silently drop everything).
    checks = await _filter_unselective_checks(checks, intents, user_id=wf_data.get("user_id", ""))

    # Persist. Regeneration replaces auto-generated checks but carries over
    # user-authored ones.
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if wf:
        checks = _merge_manual_checks(wf.validation_plan or [], checks, norm_lookup)
        wf.validation_plan = checks
        wf.validation_plan_definition_hash = compute_workflow_definition_hash(wf_data)
        wf.validation_plan_updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
        wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await wf.save()

    return checks


def _merge_manual_checks(
    existing_plan: list[dict],
    generated_checks: list[dict],
    norm_lookup: dict[str, str],
) -> list[dict]:
    """Combine freshly generated checks with user-authored ones from the old plan.

    Manual checks (source == "manual") survive regeneration; their target_step
    is re-mapped through the current step names so a case/whitespace drift
    doesn't orphan them. Checks with no source predate the field and are
    treated as auto (replaced).
    """
    manual_checks = [c for c in existing_plan if c.get("source") == "manual"]
    for c in manual_checks:
        raw = str(c.get("target_step", "") or "").strip()
        if raw:
            c["target_step"] = norm_lookup.get(raw.lower(), raw)
    return generated_checks + manual_checks


async def _filter_unselective_checks(
    checks: list[dict],
    intents: list[str],
    *,
    user_id: str,
) -> list[dict]:
    """Drop checks that pass on a typical broken output.

    Strategy: ask the LLM to predict, for each check, whether a "broken-shape"
    output (empty, error-stub, hallucinated, wrong-format) would still pass.
    Checks that pass on broken outputs aren't useful for the optimizer because
    they can't distinguish good trials from bad ones.

    Conservative: a check is dropped only when the LLM says it would pass on
    AT LEAST 2 of the 3 broken-shape probes — single false-positives are
    plausible for a real-but-loose check.
    """
    from app.services.llm_service import create_chat_agent
    from app.models.system_config import SystemConfig

    if not checks or len(checks) <= 2:
        # Too few checks to risk filtering — keep them all.
        return checks

    broken_probes = [
        "(EMPTY OUTPUT)",
        "Error: Unable to process the request. Please try again.",
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. The quick brown fox jumps over the lazy dog.",
    ]

    checks_block = "\n".join(
        f"{i + 1}. [{c['category']}] {c['name']}: {c['description'][:200]}"
        for i, c in enumerate(checks)
    )
    intents_block = "\n".join(f"- {i}" for i in intents)
    probes_block = "\n".join(f"PROBE {i + 1}: {p}" for i, p in enumerate(broken_probes))

    system_prompt = (
        "You are auditing a list of validation checks for selectivity. A good check fails on "
        "BROKEN workflow output and passes on GOOD output. A bad check passes regardless — "
        "it doesn't distinguish good from broken and just inflates the score.\n\n"
        "You will be given:\n"
        "1. End-user intents — what good output should serve\n"
        "2. A numbered list of validation checks\n"
        "3. Three BROKEN-SHAPE probes — outputs that obviously don't serve the intents\n\n"
        "For each check, decide for each probe: would this check PASS or FAIL on this probe?\n"
        "Return ONLY a JSON object: "
        '{"verdicts": [{"check_index": 1, "probe_passes": [false, false, false]}, ...]}.'
    )

    user_prompt = (
        f"## Intents\n{intents_block}\n\n"
        f"## Checks\n{checks_block}\n\n"
        f"## Broken-shape probes\n{probes_block}\n\n"
        "For each check, indicate which probes would PASS it (true) vs FAIL it (false)."
    )

    try:
        model = await get_user_model_name(user_id)
        sys_config = await SystemConfig.get_config()
        sys_config_doc = sys_config.model_dump() if sys_config else {}
        agent = create_chat_agent(
            model, system_prompt=system_prompt, system_config_doc=sys_config_doc,
        )
        result = await agent.run(user_prompt)
    except Exception as e:
        logger.warning("Meta-check filter LLM call failed: %s — keeping all checks", e)
        return checks

    raw = _parse_json_object(result.output or "")
    if not raw:
        return checks
    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, list):
        return checks

    # Map check_index → number of probes it passed (false negatives).
    pass_count_by_index: dict[int, int] = {}
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        try:
            idx = int(v.get("check_index", 0))
        except (TypeError, ValueError):
            continue
        passes = v.get("probe_passes")
        if not isinstance(passes, list):
            continue
        pass_count_by_index[idx] = sum(1 for p in passes if bool(p))

    # Drop checks that passed on ≥2 of 3 probes — clearly unselective.
    kept: list[dict] = []
    dropped: list[str] = []
    for i, c in enumerate(checks, start=1):
        if pass_count_by_index.get(i, 0) >= 2:
            dropped.append(c.get("name", ""))
            continue
        kept.append(c)

    # Safety: if filtering would nuke everything, keep all and log. Better to
    # show the user a noisy plan than nothing.
    if not kept:
        logger.warning("Meta-check filter would drop all %d checks — keeping all", len(checks))
        return checks

    if dropped:
        logger.info("Meta-check filter dropped %d unselective check(s): %s", len(dropped), dropped)
    return kept


# ---------------------------------------------------------------------------
# Validation Execution
# ---------------------------------------------------------------------------

# Category weights — completeness and accuracy matter more than formatting.
_CATEGORY_WEIGHTS = {
    "completeness": 1.5,
    "accuracy": 1.3,
    "content": 1.0,
    "formatting": 0.7,
}


def _text_similarity(a: str, b: str) -> float:
    """Jaccard similarity over whitespace-split tokens (case-insensitive)."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _input_doc_key(result) -> str:
    """Stable key for the input document set a WorkflowResult ran against.

    Two runs share a key only when they ran on the exact same set of input
    documents — so comparing their outputs measures workflow nondeterminism,
    not document variance.
    """
    ctx = getattr(result, "input_context", None) or {}
    uuids = ctx.get("doc_uuids") or []
    if not isinstance(uuids, list):
        return ""
    return "|".join(sorted(str(u) for u in uuids))


def _compute_output_stability(results: list) -> dict:
    """Compare actual workflow outputs across multiple executions.

    Only compares runs that shared the SAME input document set — otherwise
    we'd be measuring per-document variance, not workflow nondeterminism.
    Returns a stability dict with a 0-1 score, or ``stability_score=None``
    with a diagnostic detail when there aren't enough same-input runs.
    """
    if len(results) < 2:
        return {"stability_score": None, "detail": "Need 2+ runs for stability measurement"}

    # Bucket by input doc set; pick the largest group that has 2+ runs.
    by_input: dict[str, list] = {}
    for r in results:
        by_input.setdefault(_input_doc_key(r), []).append(r)
    same_input_group = max(by_input.values(), key=len) if by_input else []

    if len(same_input_group) < 2:
        return {
            "stability_score": None,
            "detail": (
                "Stability requires 2+ runs against the same input documents; "
                f"the last {len(results)} runs all used different inputs. "
                "Re-run the workflow on the same input to measure nondeterminism."
            ),
            "num_outputs_compared": 0,
            "num_input_groups": len(by_input),
        }

    # Serialize the same-input group to text
    text_outputs = []
    for r in same_input_group:
        text = _serialize_output(r.final_output)
        if text is not None:
            text_outputs.append(text)

    if len(text_outputs) < 2:
        return {"stability_score": None, "detail": "Not enough text outputs to compare"}

    # Pairwise text similarity
    similarities = []
    for i in range(len(text_outputs)):
        for j in range(i + 1, len(text_outputs)):
            similarities.append(_text_similarity(text_outputs[i], text_outputs[j]))

    text_stability = sum(similarities) / len(similarities)

    # Structured field-level stability (if outputs are dicts)
    structured_stability = _structured_field_stability(same_input_group)

    # Use structured stability when available (more precise), blend with text
    if structured_stability is not None:
        stability_score = structured_stability * 0.6 + text_stability * 0.4
    else:
        stability_score = text_stability

    return {
        "stability_score": round(stability_score, 4),
        "text_similarity": round(text_stability, 4),
        "structured_field_stability": (
            round(structured_stability, 4) if structured_stability is not None else None
        ),
        "num_outputs_compared": len(text_outputs),
        "pairwise_similarities": [round(s, 4) for s in similarities],
        "num_input_groups": len(by_input),
        "compared_same_input": True,
    }


def _structured_field_stability(results: list) -> float | None:
    """Compare structured (dict) outputs field-by-field across runs.

    Returns fraction of fields that are consistent across all runs, or None
    if outputs are not structured.
    """
    outputs = []
    for r in results:
        fo = r.final_output
        if not isinstance(fo, dict):
            continue
        out = fo.get("output", fo)
        if isinstance(out, dict):
            outputs.append(out)

    if len(outputs) < 2:
        return None

    # Union of all keys
    all_keys = set()
    for o in outputs:
        all_keys.update(o.keys())

    if not all_keys:
        return None

    consistent = 0
    for key in all_keys:
        values = [str(o.get(key, "")).strip().lower() for o in outputs]
        if len(set(values)) == 1:
            consistent += 1

    return consistent / len(all_keys)


_STATUS_TO_SCORE = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}


async def _run_judge_replay(
    *,
    plan: list[dict],
    last_result,
    wf_data: dict,
    original_checks_per_run: list[list[dict]],
) -> list[tuple[dict, dict]] | None:
    """Re-evaluate the most-recent run once and return matched (orig, replay)
    verdict pairs. Returns ``None`` when not measurable.

    Centralizes the one expensive LLM call so both the overall variance and
    the per-step variance derive from the same replay rather than each
    doing its own. SKIP verdicts on either side are filtered — they mean
    the judge couldn't evaluate that check in one or both passes.
    """
    if not plan or not original_checks_per_run or not last_result:
        return None

    output_text = _serialize_output(getattr(last_result, "final_output", None))
    if output_text is None:
        return None

    original_checks = original_checks_per_run[0]
    if not original_checks:
        return None

    try:
        replay = await _evaluate_checks_against_output(
            plan, output_text, getattr(last_result, "steps_output", None) or {}, wf_data,
        )
    except Exception as e:
        logger.warning("Workflow judge variance replay failed: %s", e)
        return None

    replay_by_id = {str(c.get("check_id", "")): c for c in (replay or [])}
    samples: list[tuple[dict, dict]] = []
    for orig in original_checks:
        cid = str(orig.get("check_id", ""))
        rep = replay_by_id.get(cid)
        if not rep:
            continue
        if orig.get("status") == "SKIP" or rep.get("status") == "SKIP":
            continue
        samples.append((orig, rep))
    return samples


async def _sample_workflow_judge_variance(
    *,
    plan: list[dict],
    last_result,
    wf_data: dict,
    original_checks_per_run: list[list[dict]],
) -> float | None:
    """Re-evaluate one workflow run and measure verdict stability.

    Returns stddev of per-check score deltas (0-1 scale), or None when not
    measurable. Kept as a stable entry point for callers and tests that
    only need the overall scalar.
    """
    samples = await _run_judge_replay(
        plan=plan, last_result=last_result, wf_data=wf_data,
        original_checks_per_run=original_checks_per_run,
    )
    return _stddev_of_deltas(samples)


def _stddev_of_deltas(
    samples: list[tuple[dict, dict]] | None,
) -> float | None:
    """Sample stddev of (replay − original) verdict scores across pairs.

    Synchronous arithmetic on already-collected replay verdicts — no LLM
    call. Returns None when fewer than 2 comparable pairs are available.
    Matches the semantics of the shared ``sample_judge_variance`` helper
    so badges driven by it can use the same ±1.96σ scaling.
    """
    if not samples or len(samples) < 2:
        return None
    deltas = [
        _STATUS_TO_SCORE.get(rep.get("status", ""), 0.0)
        - _STATUS_TO_SCORE.get(orig.get("status", ""), 0.0)
        for orig, rep in samples
    ]
    mean = sum(deltas) / len(deltas)
    var = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
    return var ** 0.5


def _compute_per_step_variance(
    samples: list[tuple[dict, dict]] | None,
    plan: list[dict] | None,
) -> dict[str, float]:
    """Per-target_step stddev of score deltas.

    Buckets the (orig, replay) sample pairs by each check's ``target_step``
    in the plan, then computes per-bucket stddev. Buckets with fewer than 2
    samples are omitted (no signal). The result feeds into
    ``step_breakdown`` so the UI can show ±N pts on each step's score.
    """
    if not samples or not plan:
        return {}

    target_lookup = {
        str(p.get("id", "")): (p.get("target_step") or "").strip()
        for p in plan
    }

    by_step: dict[str, list[tuple[dict, dict]]] = {}
    for orig, rep in samples:
        cid = str(orig.get("check_id", ""))
        target = target_lookup.get(cid) or ""
        if not target:
            continue
        by_step.setdefault(target, []).append((orig, rep))

    out: dict[str, float] = {}
    for step, step_samples in by_step.items():
        stddev = _stddev_of_deltas(step_samples)
        if stddev is not None:
            out[step] = stddev
    return out


def _compute_step_breakdown(plan: list[dict], checks: list[dict]) -> list[dict]:
    """Aggregate per-check verdicts by ``target_step`` so the UI can show
    *which* step is dragging the score, not just that the score is dragging.

    No new judge calls — this is pure re-aggregation of existing verdicts.

    Returns a list of step entries ordered by step name (stable). Each entry:
        {
          "step": str,             # target_step name, or "Unassigned" when missing
          "score": float,          # 0-100, weighted PASS/WARN/FAIL ratio
          "pass": int,             # PASS count
          "warn": int,
          "fail": int,
          "skip": int,
          "total": int,            # all checks including SKIP
          "evaluated": int,        # total minus SKIP
        }

    Returns an empty list when there's only one (or zero) distinct target_step
    — the breakdown wouldn't add information vs. the overall grade in that case.
    """
    # Map check_id → (target_step, category) using the plan as the source of truth
    target_lookup: dict[str, tuple[str, str]] = {}
    for p in plan or []:
        cid = str(p.get("id", ""))
        if not cid:
            continue
        step = (p.get("target_step") or "").strip()
        cat = p.get("category", "content")
        target_lookup[cid] = (step or "Unassigned", cat)

    # Group checks by step name
    by_step: dict[str, dict] = {}
    for c in checks or []:
        cid = str(c.get("check_id", ""))
        step, cat = target_lookup.get(cid, ("Unassigned", "content"))
        status = c.get("status", "SKIP")
        bucket = by_step.setdefault(step, {
            "step": step,
            "pass": 0, "warn": 0, "fail": 0, "skip": 0,
            "weighted_sum": 0.0, "weight_total": 0.0,
        })
        # Status counts
        if status == "PASS":
            bucket["pass"] += 1
        elif status == "WARN":
            bucket["warn"] += 1
        elif status == "FAIL":
            bucket["fail"] += 1
        else:
            bucket["skip"] += 1
        # Weighted score contribution (matches _build_result's formula)
        if status != "SKIP":
            w = _CATEGORY_WEIGHTS.get(cat, 1.0)
            status_val = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}.get(status, 0.0)
            bucket["weighted_sum"] += status_val * w
            bucket["weight_total"] += w

    # Suppress when only one step appears — the breakdown would just restate the overall
    if len(by_step) <= 1:
        return []

    # Materialize: compute score per step, drop intermediate sums
    breakdown: list[dict] = []
    for step_name in sorted(by_step.keys()):
        b = by_step[step_name]
        total = b["pass"] + b["warn"] + b["fail"] + b["skip"]
        evaluated = total - b["skip"]
        score = (b["weighted_sum"] / b["weight_total"]) * 100 if b["weight_total"] > 0 else 0.0
        breakdown.append({
            "step": step_name,
            "score": round(score, 1),
            "pass": b["pass"],
            "warn": b["warn"],
            "fail": b["fail"],
            "skip": b["skip"],
            "total": total,
            "evaluated": evaluated,
        })
    return breakdown


# ---------------------------------------------------------------------------
# No-workflow baseline (Phase 2A)
#
# Answers the user's "is this workflow earning its complexity?" question:
# given the same input the workflow ran on, what does a single-shot LLM call
# produce — and how does its score against the validation plan compare to the
# workflow's score?
#
# This isn't an optimizer; it's a diagnostic. We don't propose deleting the
# workflow. We just surface the lift number so the user can decide.
# ---------------------------------------------------------------------------


_NO_WORKFLOW_BASELINE_SYSTEM_PROMPT = (
    "You are doing in a single shot what a multi-step workflow would do. "
    "Read the instructions carefully, read the input, and produce the output "
    "the workflow would produce. Be concise — match the format the workflow "
    "would use. Output the result directly with no preamble."
)


def _build_baseline_instructions(wf_data: dict | None) -> str:
    """Concatenate workflow-level + step-level descriptions into a single
    instruction blob for the no-workflow counterfactual.

    The LLM sees what the workflow was *trying to do* without seeing the
    decomposition. If the description is empty, fall back to step names so
    the model has at least a list of intents to follow.
    """
    if not wf_data:
        return ""
    parts: list[str] = []
    name = (wf_data.get("name") or "").strip()
    desc = (wf_data.get("description") or "").strip()
    if name:
        parts.append(f"Task: {name}")
    if desc:
        parts.append(desc)
    # Step intents — only step names + short descriptions, not full task config.
    steps = wf_data.get("steps") or []
    step_intents: list[str] = []
    for s in steps:
        sname = (s.get("name") or "").strip() if isinstance(s, dict) else ""
        sdesc = (s.get("description") or "").strip() if isinstance(s, dict) else ""
        if sname and sdesc:
            step_intents.append(f"- {sname}: {sdesc}")
        elif sname:
            step_intents.append(f"- {sname}")
    if step_intents:
        parts.append("The workflow performs these steps end-to-end:\n" + "\n".join(step_intents))
    return "\n\n".join(parts)


def _extract_source_text_from_steps(steps_output: dict | None) -> str:
    """Pull the source document text from a WorkflowResult's steps_output.

    Workflows typically start with a Document or AddDocument step that loads
    the raw text. That's the "input" the no-workflow baseline needs to consume.
    """
    if not steps_output:
        return ""
    for step_name, step_data in steps_output.items():
        if step_name.lower() in ("document", "adddocument") or (
            isinstance(step_data, dict) and step_data.get("step_name") in ("Document", "AddDocument")
        ):
            raw = step_data.get("output", step_data) if isinstance(step_data, dict) else step_data
            if isinstance(raw, str) and raw.strip():
                return raw
    return ""


async def _measure_no_workflow_baseline(
    *,
    wf_data: dict,
    last_result,
    user_id: str | None = None,
) -> dict | None:
    """Run a single-shot LLM call as a counterfactual to the workflow.

    Returns:
        {
          "score": float (0-100),
          "checks": list[dict],            # per-check verdicts on the single-shot output
          "output": str,                   # the LLM's single-shot answer
          "weighted_pass_rate": float,     # for comparison to the workflow's metric
        }
        or None when we can't measure (no input text, no plan, LLM error).

    Side-effects: none. This is a pure read + LLM-call helper. The caller wires
    its score into the validation result dict.
    """
    from app.services.workflow_validator import _resolve_model_name
    from app.services.llm_service import get_agent_model
    from pydantic_ai import Agent

    plan = (wf_data or {}).get("validation_plan", []) if wf_data else []
    if not plan:
        return None  # no checks to score against

    source_text = _extract_source_text_from_steps(
        getattr(last_result, "steps_output", None)
    )
    if not source_text:
        # Workflow input isn't a document text we can reuse — skip.
        return None

    instructions = _build_baseline_instructions(wf_data)
    if not instructions:
        return None  # nothing to instruct the model with

    user_prompt = (
        f"{instructions}\n\n"
        f"---\nInput document:\n{source_text[:30_000]}\n---\n\n"
        "Now produce the workflow's expected output for this input."
    )

    try:
        model_name = _resolve_model_name(user_id)
        model = get_agent_model(model_name)
        agent = Agent(model, system_prompt=_NO_WORKFLOW_BASELINE_SYSTEM_PROMPT)
        result = await agent.run(user_prompt)
        baseline_output = (result.output or "").strip()
    except Exception as e:
        logger.warning("No-workflow baseline LLM call failed: %s", e)
        return None

    if not baseline_output:
        return None

    # Evaluate via the same checks the workflow runs. steps_output for the
    # baseline is empty (no intermediate steps); wf_data carries the plan.
    try:
        baseline_checks = await _evaluate_checks_against_output(
            plan, baseline_output, {}, wf_data,
        )
    except Exception as e:
        logger.warning("No-workflow baseline check evaluation failed: %s", e)
        return None

    # Score with the same weighted-pass formula as the workflow result. We use
    # a lightweight inline calculation rather than _build_result to avoid
    # persisting a ValidationRun for the baseline (it's diagnostic, not a run).
    cat_lookup: dict[str, str] = {c["id"]: c.get("category", "content") for c in plan}
    weighted_sum = 0.0
    weight_total = 0.0
    for c in baseline_checks:
        if c.get("status") == "SKIP":
            continue
        cat = cat_lookup.get(c.get("check_id", ""), "content")
        w = _CATEGORY_WEIGHTS.get(cat, 1.0)
        status_val = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}.get(c.get("status", ""), 0.0)
        weighted_sum += status_val * w
        weight_total += w
    weighted_pass_rate = weighted_sum / weight_total if weight_total > 0 else 0.0
    score = round(weighted_pass_rate * 100, 1)

    return {
        "score": score,
        "checks": baseline_checks,
        "output": baseline_output[:5000],  # truncate; full text isn't needed downstream
        "weighted_pass_rate": round(weighted_pass_rate, 4),
    }


async def _gather_static_diagnostics(
    wf_data: dict | None,
    steps_output: dict | None = None,
    validation_plan: list[dict] | None = None,
) -> list[dict]:
    """Run deterministic structural + runtime diagnostics on a workflow.

    Looks up valid search_set UUIDs so the dangling-reference check has a
    real allow-list. If the lookup fails we pass ``None`` so the check
    silently skips rather than false-flagging every workflow.
    """
    from app.services import workflow_diagnostics as wdiag
    from app.models.search_set import SearchSet

    valid_uuids: set[str] | None
    try:
        all_sets = await SearchSet.find_all().to_list()
        valid_uuids = {str(s.uuid) for s in all_sets if getattr(s, "uuid", None)}
    except Exception as e:
        logger.warning("Static diagnostics: search_set lookup failed: %s", e)
        valid_uuids = None

    return [
        dict(d) for d in wdiag.run_diagnostics(
            wf_data, steps_output,
            valid_search_set_uuids=valid_uuids,
            validation_plan=validation_plan,
        )
    ]


_STRUCTURAL_FAIL_CODES: dict[str, str] = {
    "empty_step_output": "produced an empty output",
    "error_shaped_step_output": "produced an error-shaped output",
    "invalid_json_output": "claimed JSON but the output does not parse",
    "low_source_grounding": "extracted values that don't appear in the source document",
}


def _inject_step_output_fails(
    checks: list[dict],
    plan: list[dict],
    diagnostics: list[dict],
) -> None:
    """Mutate `checks` to FAIL any check whose target_step has a structural
    error-level diagnostic against it. The judge often misses these (the
    LLM sees "" or a hallucinated value and has nothing concrete to
    disagree with), so we override its verdict here.

    The check's existing detail is preserved alongside the diagnostic
    message so users can see both the judge's read and the structural
    reason. SKIP verdicts stay SKIP — "we don't know" shouldn't be
    promoted to a confident FAIL.
    """
    # step name → reason it's considered broken (first diagnostic wins)
    broken_steps: dict[str, str] = {}
    for d in diagnostics:
        code = d.get("code", "")
        if code not in _STRUCTURAL_FAIL_CODES:
            continue
        target = d.get("target_step")
        if target and target not in broken_steps:
            broken_steps[target] = _STRUCTURAL_FAIL_CODES[code]
    if not broken_steps:
        return

    plan_by_id = {p.get("id"): p for p in plan or []}
    for c in checks:
        plan_check = plan_by_id.get(c.get("check_id")) or {}
        target = (plan_check.get("target_step") or "").strip()
        reason = broken_steps.get(target)
        if reason and c.get("status") != "SKIP":
            existing = c.get("detail", "") or ""
            c["status"] = "FAIL"
            c["detail"] = (
                f"Step '{target}' {reason} (deterministic check). "
                + (f"Judge said: {existing}" if existing else "")
            ).strip()


async def validate_workflow(workflow_id: str, user: User | None = None) -> dict:
    """Evaluate the last N executions' output against the persisted validation plan."""
    if user is not None:
        wf = await get_authorized_workflow(workflow_id, user)
        if not wf:
            raise ValueError("Workflow not found")
    else:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
        if not wf:
            raise ValueError("Workflow not found")

    plan = wf.validation_plan
    if not plan:
        raise ValueError("No validation plan - generate or add checks first")

    wf_data = await get_workflow(workflow_id)

    # Flag runs graded against a stale plan — the grade card renders a caveat
    # so a low grade caused by orphaned/drifted checks isn't mistaken for a
    # bad workflow.
    plan_stale, _, _ = _plan_staleness(
        plan, wf.validation_plan_definition_hash, wf_data,
    )

    # Find the last N completed WorkflowResults for consistency measurement
    num_runs = min(3, await WorkflowResult.find(
        WorkflowResult.workflow == wf.id,
        WorkflowResult.status == "completed",
    ).count())
    if num_runs == 0:
        num_runs = 1  # Will trigger the no-results path below

    last_results = await WorkflowResult.find(
        WorkflowResult.workflow == wf.id,
        WorkflowResult.status == "completed",
    ).sort("-_id").limit(max(num_runs, 1)).to_list()

    # Static diagnostics — these run independent of the validation plan and
    # the LLM judge. Computed once up-front so the no-results path can still
    # surface dangling refs / prompt-field mismatches.
    static_diagnostics = await _gather_static_diagnostics(
        wf_data,
        steps_output=last_results[0].steps_output if last_results else None,
        validation_plan=plan,
    )

    if not last_results:
        # All checks SKIP
        checks = [
            {
                "check_id": c["id"],
                "name": c["name"],
                "status": "SKIP",
                "detail": "No completed execution found. Run the workflow first.",
            }
            for c in plan
        ]
        return await _build_result(
            checks, workflow_id, wf_data, num_runs=0,
            output_comparison=None, stability_data=None,
            static_diagnostics=static_diagnostics,
            plan_stale=plan_stale,
        )

    # Compute output-to-output stability (compares actual outputs across runs)
    stability_data = _compute_output_stability(last_results)

    # Evaluate each execution independently
    all_run_checks = []
    for wr in last_results:
        output_text = _serialize_output(wr.final_output)
        if output_text is None:
            # Skip binary outputs
            run_checks = [
                {"check_id": c["id"], "name": c["name"], "status": "SKIP",
                 "detail": "Binary output cannot be evaluated as text."}
                for c in plan
            ]
        else:
            src = await _resolve_run_source_text(wr)
            run_checks = await _evaluate_checks_against_output(
                plan, output_text, wr.steps_output, wf_data, source_text_override=src,
            )
        all_run_checks.append(run_checks)

    # Merge multi-run results with consistency tracking
    checks = _merge_multi_run_checks(plan, all_run_checks)

    # Deterministic comparison against stored expected outputs
    expected_outputs = [inp for inp in wf.validation_inputs if inp.get("type") == "expected_output"]
    output_comparison = None
    if expected_outputs and last_results:
        output_comparison = _compare_outputs(last_results, expected_outputs)

    # No-workflow baseline (Phase 2A): how would a single-shot LLM call score
    # against the same checks? Surfaces the "is this workflow earning its
    # complexity?" diagnostic. Best-effort — None when not measurable.
    baseline_no_workflow = await _measure_no_workflow_baseline(
        wf_data=wf_data,
        last_result=last_results[0] if last_results else None,
        user_id=user.user_id if user else None,
    )

    # Judge variance (Phase 2A): re-evaluate the most-recent run and measure
    # how often verdicts flip. Drives the "± N pts" CI on the grade so users
    # know whether a borderline PASS could swing to FAIL on the next run.
    # We run the replay ONCE and derive both overall and per-step variance
    # from the same (orig, replay) sample pairs — no second LLM call.
    replay_samples = await _run_judge_replay(
        plan=plan,
        last_result=last_results[0],
        wf_data=wf_data,
        original_checks_per_run=all_run_checks,
    )
    judge_variance = _stddev_of_deltas(replay_samples)
    per_step_variance = _compute_per_step_variance(replay_samples, plan)

    # Deterministic step-output errors get promoted to FAIL checks tied to
    # the offending step. Without this, the LLM judge has been observed to
    # silently rate empty / "Error: rate limit" outputs as PASS for any
    # check the model couldn't parse a target for.
    _inject_step_output_fails(checks, plan, static_diagnostics)

    return await _build_result(
        checks, workflow_id, wf_data,
        num_runs=len(all_run_checks),
        output_comparison=output_comparison,
        stability_data=stability_data,
        baseline_no_workflow=baseline_no_workflow,
        judge_variance=judge_variance,
        per_step_variance=per_step_variance,
        static_diagnostics=static_diagnostics,
        plan_stale=plan_stale,
    )


def _serialize_output(final_output: dict | None) -> str | None:
    """Convert final_output to a text string for LLM evaluation.

    Returns ``None`` for binary formats that cannot be evaluated as text.
    """
    import json as _json
    import base64 as _b64

    if final_output is None:
        return ""

    output_data = final_output.get("output", final_output) if isinstance(final_output, dict) else final_output

    # Handle file_download type
    if isinstance(output_data, dict) and output_data.get("type") == "file_download":
        file_type = output_data.get("file_type", "")
        if file_type in ("zip", "pdf", "xlsx"):
            return None  # binary — cannot evaluate
        # Text-based file downloads (csv, json, md, txt)
        try:
            raw = _b64.b64decode(output_data.get("data_b64", ""))
            return raw.decode("utf-8", errors="replace")[:50_000]
        except Exception:
            return None

    if isinstance(output_data, (dict, list)):
        return _json.dumps(output_data, indent=2, default=str)[:50_000]

    return str(output_data)[:50_000]


async def _resolve_run_source_text(result) -> str:
    """Resolve a run's ACTUAL source text for the validation judge.

    The ``Document`` trigger step only stores document UUIDs (its output is a
    list of uuid hex strings), so the judge's legacy steps_output extraction
    feeds those UUIDs as "ground truth" — the judge then sees opaque hash
    strings instead of the document and cannot verify grounding. Here we
    resolve ``input_context.doc_uuids`` to ``SmartDocument.raw_text`` (the same
    text the workflow itself ran on) and append any KB chunks the run
    retrieved, so accuracy/completeness checks evaluate against the real
    source. Returns "" when no source text is recoverable.
    """
    parts: list[str] = []
    ic = getattr(result, "input_context", None) or {}
    uuids = ic.get("doc_uuids") or [] if isinstance(ic, dict) else []
    for u in uuids:
        try:
            doc = await SmartDocument.find_one(SmartDocument.uuid == u)
        except Exception:
            doc = None
        if doc and getattr(doc, "raw_text", ""):
            parts.append(doc.raw_text)
    for s in (getattr(result, "retrieved_sources", None) or []):
        cp = s.get("content_preview") if isinstance(s, dict) else None
        if cp:
            parts.append(str(cp))
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "\n\n=== Document ===\n".join(parts)


async def _evaluate_checks_against_output(
    plan: list[dict],
    output_text: str,
    steps_output: dict,
    wf_data: dict,
    source_text_override: str | None = None,
) -> list[dict]:
    """Single LLM call to evaluate all checks against the actual output.

    When *source_text_override* is provided, it is used as the ground-truth
    source document text (resolved from the run's uploaded documents) instead
    of the legacy steps_output scan, which only sees document UUIDs.
    """
    import json as _json
    from app.services.llm_service import create_chat_agent
    from app.models.system_config import SystemConfig

    # Build the check definitions for the prompt
    checks_desc = _json.dumps(
        [{"check_id": c["id"], "name": c["name"], "description": c.get("description", "")} for c in plan],
        indent=2,
    )

    # Extract source document text from steps_output so the evaluator can
    # verify extracted values actually come from the source (not hallucinated).
    source_text = ""
    if source_text_override is not None:
        _gt = source_text_override.strip()
        if _gt:
            source_text = (
                "\n\n## Source Document Text (ground truth)\n"
                "Use this to verify that extracted values actually appear in the "
                "source document. Values not grounded in this text may be hallucinated.\n"
                + _gt[:15_000]
            )
    elif steps_output:
        for step_name, step_data in steps_output.items():
            # Document / AddDocument steps carry the raw source text
            if step_name.lower() in ("document", "adddocument") or (
                isinstance(step_data, dict) and step_data.get("step_name") in ("Document", "AddDocument")
            ):
                raw = step_data.get("output", step_data) if isinstance(step_data, dict) else step_data
                if isinstance(raw, str) and raw.strip():
                    source_text = (
                        "\n\n## Source Document Text (ground truth)\n"
                        "Use this to verify that extracted values actually appear in the "
                        "source document. Values not grounded in this text may be hallucinated.\n"
                        + raw[:15_000]
                    )
                    break
                if isinstance(raw, list):
                    combined = "\n---\n".join(str(item) for item in raw[:5])
                    if combined.strip():
                        source_text = (
                            "\n\n## Source Document Text (ground truth)\n"
                            "Use this to verify that extracted values actually appear in the "
                            "source document. Values not grounded in this text may be hallucinated.\n"
                            + combined[:15_000]
                        )
                        break

    # Include intermediate step outputs so the evaluator can cross-reference
    # whether data was faithfully carried through the pipeline
    steps_text = ""
    if steps_output:
        steps_text = (
            "\n\n## Intermediate Step Outputs (for cross-referencing)\n"
            "Use these to verify that data extracted in earlier steps actually "
            "appears in the final output.\n"
            + _json.dumps(steps_output, indent=2, default=str)[:20_000]
        )

    # Detect whether the output is structured JSON. When it is, tell the judge
    # explicitly so it reasons about field-level presence rather than searching
    # free text for the values — a known failure mode for completeness checks.
    output_is_structured = False
    output_shape_hint = ""
    stripped_output = (output_text or "").strip()
    if stripped_output.startswith("{") or stripped_output.startswith("["):
        try:
            parsed_struct = _json.loads(stripped_output)
            if isinstance(parsed_struct, dict):
                output_is_structured = True
                top_keys = list(parsed_struct.keys())[:20]
                output_shape_hint = (
                    f"\n\n## Output Shape Hint\n"
                    f"The final output is a JSON object with keys: {top_keys}. "
                    "When checking completeness, reason about which keys/values are present."
                )
            elif isinstance(parsed_struct, list):
                output_is_structured = True
                output_shape_hint = (
                    f"\n\n## Output Shape Hint\n"
                    f"The final output is a JSON array of length {len(parsed_struct)}. "
                    "When checking completeness, verify expected elements are present."
                )
        except _json.JSONDecodeError:
            pass

    structured_note = (
        "Note: the workflow output is STRUCTURED JSON. Reason about it as data "
        "(specific keys/values) — don't fall back to free-text matching when a key "
        "is named explicitly in the check description.\n\n"
        if output_is_structured else ""
    )

    system_prompt = (
        "You are a strict quality evaluator for workflow outputs. You will be given:\n"
        "1. A list of quality checks to evaluate\n"
        "2. The final output of a workflow execution\n"
        "3. The source document text (when available) — this is ground truth\n"
        "4. Intermediate step outputs (to cross-reference data flow)\n\n"
        + structured_note +
        "Your job is to determine whether the FINAL OUTPUT satisfies each check.\n\n"
        "Key evaluation principles:\n"
        "- For COMPLETENESS checks: verify that specific named data points actually appear "
        "in the output. Cross-reference with intermediate step outputs to confirm data "
        "was carried through. If an extraction step produced a value but it's missing from "
        "the final output, that's a FAIL.\n"
        "- For ACCURACY checks: compare values in the final output against BOTH the "
        "intermediate step data AND the source document. If the output claims a value "
        "that doesn't appear in the source document, that's likely a hallucination — FAIL. "
        "If values were faithfully extracted and carried through, that's a PASS.\n"
        "- For CONTENT checks: assess whether the output fulfills its stated purpose "
        "(e.g., 'human readable summary' should be a coherent narrative, not raw data).\n"
        "- For FORMATTING checks: verify the output matches the requested format.\n\n"
        "For EACH check, determine: PASS, FAIL, or WARN.\n\n"
        "EVIDENCE REQUIREMENT (strict):\n"
        "- Every FAIL verdict MUST quote the specific output value (or named absence) that failed.\n"
        "- Every PASS verdict MUST cite at least one concrete supporting value from the output.\n"
        "- For accuracy checks, quote BOTH the output value and the source document value.\n"
        "- Verdicts without concrete quoted evidence should be marked WARN, not PASS.\n\n"
        "Return ONLY a JSON array of result objects. Each object must have:\n"
        '- "check_id": the check ID from the input (string)\n'
        '- "status": one of "PASS", "FAIL", "WARN" (string)\n'
        '- "detail": specific evidence — quote actual values in double quotes (string)\n\n'
        "Return ONLY the JSON array, no other text."
    )

    user_prompt = (
        f"## Quality Checks to Evaluate\n{checks_desc}\n\n"
        f"## Workflow Final Output\n{output_text}"
        f"{output_shape_hint}"
        f"{source_text}"
        f"{steps_text}"
    )

    model = await get_user_model_name(wf_data.get("user_id", ""))

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    agent = create_chat_agent(
        model,
        system_prompt=system_prompt,
        system_config_doc=sys_config_doc,
    )

    try:
        from app.services.metering import metered_async
        async with metered_async("validation"):
            result = await agent.run(user_prompt)
    except Exception:
        return [
            {"check_id": c["id"], "name": c["name"], "status": "SKIP", "detail": "LLM evaluation failed"}
            for c in plan
        ]

    parsed = _parse_json_array(result.output)
    if parsed is None:
        return [
            {"check_id": c["id"], "name": c["name"], "status": "SKIP", "detail": "Could not parse LLM evaluation response"}
            for c in plan
        ]

    # Build a lookup from check_id → result
    result_map: dict[str, dict] = {}
    valid_statuses = {"PASS", "FAIL", "WARN", "SKIP"}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("check_id", ""))
        status = str(item.get("status", "SKIP")).upper()
        if status not in valid_statuses:
            status = "SKIP"
        result_map[cid] = {"status": status, "detail": str(item.get("detail", ""))}

    # Merge with plan to guarantee every check has a result
    checks = []
    for c in plan:
        r = result_map.get(c["id"], {"status": "SKIP", "detail": "No evaluation returned for this check"})
        checks.append({
            "check_id": c["id"],
            "name": c["name"],
            "status": r["status"],
            "detail": r["detail"],
        })

    return checks


def _merge_multi_run_checks(plan: list[dict], all_run_checks: list[list[dict]]) -> list[dict]:
    """Merge check results from multiple runs, computing per-check consistency.

    For each check, reports the most common status, consistency (fraction of
    runs that agree), and details from all runs.
    """
    from collections import Counter

    num_runs = len(all_run_checks)
    if num_runs == 0:
        return []
    if num_runs == 1:
        # Single run — no consistency measurement, return as-is
        for c in all_run_checks[0]:
            c["consistency"] = 1.0
            c["run_statuses"] = [c["status"]]
            c["run_details"] = [c["detail"]]
        return all_run_checks[0]

    merged = []
    for i, check_def in enumerate(plan):
        check_id = check_def["id"]
        # Collect statuses and details across runs
        statuses = []
        details = []
        for run_checks in all_run_checks:
            # Find this check in the run results
            for rc in run_checks:
                if rc.get("check_id") == check_id:
                    statuses.append(rc["status"])
                    details.append(rc.get("detail", ""))
                    break
            else:
                statuses.append("SKIP")
                details.append("Check not evaluated in this run")

        # Most common status = consensus
        counter = Counter(statuses)
        consensus_status, consensus_count = counter.most_common(1)[0]
        consistency = consensus_count / len(statuses)

        # Build merged detail
        if consistency == 1.0:
            merged_detail = details[0]  # All agree, use first detail
        else:
            # Show disagreement
            status_summary = ", ".join(f"Run {j+1}: {s}" for j, s in enumerate(statuses))
            merged_detail = f"Inconsistent across runs ({status_summary}). {details[0]}"

        merged.append({
            "check_id": check_id,
            "name": check_def["name"],
            "status": consensus_status,
            "detail": merged_detail,
            "consistency": consistency,
            "run_statuses": statuses,
            "run_details": details,
        })

    return merged


def _compare_outputs(
    results: list["WorkflowResult"],
    expected_outputs: list[dict],
) -> dict:
    """Compare actual workflow outputs against stored expected outputs.

    For structured output (JSON/dict), does field-level comparison.
    For text output, does normalized text similarity.
    Returns comparison metrics that can feed into the quality score.
    """

    comparisons = []
    for expected in expected_outputs:
        exp_snapshot = expected.get("output_snapshot", {})
        exp_output = exp_snapshot.get("output", exp_snapshot) if isinstance(exp_snapshot, dict) else exp_snapshot

        for wr in results:
            actual_output = wr.final_output
            if isinstance(actual_output, dict):
                actual_output = actual_output.get("output", actual_output)

            # Structured comparison for dict/JSON outputs
            if isinstance(exp_output, dict) and isinstance(actual_output, dict):
                total_fields = 0
                matching_fields = 0
                field_details = []

                for key in set(list(exp_output.keys()) + list(actual_output.keys())):
                    total_fields += 1
                    exp_val = str(exp_output.get(key, ""))
                    act_val = str(actual_output.get(key, ""))

                    # Use extraction validation's normalization for comparison
                    from app.services.extraction_validation_service import _values_match, _is_not_found

                    if _is_not_found(exp_val) and _is_not_found(act_val):
                        matched = True
                    elif exp_val and act_val and _values_match(act_val, exp_val):
                        matched = True
                    else:
                        matched = exp_val == act_val

                    if matched:
                        matching_fields += 1
                    field_details.append({
                        "field": key,
                        "expected": exp_val[:200],
                        "actual": act_val[:200],
                        "matched": matched,
                    })

                accuracy = matching_fields / total_fields if total_fields > 0 else 0.0
                comparisons.append({
                    "expected_label": expected.get("label", ""),
                    "accuracy": accuracy,
                    "total_fields": total_fields,
                    "matching_fields": matching_fields,
                    "fields": field_details,
                })

            elif isinstance(exp_output, list) and isinstance(actual_output, list):
                # List comparison — compare lengths and items
                total = max(len(exp_output), len(actual_output))
                matching = 0
                if total > 0:
                    for i in range(min(len(exp_output), len(actual_output))):
                        if str(exp_output[i]) == str(actual_output[i]):
                            matching += 1
                    accuracy = matching / total
                else:
                    accuracy = 1.0
                comparisons.append({
                    "expected_label": expected.get("label", ""),
                    "accuracy": accuracy,
                    "total_fields": total,
                    "matching_fields": matching,
                })

            else:
                # Text comparison — normalized
                exp_text = str(exp_output).strip().lower()
                act_text = str(actual_output).strip().lower()
                accuracy = 1.0 if exp_text == act_text else 0.0
                comparisons.append({
                    "expected_label": expected.get("label", ""),
                    "accuracy": accuracy,
                })

    if not comparisons:
        return {"has_expected": False}

    avg_accuracy = sum(c["accuracy"] for c in comparisons) / len(comparisons)
    return {
        "has_expected": True,
        "comparisons": comparisons,
        "output_accuracy": round(avg_accuracy, 4),
    }


async def _build_result(
    checks: list[dict],
    workflow_id: str,
    wf_data: dict | None,
    num_runs: int = 1,
    output_comparison: dict | None = None,
    stability_data: dict | None = None,
    baseline_no_workflow: dict | None = None,
    judge_variance: float | None = None,
    per_step_variance: dict[str, float] | None = None,
    static_diagnostics: list[dict] | None = None,
    plan_stale: bool = False,
) -> dict:
    """Compute separate quality / stability scores, combined score, grade, and persist."""
    statuses = [c["status"] for c in checks]
    fail_count = statuses.count("FAIL")
    warn_count = statuses.count("WARN")
    pass_count = statuses.count("PASS")
    skip_count = statuses.count("SKIP")
    total = len(checks)
    evaluated = total - skip_count

    # -- Weighted check pass rate (by category) --
    # Build check_id → category lookup from the workflow's validation plan
    plan = (wf_data or {}).get("validation_plan", [])
    cat_lookup: dict[str, str] = {c["id"]: c.get("category", "content") for c in plan}

    weighted_sum = 0.0
    weight_total = 0.0
    unweighted_sum = 0.0
    for c in checks:
        if c["status"] == "SKIP":
            continue
        cat = cat_lookup.get(c.get("check_id", ""), "content")
        w = _CATEGORY_WEIGHTS.get(cat, 1.0)
        status_val = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}.get(c["status"], 0.0)
        weighted_sum += status_val * w
        weight_total += w
        unweighted_sum += status_val

    weighted_pass_rate = weighted_sum / weight_total if weight_total > 0 else 0.0
    check_pass_rate = unweighted_sum / evaluated if evaluated > 0 else 0.0

    # -- Quality score (how good is the output?) --
    # Based on weighted check pass rate + expected-output comparison when available
    quality_score_raw = weighted_pass_rate * 100
    output_accuracy = None
    if output_comparison and output_comparison.get("has_expected"):
        output_accuracy = output_comparison["output_accuracy"]
        # Blend: 70% weighted checks + 30% ground-truth comparison
        quality_score_raw = weighted_pass_rate * 100 * 0.7 + output_accuracy * 100 * 0.3

    quality_score = min(100.0, max(0.0, quality_score_raw))

    # -- Stability score (how consistent are the actual outputs?) --
    # This measures output-to-output similarity, not evaluator consistency.
    stability_score_val = None
    if stability_data and stability_data.get("stability_score") is not None:
        stability_score_val = stability_data["stability_score"] * 100  # convert 0-1 → 0-100

    # Evaluator consistency is kept as a diagnostic signal
    consistencies = [c.get("consistency", 1.0) for c in checks if c["status"] != "SKIP"]
    avg_evaluator_consistency = sum(consistencies) / len(consistencies) if consistencies else 0.0

    # -- Combined score --
    if stability_score_val is not None:
        # Both dimensions available: 60% quality + 40% stability
        score = min(100.0, max(0.0, quality_score * 0.6 + stability_score_val * 0.4))
    else:
        # Single run — quality only, but note reduced confidence
        score = quality_score

    # -- Grade from combined score --
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    # -- Summary --
    parts = [f"{pass_count}/{total} checks passed, {warn_count} warnings, {fail_count} failures"]
    if stability_score_val is not None:
        parts.append(f"{stability_score_val:.0f}% stable")
    if num_runs > 1:
        parts.append(f"{avg_evaluator_consistency*100:.0f}% evaluator agreement")
    summary = ", ".join(parts)

    # No-workflow baseline lift: how much better the workflow is than a
    # single-shot LLM call. Null when baseline not measurable.
    baseline_no_workflow_score = (
        baseline_no_workflow.get("score") if baseline_no_workflow else None
    )
    lift_vs_no_workflow = (
        round(quality_score - baseline_no_workflow_score, 1)
        if baseline_no_workflow_score is not None
        else None
    )

    # Per-step breakdown (Phase 2A): which step is dragging the score?
    # Empty list when all checks target the same step (or no target_step set)
    # — the breakdown wouldn't add information vs. the overall grade.
    step_breakdown = _compute_step_breakdown(plan, checks)
    # Layer per-step variance onto each row so the UI can render a ±N pts
    # CI on each step's score. None when no per-step samples were available
    # (single-step plan or judge replay produced too few comparable verdicts).
    if per_step_variance:
        for row in step_breakdown:
            v = per_step_variance.get(row["step"])
            row["variance"] = v

    result_dict = {
        "grade": grade,
        "summary": summary,
        "checks": checks,
        "score": round(score, 1),
        "quality_score": round(quality_score, 1),
        "stability_score": round(stability_score_val, 1) if stability_score_val is not None else None,
        "stability_detail": stability_data,
        "check_pass_rate": round(check_pass_rate, 4),
        "weighted_pass_rate": round(weighted_pass_rate, 4),
        "consistency": round(avg_evaluator_consistency, 4),
        "num_runs": num_runs,
        "num_checks": total,
        "output_comparison": output_comparison,
        "baseline_no_workflow_score": baseline_no_workflow_score,
        "lift_vs_no_workflow": lift_vs_no_workflow,
        "baseline_no_workflow_detail": baseline_no_workflow,
        "step_breakdown": step_breakdown,
        "judge_variance": judge_variance,
        "static_diagnostics": static_diagnostics or [],
        "plan_stale": plan_stale,
    }

    from app.services.quality_service import persist_validation_run
    await persist_validation_run(
        item_kind="workflow",
        item_id=workflow_id,
        item_name=(wf_data or {}).get("name", ""),
        run_type="workflow",
        result=result_dict,
        user_id=(wf_data or {}).get("user_id", ""),
    )

    return result_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_array(text: str) -> list | None:
    """Best-effort extraction of a JSON array from LLM text output."""
    import json as _json

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = _json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except _json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            parsed = _json.loads(text[start:end])
            if isinstance(parsed, list):
                return parsed
        except _json.JSONDecodeError:
            pass

    return None
