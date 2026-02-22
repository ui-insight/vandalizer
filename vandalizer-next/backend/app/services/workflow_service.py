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

    celery_app.send_task(
        "tasks.workflow_next.execution",
        kwargs={
            "workflow_result_id": str(result.id),
            "workflow_id": str(wf.id),
            "trigger_step_data": trigger_step_data,
            "model": model,
        },
        queue="workflows",
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

async def reorder_steps(workflow_id: str, step_ids: list[str]) -> bool:
    """Reorder steps in a workflow by providing the full ordered list of step IDs."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
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
# Validation
# ---------------------------------------------------------------------------

async def validate_workflow(
    workflow_id: str,
    eval_plan: str | None = None,
    text_input: str | None = None,
) -> dict:
    """Run validation checks on a workflow and return grade + check results."""
    wf_data = await get_workflow(workflow_id)
    if not wf_data:
        raise ValueError("Workflow not found")

    checks = []
    steps = wf_data.get("steps", [])

    # Check 1: Has at least one step
    if len(steps) > 0:
        checks.append({"name": "Has steps", "status": "PASS", "detail": f"{len(steps)} step(s) defined"})
    else:
        checks.append({"name": "Has steps", "status": "FAIL", "detail": "No steps defined"})

    # Check 2: All steps have at least one task
    empty_steps = [s["name"] for s in steps if len(s.get("tasks", [])) == 0]
    if not empty_steps:
        checks.append({"name": "Steps have tasks", "status": "PASS", "detail": "All steps have at least one task"})
    elif steps:
        checks.append({"name": "Steps have tasks", "status": "WARN", "detail": f"Empty steps: {', '.join(empty_steps)}"})
    else:
        checks.append({"name": "Steps have tasks", "status": "SKIP", "detail": "No steps to check"})

    # Check 3: Has an output step
    output_steps = [s for s in steps if s.get("is_output")]
    if output_steps:
        checks.append({"name": "Output step defined", "status": "PASS", "detail": f"Output step: {output_steps[0]['name']}"})
    else:
        checks.append({"name": "Output step defined", "status": "WARN", "detail": "No output step designated"})

    # Check 4: Has been executed at least once
    if wf_data.get("num_executions", 0) > 0:
        checks.append({"name": "Has been tested", "status": "PASS", "detail": f"Executed {wf_data['num_executions']} time(s)"})
    else:
        checks.append({"name": "Has been tested", "status": "WARN", "detail": "Never executed"})

    # Check 5: Last run succeeded (check most recent result)
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    last_result = await WorkflowResult.find(
        WorkflowResult.workflow == wf.id
    ).sort("-_id").limit(1).to_list()

    if last_result:
        result = last_result[0]
        if result.status == "completed":
            checks.append({"name": "Last run succeeded", "status": "PASS", "detail": "Last execution completed successfully"})
        elif result.status in ("error", "failed"):
            checks.append({"name": "Last run succeeded", "status": "FAIL", "detail": f"Last execution status: {result.status}"})
        else:
            checks.append({"name": "Last run succeeded", "status": "SKIP", "detail": f"Last execution status: {result.status}"})
    else:
        checks.append({"name": "Last run succeeded", "status": "SKIP", "detail": "No execution history"})

    # Check 6: Extraction tasks have search set configured
    for step in steps:
        for task in step.get("tasks", []):
            if task["name"] == "Extraction":
                if task.get("data", {}).get("search_set_uuid") or task.get("data", {}).get("extractions"):
                    checks.append({"name": f"Extraction configured ({step['name']})", "status": "PASS", "detail": "Extraction fields defined"})
                else:
                    checks.append({"name": f"Extraction configured ({step['name']})", "status": "WARN", "detail": "No extraction fields configured"})
            elif task["name"] == "Prompt":
                if task.get("data", {}).get("prompt"):
                    checks.append({"name": f"Prompt configured ({step['name']})", "status": "PASS", "detail": "Prompt text defined"})
                else:
                    checks.append({"name": f"Prompt configured ({step['name']})", "status": "WARN", "detail": "No prompt text"})

    # LLM-powered checks from eval_plan
    if eval_plan and eval_plan.strip():
        llm_checks = await _generate_llm_checks(wf_data, eval_plan, text_input)
        checks.extend(llm_checks)

    # Calculate grade
    statuses = [c["status"] for c in checks]
    fail_count = statuses.count("FAIL")
    warn_count = statuses.count("WARN")
    pass_count = statuses.count("PASS")
    total = len(checks)

    if fail_count == 0 and warn_count == 0:
        grade = "A"
    elif fail_count == 0 and warn_count <= 1:
        grade = "B"
    elif fail_count == 0:
        grade = "C"
    elif fail_count == 1:
        grade = "D"
    else:
        grade = "F"

    summary = f"{pass_count}/{total} checks passed, {warn_count} warnings, {fail_count} failures"

    return {"grade": grade, "summary": summary, "checks": checks}


async def _generate_llm_checks(
    wf_data: dict,
    eval_plan: str,
    text_input: str | None = None,
) -> list[dict]:
    """Use an LLM to generate validation checks based on the eval plan."""
    import json as _json
    from app.services.llm_service import create_chat_agent
    from app.models.system_config import SystemConfig

    # Build workflow summary for the LLM
    steps_summary = []
    for step in wf_data.get("steps", []):
        tasks_desc = []
        for task in step.get("tasks", []):
            task_info = f"  - Task: {task['name']}"
            data = task.get("data", {})
            if task["name"] == "Prompt" and data.get("prompt"):
                task_info += f" (prompt: {data['prompt'][:200]})"
            elif task["name"] == "Extraction" and data.get("extractions"):
                task_info += f" (fields: {', '.join(e.get('key', '') for e in data['extractions'][:10])})"
            tasks_desc.append(task_info)
        step_desc = f"Step: {step['name']}" + (" [OUTPUT]" if step.get("is_output") else "")
        steps_summary.append(step_desc + "\n" + "\n".join(tasks_desc))

    workflow_desc = (
        f"Workflow: {wf_data.get('name', 'Unnamed')}\n"
        f"Description: {wf_data.get('description', 'No description')}\n\n"
        + "\n\n".join(steps_summary)
    )

    system_prompt = (
        "You are a workflow validation assistant. Given a workflow definition and an evaluation plan, "
        "generate validation checks that assess whether the workflow meets the criteria described in the evaluation plan.\n\n"
        "Return ONLY a JSON array of check objects. Each object must have:\n"
        '- "name": short check name (string)\n'
        '- "status": one of "PASS", "FAIL", "WARN", or "SKIP" (string)\n'
        '- "detail": explanation of the check result (string)\n\n'
        "Assess the workflow structure against the evaluation criteria. "
        "Use PASS when a criterion is clearly met, FAIL when clearly not met, "
        "WARN when partially met or uncertain, and SKIP when not applicable.\n\n"
        "Return ONLY the JSON array, no other text."
    )

    user_prompt = f"## Workflow\n{workflow_desc}\n\n## Evaluation Plan\n{eval_plan}"
    if text_input and text_input.strip():
        user_prompt += f"\n\n## Sample Input Text\nThe following is sample text that this workflow should be able to handle:\n{text_input[:50000]}"

    # Resolve model — use a default model for validation
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
        return [{"name": "Eval plan analysis", "status": "SKIP", "detail": "LLM call failed — could not generate eval checks"}]

    # Parse JSON from response
    text = result.output.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = _json.loads(text)
    except _json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                parsed = _json.loads(text[start:end])
            except _json.JSONDecodeError:
                return [{"name": "Eval plan analysis", "status": "SKIP", "detail": "Could not parse LLM response"}]
        else:
            return [{"name": "Eval plan analysis", "status": "SKIP", "detail": "Could not parse LLM response"}]

    if not isinstance(parsed, list):
        return [{"name": "Eval plan analysis", "status": "SKIP", "detail": "Unexpected LLM response format"}]

    # Normalize and validate each check
    valid_statuses = {"PASS", "FAIL", "WARN", "SKIP"}
    llm_checks = []
    for item in parsed:
        if not isinstance(item, dict) or "name" not in item:
            continue
        status = str(item.get("status", "SKIP")).upper()
        if status not in valid_statuses:
            status = "SKIP"
        llm_checks.append({
            "name": str(item["name"]),
            "status": status,
            "detail": str(item.get("detail", "")),
        })

    return llm_checks
