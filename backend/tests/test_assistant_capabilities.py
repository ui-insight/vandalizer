"""Every chat tool has one capability, and an off capability's tools are withheld."""
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


def test_chat_is_told_what_is_off_and_nothing_when_all_is_on():
    assert caps.instructions(frozenset()) == ""
    note = caps.instructions(frozenset({"web_search", "ra_inbox"}))
    assert "Search the web; RA inbox" in note
    assert "(/assistant)" in note


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
    config.set = AsyncMock()
    return config


def _signed_in(admin=False, off=()):
    user = _make_user()
    user.is_admin = admin
    user.assistant_capabilities_off = list(off)
    user.set = AsyncMock()
    return user


@pytest.mark.asyncio
async def test_a_person_switches_a_capability_off_for_themselves(client):  # noqa: F811
    user, config = _signed_in(), _config()
    cookies, headers = _auth()
    with _as(user, config):
        saved = await client.put("/api/assistant/capabilities", json={"off": ["web_search"]}, cookies=cookies, headers=headers)
        unknown = await client.put("/api/assistant/capabilities", json={"off": ["everything"]}, cookies=cookies, headers=headers)
    assert saved.status_code == 200
    user.set.assert_awaited_once_with({"assistant_capabilities_off": ["web_search"]})
    rows = {row["id"]: row for row in saved.json()["capabilities"]}
    assert rows["web_search"]["active"] is False and rows["pages"]["active"] is True
    assert saved.json()["can_set_limits"] is False
    assert unknown.status_code == 422
    config.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_an_admin_sets_the_limit_for_everyone(client):  # noqa: F811
    cookies, headers = _auth()
    config = _config()
    with _as(_signed_in(), config):
        refused = await client.put("/api/assistant/capabilities/limits", json={"off": ["workflows"]}, cookies=cookies, headers=headers)
    assert refused.status_code == 403
    config.set.assert_not_awaited()

    audit = MagicMock(insert=AsyncMock())
    with _as(_signed_in(admin=True), config), \
         patch("app.models.audit_log.AdminAuditLog", MagicMock(return_value=audit)) as log:
        allowed = await client.put("/api/assistant/capabilities/limits", json={"off": ["workflows"]}, cookies=cookies, headers=headers)
    assert allowed.status_code == 200
    assert config.set.await_args.args[0]["assistant_capabilities_off"] == ["workflows"]
    assert log.call_args.kwargs["payload"] == {"before": [], "after": ["workflows"]}
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


def _skill(uuid="s1", title="Award review", when="Reviewing a new award notice"):
    return SkillSnapshot(uuid=uuid, title=title, version="v1", instructions="Check every deadline.", when_to_use=when)


@pytest.mark.asyncio
async def test_core_skills_skip_what_chat_cannot_use_without_failing_the_turn():
    user = SimpleNamespace(core_skill_uuids=["s1", "gone", "no-line"])
    results = {"s1": _skill(), "gone": HTTPException(404, "Skill not found"), "no-line": _skill("no-line", "Tone", "")}

    async def snapshot(uuid, _user):
        if isinstance(results[uuid], Exception):
            raise results[uuid]
        return results[uuid]

    with patch.object(skill_service, "snapshot_skill", snapshot):
        assert [s.uuid for s in await skill_service.core_skills(user)] == ["s1"]
    assert await skill_service.core_skills(SimpleNamespace()) == []


def test_chat_sees_names_and_when_to_use_but_not_the_instructions():
    note = skill_service.core_skill_instructions([_skill()], None)
    assert '"when_to_use": "Reviewing a new award notice"' in note and "use_core_skill" in note
    assert "Check every deadline." not in note
    # A Skill selected for the conversation takes precedence: no core list at all.
    assert skill_service.core_skill_instructions([_skill()], _skill("pinned")) == ""
    assert skill_service.core_skill_instructions([], None) == ""


def _core_context(core=("s1",), active=None):
    conversation = SimpleNamespace(active_skill=active)
    return SimpleNamespace(deps=SimpleNamespace(user=SimpleNamespace(core_skill_uuids=list(core)), conversation=conversation))


@pytest.mark.asyncio
async def test_use_core_skill_loads_only_a_listed_skill_and_yields_to_a_selected_one():
    with patch.object(skill_service, "snapshot_skill", AsyncMock(return_value=_skill())) as read:
        loaded = await chat_skill_tools.use_core_skill(_core_context(), "s1")
        other = await chat_skill_tools.use_core_skill(_core_context(), "someone-elses")
        pinned = await chat_skill_tools.use_core_skill(_core_context(active=_skill("pinned")), "s1")
    assert loaded["status"] == "applied_to_this_reply"
    assert loaded["skill"]["instructions"] == "Check every deadline." and loaded["skill"]["version"] == "v1"
    assert "error" in other and "error" in pinned
    # Only the listed Skill was ever read; access is rechecked on that read.
    assert read.await_count == 1


@pytest.mark.asyncio
async def test_use_core_skill_reports_lost_access_instead_of_instructions():
    with patch.object(skill_service, "snapshot_skill", AsyncMock(side_effect=HTTPException(404, "Skill not found or no longer accessible"))):
        result = await chat_skill_tools.use_core_skill(_core_context(), "s1")
    assert result == {"error": "Skill not found or no longer accessible"}


@pytest.mark.asyncio
async def test_core_skill_routes_require_a_when_to_use_line_and_cap_the_list(client):  # noqa: F811
    cookies, headers = _auth()
    user = _signed_in()
    user.core_skill_uuids = ["old"]

    async def snapshot(uuid, _user):
        if uuid == "old":
            raise HTTPException(404, "Skill not found or no longer accessible")
        return _skill(uuid, "Tone" if uuid == "no-line" else "Award review", "" if uuid == "no-line" else "Reviewing a new award notice")

    with _as(user, _config()), patch.object(skill_service, "snapshot_skill", snapshot):
        refused = await client.put("/api/assistant/core-skills", json={"uuids": ["no-line"]}, cookies=cookies, headers=headers)
        too_many = await client.put("/api/assistant/core-skills", json={"uuids": list("abcdef")}, cookies=cookies, headers=headers)
        # "old" lost access but is already listed, so it does not block adding s1.
        saved = await client.put("/api/assistant/core-skills", json={"uuids": ["old", "s1", "s1"]}, cookies=cookies, headers=headers)
    assert refused.status_code == 422 and "When to use" in refused.json()["detail"]
    assert too_many.status_code == 422
    assert saved.status_code == 200
    user.set.assert_awaited_once_with({"core_skill_uuids": ["old", "s1"]})
    rows = saved.json()["skills"]
    assert [(r["uuid"], r["usable"]) for r in rows] == [("old", False), ("s1", True)]
    assert rows[0]["problem"] == "Skill not found or no longer accessible"
