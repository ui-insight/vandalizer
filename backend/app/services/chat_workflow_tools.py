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


# Task types whose input comes from input_sources (doc-consuming step types).
_SOURCE_READING_TASKS = {"Extraction", "Prompt", "Formatter", "ResearchNode"}


def _task_sources(data: dict) -> list[str]:
    raw = data.get("input_sources")
    if isinstance(raw, list) and raw:
        return [str(s) for s in raw]
    return [str(data.get("input_source") or "step_input")]


def _rewire_moved_steps(current_steps: list[dict], built: list[dict], kept: set[int]) -> dict[int, str]:
    """Keep each kept step reading what it read before the edit.

    "Previous step output" names a position, not a step. Support ticket: chat
    inserted "Flag F&A rate above 50%" between an extraction and the PI
    summary, kept the summary "unchanged", and the summary then saw only the
    one-line flag. A kept step whose predecessor changed is rewired: one that
    followed a step now reads all earlier steps (its old input is still among
    them); one that was first, reading the workflow documents through the
    trigger, now reads them directly. Returns a preview note per rewired index.
    """
    import copy

    old_names = [s["name"] for s in current_steps]
    old_prev = {name: (old_names[i - 1] if i else None) for i, name in enumerate(old_names)}
    notes: dict[int, str] = {}
    for idx in sorted(kept):
        step = built[idx]
        before = old_prev.get(step["name"])
        after = built[idx - 1]["name"] if idx else None
        if before == after:
            continue
        if after is None:
            # Now first: "previous step output" is the trigger's documents,
            # and there are no earlier steps to read instead.
            if any(task.get("name") in _SOURCE_READING_TASKS and isinstance(task.get("data"), dict)
                   and "step_input" in _task_sources(task["data"]) for task in step.get("tasks") or []):
                notes[idx] = f'input changed: now first, it reads the workflow documents instead of "{before}"'
            continue
        rewired = copy.deepcopy(step)
        changed = False
        for task in rewired.get("tasks") or []:
            data = task.get("data")
            if task.get("name") not in _SOURCE_READING_TASKS or not isinstance(data, dict):
                continue
            sources = _task_sources(data)
            if "step_input" not in sources:
                continue
            replacement = "workflow_documents" if before is None else "earlier_steps"
            new_sources: list[str] = []
            for source in sources:
                source = replacement if source == "step_input" else source
                if source not in new_sources:
                    new_sources.append(source)
            data["input_sources"] = new_sources
            data.pop("input_source", None)
            changed = True
        if not changed:
            continue
        built[idx] = rewired
        if before is None:
            notes[idx] = "input rewired: still reads the workflow documents, now that a step comes before it"
        elif before in {b["name"] for b in built}:
            notes[idx] = (f'input rewired: now reads all earlier steps, so it still gets "{before}" '
                          f'and not only "{after}"')
        else:
            notes[idx] = (f'input rewired: "{before}", the step it read, is removed; '
                          "it now reads all earlier steps")
    return notes


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
        change doesn't touch. A kept step that read the previous step's
        output and gets a new step before it is rewired to read all earlier
        steps, so it keeps its old input; the preview says so. To add a
        check without touching what other steps read, put it at the end.
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
        kept_indexes: set[int] = set()
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
                kept_indexes.add(len(built))
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
        for idx, note in _rewire_moved_steps(current["steps"], built, kept_indexes).items():
            preview_steps[idx] = f"{idx + 1}. {built[idx]['name']} ({note})"
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
