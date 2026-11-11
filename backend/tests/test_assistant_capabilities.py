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


# ── Core Skills ─────────────────────────────────────────────────────────────

from fastapi import HTTPException  # noqa: E402

from app.schemas.skills import SkillSnapshot  # noqa: E402
from app.services import chat_skill_tools, skill_service  # noqa: E402
from app.services.access_control import TeamAccessContext  # noqa: E402
from app.services.chat_tools import COMPACTABLE_TOOLS  # noqa: E402


def _skill(uuid="s1", title="Award review", when="Reviewing a new award notice", version="v1"):
    return SkillSnapshot(uuid=uuid, title=title, version=version, instructions="Check every deadline.", when_to_use=when)


def _doc(uuid, *, team="t1", when="Reviewing a new award notice", content="Check every deadline.", **extra):
    config = {"content": content, **({"when_to_use": when} if when else {})}
    return SimpleNamespace(**{"uuid": uuid, "title": f"Skill {uuid}", "set_type": "prompt", "extraction_config": config,
                              "team_id": team, "is_global": False, "verified": False, "user_id": "someone", **extra})


def _version(doc):
    return skill_service._snapshot(doc, []).version


class _Query:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self):
        return self.rows


@pytest.mark.asyncio
async def test_a_core_skill_is_used_only_as_accepted_in_its_own_team_with_a_when_to_use_line(monkeypatch):
    docs = {d.uuid: d for d in [
        _doc("ok"), _doc("edited"), _doc("elsewhere", team="t2"), _doc("no-line", when=""),
        _doc("unshared", team="t9"), _doc("empty", content=""), _doc("mine-no-team", team=None, user_id="u1"),
    ]}
    finds = []
    monkeypatch.setattr(skill_service, "SearchSet", SimpleNamespace(find=lambda q: finds.append(q) or _Query(list(docs.values()))))
    monkeypatch.setattr(skill_service, "SearchSetItem", SimpleNamespace(find=lambda q: finds.append(q) or _Query([])))
    monkeypatch.setattr(skill_service.access_control, "get_authorized_search_set", AsyncMock(return_value=None))
    pinned = {uuid: _version(doc) for uuid, doc in docs.items() if uuid != "empty"}
    pinned["edited"] = "the-text-before-a-teammate-edited-it"
    user = SimpleNamespace(user_id="u1", current_team="t1", core_skills=[
        {"uuid": uuid, "version": pinned.get(uuid, "")} for uuid in ["ok", "edited", "elsewhere", "no-line", "unshared"]
    ])
    access = TeamAccessContext(team_uuids={"t1", "t2"})
    states = {s.uuid: s for s in await skill_service.core_skill_states(user, access)}
    assert {uuid: s.status for uuid, s in states.items()} == {
        "ok": "ok", "edited": "changed", "elsewhere": "other_team", "no-line": "no_line", "unshared": "unavailable",
    }
    # Whatever the list's length: one query for the Skills, one for their edited text.
    assert len(finds) == 2
    # Chat is given the accepted one only.
    assert [s.uuid for s in await skill_service.core_skills(user, access)] == ["ok"]

    user.core_skills = [{"uuid": "empty", "version": "x"}, {"uuid": "deleted", "version": "x"},
                        {"uuid": "mine-no-team", "version": pinned["mine-no-team"]}]
    more = {s.uuid: s for s in await skill_service.core_skill_states(user, access)}
    assert (more["empty"].status, more["empty"].title) == ("unavailable", "Skill empty")
    assert more["deleted"].status == "unavailable" and more["deleted"].title is None
    assert more["mine-no-team"].status == "ok"
    assert await skill_service.core_skill_states(SimpleNamespace(), access) == []


def test_chat_sees_names_and_when_to_use_but_not_the_instructions():
    note = skill_service.core_skill_instructions([_skill()], None)
    assert '"when_to_use": "Reviewing a new award notice"' in note and "use_core_skill" in note
    assert "Check every deadline." not in note
    # A Skill selected for the conversation takes precedence: no core list at all.
    assert skill_service.core_skill_instructions([_skill()], _skill("pinned")) == ""
    assert skill_service.core_skill_instructions([], None) == ""


def test_the_core_list_disappears_the_moment_a_skill_is_selected_mid_run():
    make = chat_skill_tools.conversation_instructions("BASE", "\nCORE LIST")
    conversation = SimpleNamespace(active_skill=None)
    context = SimpleNamespace(deps=SimpleNamespace(conversation=conversation))
    assert make(context) == "BASE\nCORE LIST"
    conversation.active_skill = _skill("pinned")
    assert "CORE LIST" not in make(context) and "Selected Skill (JSON)" in make(context)


