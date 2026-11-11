"""Every chat tool has one capability, and an off capability's tools are withheld."""
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.tools import ToolDefinition

from app.services import assistant_capabilities as caps
from app.services.chat_tools import TOOLS


def _tool(name):
    return ToolDefinition(name=name, parameters_json_schema={"type": "object", "properties": {}})


def test_every_chat_tool_belongs_to_exactly_one_capability():
    grouped = [tool for c in (*caps.ALWAYS_ON, *caps.CAPABILITIES) for tool in c.tools]
    registered = [fn.__name__ for fn in TOOLS]
    # A new chat tool must be placed on the Assistant page before it ships:
    # add it to a capability (or ALWAYS_ON) in assistant_capabilities.py.
    assert sorted(grouped) == sorted(registered)
    assert len(grouped) == len(set(grouped))
    ids = [c.id for c in (*caps.ALWAYS_ON, *caps.CAPABILITIES)]
    assert len(ids) == len(set(ids))


def test_admin_limit_and_personal_choice_combine_and_unknown_ids_are_dropped():
    user = SimpleNamespace(assistant_capabilities_off=["pages", "not-a-capability", "files"])
    config = {"assistant_capabilities_off": ["web_search"]}
    # "files" is always on, so it has no switch to turn off.
    assert caps.off_for(user, config) == frozenset({"pages", "web_search"})
    assert caps.off_for(SimpleNamespace(), None) == frozenset()


@pytest.mark.asyncio
async def test_off_capability_withholds_its_tools_and_leaves_the_rest():
    context = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset({"web_search", "pages"})))
    assert await caps.gate(context, _tool("web_search")) is None
    assert await caps.gate(context, _tool("revise_html_artifact")) is None
    kept = _tool("fetch_url")
    assert await caps.gate(context, kept) is kept
    # Always-on tools have no capability to switch off.
    always = _tool("update_plan")
    assert await caps.gate(context, always) is always
    everything = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset()))
    assert await caps.gate(everything, _tool("web_search")) is not None


def test_chat_is_told_what_is_off_and_who_can_turn_it_back_on():
    assert caps.instructions(frozenset(), frozenset()) == ""
    note = caps.instructions(frozenset({"web_search", "ra_inbox", "workflows"}), frozenset({"workflows"}))
    assert "Turned off by this person: Search the web; RA inbox." in note and "(/assistant)" in note
    # An admin lock is never described as something the person can switch on.
    assert "Turned off for everyone by an administrator: Workflows." in note
    assert "cannot turn these on" in note
    only_locked = caps.instructions(frozenset(), frozenset({"pages"}))
    assert "Turned off by this person" not in only_locked and "(/assistant)" not in only_locked


@pytest.mark.asyncio
async def test_a_tool_that_does_another_capabilitys_work_needs_both_on():
    # Adding a URL to a knowledge base fetches the page.
    context = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset({"web_pages"})))
    assert await caps.gate(context, _tool("add_url_to_kb")) is None
    assert await caps.gate(context, _tool("add_documents_to_kb")) is not None
    # Where the other capability is known only from the arguments, the tool refuses.
    off = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset({"workflows"})))
    assert "Workflows is turned off" in caps.refusal(off, "workflows")["error"]
    assert caps.refusal(off, "extractions") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("call", ["pin", "automation", "execute"])
async def test_projects_and_automations_cannot_run_a_switched_off_workflow(call):
    from app.services import chat_tools

    context = SimpleNamespace(deps=SimpleNamespace(
        capabilities_off=frozenset({"workflows"}), user=SimpleNamespace(), team_id=None, user_id="u",
    ))
    if call == "pin":
        with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=SimpleNamespace(uuid="p"))):
            result = await chat_tools.run_pin_on_project(context, "workflow", "wf1", confirmed=True)
    elif call == "automation":
        result = await chat_tools.create_automation(context, "Nightly", "workflow", "wf1", confirmed=True)
    else:
        result = await chat_tools._execute_workflow(context, SimpleNamespace(id="wf1"), ["d1"])
    assert "Workflows is turned off" in result["error"]


def test_cards_for_a_switched_off_capability_are_found_by_their_tool():
    pending = [{"fp": "a", "tool": "run_workflow"}, {"fp": "b", "tool": "add_url_to_kb"}, {"fp": "c", "tool": "create_project"}]
    assert [p["fp"] for p in caps.stranded(pending, frozenset({"workflows", "web_pages"}))] == ["a", "b"]
    assert caps.stranded(pending, frozenset()) == []


def test_page_separates_the_persons_choice_from_the_admin_limit():
    user = SimpleNamespace(assistant_capabilities_off=["pages"])
    config = {"assistant_capabilities_off": ["workflows"], "web_search_provider": ""}
    rows = {row["id"]: row for row in caps.describe(user, config)["capabilities"]}
    assert rows["pages"] == {**rows["pages"], "enabled": False, "allowed": True, "active": False}
    # The admin limit hides it without overwriting what the person chose.
    assert rows["workflows"] == {**rows["workflows"], "enabled": True, "allowed": False, "active": False}
    assert rows["web_search"]["available"] is False and rows["web_search"]["active"] is False
    assert rows["projects"]["active"] is True
    assert [c["id"] for c in caps.describe(user, config)["always_on"]] == ["files", "skills", "guidance"]


