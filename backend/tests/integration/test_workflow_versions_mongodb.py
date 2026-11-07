"""Workflow version history against a real MongoDB.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_workflow_versions_mongodb.py
"""

import os

import pytest

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]


async def _workflow(name="NSF Subaward Compliance Scan", prompt="Check against NSF PAPPG."):
    from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask

    task = WorkflowStepTask(name="Prompt", data={"prompt": prompt, "input_sources": ["workflow_documents"]})
    await task.insert()
    step = WorkflowStep(name="Check rules", tasks=[task.id], is_output=True)
    await step.insert()
    wf = Workflow(name=name, user_id="owner-1", steps=[step.id])
    await wf.insert()
    return wf


def _definition_with_prompt(definition, prompt):
    step = dict(definition["steps"][0])
    step["tasks"] = [{"name": "Prompt", "data": {"prompt": prompt, "input_sources": ["workflow_documents"]}}]
    return {**definition, "steps": [step]}


async def _prompt(wf):
    from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask

    wf = await Workflow.get(wf.id)
    step = await WorkflowStep.get(wf.steps[0])
    return (await WorkflowStepTask.get(step.tasks[0])).data["prompt"]


async def test_an_edit_changes_the_workflow_in_place_and_keeps_the_original(mongo_client):
    from app.models.workflow import Workflow, WorkflowStep, WorkflowVersion
    from app.services import workflow_versions

    wf = await _workflow()
    old_step_id = wf.steps[0]
    definition = await workflow_versions.current_definition(wf)
    usda = {**_definition_with_prompt(definition, "Check against USDA NIFA terms."), "name": "USDA Subaward Compliance Scan"}

    version = await workflow_versions.apply_edit(wf, usda, note="Check USDA rules instead of NSF", source="chat", user_id="owner-1")

    assert await Workflow.find_all().count() == 1
    assert version.number == 2 and (await Workflow.get(wf.id)).version == 2
    assert await _prompt(wf) == "Check against USDA NIFA terms."
    assert (await Workflow.get(wf.id)).name == "USDA Subaward Compliance Scan"
    assert await WorkflowStep.get(old_step_id) is None  # replaced steps don't linger
    original, edit = await WorkflowVersion.find(WorkflowVersion.workflow_id == str(wf.id)).sort("number").to_list()
    assert (original.source, original.note) == ("original", "Original")
    assert original.definition["steps"][0]["tasks"][0]["data"]["prompt"] == "Check against NSF PAPPG."
    assert (edit.source, edit.note) == ("chat", "Check USDA rules instead of NSF")


async def test_editor_changes_are_captured_before_a_chat_edit_replaces_them(mongo_client):
    from app.models.workflow import WorkflowStep, WorkflowStepTask
    from app.services import workflow_versions

    wf = await _workflow()
    await workflow_versions.record_version(wf, note="Original", source="original", user_id="owner-1")
    step = await WorkflowStep.get(wf.steps[0])
    task = await WorkflowStepTask.get(step.tasks[0])
    task.data = {**task.data, "prompt": "Check against NSF PAPPG, chapter II."}
    await task.save()  # an edit in the workflow editor

    history = await workflow_versions.list_versions(wf)
    assert history["unsaved_changes"] is True and history["versions"][0]["is_current"] is False

    definition = await workflow_versions.current_definition(wf)
    await workflow_versions.apply_edit(
        wf, _definition_with_prompt(definition, "Check USDA."), note="Switch to USDA", source="chat", user_id="owner-1",
    )
    history = await workflow_versions.list_versions(wf)
    assert [(v["number"], v["source"]) for v in history["versions"]] == [(3, "chat"), (2, "editor"), (1, "original")]
    assert history["unsaved_changes"] is False and history["versions"][0]["is_current"] is True


async def test_restore_brings_back_an_earlier_version_as_a_new_one(mongo_client):
    from app.models.workflow import WorkflowVersion
    from app.services import workflow_versions

    wf = await _workflow()
    definition = await workflow_versions.current_definition(wf)
    await workflow_versions.apply_edit(
        wf, _definition_with_prompt(definition, "Check USDA."), note="Switch to USDA", source="chat", user_id="owner-1",
    )
    first = await WorkflowVersion.find_one(WorkflowVersion.workflow_id == str(wf.id), WorkflowVersion.number == 1)

    restored, name_note = await workflow_versions.restore_version(wf, first, "owner-1")

    assert name_note is None
    assert (restored.number, restored.source, restored.restored_from) == (3, "restore", 1)
    assert restored.note == "Restored version 1"
    assert await _prompt(wf) == "Check against NSF PAPPG."
    history = await workflow_versions.list_versions(wf)
    # Version 1 has the same content, but only the newest is marked current.
    assert [v["is_current"] for v in history["versions"]] == [True, False, False]


async def test_restore_keeps_the_current_name_when_the_old_one_was_reused(mongo_client):
    from app.models.workflow import Workflow, WorkflowVersion
    from app.services import workflow_versions

    wf = await _workflow()
    definition = await workflow_versions.current_definition(wf)
    await workflow_versions.apply_edit(wf, {**definition, "name": "USDA Scan"}, note="Rename", source="chat", user_id="owner-1")
    await _workflow(name="NSF Subaward Compliance Scan")  # a new workflow takes the old name
    first = await WorkflowVersion.find_one(WorkflowVersion.workflow_id == str(wf.id), WorkflowVersion.number == 1)

    _, name_note = await workflow_versions.restore_version(wf, first, "owner-1")

    assert (await Workflow.get(wf.id)).name == "USDA Scan"
    assert "already named" in name_note


async def test_deleting_a_workflow_deletes_its_versions(mongo_client):
    from app.models.user import User
    from app.models.workflow import WorkflowVersion
    from app.services import workflow_service, workflow_versions

    owner = User(user_id="owner-1", email="owner@example.edu", name="Owner")
    await owner.insert()
    wf = await _workflow()
    await workflow_versions.record_version(wf, note="Original", source="original", user_id="owner-1")

    assert await workflow_service.delete_workflow(str(wf.id), owner) is True
    assert await WorkflowVersion.find(WorkflowVersion.workflow_id == str(wf.id)).count() == 0