def _core_context(active=None):
    return SimpleNamespace(deps=SimpleNamespace(
        user=SimpleNamespace(), team_access=None, conversation=SimpleNamespace(active_skill=active),
    ))


@pytest.mark.asyncio
async def test_use_core_skill_follows_the_same_rules_as_the_listing():
    State = skill_service.CoreSkillState
    states = [State("s1", "ok", skill=_skill(title='Award "review"'), title='Award "review"'),
              State("s2", "changed", skill=_skill("s2"), title="Edited", problem="This Skill was edited after you added it.")]
    with patch.object(skill_service, "core_skill_states", AsyncMock(return_value=states)) as read:
        loaded = await chat_skill_tools.use_core_skill(_core_context(), "s1")
        edited = await chat_skill_tools.use_core_skill(_core_context(), "s2")
        other = await chat_skill_tools.use_core_skill(_core_context(), "someone-elses")
        pinned = await chat_skill_tools.use_core_skill(_core_context(active=_skill("pinned")), "s1")
    assert loaded["status"] == "completed"
    assert loaded["skill"]["instructions"] == "Check every deadline." and loaded["skill"]["version"] == "v1"
    # The title is data in the result, never spliced into the instruction sentence.
    assert 'Award "review"' not in loaded["assistant_instruction"]
    # An edit nobody accepted is not loaded, even if the model still has the uuid.
    assert "edited after you added it" in edited["error"] and "skill" not in edited
    assert "error" in other
    assert "error" in pinned and read.await_count == 3


def test_a_loaded_core_skill_can_be_cleared_from_old_history():
    assert "use_core_skill" in COMPACTABLE_TOOLS


class _Users:
    def __init__(self, modified=1, matched=1, stored=()):
        self.calls, self.modified, self.matched, self.stored = [], modified, matched, list(stored)

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(modified_count=self.modified, matched_count=self.matched)

    async def find_one(self, query, projection=None):
        return {"core_skills": [{"uuid": uuid, "version": "v"} for uuid in self.stored]}


@pytest.mark.asyncio
async def test_core_skill_writes_are_single_conditional_updates(monkeypatch):
    user = SimpleNamespace(id="user-id", core_skills=[])
    users = _Users()
    monkeypatch.setattr(skill_service, "_users", lambda: users)
    assert await skill_service.add_core_skill(user, _skill()) == "added"
    query, update = users.calls[0]
    # Not already listed, and under the cap, checked by the database in the same write.
    assert query == {"_id": "user-id", "core_skills.uuid": {"$ne": "s1"}, "core_skills.4": {"$exists": False}}
    assert update == {"$push": {"core_skills": {"uuid": "s1", "version": "v1"}}}

    full = _Users(modified=0, stored=["a", "b", "c", "d", "e"])
    monkeypatch.setattr(skill_service, "_users", lambda: full)
    assert await skill_service.add_core_skill(user, _skill()) == "full"
    present = _Users(modified=0, stored=["s1"])
    monkeypatch.setattr(skill_service, "_users", lambda: present)
    assert await skill_service.add_core_skill(user, _skill()) == "present"

    monkeypatch.setattr(skill_service, "_users", lambda: users)
    assert await skill_service.accept_core_skill(user, _skill(version="v2")) is True
    assert users.calls[-1] == ({"_id": "user-id", "core_skills.uuid": "s1"}, {"$set": {"core_skills.$.version": "v2"}})
    await skill_service.remove_core_skill(user, "s1")
    assert users.calls[-1] == ({"_id": "user-id"}, {"$pull": {"core_skills": {"uuid": "s1"}}})


