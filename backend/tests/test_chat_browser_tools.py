"""Chat's browser tools wait for the extension's answer and only report figures a page showed."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.tools import ToolDefinition

from app.services import assistant_capabilities as caps
from app.services import chat_browser_tools as browser
from app.services.chat_deps import AgenticChatDeps


class FakeRedis:
    """The two list operations the tools use, shared across 'workers'."""

    lists: dict[str, list[bytes]] = {}

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value.encode())

    async def expire(self, key, seconds):
        return True

    async def blpop(self, keys, timeout=0):
        for _ in range(int(timeout * 20) or 1):
            for key in keys:
                if self.lists.get(key):
                    return key.encode(), self.lists[key].pop(0)
            await asyncio.sleep(0.05)
        return None

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    FakeRedis.lists = {}
    monkeypatch.setattr(browser, "_redis", FakeRedis)


@pytest.fixture(autouse=True)
def review_allows(monkeypatch):
    """These tests are about the relay; tests/test_browser_policy.py covers the review."""
    from app.services import browser_policy

    async def allow(deps, prompt):
        return '{"decision": "allow", "reason": "Ordinary reading for work."}'

    monkeypatch.setattr(browser_policy, "_ask_model", allow)


def _context(*, available=True, user_id="ra", call_id="call-1"):
    deps = AgenticChatDeps(
        user=SimpleNamespace(), user_id=user_id, team_id=None, team_access=None,
        organization_id=None, system_config_doc={}, model_name="m", browser_available=available,
    )
    return SimpleNamespace(deps=deps, tool_call_id=call_id)


def _page_only(result: dict) -> dict:
    """A read's result without the note that marks page text as data."""
    return {k: v for k, v in result.items() if k != "untrusted_content_note"}


PAGE = {"page": {"url": "https://fin.example.edu/award/123", "title": "Award 123",
                 "text": "# Award 123\nExpenditures to date | $1,234,567.89\nRemaining balance | 15,000.00"}}


@pytest.mark.asyncio
async def test_a_tool_returns_what_the_page_posts_for_its_own_call():
    context = _context()
    waiting = asyncio.create_task(browser.browser_open(context, "https://fin.example.edu/award/123"))
    await asyncio.sleep(0.05)
    # Another person's answer for the same call id never reaches this turn.
    await browser.deliver_result("someone-else", "call-1", {"page": {"text": "wrong"}})
    await browser.deliver_result("ra", "call-1", PAGE)
    assert _page_only(await waiting) == PAGE
    assert context.deps.browser_pages[-1]["url"] == "https://fin.example.edu/award/123"


@pytest.mark.asyncio
async def test_a_browser_that_never_answers_is_reported_not_waited_on_forever(monkeypatch):
    monkeypatch.setattr(browser, "ACTION_TIMEOUT_SECONDS", 0.1)
    result = await browser.browser_read(_context(), "balance")
    assert result["error"] == "browser_timeout"


@pytest.mark.asyncio
async def test_without_the_extension_the_tool_says_so_instead_of_waiting():
    result = await browser.browser_click(_context(available=False), 3)
    assert result["error"] == "browser_not_connected"
    assert "(/assistant#browser-setup)" in result["hint"] and "fetch_url" in result["hint"]
    assert FakeRedis.lists == {}


@pytest.mark.asyncio
async def test_an_extension_that_went_away_mid_chat_is_not_quietly_replaced_by_the_web_reader():
    # The turn was sent as connected; the chat page then found the extension gone.
    context = _context()
    waiting = asyncio.create_task(browser.browser_open(context, "https://fin.example.edu/award/123"))
    await asyncio.sleep(0.05)
    await browser.deliver_result("ra", "call-1", {"error": "browser_not_connected", "message": "Not connected on this page."})
    result = await waiting
    assert result["error"] == "browser_not_connected"
    assert "isn't connected" in result["hint"] and "Do not read the page with fetch_url" in result["hint"]


