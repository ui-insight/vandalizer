"""Workflow CRUD service."""

import datetime
import uuid as uuid_mod
from typing import Optional

from beanie import PydanticObjectId
from celery.result import AsyncResult

from app.celery_app import celery_app
from app.models.search_set import SearchSet, SearchSetItem
from app.models.workflow import (
    Workflow,
    WorkflowAttachment,
    WorkflowResult,
    WorkflowStep,
    WorkflowStepTask,
)
from app.services.config_service import get_user_model_name
from app.tasks.workflow_tasks import execute_task_step_test, execute_workflow_task


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

async def create_workflow(name: str, user_id: str, space: str | None = None, description: str | None = None) -> Workflow:
    wf = Workflow(
        name=name,
        description=description,
        user_id=user_id,
        space=space,
        created_by_user_id=user_id,
    )
    await wf.insert()
    return wf


async def list_workflows(space: str | None = None, user_id: str | None = None) -> list[Workflow]:
    query = {}
    if space:
        query["space"] = space
    return await Workflow.find(query).to_list()


async def get_workflow(workflow_id: str) -> dict | None:
    """Get workflow with dereferenced steps and tasks."""
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
        "space": wf.space,
        "num_executions": wf.num_executions,
        "steps": steps,
    }


async def update_workflow(workflow_id: str, name: str | None = None, description: str | None = None) -> Workflow | None:
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        return None
    if name is not None:
        wf.name = name
    if description is not None:
        wf.description = description
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf


async def delete_workflow(workflow_id: str) -> bool:
    wf = await Workflow.get(PydanticObjectId(workflow_id))
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


async def duplicate_workflow(workflow_id: str, user_id: str) -> dict | None:
    original = await get_workflow(workflow_id)
    if not original:
        return None

    new_wf = Workflow(
        name=f"{original['name']} (Copy)",
        description=original.get("description"),
        user_id=user_id,
        space=original.get("space"),
        created_by_user_id=user_id,
    )
    await new_wf.insert()

    # Clone steps and tasks
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

    new_wf.steps = new_step_ids
    await new_wf.save()

    return await get_workflow(str(new_wf.id))


# ---------------------------------------------------------------------------
# Step CRUD
# ---------------------------------------------------------------------------

async def add_step(workflow_id: str, name: str, data: dict = {}, is_output: bool = False) -> dict | None:
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        return None

    step = WorkflowStep(name=name, data=data, is_output=is_output)
    await step.insert()
    wf.steps.append(step.id)
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()

    return {"id": str(step.id), "name": step.name, "data": step.data, "is_output": step.is_output, "tasks": []}


async def update_step(step_id: str, name: str | None = None, data: dict | None = None, is_output: bool | None = None) -> dict | None:
    step = await WorkflowStep.get(PydanticObjectId(step_id))
    if not step:
        return None
    if name is not None:
        step.name = name
    if data is not None:
        step.data = data
    if is_output is not None:
        step.is_output = is_output
    await step.save()
    return {"id": str(step.id), "name": step.name, "data": step.data, "is_output": step.is_output}


async def delete_step(step_id: str) -> bool:
    step = await WorkflowStep.get(PydanticObjectId(step_id))
    if not step:
        return False
    # Remove from parent workflow
    wf = await Workflow.find_one(Workflow.steps == step.id)
    if wf:
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

async def add_task(step_id: str, name: str, data: dict = {}) -> dict | None:
    step = await WorkflowStep.get(PydanticObjectId(step_id))
    if not step:
        return None

    task = WorkflowStepTask(name=name, data=data)
    await task.insert()
    step.tasks.append(task.id)
    await step.save()

    return {"id": str(task.id), "name": task.name, "data": task.data}


async def update_task(task_id: str, name: str | None = None, data: dict | None = None) -> dict | None:
    task = await WorkflowStepTask.get(PydanticObjectId(task_id))
    if not task:
        return None
    if name is not None:
        task.name = name
    if data is not None:
        task.data = data
    await task.save()
    return {"id": str(task.id), "name": task.name, "data": task.data}


async def delete_task(task_id: str) -> bool:
    task = await WorkflowStepTask.get(PydanticObjectId(task_id))
    if not task:
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

async def run_workflow(workflow_id: str, document_uuids: list[str], user_id: str, model: str | None = None) -> str:
    """Start workflow execution. Returns session_id for polling."""
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
    )
    await result.insert()

    trigger_step_data = {"doc_uuids": document_uuids}

    execute_workflow_task.delay(
        workflow_result_id=str(result.id),
        workflow_id=str(wf.id),
        trigger_step_data=trigger_step_data,
        model=model,
    )

    return session_id


async def get_workflow_status(session_id: str) -> dict | None:
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

    result = execute_task_step_test.delay(
        task_name=task_name,
        task_data=task_data,
        doc_uuids=document_uuids,
    )
    return result.id


def get_test_status(task_id: str) -> dict:
    """Poll a step test Celery task."""
    result = AsyncResult(task_id, app=celery_app)
    if result.ready():
        return {"status": "completed", "result": result.result}
    return {"status": result.state}
