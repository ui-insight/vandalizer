"""Workflow CRUD service."""

from __future__ import annotations

import datetime
import uuid as uuid_mod
from typing import TYPE_CHECKING

from beanie import PydanticObjectId
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
    can_view_workflow,
    get_authorized_document,
    get_authorized_workflow,
    get_team_access_context,
)
from app.services.config_service import get_user_model_name

if TYPE_CHECKING:
    from app.models.user import User


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

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


async def get_workflow(workflow_id: str, user: User | None = None) -> dict | None:
    """Get workflow with dereferenced steps and tasks."""
    if user is not None:
        wf = await get_authorized_workflow(workflow_id, user)
        if not wf:
            return None
    else:
        wf = await Workflow.get(PydanticObjectId(workflow_id))
        if not wf:
            return None

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
                    "data": task.data,
                })
        steps.append({
            "id": str(step.id),
            "name": step.name,
            "data": step.data,
            "is_output": step.is_output,
            "tasks": tasks,
        })

    return {
        "id": str(wf.id),
        "name": wf.name,
        "description": wf.description,
        "user_id": wf.user_id,
        "num_executions": wf.num_executions,
        "steps": steps,
        "input_config": wf.input_config,
        "validation_plan": wf.validation_plan,
        "validation_inputs": wf.validation_inputs,
    }