# ── Routes ──────────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from contextlib import contextmanager  # noqa: E402

from app.dependencies import get_current_user  # noqa: E402
from tests.test_chat_routes import _auth, _make_user, client  # noqa: E402,F401


@contextmanager
def _as(user, config):
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch("app.routers.assistant.SystemConfig.get_config", AsyncMock(return_value=config)):
            yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _config(off=()):
    config = MagicMock()
    config.assistant_capabilities_off = list(off)
    config.model_dump.return_value = {"assistant_capabilities_off": list(off), "web_search_provider": "tavily"}
    config.update = AsyncMock()
    return config


def _signed_in(admin=False, off=()):
    user = _make_user()
    user.is_admin = admin
    user.assistant_capabilities_off = list(off)
    user.update = AsyncMock()
    return user


@pytest.mark.asyncio
async def test_a_person_switches_one_capability_without_resending_the_others(client):  # noqa: F811
    user, config = _signed_in(off=["pages"]), _config()
    cookies, headers = _auth()
    with _as(user, config):
        off = await client.put("/api/assistant/capabilities/web_search", json={"on": False}, cookies=cookies, headers=headers)
        on = await client.put("/api/assistant/capabilities/pages", json={"on": True}, cookies=cookies, headers=headers)
        unknown = await client.put("/api/assistant/capabilities/everything", json={"on": False}, cookies=cookies, headers=headers)
        always_on = await client.put("/api/assistant/capabilities/files", json={"on": False}, cookies=cookies, headers=headers)
    assert off.status_code == 200 and on.status_code == 200
    # Each change is one atomic set operation, so two tabs cannot overwrite each other.
    assert [call.args[0] for call in user.update.await_args_list] == [
        {"$addToSet": {"assistant_capabilities_off": "web_search"}},
        {"$pull": {"assistant_capabilities_off": "pages"}},
    ]
    assert off.json()["can_set_limits"] is False
    assert unknown.status_code == 422 and always_on.status_code == 422
    config.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_an_admin_sets_the_limit_for_everyone(client):  # noqa: F811
    cookies, headers = _auth()
    config = _config()
    with _as(_signed_in(), config):
        refused = await client.put("/api/assistant/capabilities/workflows/limit", json={"on": False}, cookies=cookies, headers=headers)
    assert refused.status_code == 403
    config.update.assert_not_awaited()

    audit = MagicMock(insert=AsyncMock())
    with _as(_signed_in(admin=True), config), \
         patch("app.models.audit_log.AdminAuditLog", MagicMock(return_value=audit)) as log:
        allowed = await client.put("/api/assistant/capabilities/workflows/limit", json={"on": False}, cookies=cookies, headers=headers)
        # Already on: nothing to write and nothing to audit.
        unchanged = await client.put("/api/assistant/capabilities/pages/limit", json={"on": True}, cookies=cookies, headers=headers)
    assert allowed.status_code == 200 and unchanged.status_code == 200
    config.update.assert_awaited_once()
    written = config.update.await_args.args[0]
    assert written["$addToSet"] == {"assistant_capabilities_off": "workflows"}
    assert set(written["$set"]) == {"updated_by", "updated_at"}
    assert log.call_args.kwargs["detail"] == "Workflows turned off in chat for everyone"
    audit.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_model_is_never_offered_a_switched_off_tool():
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    offered: list[list[str]] = []

    def model(messages, info):
        offered.append(sorted(tool.name for tool in info.function_tools))
        return ModelResponse(parts=[TextPart("ok")])

    agent = Agent(FunctionModel(model), deps_type=SimpleNamespace)

    @agent.tool(prepare=caps.gate)
    async def web_search(context, query: str) -> str:
        return query

    @agent.tool(prepare=caps.gate)
    async def fetch_url(context, url: str) -> str:
        return url

    await agent.run("hi", deps=SimpleNamespace(capabilities_off=frozenset({"web_search"})))
    await agent.run("hi", deps=SimpleNamespace(capabilities_off=frozenset()))
    assert offered == [["fetch_url"], ["fetch_url", "web_search"]]


@pytest.mark.asyncio
async def test_the_real_chat_agent_withholds_every_tool_of_an_off_capability(monkeypatch):
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from app.services import llm_service

    offered: list[set[str]] = []

    def model(messages, info):
        offered.append({tool.name for tool in info.function_tools})
        return ModelResponse(parts=[TextPart("ok")])

    monkeypatch.setattr(llm_service, "get_agent_model", lambda *a, **k: FunctionModel(model))
    monkeypatch.setattr(llm_service, "build_prompt_cache_model_settings", lambda *a, **k: None)
    llm_service._agentic_chat_agent_cache.clear()
    try:
        agent = llm_service.create_agentic_chat_agent("capability-test-model", system_config_doc={})
        deps = SimpleNamespace(capabilities_off=frozenset({"workflows", "web_search"}), queued_user_parts=[])
        await agent.run("hi", deps=deps, instructions="test")
    finally:
        llm_service._agentic_chat_agent_cache.clear()
    every = {fn.__name__ for fn in TOOLS}
    withheld = set(caps._BY_ID["workflows"].tools) | set(caps._BY_ID["web_search"].tools)
    assert offered[0] == every - withheld


