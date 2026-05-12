"""Unit tests for chat continuity — find_continuity_candidate selection logic.

Exercises the recency window, idle threshold, and assistant-message-required
filter against mocked ChatConversation / ChatMessage records.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.chat import ChatRole


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _conv(uuid: str, hours_ago: int, messages: list[str] | None = None, title: str = "Test"):
    """Build a ChatConversation-shaped mock."""
    c = MagicMock()
    c.uuid = uuid
    c.user_id = "alice"
    c.title = title
    c.messages = [MagicMock() for _ in (messages or [])]
    # Stable ids on each message mock so we can look them up later
    for i, m in enumerate(c.messages):
        m._test_idx = i
    c.updated_at = _now() - datetime.timedelta(hours=hours_ago)
    return c


def _msg(role: ChatRole, message: str):
    m = MagicMock()
    m.role = role
    m.message = message
    return m


class _AnyCompare:
    """Sentinel for Beanie field references in unit tests.

    The service code does e.g. `ChatConversation.updated_at <= some_datetime`
    to build a Beanie query expression. MagicMock's default __le__ raises
    TypeError when compared to a datetime, so we substitute an opaque
    sentinel whose comparison ops return a fresh sentinel (truthy)."""

    def __le__(self, other): return _AnyCompare()
    def __ge__(self, other): return _AnyCompare()
    def __lt__(self, other): return _AnyCompare()
    def __gt__(self, other): return _AnyCompare()
    def __eq__(self, other): return _AnyCompare()
    def __ne__(self, other): return _AnyCompare()
    def __neg__(self): return _AnyCompare()  # for `-ChatConversation.updated_at` in sort
    def __bool__(self): return True
    def __hash__(self): return 0


def _patch_query(conversations, messages_by_id_idx):
    """Replace ChatConversation/ChatMessage in chat_service with MagicMocks.

    We mock the whole classes because Beanie's field descriptors require
    Beanie to be initialized. Field references like `ChatConversation.user_id`
    return _AnyCompare sentinels that tolerate the comparison operators the
    service uses when building query expressions.
    """
    # Build a chain mock for ChatConversation.find(...).sort(...).limit(...).to_list()
    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=conversations)
    sort_chain = MagicMock()
    sort_chain.limit = MagicMock(return_value=chain)
    find_chain = MagicMock()
    find_chain.sort = MagicMock(return_value=sort_chain)

    conv_klass = MagicMock()
    conv_klass.find = MagicMock(return_value=find_chain)
    conv_klass.user_id = _AnyCompare()
    conv_klass.updated_at = _AnyCompare()

    conversations_by_id = {c.uuid: c.messages for c in conversations}

    async def _msg_get(msg_id):
        for conv_uuid, conv_messages in conversations_by_id.items():
            for i, m_mock in enumerate(conv_messages):
                if m_mock is msg_id:
                    return messages_by_id_idx.get((conv_uuid, i))
        return None

    def _msg_find(_filter):
        ids = _filter.get("_id", {}).get("$in", [])
        for conv_uuid, conv_messages in conversations_by_id.items():
            if any(m_mock in ids for m_mock in conv_messages):
                for i, m_mock in enumerate(conv_messages):
                    msg = messages_by_id_idx.get((conv_uuid, i))
                    if msg and msg.role == ChatRole.ASSISTANT:
                        chain2 = MagicMock()
                        chain2.limit = MagicMock(return_value=chain2)
                        chain2.to_list = AsyncMock(return_value=[msg])
                        return chain2
        empty = MagicMock()
        empty.limit = MagicMock(return_value=empty)
        empty.to_list = AsyncMock(return_value=[])
        return empty

    msg_klass = MagicMock()
    msg_klass.get = AsyncMock(side_effect=_msg_get)
    msg_klass.find = MagicMock(side_effect=_msg_find)

    return [
        patch("app.services.chat_service.ChatConversation", new=conv_klass),
        patch("app.services.chat_service.ChatMessage", new=msg_klass),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_returns_none_when_no_conversations():
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate

    stack = ExitStack()
    for p in _patch_query([], {}):
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")
    assert result is None


async def test_returns_candidate_when_assistant_reply_is_last_message():
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate

    conv = _conv("c1", hours_ago=17, messages=["user-msg", "asst-msg"])
    messages = {
        ("c1", 0): _msg(ChatRole.USER, "Question about NIH proposal"),
        ("c1", 1): _msg(ChatRole.ASSISTANT, "Here is a 4-step plan for extracting budget categories from your NIH proposal..."),
    }

    stack = ExitStack()
    for p in _patch_query([conv], messages):
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")

    assert result is not None
    assert result["has_recent"] is True
    assert result["conversation_uuid"] == "c1"
    assert result["last_message_role"] == "assistant"
    assert "Here is a 4-step plan" in result["last_message_snippet"]
    assert result["hours_ago"] == 17


async def test_returns_candidate_when_assistant_message_exists_anywhere():
    """Conversation that ended with a user message still qualifies if assistant replied earlier."""
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate

    conv = _conv("c1", hours_ago=12, messages=["u1", "a1", "u2"])
    messages = {
        ("c1", 0): _msg(ChatRole.USER, "first question"),
        ("c1", 1): _msg(ChatRole.ASSISTANT, "first reply"),
        ("c1", 2): _msg(ChatRole.USER, "follow-up that never got answered"),
    }

    stack = ExitStack()
    for p in _patch_query([conv], messages):
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")

    assert result is not None
    assert result["conversation_uuid"] == "c1"
    assert result["last_message_role"] == "user"  # last message is user
    assert "follow-up" in result["last_message_snippet"]


async def test_skips_conversation_with_only_user_messages():
    """A conversation with no assistant reply anywhere should not qualify."""
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate

    conv = _conv("c1", hours_ago=12, messages=["u1"])
    messages = {("c1", 0): _msg(ChatRole.USER, "abandoned prompt")}

    stack = ExitStack()
    for p in _patch_query([conv], messages):
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")

    assert result is None


async def test_snippet_is_truncated():
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate, _SNIPPET_MAX_CHARS

    long_text = "x" * (_SNIPPET_MAX_CHARS + 200)
    conv = _conv("c1", hours_ago=10, messages=["a1"])
    messages = {("c1", 0): _msg(ChatRole.ASSISTANT, long_text)}

    stack = ExitStack()
    for p in _patch_query([conv], messages):
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")

    assert result is not None
    assert len(result["last_message_snippet"]) <= _SNIPPET_MAX_CHARS
    assert result["last_message_snippet"].endswith("…")


async def test_first_qualifying_conversation_wins():
    """Conversations are sorted by updated_at desc; the first qualifier wins."""
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate

    c1 = _conv("c1", hours_ago=8, messages=["a1"])
    c2 = _conv("c2", hours_ago=20, messages=["a1"])
    messages = {
        ("c1", 0): _msg(ChatRole.ASSISTANT, "newer answer"),
        ("c2", 0): _msg(ChatRole.ASSISTANT, "older answer"),
    }

    stack = ExitStack()
    for p in _patch_query([c1, c2], messages):  # already in updated_at-desc order
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")

    assert result is not None
    assert result["conversation_uuid"] == "c1"


async def test_hours_ago_is_at_least_one():
    """Defensive: even a sub-hour idle conversation reports >= 1 hour."""
    from contextlib import ExitStack

    from app.services.chat_service import find_continuity_candidate

    conv = _conv("c1", hours_ago=0, messages=["a1"])
    messages = {("c1", 0): _msg(ChatRole.ASSISTANT, "reply")}

    stack = ExitStack()
    for p in _patch_query([conv], messages):
        stack.enter_context(p)
    with stack:
        result = await find_continuity_candidate("alice")

    assert result is not None
    assert result["hours_ago"] >= 1
