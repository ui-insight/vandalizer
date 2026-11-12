"""A project pin never grants access to what it points at.

Pinning, listing and running a pin each check the person's own access to the
pinned workflow, extraction, automation or knowledge base.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import access_control, chat_tools, project_service

BOB = SimpleNamespace(user_id="bob")
PROJECT = SimpleNamespace(uuid="p1", title="S1 Test")
PIN_TYPES = ["workflow", "extraction", "automation", "knowledge_base"]
LOOKUPS = {
    "workflow": "get_authorized_workflow",
    "extraction": "get_authorized_search_set",
    "automation": "get_authorized_automation",
    "knowledge_base": "get_authorized_knowledge_base",
}


def _no_access():
    """Every access check answers 'not yours' (or 'does not exist')."""
    return [patch.object(access_control, name, AsyncMock(return_value=None)) for name in LOOKUPS.values()]


def _context():
    context = MagicMock()
    context.deps.user = BOB
    context.deps.user_id = "bob"
    return context


@pytest.mark.parametrize("pin_type", PIN_TYPES)
async def test_pinning_something_you_cannot_open_is_refused(pin_type):
    patches = _no_access()
    with patch.object(project_service, "can_manage_project", AsyncMock(return_value=True)), \
         patch.object(project_service, "ProjectPin") as model, \
         patches[0], patches[1], patches[2], patches[3]:
        with pytest.raises(ValueError) as refused:
            await project_service.add_pin(PROJECT, pin_type, "a-private-id", BOB)
    assert str(refused.value).startswith("You don't have access to this ")
    # Nothing was looked up or written by id.
    model.assert_not_called()
    model.find_one.assert_not_called()


async def test_pinning_your_own_workflow_still_works():
    insert = AsyncMock()
    with patch.object(project_service, "can_manage_project", AsyncMock(return_value=True)), \
         patch.object(access_control, "get_authorized_workflow", AsyncMock(return_value=SimpleNamespace(name="Mine"))), \
         patch.object(project_service, "ProjectPin") as model:
        model.find_one = AsyncMock(return_value=None)
        model.return_value.insert = insert
        await project_service.add_pin(PROJECT, "workflow", "wf-1", BOB)
    insert.assert_awaited_once()


async def test_a_pin_you_cannot_open_is_not_listed_so_its_name_is_never_shown():
    pins = [
        SimpleNamespace(pin_type="workflow", target_id="a-private-id"),
        SimpleNamespace(pin_type="workflow", target_id="bobs"),
        SimpleNamespace(pin_type="extraction", target_id="a-private-set"),
    ]

    async def workflow(target_id, user, **_):
        return SimpleNamespace(name="Bob's workflow") if target_id == "bobs" else None

    with patch.object(project_service, "ProjectPin") as model, \
         patch.object(access_control, "get_authorized_workflow", AsyncMock(side_effect=workflow)), \
         patch.object(access_control, "get_authorized_search_set", AsyncMock(return_value=None)):
        model.find.return_value.to_list = AsyncMock(return_value=pins)
        listed = await project_service.list_pins(PROJECT, BOB)
        # With no viewer there is nobody to check against: nothing is named.
        unnamed = await project_service.list_pins(PROJECT)

    assert listed == [{"pin_type": "workflow", "target_id": "bobs", "name": "Bob's workflow"}]
    assert unnamed == []


@pytest.mark.parametrize("pin_type", ["workflow", "extraction"])
async def test_running_a_pin_you_cannot_open_is_refused_without_its_name(pin_type):
    # A pin already on the project, but not Bob's to open.
    pins = [SimpleNamespace(pin_type=pin_type, target_id="a-private-id")]
    patches = _no_access()
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=PROJECT)), \
         patch("app.services.assistant_capabilities.refusal", return_value=None), \
         patch.object(project_service, "can_manage_project", AsyncMock(return_value=True)), \
         patch.object(project_service, "ProjectPin") as model, \
         patch.object(chat_tools, "_confirm_gate", AsyncMock()) as gate, \
         patch.object(chat_tools, "_execute_workflow", AsyncMock()) as run_workflow, \
         patch.object(chat_tools, "_execute_extraction", AsyncMock()) as run_extraction, \
         patches[0], patches[1], patches[2], patches[3]:
        model.find.return_value.to_list = AsyncMock(return_value=pins)
        result = await chat_tools.run_pin_on_project(_context(), pin_type, "a-private-id", confirmed=True)

    assert result == {"error": f"That {pin_type} is not pinned to this project, or you don't have access to it."}
    gate.assert_not_awaited()
    run_workflow.assert_not_awaited()
    run_extraction.assert_not_awaited()


async def test_access_lost_while_the_run_waited_for_approval_stops_it():
    listed = [{"pin_type": "extraction", "target_id": "ss-1", "name": "Budget"}]
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=PROJECT)), \
         patch("app.services.assistant_capabilities.refusal", return_value=None), \
         patch.object(project_service, "can_manage_project", AsyncMock(return_value=True)), \
         patch.object(project_service, "list_pins", AsyncMock(return_value=listed)), \
         patch.object(project_service, "get_project_document_uuids", AsyncMock(return_value=["d1"])), \
         patch.object(chat_tools, "_confirm_gate", AsyncMock(return_value=None)), \
         patch.object(access_control, "get_authorized_search_set", AsyncMock(return_value=None)), \
         patch.object(chat_tools, "_execute_extraction", AsyncMock()) as run_extraction:
        result = await chat_tools.run_pin_on_project(_context(), "extraction", "ss-1", confirmed=True)

    assert result == {"error": "You don't have access to this extraction."}
    run_extraction.assert_not_awaited()


async def test_chat_refuses_the_pin_before_asking_for_approval():
    patches = _no_access()
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=PROJECT)), \
         patch.object(project_service, "can_manage_project", AsyncMock(return_value=True)), \
         patch.object(project_service, "add_pin", AsyncMock()) as add, \
         patch.object(chat_tools, "_confirm_gate", AsyncMock()) as gate, \
         patches[0], patches[1], patches[2], patches[3]:
        result = await chat_tools.pin_to_project(_context(), "workflow", "a-private-id")

    assert result == {"error": "You don't have access to this workflow. Nothing was pinned."}
    gate.assert_not_awaited()
    add.assert_not_awaited()


async def test_the_chat_prompt_lists_pins_for_the_person_chatting():
    from app.services import chat_service

    overview = {"role": "owner", "capabilities": {"files": {"count": 0}, "knowledge": {"ready": False, "documents": 0}}}
    project = SimpleNamespace(uuid="p1", title="S1 Test", state="active", description=None)
    with patch.object(project_service, "get_authorized_project", AsyncMock(return_value=project)), \
         patch.object(project_service, "get_project_overview", AsyncMock(return_value=overview)), \
         patch.object(project_service, "list_pins", AsyncMock(return_value=[])) as list_pins, \
         patch("app.services.project_context.context_text", return_value=""), \
         patch("app.services.project_context.render_context", return_value=""):
        await chat_service._build_project_context("p1", BOB)

    list_pins.assert_awaited_once_with(project, BOB)


async def test_access_lost_while_a_workflow_run_waited_for_approval_stops_it():
    listed = [{"pin_type": "workflow", "target_id": "wf-1", "name": "Compliance"}]
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=PROJECT)), \
         patch("app.services.assistant_capabilities.refusal", return_value=None), \
         patch.object(project_service, "can_manage_project", AsyncMock(return_value=True)), \
         patch.object(project_service, "list_pins", AsyncMock(return_value=listed)), \
         patch.object(project_service, "get_project_document_uuids", AsyncMock(return_value=["d1"])), \
         patch.object(chat_tools, "_confirm_gate", AsyncMock(return_value=None)), \
         patch.object(access_control, "get_authorized_workflow", AsyncMock(return_value=None)), \
         patch.object(chat_tools, "_execute_workflow", AsyncMock()) as run_workflow:
        result = await chat_tools.run_pin_on_project(_context(), "workflow", "wf-1", confirmed=True)

    assert result == {"error": "You don't have access to this workflow."}
    run_workflow.assert_not_awaited()


@pytest.mark.parametrize("pin_type", ["automation", "knowledge_base"])
async def test_automation_and_knowledge_base_pins_are_listed_only_for_people_who_can_open_them(pin_type):
    pins = [SimpleNamespace(pin_type=pin_type, target_id="theirs"), SimpleNamespace(pin_type=pin_type, target_id="mine")]

    async def lookup(target_id, user, **_):
        return SimpleNamespace(name="Mine", title="Mine") if target_id == "mine" else None

    with patch.object(project_service, "ProjectPin") as model, \
         patch.object(access_control, LOOKUPS[pin_type], AsyncMock(side_effect=lookup)):
        model.find.return_value.to_list = AsyncMock(return_value=pins)
        listed = await project_service.list_pins(PROJECT, BOB)

    assert listed == [{"pin_type": pin_type, "target_id": "mine", "name": "Mine"}]


async def test_someone_who_manages_the_project_sees_a_pin_they_cannot_open_by_type_only():
    pins = [SimpleNamespace(pin_type="workflow", target_id="a-private-id"),
            SimpleNamespace(pin_type="extraction", target_id="deleted-set")]
    exists = AsyncMock(side_effect=lambda pin: pin.target_id == "a-private-id")
    with patch.object(project_service, "ProjectPin") as model, \
         patch.object(project_service, "_pin_target_exists", exists), \
         patch.object(access_control, "get_authorized_workflow", AsyncMock(return_value=None)), \
         patch.object(access_control, "get_authorized_search_set", AsyncMock(return_value=None)):
        model.find.return_value.to_list = AsyncMock(return_value=pins)
        listed = await project_service.list_pins(PROJECT, BOB, include_restricted=True)

    # Removable, but with no name; a pin whose target was deleted stays hidden.
    assert listed == [{
        "pin_type": "workflow", "target_id": "a-private-id",
        "name": "A workflow you don't have access to", "restricted": True,
    }]


async def test_the_award_snapshot_lists_a_pinned_page_only_for_someone_who_can_open_it():
    from fastapi import HTTPException

    from app.services import award_snapshot

    pins = [SimpleNamespace(target_id="page-open"), SimpleNamespace(target_id="page-private")]

    async def authorize(pin_type, target_id, user):
        if target_id == "page-private":
            raise HTTPException(404, "Unavailable")
        return "Open page"

    activity = MagicMock()
    activity.find.return_value.sort.return_value.first_or_none = AsyncMock(return_value=None)
    artifact = MagicMock()
    artifact.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    pin_model = MagicMock()
    pin_model.find.return_value.to_list = AsyncMock(return_value=pins)
    with patch("app.models.activity.ActivityEvent", activity), \
         patch("app.models.artifact.Artifact", artifact), \
         patch("app.models.project.ProjectPin", pin_model), \
         patch.object(project_service, "authorize_resource", AsyncMock(side_effect=authorize)):
        await award_snapshot._activity(PROJECT, BOB)

    query = artifact.find.call_args.args[0]
    assert query["$or"][1] == {"uuid": {"$in": ["page-open"]}}