@pytest.mark.asyncio
async def test_record_value_accepts_only_figures_a_page_showed_this_turn():
    context = _context()
    context.deps.browser_pages.append({"url": PAGE["page"]["url"], "title": "Award 123", "text": PAGE["page"]["text"]})
    kept = await browser.record_value(context, "Expenditures to date", "1234567.89")
    assert kept["recorded"] is True and kept["url"] == "https://fin.example.edu/award/123"
    assert (await browser.record_value(context, "Remaining balance", "$15,000.00"))["recorded"] is True
    invented = await browser.record_value(context, "Remaining balance", "$16,000.00")
    assert invented["recorded"] is False and invented["error"] == "value_not_on_page"
    assert [v["value"] for v in context.deps.browser_values] == ["1234567.89", "$15,000.00"]
    assert (await browser.record_value(context, "Blank", " "))["recorded"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["100", "10,000", "5", "1,234,567", "500", "0.5", "active"])
async def test_record_value_refuses_part_of_a_longer_figure(value):
    """A short or partial number is inside almost any page; only a whole value counts."""
    context = _context()
    context.deps.browser_pages.append({
        "url": "https://fin.example.edu/award/9", "title": "Award 9",
        "text": "Total award: $1,000,000\nSpent | 1,234,567.89\nCredit | -500\nRate | 10.5\nStatus | Inactive",
    })
    assert (await browser.record_value(context, "Figure", value))["recorded"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["$1,000,000", "1000000", "1,234,567.89", "-500", "10.5", "Inactive"])
async def test_record_value_accepts_whole_values_however_they_are_formatted(value):
    context = _context()
    context.deps.browser_pages.append({
        "url": "https://fin.example.edu/award/9", "title": "Award 9",
        "text": "Total award: $1,000,000\nSpent | 1,234,567.89\nCredit | -500\nRate | 10.5\nStatus | Inactive",
    })
    assert (await browser.record_value(context, "Figure", value))["recorded"] is True


def test_only_calls_that_will_run_are_sent_to_the_browser():
    deps = _context().deps
    assert browser.should_relay("browser_open", True, deps)
    assert browser.should_relay("browser_finish", True, deps)
    # Server-side tool, bad arguments, unknown validation, no extension, switched off.
    assert not browser.should_relay("record_value", True, deps)
    assert not browser.should_relay("browser_type", False, deps)
    assert not browser.should_relay("browser_open", None, deps)
    assert not browser.should_relay("browser_open", True, _context(available=False).deps)
    deps.capabilities_off = frozenset({"browser"})
    assert not browser.should_relay("browser_open", True, deps)
    assert not browser.should_relay("browser_open", True, None)


@pytest.mark.asyncio
async def test_browser_tools_are_offered_only_when_the_chat_page_has_the_extension():
    tool = ToolDefinition(name="browser_open", parameters_json_schema={"type": "object", "properties": {}})
    other = ToolDefinition(name="web_search", parameters_json_schema={"type": "object", "properties": {}})
    without = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset(), browser_available=False))
    with_ext = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset(), browser_available=True))
    switched_off = SimpleNamespace(deps=SimpleNamespace(capabilities_off=frozenset({"browser"}), browser_available=True))
    assert await caps.gate(without, tool) is None
    assert await caps.gate(without, other) is other
    assert await caps.gate(with_ext, tool) is tool
    assert await caps.gate(switched_off, tool) is None


def test_browser_tools_run_one_at_a_time():
    from app.services.chat_tools import PARALLEL_SAFE_TOOLS

    assert not browser.BROWSER_TOOL_NAMES & PARALLEL_SAFE_TOOLS


@pytest.mark.asyncio
async def test_the_result_route_delivers_to_the_signed_in_person_only():
    from httpx import ASGITransport, AsyncClient

    from tests.test_chat_routes import _auth, _make_user

    cookies, headers = _auth("ra")
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.dependencies.decode_token", return_value={"sub": "ra", "type": "access"}),
        patch("app.dependencies.User") as users,
    ):
        users.find_one = AsyncMock(return_value=_make_user("ra"))
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ok = await client.post("/api/chat/browser-results", json={"tool_call_id": "call-9", "result": PAGE},
                                   cookies=cookies, headers=headers)
            assert ok.status_code == 200
            assert json.loads(FakeRedis.lists[browser.result_key("ra", "call-9")][0]) == PAGE
            huge = {"page": {"text": "x" * 300_000}}
            too_big = await client.post("/api/chat/browser-results", json={"tool_call_id": "call-9", "result": huge},
                                        cookies=cookies, headers=headers)
            assert too_big.status_code == 413
            bad_id = await client.post("/api/chat/browser-results", json={"tool_call_id": "a b", "result": {}},
                                       cookies=cookies, headers=headers)
            assert bad_id.status_code == 422


