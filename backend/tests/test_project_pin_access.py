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

    assert "you don't have access to it" in result["error"]
    assert "private workflow" not in result["error"].lower()
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