# ── A whole chat turn (tests.test_chat_output.chat_harness) ──────────────────

from pydantic_ai import Agent, Tool  # noqa: E402
from pydantic_ai.models.function import FunctionModel  # noqa: E402

from tests.test_chat_output import chat_harness  # noqa: E402,F401


def _recording_agent(seen):
    async def respond(messages, info):
        seen["tools"] = sorted(tool.name for tool in info.function_tools)
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = "\n".join(
            str(part.content) for message in messages for part in message.parts if hasattr(part, "content")
        )
        yield "Done."

    async def web_search(query: str) -> str:
        return query

    async def fetch_url(url: str) -> str:
        return url

    async def run_workflow(workflow_id: str) -> str:
        return workflow_id

    return Agent(FunctionModel(stream_function=respond), deps_type=object, tools=[
        Tool(fn, name=fn.__name__, prepare=caps.gate) for fn in (web_search, fetch_url, run_workflow)
    ])


async def _turn(monkeypatch, agent, *, user_off=(), admin_off=(), **kwargs):
    from app.services import chat_service as chat

    config = SimpleNamespace(model_dump=lambda: {"assistant_capabilities_off": list(admin_off)})
    monkeypatch.setattr(chat.SystemConfig, "get_config", AsyncMock(return_value=config))
    monkeypatch.setattr(chat, "create_agentic_chat_agent", lambda *a, **k: agent)
    user = SimpleNamespace(current_team=None, organization_id=None, assistant_capabilities_off=list(user_off))
    return [json.loads(chunk) async for chunk in chat.chat_stream(
        kwargs.pop("message", "Find the latest NSF notice."), [], "conversation", "user",
        user=user, team_access=SimpleNamespace(), **kwargs,
    )]


async def test_a_chat_turn_withholds_off_tools_and_tells_the_model_who_switched_them_off(chat_harness, monkeypatch):  # noqa: F811
    seen: dict = {}
    chunks = await _turn(monkeypatch, _recording_agent(seen), user_off=["web_search"], admin_off=["workflows"])
    assert not [c for c in chunks if c["kind"] == "error"], chunks
    # deps.capabilities_off reached the gate, and the note reached the instructions.
    assert seen["tools"] == ["fetch_url"]
    assert "Turned off by this person: Search the web." in seen["instructions"]
    assert "Turned off for everyone by an administrator: Workflows." in seen["instructions"]

    seen.clear()
    await _turn(monkeypatch, _recording_agent(seen))
    assert seen["tools"] == ["fetch_url", "run_workflow", "web_search"]
    assert "Some capabilities are turned off" not in seen["instructions"]


async def test_knowledge_bases_off_stops_retrieval_before_the_model_runs(chat_harness, monkeypatch):  # noqa: F811
    from app.services import builtin_kbs, chat_service as chat

    route = AsyncMock(return_value=[])
    retrieve = AsyncMock(return_value=(None, []))
    monkeypatch.setattr(builtin_kbs, "route", route)
    monkeypatch.setattr(chat, "_build_multi_kb_segment", retrieve)
    seen: dict = {}
    chunks = await _turn(monkeypatch, _recording_agent(seen), user_off=["knowledge_bases"],
                         message="What does 2 CFR 200 say about equipment?", kbs=[("kb1", "Uniform Guidance")])
    # Neither the attached knowledge base nor a built-in one was consulted.
    retrieve.assert_not_awaited()
    route.assert_not_awaited()
    assert [c["action"] for c in chunks if c["kind"] == "context_notice"] == ["knowledge_bases_off"]

    await _turn(monkeypatch, _recording_agent(seen), message="What does 2 CFR 200 say about equipment?")
    route.assert_awaited_once()


async def test_a_card_waiting_on_a_switched_off_capability_is_retired_and_explained(chat_harness, monkeypatch):  # noqa: F811
    chat_harness.conversation.set = AsyncMock()
    chat_harness.conversation.pending_confirmations = [
        {"fp": "f1", "tool": "run_workflow", "call_id": "c1", "label": "Run workflow", "turn": 0},
        {"fp": "f2", "tool": "create_project", "call_id": "c2", "label": "Create project", "turn": 0},
    ]
    seen: dict = {}
    await _turn(monkeypatch, _recording_agent(seen), user_off=["workflows"], message="Yes, go ahead", approval_for="c1")
    assert [p["call_id"] for p in chat_harness.conversation.pending_confirmations] == ["c2"]
    chat_harness.conversation.set.assert_awaited_once()
    assert "Run workflow" in seen["prompt"] and "cancelled" in seen["prompt"]