from tests.test_chat_output import chat_harness  # noqa: E402,F401


@pytest.mark.asyncio
async def test_the_page_sees_each_browser_call_before_the_tool_waits_for_it(chat_harness, monkeypatch):  # noqa: F811
    """The relay depends on this order: a tool_call chunk that only arrived
    after the tool finished waiting would deadlock every browser turn."""
    from pydantic_ai import Agent
    from pydantic_ai.messages import ToolReturnPart
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    from app.services import chat_service as chat

    monkeypatch.setattr(browser, "ACTION_TIMEOUT_SECONDS", 2)

    async def model(messages, info):
        returned = [p for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)]
        if not returned:
            assert "browser_read" in {t.name for t in info.function_tools}
            yield {0: DeltaToolCall(name="browser_read", json_args='{"query":"balance"}', tool_call_id="read-1")}
        elif len(returned) == 1:
            yield {0: DeltaToolCall(name="record_value", json_args='{"label":"Remaining balance","value":"15,000.00"}',
                                    tool_call_id="rec-1")}
        else:
            yield "Remaining balance: $15,000.00 (fin.example.edu)."

    agent = Agent(FunctionModel(stream_function=model), deps_type=AgenticChatDeps)
    for fn in (browser.browser_read, browser.record_value):
        agent.tool(prepare=caps.gate)(fn)
    monkeypatch.setattr(chat, "create_agentic_chat_agent", lambda *a, **k: agent)

    chunks = []
    async for raw in chat.chat_stream(
        "What's the remaining balance?", [], "conversation", "user",
        user=SimpleNamespace(current_team=None, organization_id=None), team_access=SimpleNamespace(),
        browser_available=True,
    ):
        chunk = json.loads(raw)
        chunks.append(chunk)
        if chunk["kind"] == "tool_call" and chunk["tool_name"] == "browser_read":
            # What the chat page does: run it in the extension, post the result.
            await browser.deliver_result("user", chunk["tool_call_id"], PAGE)

    assert not [c for c in chunks if c["kind"] == "error"], chunks
    calls = {c["tool_name"]: c for c in chunks if c["kind"] == "tool_call"}
    assert calls["browser_read"]["relay"] is True
    assert "relay" not in calls["record_value"]
    results = {c["tool_name"]: c["content"] for c in chunks if c["kind"] == "tool_result"}
    assert _page_only(results["browser_read"]) == PAGE
    assert results["record_value"]["recorded"] is True
    assert results["record_value"]["url"] == "https://fin.example.edu/award/123"


@pytest.mark.asyncio
@pytest.mark.parametrize(("available", "off", "json_args"), [
    (False, frozenset(), '{"url":"https://fin.example.edu"}'),          # no extension: tool withheld
    (True, frozenset({"browser"}), '{"url":"https://fin.example.edu"}'),  # switched off: tool withheld
    (True, frozenset(), '{"address":"https://fin.example.edu"}'),       # arguments fail validation
])
async def test_a_browser_call_that_will_not_run_is_not_sent_to_the_browser(chat_harness, monkeypatch, available, off, json_args):  # noqa: F811
    """pydantic-ai still streams a call event for these; the page must not act on it."""
    from pydantic_ai import Agent
    from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    from app.services import chat_service as chat

    async def model(messages, info):
        answered = [p for m in messages for p in getattr(m, "parts", []) if isinstance(p, (ToolReturnPart, RetryPromptPart))]
        if not answered:
            yield {0: DeltaToolCall(name="browser_open", json_args=json_args, tool_call_id="open-1")}
        else:
            yield "I could not open it."

    agent = Agent(FunctionModel(stream_function=model), deps_type=AgenticChatDeps)
    agent.tool(prepare=caps.gate)(browser.browser_open)
    monkeypatch.setattr(chat, "create_agentic_chat_agent", lambda *a, **k: agent)
    monkeypatch.setattr(caps, "off_for", lambda *a, **k: off)

    chunks = []
    async for raw in chat.chat_stream(
        "Open the finance portal", [], "conversation", "user",
        user=SimpleNamespace(current_team=None, organization_id=None), team_access=SimpleNamespace(),
        browser_available=available,
    ):
        chunks.append(json.loads(raw))

    calls = [c for c in chunks if c["kind"] == "tool_call" and c["tool_name"] == "browser_open"]
    assert calls, chunks
    assert all("relay" not in c for c in calls)