@pytest.mark.asyncio
async def test_core_skill_routes_pin_on_add_and_accept_only_the_text_that_was_shown(client):  # noqa: F811
    cookies, headers = _auth()
    user = _signed_in()
    user.core_skills = []
    user.current_team = None
    State = skill_service.CoreSkillState
    page = [State("s1", "changed", skill=_skill(version="v2"), title="Award review", problem="Edited.")]

    async def snapshot(uuid, _user):
        if uuid == "gone":
            raise HTTPException(404, "Skill not found or no longer accessible")
        return _skill(uuid, "Tone" if uuid == "no-line" else "Award review", "" if uuid == "no-line" else "Reviewing", version="v2")

    with _as(user, _config()), patch.object(skill_service, "snapshot_skill", snapshot), \
         patch.object(skill_service, "core_skill_states", AsyncMock(return_value=page)), \
         patch.object(skill_service, "reload_core_skills", AsyncMock()), \
         patch.object(skill_service, "add_core_skill", AsyncMock(side_effect=["added", "full"])) as add, \
         patch.object(skill_service, "accept_core_skill", AsyncMock(return_value=True)) as accept, \
         patch.object(skill_service, "remove_core_skill", AsyncMock()) as remove:
        no_line = await client.post("/api/assistant/core-skills", json={"uuid": "no-line"}, cookies=cookies, headers=headers)
        gone = await client.post("/api/assistant/core-skills", json={"uuid": "gone"}, cookies=cookies, headers=headers)
        added = await client.post("/api/assistant/core-skills", json={"uuid": "s1"}, cookies=cookies, headers=headers)
        full = await client.post("/api/assistant/core-skills", json={"uuid": "s1"}, cookies=cookies, headers=headers)
        stale = await client.post("/api/assistant/core-skills/s1/accept", json={"version": "v1"}, cookies=cookies, headers=headers)
        accepted = await client.post("/api/assistant/core-skills/s1/accept", json={"version": "v2"}, cookies=cookies, headers=headers)
        removed = await client.delete("/api/assistant/core-skills/s1", cookies=cookies, headers=headers)
    assert no_line.status_code == 422 and "When to use" in no_line.json()["detail"]
    assert gone.status_code == 404
    assert added.status_code == 200 and add.await_args_list[0].args[1].version == "v2"
    assert full.status_code == 422 and "up to 5" in full.json()["detail"]
    # A second edit made while the person was reading is not accepted unseen.
    assert stale.status_code == 409 and accept.await_count == 1
    assert accepted.status_code == 200 and removed.status_code == 200
    remove.assert_awaited_once()
    row = added.json()["skills"][0]
    assert (row["status"], row["usable"], row["version"]) == ("changed", False, "v2")
    # The new text is shown for review only on an edited Skill.
    assert row["instructions"] == "Check every deadline."


@pytest.mark.asyncio
async def test_the_picker_offers_library_skills_that_are_not_already_core(client):  # noqa: F811
    cookies, headers = _auth()
    user = _signed_in()
    user.core_skills = [{"uuid": "s1", "version": "v1"}]
    user.current_team = None
    items = [
        {"item_uuid": "s1", "set_type": "prompt", "name": "Award review", "when_to_use": "Reviewing"},
        {"item_uuid": "s2", "set_type": "prompt", "name": "subaward intake", "when_to_use": "Checking a subaward"},
        {"item_uuid": "s2", "set_type": "prompt", "name": "subaward intake", "when_to_use": "Checking a subaward"},
        {"item_uuid": "s3", "set_type": "prompt", "name": "House tone", "when_to_use": None},
        {"item_uuid": "x1", "set_type": "extraction", "name": "Budget fields"},
    ]
    with _as(user, _config()), patch("app.services.library_service.search_libraries", AsyncMock(return_value=items)) as search:
        response = await client.get("/api/assistant/core-skills/choices?search=a", cookies=cookies, headers=headers)
    assert response.json() == {"more": False, "choices": [
        {"uuid": "s3", "title": "House tone", "when_to_use": ""},
        {"uuid": "s2", "title": "subaward intake", "when_to_use": "Checking a subaward"},
    ]}
    assert search.await_args.args[1] == "a" and search.await_args.kwargs["kind"] == "search_set"


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


async def test_a_chat_turn_lists_core_skills_only_while_no_skill_is_selected(chat_harness, monkeypatch):  # noqa: F811
    read = AsyncMock(return_value=[_skill()])
    monkeypatch.setattr(skill_service, "core_skills", read)
    seen: dict = {}
    await _turn(monkeypatch, _recording_agent(seen))
    assert "Core Skills (JSON)" in seen["instructions"] and '"title": "Award review"' in seen["instructions"]
    assert "Check every deadline." not in seen["instructions"]
    read.assert_awaited_once()

    # A selected Skill takes precedence, and nothing is read for the discarded list.
    read.reset_mock()
    chat_harness.conversation.active_skill = _skill("pinned", "Pinned")
    await _turn(monkeypatch, _recording_agent(seen), active_skill=_skill("pinned", "Pinned"))
    assert "Core Skills (JSON)" not in seen["instructions"] and "Selected Skill (JSON)" in seen["instructions"]
    read.assert_not_awaited()