async def update_workflow(
    workflow_id: str,
    user: User,
    name: str | None = None,
    description: str | None = None,
    input_config: dict | None = None,
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


async def duplicate_workflow(workflow_id: str, user: User, user_id: str, team_id: str | None = None) -> dict | None:
    # Authorize access to the original workflow before duplicating
    wf_check = await get_authorized_workflow(workflow_id, user)
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

    result = WorkflowResult(
        workflow=wf.id,
        session_id=session_id,
        status="queued",
        num_steps_total=len(wf.steps),
        input_context={"doc_uuids": document_uuids},
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
    )

    return session_id


async def _get_authorized_workflow_result(
    session_id: str,
    user: User,
) -> WorkflowResult | None:
    result = await WorkflowResult.find_one(WorkflowResult.session_id == session_id)
    if not result or not result.workflow:
        return None

    workflow = await Workflow.get(result.workflow)
    if not workflow:
        return None

    team_access = await get_team_access_context(user)
    if not can_view_workflow(workflow, user, team_access):
        return None

    return result


async def get_workflow_status(session_id: str, user: User | None = None) -> dict | None:
    if user is not None:
        result = await _get_authorized_workflow_result(session_id, user)
    else:
        result = await WorkflowResult.find_one(WorkflowResult.session_id == session_id)
    if not result:
        return None
    return {
        "status": result.status,
        "num_steps_completed": result.num_steps_completed,
        "num_steps_total": result.num_steps_total,
        "current_step_name": result.current_step_name,
        "current_step_detail": result.current_step_detail,
        "current_step_preview": result.current_step_preview,
        "final_output": result.final_output,
        "steps_output": result.steps_output,
        "approval_request_id": result.approval_request_id,
    }


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
        workflow = await Workflow.get(first.workflow)
        if not workflow:
            return None
        team_access = await get_team_access_context(user)
        if not can_view_workflow(workflow, user, team_access):
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
    if result.ready():
        return {"status": "completed", "result": result.result}
    return {"status": result.state}


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

async def get_validation_plan(workflow_id: str, user: User) -> list[dict]:
    """Return the workflow's persisted validation plan."""
    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")
    return wf.validation_plan


async def update_validation_plan(workflow_id: str, checks: list[dict], user: User) -> list[dict]:
    """Replace the workflow's validation plan with *checks*."""
    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        raise ValueError("Workflow not found")
    wf.validation_plan = checks
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf.validation_plan


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

    system_prompt = (
        "You are a workflow output quality analyst. Your job is to generate validation "
        "checks that will be evaluated against the ACTUAL OUTPUT of a workflow — not the "
        "workflow definition itself.\n\n"
        "You will be given a detailed data flow analysis of a workflow: what each step "
        "extracts or transforms, how data flows between steps, and what the final output "
        "should contain.\n\n"
        "Generate 4-8 quality check DEFINITIONS. Each check must be something that can be "
        "verified by reading the workflow's output text.\n\n"
        "IMPORTANT — focus on these aspects:\n"
        "- **completeness**: Does the output contain ALL the specific data points that were "
        "extracted or computed upstream? Name the specific fields/values that must be present. "
        "For example, if the workflow extracts 4 fields, check that all 4 appear in the output.\n"
        "- **accuracy**: Does the extracted data appear to be faithfully carried through? "
        "Are values reasonable and consistent with what was asked for? Are any values "
        "hallucinated or contradictory?\n"
        "- **content**: Does the output fulfill the purpose described in the prompt/formatting "
        "instructions? If the workflow says 'format into human readable language', is it "
        "actually readable and well-written?\n"
        "- **formatting**: Does the output match the requested format (e.g., if the prompt "
        "asks for a paragraph, is it a paragraph and not a JSON blob)?\n\n"
        "DO NOT generate checks about:\n"
        "- The workflow definition's structure (YAML syntax, step headers, indentation)\n"
        "- Whether the workflow has a name or description\n"
        "- Step naming conventions or task formatting\n"
        "These checks are about the WORKFLOW OUTPUT, not the workflow definition.\n\n"
        "Make each check description SPECIFIC to this workflow. Reference the actual field "
        "names, prompt instructions, and expected data. A good check is one where a human "
        "reading just the check description would know exactly what to look for in the output.\n\n"
        "Return ONLY a JSON array of check definition objects. Each object must have:\n"
        '- "name": short check name (string, max 60 chars)\n'
        '- "description": detailed description of what the evaluator should look for in the '
        "output — be specific, name the fields and values (string)\n"
        '- "category": one of "completeness", "formatting", "content", "accuracy" (string)\n\n'
        "Return ONLY the JSON array, no other text."
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
        result = await agent.run(f"## Workflow\n{workflow_desc}")
    except Exception:
        raise ValueError("LLM call failed — could not generate validation plan")

    parsed = _parse_json_array(result.output)
    if parsed is None:
        raise ValueError("Could not parse LLM response into a validation plan")

    # Normalize into check definitions with UUIDs
    checks: list[dict] = []
    valid_categories = {"completeness", "formatting", "content", "accuracy"}
    for item in parsed:
        if not isinstance(item, dict) or "name" not in item:
            continue
        cat = str(item.get("category", "content")).lower()
        if cat not in valid_categories:
            cat = "content"
        checks.append({
            "id": str(uuid_mod.uuid4()),
            "name": str(item["name"])[:60],
            "description": str(item.get("description", "")),
            "category": cat,
        })

    # Persist
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if wf:
        wf.validation_plan = checks
        wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await wf.save()

    return checks


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


def _compute_output_stability(results: list) -> dict:
    """Compare actual workflow outputs across multiple executions.

    Returns a stability dict with a 0-1 score representing how similar the
    outputs are to each other, plus diagnostic details.
    """
    if len(results) < 2:
        return {"stability_score": None, "detail": "Need 2+ runs for stability measurement"}

    # Serialize all outputs to text
    text_outputs = []
    for r in results:
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
    structured_stability = _structured_field_stability(results)

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
        raise ValueError("No validation plan — generate or add checks first")

    wf_data = await get_workflow(workflow_id)

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
            run_checks = await _evaluate_checks_against_output(plan, output_text, wr.steps_output, wf_data)
        all_run_checks.append(run_checks)

    # Merge multi-run results with consistency tracking
    checks = _merge_multi_run_checks(plan, all_run_checks)

    # Deterministic comparison against stored expected outputs
    expected_outputs = [inp for inp in wf.validation_inputs if inp.get("type") == "expected_output"]
    output_comparison = None
    if expected_outputs and last_results:
        output_comparison = _compare_outputs(last_results, expected_outputs)

    return await _build_result(
        checks, workflow_id, wf_data,
        num_runs=len(all_run_checks),
        output_comparison=output_comparison,
        stability_data=stability_data,
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


async def _evaluate_checks_against_output(
    plan: list[dict],
    output_text: str,
    steps_output: dict,
    wf_data: dict,
) -> list[dict]:
    """Single LLM call to evaluate all checks against the actual output."""
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
    if steps_output:
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

    system_prompt = (
        "You are a strict quality evaluator for workflow outputs. You will be given:\n"
        "1. A list of quality checks to evaluate\n"
        "2. The final output of a workflow execution\n"
        "3. The source document text (when available) — this is ground truth\n"
        "4. Intermediate step outputs (to cross-reference data flow)\n\n"
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
        "For EACH check, determine: PASS, FAIL, or WARN.\n"
        "Cite specific evidence from the output (quote actual text/values) to justify "
        "your assessment. When checking accuracy, quote both the output value and the "
        "source document value for comparison.\n\n"
        "Return ONLY a JSON array of result objects. Each object must have:\n"
        '- "check_id": the check ID from the input (string)\n'
        '- "status": one of "PASS", "FAIL", "WARN" (string)\n'
        '- "detail": specific evidence from the output justifying the status — quote '
        "actual values and text (string)\n\n"
        "Return ONLY the JSON array, no other text."
    )

    user_prompt = (
        f"## Quality Checks to Evaluate\n{checks_desc}\n\n"
        f"## Workflow Final Output\n{output_text}"
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
