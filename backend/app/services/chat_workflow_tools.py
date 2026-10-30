"""Chat tools for reading and editing an existing workflow.

``create_workflow`` makes a new workflow; asked to change one ("check for
USDA compliance instead of NSF"), the assistant used to call it again and
leave two workflows in the library. ``update_workflow`` edits the workflow in
place and records the change in its version history (see
``workflow_versions``), from which any earlier version can be restored.

Registered in ``chat_tools.TOOLS``. The chat_tools helpers are imported
inside the functions, since chat_tools imports this module.
"""

import logging
from typing import Optional

from pydantic_ai.tools import RunContext

from app.services.chat_deps import AgenticChatDeps

logger = logging.getLogger(__name__)

# Task name → the friendly step type create_workflow / update_workflow take.
_TASK_TYPES = {
    "Extraction": "extraction",
    "Prompt": "prompt",
    "Formatter": "format",
    "ResearchNode": "research",
    "KnowledgeBaseQuery": "knowledge_base_query",
    "AddWebsite": "website",
    "WebSearch": "web_search",
    "Approval": "approval",
}
_INSTRUCTION_KEYS = ("prompt", "format_template", "question", "query", "review_instructions", "url")


def _describe_step(step: dict) -> dict:
    task = (step.get("tasks") or [{}])[0]
    data = task.get("data") or {}
    described = {
        "name": step.get("name", ""),
        "type": _TASK_TYPES.get(task.get("name", ""), task.get("name", "")),
        "is_output": bool(step.get("is_output")),
    }
    for key in _INSTRUCTION_KEYS:
        if data.get(key):
            described["instruction"] = str(data[key])[:2000]
            break
    if data.get("extractions"):
        described["extractions"] = [str(f) for f in data["extractions"]][:100]
    if data.get("search_set_uuid"):
        described["extraction_set_uuid"] = data["search_set_uuid"]
    if data.get("kb_uuid"):
        described["kb_uuid"] = data["kb_uuid"]
    if len(step.get("tasks") or []) > 1:
        described["note"] = f"{len(step['tasks'])} tasks; keep this step to preserve all of them"
    return described


def _input_mode(input_config: dict) -> str:
    trigger = (input_config or {}).get("trigger_type")
    return trigger if trigger in ("text_input", "no_input") else "documents"


async def get_workflow_definition(
    context: RunContext[AgenticChatDeps],
    workflow_id: str,
) -> dict:
    """Read an existing workflow's steps, so it can be changed with update_workflow.

    Call this before update_workflow to see each step's name, type and
    instruction. Get the workflow_id from create_workflow's result or from
    list_workflows.

    Args:
        context: The call context.
        workflow_id: The workflow's id.
    """
    from beanie import PydanticObjectId

    from app.models.workflow import Workflow
    from app.services import workflow_service

    try:
        wf = await workflow_service.get_workflow(workflow_id, context.deps.user)
    except Exception:
        wf = None
    if not wf:
        return {"error": "Workflow not found, or you don't have access to it."}
    doc = await Workflow.get(PydanticObjectId(workflow_id))
    return {
        "workflow_id": wf["id"],
        "name": wf["name"],
        "description": wf.get("description") or "",
        "input_mode": _input_mode(wf.get("input_config") or {}),
        "version": doc.version if doc else None,
        "can_edit": bool(wf.get("can_manage")),
        "steps": [_describe_step(s) for s in wf.get("steps", [])],
    }


