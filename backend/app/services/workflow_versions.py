"""Workflow version history.

A workflow is edited in place; its history lives in ``WorkflowVersion``
records, each holding the full definition (name, description, input and
output settings, steps and their tasks) as it stood after one change.

Versions are recorded when chat edits a workflow, when a version is restored,
and when someone saves a version from the editor. The editor itself saves
step by step, so its changes aren't versioned one keystroke at a time; they
are captured as an "Edited in the workflow editor" version the next time a
version is recorded, so nothing is lost when chat edits or a restore replaces
the steps.
"""

from __future__ import annotations

import datetime
import logging

from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask, WorkflowVersion
from app.services import name_conflicts
from app.services.quality_service import compute_config_hash

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "original": "Original",
    "chat": "Edited in chat",
    "editor": "Edited in the workflow editor",
    "restore": "Restored",
}


async def current_definition(wf: Workflow) -> dict:
    """The workflow's authored definition, in the shape versions store."""
    from app.services.workflow_service import _sanitize_for_json

    steps = []
    for step_id in wf.steps:
        step = await WorkflowStep.get(step_id)
        if not step:
            continue
        tasks = []
        for task_id in step.tasks:
            task = await WorkflowStepTask.get(task_id)
            if task:
                tasks.append({"name": task.name, "data": _sanitize_for_json(task.data or {})})
        steps.append({
            "name": step.name,
            "is_output": bool(step.is_output),
            "data": _sanitize_for_json(step.data or {}),
            "tasks": tasks,
        })
    return {
        "name": wf.name,
        "description": wf.description,
        "input_config": _sanitize_for_json(wf.input_config or {}),
        "output_config": _sanitize_for_json(wf.output_config or {}),
        "steps": steps,
    }


def definition_hash(definition: dict) -> str:
    return compute_config_hash(definition)


async def latest_version(workflow_id: str) -> WorkflowVersion | None:
    return await WorkflowVersion.find(
        WorkflowVersion.workflow_id == workflow_id,
    ).sort("-number").first_or_none()


async def record_version(
    wf: Workflow,
    *,
    note: str,
    source: str,
    user_id: str | None,
    definition: dict | None = None,
    restored_from: int | None = None,
) -> WorkflowVersion:
    """Record the workflow's current definition as its next version."""
    definition = definition if definition is not None else await current_definition(wf)
    latest = await latest_version(str(wf.id))
    version = WorkflowVersion(
        workflow_id=str(wf.id),
        number=(latest.number + 1) if latest else 1,
        note=(note or SOURCE_LABELS.get(source, "Saved")).strip()[:500],
        source=source,
        created_by_user_id=user_id,
        definition=definition,
        definition_hash=definition_hash(definition),
        restored_from=restored_from,
    )
    await version.insert()
    wf.version = version.number
    await wf.save()
    return version


async def capture_unrecorded(wf: Workflow, user_id: str | None) -> WorkflowVersion | None:
    """Record the current definition if no version holds it yet.

    The first time, that is the workflow as it was before versioning reached
    it ("Original"); afterwards, changes made in the editor since the last
    version. Returns the version recorded, or None when history is current.
    """
    definition = await current_definition(wf)
    latest = await latest_version(str(wf.id))
    if latest and latest.definition_hash == definition_hash(definition):
        return None
    if latest is None:
        return await record_version(wf, note="Original", source="original", user_id=user_id, definition=definition)
    return await record_version(
        wf, note=SOURCE_LABELS["editor"], source="editor", user_id=user_id, definition=definition,
    )


async def replace_definition(wf: Workflow, definition: dict) -> None:
    """Make ``definition`` the workflow's steps and settings, in place.

    New step and task documents are written first and the workflow is pointed
    at them before the old ones are removed, so a failure part-way leaves the
    workflow on its previous steps rather than on none.
    """
    old_step_ids = list(wf.steps)
    new_step_ids = []
    for step_data in definition.get("steps", []):
        task_ids = []
        for task_data in step_data.get("tasks", []):
            task = WorkflowStepTask(name=task_data["name"], data=dict(task_data.get("data") or {}))
            await task.insert()
            task_ids.append(task.id)
        step = WorkflowStep(
            name=step_data["name"],
            tasks=task_ids,
            data=dict(step_data.get("data") or {}),
            is_output=bool(step_data.get("is_output")),
        )
        await step.insert()
        new_step_ids.append(step.id)

    wf.steps = new_step_ids
    if definition.get("name"):
        wf.name = definition["name"]
    wf.description = definition.get("description")
    wf.input_config = dict(definition.get("input_config") or {})
    wf.output_config = dict(definition.get("output_config") or {})
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()

    for step_id in old_step_ids:
        step = await WorkflowStep.get(step_id)
        if not step:
            continue
        for task_id in step.tasks:
            task = await WorkflowStepTask.get(task_id)
            if task:
                await task.delete()
        await step.delete()


async def apply_edit(
    wf: Workflow, definition: dict, *, note: str, source: str, user_id: str | None,
    restored_from: int | None = None,
) -> WorkflowVersion:
    """Edit the workflow in place and record the result as a new version.

    Unrecorded editor changes are saved as their own version first, so the
    state being replaced can always be restored.
    """
    await capture_unrecorded(wf, user_id)
    await replace_definition(wf, definition)
    return await record_version(
        wf, note=note, source=source, user_id=user_id, restored_from=restored_from,
    )


async def restore_version(wf: Workflow, version: WorkflowVersion, user_id: str | None) -> tuple[WorkflowVersion, str | None]:
    """Make an earlier version current again, recorded as a new version.

    Returns the new version and, when the old name now belongs to another
    workflow, a note that the current name was kept.
    """
    definition = dict(version.definition)
    name_note = None
    old_name = definition.get("name")
    if old_name and old_name != wf.name and await name_conflicts.workflow_name_taken(
        old_name, wf.user_id, wf.team_id, exclude_id=str(wf.id),
    ):
        definition["name"] = wf.name
        name_note = f'Kept the name "{wf.name}": another workflow is already named "{old_name}".'
    restored = await apply_edit(
        wf, definition, note=f"Restored version {version.number}", source="restore",
        user_id=user_id, restored_from=version.number,
    )
    return restored, name_note


async def list_versions(wf: Workflow) -> dict:
    """The version history, newest first, and whether the workflow has
    changed since the newest version (editor edits not yet saved as one)."""
    versions = await WorkflowVersion.find(
        WorkflowVersion.workflow_id == str(wf.id),
    ).sort("-number").to_list()
    current_hash = definition_hash(await current_definition(wf))
    rows = [
        {
            "id": str(v.id),
            "number": v.number,
            "note": v.note,
            "source": v.source,
            "created_by_user_id": v.created_by_user_id,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "restored_from": v.restored_from,
            "name": v.definition.get("name"),
            "step_names": [s.get("name", "") for s in v.definition.get("steps", [])],
            # Only the newest version can be "current": a restore makes a
            # later version with the same content as an earlier one.
            "is_current": index == 0 and v.definition_hash == current_hash,
        }
        for index, v in enumerate(versions)
    ]
    return {
        "versions": rows,
        # True when the workflow holds changes no version records yet,
        # including a workflow that has never been versioned.
        "unsaved_changes": not versions or versions[0].definition_hash != current_hash,
    }


async def delete_versions(workflow_id: str) -> None:
    await WorkflowVersion.find(WorkflowVersion.workflow_id == workflow_id).delete()
