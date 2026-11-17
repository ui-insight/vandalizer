"""Chat tools that act in the person's own Chrome through the Vandalizer extension.

The agent runs here, but the browser is on the person's machine. Each tool
call already streams to the chat page as a ``tool_call`` chunk before the tool
runs; the page hands it to the extension and posts the extension's answer to
``POST /api/chat/browser-results``. The tool below waits for that answer in
Redis, keyed by the person and the tool call, so any worker can receive it.

Read-only by design: the extension refuses to click anything labelled like a
write (submit, save, approve, send, delete, pay ...) and never types into a
password field. A figure reaches the answer only through ``record_value``,
which checks that the figure is on a page read this turn.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolFuncContext

from app.services.chat_deps import AgenticChatDeps

logger = logging.getLogger(__name__)

BROWSER_TOOL_NAMES: frozenset[str] = frozenset({
    "browser_open", "browser_read", "browser_click", "browser_type", "browser_select", "record_value",
})
# Tools whose work happens in the extension; record_value runs here.
RELAYED_TOOL_NAMES: frozenset[str] = BROWSER_TOOL_NAMES - {"record_value"}

# Opening a site the person has not allowed yet waits on their click in the
# extension's permission window, so it gets longer than the other actions.
# The chat page gives up 5 seconds sooner (frontend/src/lib/browserExtension.ts)
# and posts a timeout, so a stuck command never holds up the next one.
OPEN_TIMEOUT_SECONDS = 180
ACTION_TIMEOUT_SECONDS = 60
# A result nobody collects (the turn was stopped) disappears on its own.
RESULT_TTL_SECONDS = 300
# Pages kept per turn for record_value's check.
MAX_PAGES_PER_TURN = 30

_NOT_CONNECTED = {
    "error": "browser_not_connected",
    "message": (
        "The Vandalizer browser extension is not connected in this chat. Tell the person to open "
        "Assistant settings → Set up Vandalizer Browser and follow the installation and connection steps."
    ),
}


def result_key(user_id: str, tool_call_id: str) -> str:
    return f"chat_browser_result:{user_id}:{tool_call_id}"


def should_relay(tool_name: str, args_valid: bool | None, deps: AgenticChatDeps | None) -> bool:
    """Whether the chat page may run this streamed tool call in the extension.

    pydantic-ai streams a call event before it knows the call will run: for a
    tool the capability gate withheld (it is then unknown) and for arguments
    that failed validation. Only a call that will reach the tool here, and so
    wait for an answer, goes to the person's browser.
    """
    from app.services.assistant_capabilities import tool_is_off

    return (
        deps is not None
        and tool_name in RELAYED_TOOL_NAMES
        and args_valid is True
        and deps.browser_available
        and not tool_is_off(tool_name, deps.capabilities_off)
    )


def _redis() -> Any:
    # Any: redis-py types its commands as sync-or-async, which mypy rejects in await.
    import redis.asyncio as aioredis

    from app.dependencies import get_settings

    return aioredis.from_url(f"redis://{get_settings().redis_host}:6379")


async def deliver_result(user_id: str, tool_call_id: str, result: dict) -> None:
    """Called by the router when the chat page posts the extension's answer."""
    key = result_key(user_id, tool_call_id)
    r = _redis()
    try:
        await r.rpush(key, json.dumps(result))
        await r.expire(key, RESULT_TTL_SECONDS)
    finally:
        await r.aclose()


async def _await_result(context: RunContext[AgenticChatDeps], timeout: int) -> dict:
    deps = context.deps
    if not deps.browser_available:
        return dict(_NOT_CONNECTED)
    if not context.tool_call_id:
        return {"error": "missing_tool_call_id"}
    r = _redis()
    try:
        item = await r.blpop([result_key(deps.user_id, context.tool_call_id)], timeout=timeout)
    finally:
        await r.aclose()
    if item is None:
        return {
            "error": "browser_timeout",
            "message": (
                "The browser did not answer in time. The person may have closed the Vandalizer tab, "
                "or a site permission window may still be open. Ask them to check, then try again."
            ),
        }
    try:
        result = json.loads(item[1])
    except (TypeError, ValueError):
        return {"error": "browser_bad_result"}
    if not isinstance(result, dict):
        return {"error": "browser_bad_result"}
    _remember_page(deps, result)
    return result


def _remember_page(deps: AgenticChatDeps, result: dict) -> None:
    page = result.get("page")
    if not isinstance(page, dict) or not isinstance(page.get("text"), str):
        return
    deps.browser_pages.append({
        "url": str(page.get("url") or ""),
        "title": str(page.get("title") or ""),
        "text": page["text"],
    })
    del deps.browser_pages[:-MAX_PAGES_PER_TURN]