async def update_workflow(
    context: RunContext[AgenticChatDeps],
    workflow_id: str,
    change_summary: str,
    steps: list[dict] | None = None,
    name: str | None = None,
    description: str | None = None,
    confirmed: bool = False,
) -> dict:
    """Change an existing workflow in place, keeping its earlier versions.

    Use this whenever the user asks to change, fix, adjust or retarget a
    workflow that already exists, including one you just created in this
    conversation ("make it check USDA rules instead of NSF"). Do NOT call
    create_workflow for an edit: that makes a second workflow. Each update is
    saved as a new version in the workflow's Versions tab, tagged with
    ``change_summary``, and any earlier version can be restored from there.

    Read the workflow first with get_workflow_definition.

    ``steps``, when given, is the complete new ordered list of steps. Each
    entry is either:
      - {"keep": "<existing step name>"}: keep that step exactly as it is,
        including settings chat can't see. Prefer this for every step the
        change doesn't touch.
      - a new step spec, exactly as create_workflow takes it ("name", "type",
        "prompt" / "extractions" / "format_template" / …, "is_output").
    Omit ``steps`` to change only the name or description.

    Call first with confirmed=false to preview the change, then confirmed=true
    after the user approves.

    Args:
        context: The call context.
        workflow_id: The workflow to change.
        change_summary: One short line saying what changed, shown in the
            version history (e.g. "Check USDA rules instead of NSF").
        steps: Optional complete new step list (see above).
        name: Optional new name.
        description: Optional new description.
        confirmed: Must be true to apply. If false, returns a preview.
    """
    from app.models.workflow import Workflow
    from app.services import name_conflicts, workflow_service, workflow_versions
    from app.services.access_control import get_authorized_workflow
    from app.services.chat_tools import _WORKFLOW_STEP_TYPES, _build_workflow_step_data, _confirm_gate

    user = context.deps.user
    change_summary = (change_summary or "").strip()
    if not change_summary:
        return {"error": "Say what the change is in change_summary; it labels this version in the workflow's history."}
    if steps is None and name is None and description is None:
        return {"error": "Nothing to change: pass steps, name or description."}
    wf: Optional[Workflow] = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        readable = await get_authorized_workflow(workflow_id, user)
        if readable:
            return {"error": (
                f"You can view \"{readable.name}\" but not edit it. Its owner or a team admin can change it, "
                "or you can make your own copy from the workflow editor."
            )}
        return {"error": "Workflow not found, or you don't have access to it."}

    current = await workflow_versions.current_definition(wf)
    new_def = dict(current)

    if name is not None:
        name = name.strip()
        if not name:
            return {"error": "The workflow name can't be empty."}
        if name != wf.name and await name_conflicts.workflow_name_taken(
            name, wf.user_id, wf.team_id, exclude_id=str(wf.id),
        ):
            return {"error": f'Another workflow is already named "{name}". Choose a different name.'}
        new_def["name"] = name
    if description is not None:
        new_def["description"] = description.strip() or None

    preview_steps: list[str] = []
    if steps is not None:
        if not isinstance(steps, list) or not steps:
            return {"error": "steps must be a non-empty list. Use {\"keep\": \"<step name>\"} for steps that stay the same."}
        if len(steps) > 25:
            return {"error": "Keep workflows to 25 or fewer steps."}
        existing = {s["name"]: s for s in current["steps"]}
        model = context.deps.model_name or None
        built: list[dict] = []
        first_doc_step_wired = False
        for idx, spec in enumerate(steps):
            if not isinstance(spec, dict):
                return {"error": f"Step {idx + 1} is malformed (expected an object)."}
            if "keep" in spec:
                kept = existing.get(str(spec["keep"]))
                if not kept:
                    return {"error": (
                        f"Step {idx + 1}: there is no step named \"{spec['keep']}\". "
                        f"Existing steps: {', '.join(existing) or 'none'}."
                    )}
                if any("workflow_documents" in ((t.get("data") or {}).get("input_sources") or []) for t in kept["tasks"]):
                    first_doc_step_wired = True
                built.append(kept)
                preview_steps.append(f"{idx + 1}. {kept['name']} (unchanged)")
                continue
            raw_type = str(spec.get("type") or "").strip().lower()
            if raw_type not in _WORKFLOW_STEP_TYPES:
                return {"error": (
                    f"Step {idx + 1} has an unknown type '{spec.get('type')}'. "
                    f"Valid types: {', '.join(sorted(set(_WORKFLOW_STEP_TYPES)))}, or {{\"keep\": \"<step name>\"}}."
                )}
            task_name, doc_consuming = _WORKFLOW_STEP_TYPES[raw_type]
            data, err = await _build_workflow_step_data(context, spec, raw_type, model)
            if err or data is None:
                return {"error": f"Step {idx + 1} ({spec.get('name') or raw_type}): {err}."}
            # Same linear wiring as create_workflow.
            if doc_consuming:
                if not first_doc_step_wired:
                    data["input_sources"] = ["workflow_documents"]
                    first_doc_step_wired = True
                elif raw_type == "format":
                    data["input_sources"] = ["earlier_steps"]
                else:
                    data["input_sources"] = ["step_input"]
            label = str(spec.get("name") or f"Step {idx + 1}").strip()
            built.append({
                "name": label,
                "is_output": bool(spec.get("is_output")),
                "data": {},
                "tasks": [{"name": task_name, "data": data}],
            })
            preview_steps.append(f"{idx + 1}. {label} ({raw_type}, {'changed' if label in existing else 'new'})")
        if not any(s["is_output"] for s in built):
            built[-1]["is_output"] = True
        new_def["steps"] = built

    if workflow_versions.definition_hash(new_def) == workflow_versions.definition_hash(current):
        return {"error": "That leaves the workflow exactly as it is. Nothing to update."}

    parts = [f"Update workflow \"{wf.name}\": {change_summary}."]
    if name is not None and name != wf.name:
        parts.append(f"Rename to \"{name}\".")
    if preview_steps:
        parts.append("Steps: " + "; ".join(preview_steps) + ".")
    parts.append("The current version stays in the workflow's version history.")
    gate = await _confirm_gate(
        context,
        tool_name="update_workflow",
        key={
            "workflow_id": workflow_id,
            "summary": change_summary,
            "name": name,
            "description": description,
            "steps": workflow_versions.definition_hash({"steps": new_def["steps"]}),
        },
        preview={
            "action": "update_workflow",
            "workflow_id": workflow_id,
            "preview": " ".join(parts),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    try:
        version = await workflow_versions.apply_edit(
            wf, new_def, note=change_summary, source="chat", user_id=context.deps.user_id,
        )
    except Exception:
        logger.exception("update_workflow failed for %s", workflow_id)
        return {"error": "Something went wrong updating the workflow. Its previous version is unchanged; try again."}

    stale_plan = bool(wf.validation_plan) and (
        wf.validation_plan_definition_hash
        and wf.validation_plan_definition_hash != workflow_service.compute_workflow_definition_hash(
            await workflow_service.get_workflow(str(wf.id))
        )
    )
    message = (
        f"Updated \"{wf.name}\" (version {version.number}): {change_summary}. "
        "Earlier versions are in the workflow's Versions tab and can be restored."
    )
    if stale_plan:
        message += " Its validation plan was written for the earlier steps; review it in the Validate tab."
    return {
        "workflow_id": str(wf.id),
        "name": wf.name,
        "version": version.number,
        "steps": len(new_def["steps"]),
        "message": message,
    }
