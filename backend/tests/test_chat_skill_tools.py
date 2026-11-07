"""Skills are discoverable guidance, not extraction schemas or workflow runs."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.schemas.skills import SkillSnapshot
from app.services import chat_skill_tools as tools
from app.services import chat_tools, skill_service
from tests.test_chat_tools import _make_context


def snapshot(title="Review", **overrides):
    return SkillSnapshot(**{"uuid": "s1", "title": title, "version": "v1",
                            "instructions": "NEW_REVIEW_GUIDANCE", **overrides})


def conversation():
    return SimpleNamespace(user_id="user1", active_skill=snapshot(instructions="OLD_GUIDANCE"),
                           pending_confirmations=[], save=AsyncMock(), set=AsyncMock())


@pytest.mark.asyncio
async def test_discovery_filters_types_deduplicates_and_rechecks_access():
    items = [{"set_type": kind, "item_uuid": uuid} for kind, uuid in [
        ("extraction", "extract"), ("formatter", "format"), ("prompt", "private"),
        ("prompt", "s1"), ("prompt", "s1"),
    ]]
    ctx = _make_context()
    with patch("app.services.library_service.search_libraries", AsyncMock(return_value=items)) as search, \
         patch.object(skill_service, "snapshot_skill", AsyncMock(side_effect=[HTTPException(404), snapshot()])) as read:
        result = await tools.list_skills(ctx, "review")
    assert result == [{"uuid": "s1", "title": "Review", "kind": "skill",
                       "description": "NEW_REVIEW_GUIDANCE", "version": "v1"}]
    assert read.await_count == 2
    assert search.await_args.kwargs["kind"] == "search_set"


@pytest.mark.asyncio
async def test_empty_discovery_does_not_fall_back_to_selected_skill():
    ctx = _make_context(conversation=conversation())
    with patch("app.services.library_service.search_libraries", AsyncMock(return_value=[])) as search, \
         patch.object(skill_service, "snapshot_skill", AsyncMock()) as read:
        assert await tools.list_skills(ctx) == []
    search.assert_awaited_once_with(ctx.deps.user, "", team_id=ctx.deps.team_id, kind="search_set")
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_discovery_description_uses_saved_instructions_not_title_or_library_metadata():
    instructions = "Compare the award end date with the source notice. " * 12
    source = SimpleNamespace(
        uuid="s1", title="Award Review", set_type="prompt",
        extraction_config={"content": "Outdated creation instructions"},
        get_items=AsyncMock(return_value=[SimpleNamespace(searchphrase=instructions)]),
    )
    items = [{"set_type": "prompt", "item_uuid": "s1", "name": "Old title",
              "description": "a structured award review method for consistency, completeness, and compliance"}]
    with patch("app.services.library_service.search_libraries", AsyncMock(return_value=items)), \
         patch.object(skill_service.access_control, "get_authorized_search_set", AsyncMock(return_value=source)):
        result = await tools.list_skills(_make_context())
    assert len(result) == 1
    assert result[0]["title"] == "Award Review"
    assert result[0]["description"] == instructions.strip()[:400]


@pytest.mark.asyncio
async def test_inspection_does_not_select_and_reports_inaccessible_skills():
    conv = conversation()
    with patch.object(skill_service, "snapshot_skill", AsyncMock(return_value=snapshot())):
        result = await tools.get_skill(_make_context(conversation=conv), "s1")
    assert result["status"] == "preview_only"
    assert conv.active_skill.instructions == "OLD_GUIDANCE"
    conv.set.assert_not_awaited()
    with patch.object(skill_service, "snapshot_skill", AsyncMock(side_effect=HTTPException(404, "Skill unavailable"))):
        assert (await tools.get_skill(_make_context(), "private"))["error"] == "Skill unavailable"


@pytest.mark.asyncio
async def test_selection_requires_prior_turn_and_pins_exact_preview_despite_library_edits():
    conv = conversation()
    ctx = _make_context(conversation=conv, turn_marker=5)
    with patch.object(skill_service, "snapshot_skill", AsyncMock(return_value=snapshot())) as read, \
         patch.object(skill_service, "authorize_skill", AsyncMock()):
        preview = await tools.select_skill(ctx, "s1", confirmed=True)
        assert preview["needs_confirmation"] and preview["skill_instructions"] == "NEW_REVIEW_GUIDANCE"
        assert preview["approval_label"] == "Use Skill"
        assert '"Use Skill" button' in preview["assistant_instruction"]
        assert (await tools.select_skill(ctx, "s1", confirmed=True))["needs_confirmation"]
        conv.set.assert_not_awaited()
        ctx.deps.turn_marker = 7
        read.return_value = snapshot(version="v2", instructions="UNREVIEWED_EDIT")
        selected = await tools.select_skill(ctx, "s1", confirmed=True)
    assert selected["active_skill"] == snapshot().model_dump()
    assert conv.active_skill == snapshot()
    assert conv.set.await_args.args[0]["active_skill"]["version"] == "v1"


@pytest.mark.asyncio
async def test_removal_preview_and_receipt_use_removal_wording_and_preserve_confirmation():
    conv = conversation()
    ctx = _make_context(conversation=conv)
    preview = await tools.select_skill(ctx, None, confirmed=True)
    assert preview["needs_confirmation"] is True
    assert preview["skill_uuid"] is None
    assert preview["approval_label"] == "Remove Skill"
    assert '"Remove Skill" button' in preview["assistant_instruction"]
    assert "Apply Skill selection" not in preview["assistant_instruction"]
    assert preview["skill_instructions"] is None
    assert conv.active_skill is not None
    conv.set.assert_not_awaited()

    ctx.deps.turn_marker += 2
    result = await tools.select_skill(ctx, None, confirmed=True)
    assert result["status"] == "selected"
    assert result["active_skill"] is None
    assert result["message"] == "Skill removed."
    assert conv.active_skill is None
    assert conv.set.await_args.args[0]["active_skill"] is None


@pytest.mark.asyncio
async def test_revocation_and_conversation_ownership_block_selection():
    conv = conversation()
    ctx = _make_context(conversation=conv)
    with patch.object(skill_service, "snapshot_skill", AsyncMock(return_value=snapshot())):
        await tools.select_skill(ctx, "s1")
    ctx.deps.turn_marker += 2
    with patch.object(skill_service, "authorize_skill", AsyncMock(side_effect=HTTPException(404, "Access revoked"))):
        assert "error" in await tools.select_skill(ctx, "s1", confirmed=True)
    conv.set.assert_not_awaited()
    conv.user_id = "someone-else"
    assert "error" in await tools.select_skill(ctx, None, confirmed=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("uuid", ["s1", None])
@pytest.mark.parametrize("queued", [False, True])
async def test_model_receives_replaced_instructions_immediately_and_on_followup(uuid, queued):
    from app.services.llm_service import _inject_queued_user_parts
    conv = conversation()
    ctx = _make_context(conversation=conv)
    ctx.deps.queued_user_parts = []
    received = []

    def respond(messages, info):
        received.append(info.instructions)
        if len(received) == 1:
            if queued:
                ctx.deps.queued_user_parts.append("Also check the dates")
            return ModelResponse(parts=[ToolCallPart("select_skill", {"skill_uuid": uuid, "confirmed": True})])
        return ModelResponse(parts=[TextPart("Selection applied.")])

    agent = Agent(FunctionModel(respond), tools=[tools.select_skill], history_processors=[_inject_queued_user_parts])
    instructions = tools.conversation_instructions("Application rules.")
    with patch.object(skill_service, "snapshot_skill", AsyncMock(return_value=snapshot())), \
         patch.object(skill_service, "authorize_skill", AsyncMock()):
        await tools.select_skill(ctx, uuid)
        ctx.deps.turn_marker += 2
        result = await agent.run("Apply the selection", deps=ctx.deps, instructions=instructions)
        await agent.run("Continue", deps=ctx.deps, instructions=instructions, message_history=result.all_messages())
    assert "OLD_GUIDANCE" in received[0]
    for current in received[1:]:
        assert "OLD_GUIDANCE" not in current
        assert ("NEW_REVIEW_GUIDANCE" in current) is bool(uuid)
        assert current.startswith("Application rules.")
        if uuid:
            assert "applying them only within their stated scope and conditions" in current
    assert conv.active_skill == (snapshot() if uuid else None)


@pytest.mark.asyncio
async def test_extraction_listing_filters_out_skills_and_formatters_before_limit():
    with patch.object(chat_tools, "SearchSet") as model:
        model.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        assert await chat_tools.list_extraction_sets(_make_context()) == []
    assert model.find.call_args.args[0]["set_type"] == {"$in": ["extraction", None]}


@pytest.mark.asyncio
async def test_skill_cannot_be_executed_as_an_extraction():
    with patch.object(chat_tools, "SearchSet") as model, patch.object(chat_tools, "_execute_extraction", AsyncMock()) as run:
        model.find_one = AsyncMock(return_value=SimpleNamespace(set_type="prompt", verified=False, user_id="user1"))
        result = await chat_tools.run_extraction(_make_context(), "s1", ["d1"])
    assert "select_skill" in result["hint"]
    run.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("has_extraction", [False, True])
async def test_inventory_cannot_advertise_prompt_records_outside_library(has_extraction):
    from app.services import chat_service
    chat_service._inventory_cache.clear()
    skill = SimpleNamespace(uuid="s1", title="NSF_Grant_Proposal_Summary", set_type="prompt")
    extraction = SimpleNamespace(uuid="e1", title="Budget fields", set_type="extraction", verified=False)

    def query(rows):
        q = MagicMock()
        q.sort.return_value = q
        q.limit.return_value = q
        q.to_list = AsyncMock(return_value=rows)
        q.count = AsyncMock(return_value=len(rows))
        return q

    with patch.object(chat_service, "SmartDocument") as docs, \
         patch.object(chat_service, "ActivityEvent") as events, \
         patch("app.models.search_set.SearchSet") as sets, \
         patch("app.models.workflow.Workflow") as workflows, \
         patch("app.models.knowledge.KnowledgeBase") as knowledge, \
         patch("app.models.validation_run.ValidationRun") as validation, \
         patch("app.models.quality_alert.QualityAlert") as alerts, \
         patch("app.services.user_memory_service.build_patterns_block", AsyncMock(return_value="")):
        for model in [docs, events, workflows, knowledge, validation, alerts]:
            model.find.return_value = query([])
        sets.find.side_effect = lambda filters: query(
            [skill] if filters["set_type"] == "prompt" else ([extraction] if has_extraction else [])
        )
        block = await chat_service._build_workspace_inventory("user1", None)
    chat_service._inventory_cache.clear()
    assert skill.title not in block
    assert all(call.args[0]["set_type"] == {"$in": ["extraction", None]} for call in sets.find.call_args_list)
    if has_extraction:
        assert '1 extraction set (newest: "Budget fields")' in block
        assert validation.find.call_args.args[0]["item_id"]["$in"] == ["e1"]
    else:
        assert block == ""
        validation.find.assert_not_called()


def test_guidance_help_and_registry_distinguish_the_three_capabilities():
    from app.services.help_content import find_topics
    from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT
    assert "Repeated instructions alone call for a Skill" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "repeatable processing stages call for a workflow" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "List only the Skills returned by that call" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "Descriptions must come from the Skill itself" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "no accessible Library Skills were found" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "Skill availability is an exception" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert "Keep internal deliberation about user intent, approval rules, and tool selection out of" in AGENTIC_CHAT_SYSTEM_PROMPT
    assert find_topics("skills", limit=1)[0]["id"] == "skills"
    names = {fn.__name__ for fn in chat_tools.TOOLS}
    assert {"list_skills", "get_skill", "select_skill"} <= names
    assert {"list_skills", "get_skill"} <= chat_tools.PARALLEL_SAFE_TOOLS
    assert "select_skill" not in chat_tools.PARALLEL_SAFE_TOOLS