async def browser_open(context: RunContext[AgenticChatDeps], url: str) -> dict:
    """Open a web address in the person's own Chrome, in the tab Vandalizer works in, and read it.

    Use this for portals the person signs into (financial systems, sponsor
    portals, grants systems): you act with their existing sign-in. The first
    visit to a site asks the person to allow it. Returns ``page`` with the
    page's text, where each link, button and field you can use is marked like
    ``[12]``; pass that number to browser_click, browser_type or
    browser_select. Numbers are valid only until the next read.

    If the result says ``login_required`` or ``unapproved_site`` (for example a
    single sign-on page), stop and ask the person to sign in or allow the site
    in that tab, then continue when they say so. Never ask for their password.
    """
    return await _await_result(context, OPEN_TIMEOUT_SECONDS)


async def browser_read(context: RunContext[AgenticChatDeps], query: str = "") -> dict:
    """Read the current page in the working browser tab again.

    Pass ``query`` (a few words, such as "remaining balance") to get only the
    parts of a long page around those words. Re-read after the page changes
    on its own, or when earlier element numbers no longer work.
    """
    return await _await_result(context, ACTION_TIMEOUT_SECONDS)


async def browser_click(context: RunContext[AgenticChatDeps], ref: int) -> dict:
    """Click a link, tab or button by its number from the latest read, then read the result.

    Read-only: buttons that would change something (submit, save, approve,
    send, delete, pay and similar) are refused. If one is needed, ask the
    person to click it themselves.
    """
    return await _await_result(context, ACTION_TIMEOUT_SECONDS)


async def browser_type(context: RunContext[AgenticChatDeps], ref: int, text: str) -> dict:
    """Type into a search or filter field by its number, replacing what is there.

    Then click the page's search or filter button. Never type passwords or
    other credentials; password fields are refused.
    """
    return await _await_result(context, ACTION_TIMEOUT_SECONDS)


async def browser_select(context: RunContext[AgenticChatDeps], ref: int, option: str) -> dict:
    """Choose an option, by its visible text, in a drop-down by its number."""
    return await _await_result(context, ACTION_TIMEOUT_SECONDS)


_CURRENCY = re.compile(r"[$€£]")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d)")
_SPACE = re.compile(r"\s+")


def _normalize(value: str) -> str:
    """Drop currency signs and thousands commas; collapse spacing."""
    text = _THOUSANDS.sub("", _CURRENCY.sub("", value))
    return _SPACE.sub(" ", text).strip().casefold()


def _as_shown(wanted: str) -> re.Pattern[str]:
    """Match ``wanted`` as a whole value, not as part of a longer one.

    ``100`` is not on a page that shows ``1000000``, ``-500`` or ``0.5`` does
    not contain ``500`` or ``5``, and ``1234567`` is not ``1234567.89``; but
    ``15000`` is ``15000.00``.
    """
    pattern = re.escape(wanted)
    if wanted[0].isalnum():
        pattern = r"(?<!\w)" + pattern
    if wanted[0].isdigit():
        pattern = r"(?<!\d\.)(?<![-−])" + pattern
    if wanted[-1].isalnum():
        pattern += r"(?!\w)"
    if wanted[-1].isdigit():
        pattern += r"(?!\.\d*[1-9])"
    return re.compile(pattern)


def _found_on(value: str, pages: list[dict]) -> dict | None:
    wanted = _normalize(value)
    if not wanted:
        return None
    shown = _as_shown(wanted)
    for page in reversed(pages):
        if shown.search(_normalize(page["text"])):
            return page
    return None


async def record_value(context: RunContext[AgenticChatDeps], label: str, value: str) -> dict:
    """Record a figure or fact you read in the browser, exactly as the page shows it.

    Call this for every number or status you will report from a website,
    before you write the answer. ``value`` must be copied from a page read
    this turn, as a whole value (currency signs, thousands commas and spacing
    may differ, not digits); anything else
    is refused. Report only recorded values, and give the page each came
    from. Use the calculate tool for totals or differences.
    """
    page = _found_on(value, context.deps.browser_pages)
    if page is None:
        return {
            "recorded": False,
            "error": "value_not_on_page",
            "message": (
                f"{value!r} does not appear on any page read this turn. Read the page again and copy "
                "the value exactly, or say that you could not find it."
            ),
        }
    entry = {
        "label": label.strip()[:200],
        "value": value.strip()[:200],
        "url": page["url"],
        "page_title": page["title"],
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    context.deps.browser_values.append(entry)
    return {"recorded": True, **entry}


TOOLS: list[ToolFuncContext[AgenticChatDeps, Any]] = [browser_open, browser_read, browser_click, browser_type, browser_select, record_value]
