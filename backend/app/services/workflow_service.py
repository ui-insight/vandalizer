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
        "validation_plan": wf.validation_plan,
        "validation_inputs": wf.validation_inputs,
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

    # Copy validation plan and inputs from original
    original_wf = await Workflow.get(PydanticObjectId(workflow_id))
    if original_wf:
        if original_wf.validation_plan:
            new_wf.validation_plan = original_wf.validation_plan
        if original_wf.validation_inputs:
            new_wf.validation_inputs = original_wf.validation_inputs

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

async def run_workflow(
    workflow_id: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
    activity_id: str | None = None,
) -> str:
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
            "activity_id": activity_id,
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
# Validation Plan
# ---------------------------------------------------------------------------

async def get_validation_plan(workflow_id: str) -> list[dict]:
    """Return the workflow's persisted validation plan."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise ValueError("Workflow not found")
    return wf.validation_plan


async def update_validation_plan(workflow_id: str, checks: list[dict]) -> list[dict]:
    """Replace the workflow's validation plan with *checks*."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise ValueError("Workflow not found")
    wf.validation_plan = checks
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return wf.validation_plan


# ---------------------------------------------------------------------------
# Validation Inputs
# ---------------------------------------------------------------------------

async def get_validation_inputs(workflow_id: str) -> list[dict]:
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise ValueError("Workflow not found")
    return wf.validation_inputs


async def update_validation_inputs(workflow_id: str, inputs: list[dict]) -> list[dict]:
    wf = await Workflow.get(PydanticObjectId(workflow_id))
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
            space="__validation_temp__",
            folder="0",
        )
        await doc.insert()
        uuids.append(uid)
    return uuids


async def generate_validation_plan(workflow_id: str) -> list[dict]:
    """Use an LLM to auto-generate quality check definitions from the workflow structure."""
    import json as _json
    from app.services.llm_service import create_chat_agent
    from app.models.system_config import SystemConfig

    wf_data = await get_workflow(workflow_id)
    if not wf_data:
        raise ValueError("Workflow not found")

    # Build a detailed summary of the workflow for the LLM
    steps_summary = []
    for step in wf_data.get("steps", []):
        tasks_desc = []
        for task in step.get("tasks", []):
            task_info = f"  - Task: {task['name']}"
            data = task.get("data", {})
            if task["name"] == "Prompt" and data.get("prompt"):
                task_info += f" (prompt: {data['prompt'][:200]})"
            elif task["name"] == "Extraction" and data.get("extractions"):
                field_names = [e.get("key", "") for e in data["extractions"][:10]]
                task_info += f" (fields: {', '.join(field_names)})"
            elif task["name"] == "DataExport":
                fmt = data.get("format", "json")
                task_info += f" (format: {fmt})"
            elif task["name"] == "DocumentRenderer":
                tpl = data.get("template_type", "")
                task_info += f" (template: {tpl})"
            tasks_desc.append(task_info)
        step_desc = f"Step: {step['name']}" + (" [OUTPUT]" if step.get("is_output") else "")
        steps_summary.append(step_desc + "\n" + "\n".join(tasks_desc))

    workflow_desc = (
        f"Workflow: {wf_data.get('name', 'Unnamed')}\n"
        f"Description: {wf_data.get('description', 'No description')}\n\n"
        + "\n\n".join(steps_summary)
    )

    system_prompt = (
        "You are a workflow quality analyst. Given a workflow definition, generate 4-8 quality "
        "check DEFINITIONS that can later be evaluated against the workflow's actual output.\n\n"
        "Focus on these categories:\n"
        "- completeness: Are all expected fields/sections present?\n"
        "- formatting: Is the output in the correct format (JSON, CSV, markdown, etc.)?\n"
        "- content: Is the content meaningful, coherent, and relevant?\n"
        "- accuracy: Are there signals of correctness (consistent data, reasonable values)?\n\n"
        "Return ONLY a JSON array of check definition objects. Each object must have:\n"
        '- "name": short check name (string, max 60 chars)\n'
        '- "description": what the evaluator should look for in the output (string)\n'
        '- "category": one of "completeness", "formatting", "content", "accuracy" (string)\n\n'
        "Do NOT evaluate anything — just define what should be checked.\n"
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

async def validate_workflow(workflow_id: str) -> dict:
    """Evaluate the last execution's output against the persisted validation plan."""
    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if not wf:
        raise ValueError("Workflow not found")

    plan = wf.validation_plan
    if not plan:
        raise ValueError("No validation plan — generate or add checks first")

    wf_data = await get_workflow(workflow_id)

    # Find the most recent completed WorkflowResult
    last_results = await WorkflowResult.find(
        WorkflowResult.workflow == wf.id,
        WorkflowResult.status == "completed",
    ).sort("-_id").limit(1).to_list()

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
        return _build_result(checks, workflow_id, wf_data)

    wr = last_results[0]
    output_text = _serialize_output(wr.final_output)
    steps_output = wr.steps_output

    if output_text is None:
        checks = [
            {
                "check_id": c["id"],
                "name": c["name"],
                "status": "SKIP",
                "detail": "Binary output cannot be evaluated as text.",
            }
            for c in plan
        ]
        return _build_result(checks, workflow_id, wf_data)

    checks = await _evaluate_checks_against_output(plan, output_text, steps_output, wf_data)
    return await _build_result(checks, workflow_id, wf_data)


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

    # Include a summary of steps_output (truncated)
    steps_text = ""
    if steps_output:
        steps_text = "\n\n## Intermediate Step Outputs\n" + _json.dumps(steps_output, indent=2, default=str)[:20_000]

    system_prompt = (
        "You are a strict quality evaluator. You are given the actual output of a workflow execution "
        "and a list of quality checks to evaluate.\n\n"
        "For EACH check, determine whether it PASSES, FAILS, or deserves a WARNING based on the output.\n"
        "Cite specific evidence from the output to justify your assessment.\n\n"
        "Return ONLY a JSON array of result objects. Each object must have:\n"
        '- "check_id": the check ID from the input (string)\n'
        '- "status": one of "PASS", "FAIL", "WARN" (string)\n'
        '- "detail": specific evidence from the output justifying the status (string)\n\n'
        "Be thorough but fair. Use PASS when the check is clearly satisfied, "
        "FAIL when clearly not satisfied, WARN when partially satisfied or ambiguous.\n"
        "Return ONLY the JSON array, no other text."
    )

    user_prompt = (
        f"## Quality Checks to Evaluate\n{checks_desc}\n\n"
        f"## Workflow Final Output\n{output_text}"
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


async def _build_result(checks: list[dict], workflow_id: str, wf_data: dict | None) -> dict:
    """Compute grade, persist, and return the validation result dict."""
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
    result_dict = {"grade": grade, "summary": summary, "checks": checks}

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
