"""Tests for the chat context-budget planner."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.context_budget import (
    DEFAULT_CONTEXT_WINDOW,
    DocumentSegment,
    count_message_tokens,
    count_tokens,
    plan_and_compact_context,
    resolve_context_window,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _FakePart:
    content: str


@dataclass
class _FakeMessage:
    parts: list = field(default_factory=list)


def _msg(text: str) -> _FakeMessage:
    return _FakeMessage(parts=[_FakePart(content=text)])


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def test_count_tokens_basic():
    assert count_tokens("") == 0
    assert count_tokens("hello world") > 0
    assert count_tokens("the same " * 100) > count_tokens("the same")


def test_count_message_tokens_adds_overhead():
    m = _msg("hi")
    assert count_message_tokens(m) >= count_tokens("hi") + 1


# ---------------------------------------------------------------------------
# Context window resolution
# ---------------------------------------------------------------------------


def test_resolve_window_prefers_config_override():
    assert resolve_context_window("whatever", {"context_window": 12345}) == 12345


def test_resolve_window_ignores_zero_or_invalid_override():
    assert resolve_context_window("claude-sonnet-4-6", {"context_window": 0}) == 200_000
    assert resolve_context_window("claude-sonnet-4-6", {"context_window": "bad"}) == 200_000


def test_resolve_window_uses_registry():
    assert resolve_context_window("gpt-4o") == 128_000
    assert resolve_context_window("claude-opus-4-7") == 200_000
    assert resolve_context_window("llama-3.1-70b") == 131_072


def test_resolve_window_fallback_default():
    assert resolve_context_window("some-mystery-model") == DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# No compaction when within budget
# ---------------------------------------------------------------------------


def test_plan_no_compaction_when_under_budget():
    result = plan_and_compact_context(
        model_name="claude-sonnet-4-6",
        model_config=None,
        system_prompt="You are helpful.",
        user_message="Tell me a joke.",
        history=[_msg("hi"), _msg("hello")],
        documents=[DocumentSegment(label="doc1", text="small doc body")],
        attachments=[],
    )
    assert result.actions == []
    assert len(result.documents) == 1
    assert len(result.history) == 2
    assert not result.fatal


# ---------------------------------------------------------------------------
# Compaction paths
# ---------------------------------------------------------------------------


def test_history_trimmed_when_over_budget():
    # Tight 1,024-token budget (config override) with a lot of history.
    long_msg = _msg("abcdefg " * 200)  # ~400 tokens
    history = [long_msg for _ in range(10)]
    result = plan_and_compact_context(
        model_name="test-model",
        model_config={"context_window": 1_500},
        system_prompt="sys",
        user_message="hi",
        history=history,
        documents=[],
        attachments=[],
        response_reserve=256,
    )
    assert len(result.history) < len(history)
    assert any(a.kind == "history_trimmed" for a in result.actions)


def test_documents_trimmed_when_over_budget():
    big_doc = DocumentSegment(label="big", text="alpha beta " * 2_000)  # ~4k tokens
    result = plan_and_compact_context(
        model_name="test-model",
        model_config={"context_window": 1_500},
        system_prompt="sys",
        user_message="hi",
        history=[],
        documents=[big_doc],
        attachments=[],
        response_reserve=256,
    )
    assert any(a.kind == "documents_trimmed" for a in result.actions)
    # The big doc should have been shrunk.
    assert len(result.documents[0].text) < len(big_doc.text)


def test_required_segment_is_not_trimmed():
    required_doc = DocumentSegment(
        label="must-keep", text="important " * 1_500, required=True
    )
    result = plan_and_compact_context(
        model_name="test-model",
        model_config={"context_window": 1_200},
        system_prompt="sys",
        user_message="hi",
        history=[],
        documents=[required_doc],
        attachments=[],
        response_reserve=128,
    )
    # The required doc is preserved verbatim.
    assert result.documents[0].text == required_doc.text
    # And we should see an over_budget action since we couldn't trim it.
    assert any(a.kind == "over_budget" for a in result.actions)
    assert result.fatal


def test_attachments_trimmed_when_over_budget():
    big_att = DocumentSegment(label="att", text="data " * 3_000)
    result = plan_and_compact_context(
        model_name="test-model",
        model_config={"context_window": 1_200},
        system_prompt="sys",
        user_message="hi",
        history=[],
        documents=[],
        attachments=[big_att],
        response_reserve=200,
    )
    assert any(
        a.kind in ("attachments_trimmed", "documents_trimmed") for a in result.actions
    )
    assert len(result.attachments[0].text) < len(big_att.text)


def test_fatal_when_floor_exceeds_budget():
    # System prompt alone blows the budget.
    huge_system = "x " * 5_000
    result = plan_and_compact_context(
        model_name="test-model",
        model_config={"context_window": 500},
        system_prompt=huge_system,
        user_message="hi",
        history=[],
        documents=[],
        attachments=[],
        response_reserve=100,
    )
    assert result.fatal
    assert any(a.kind == "over_budget" for a in result.actions)


def test_plan_dict_shape():
    result = plan_and_compact_context(
        model_name="claude-sonnet-4-6",
        model_config=None,
        system_prompt="sys",
        user_message="hi",
        history=[],
        documents=[],
        attachments=[],
    )
    plan = result.plan.to_dict()
    expected_keys = {
        "model", "context_window", "response_reserve", "input_budget",
        "total_input_tokens", "system_tokens", "user_message_tokens",
        "history_tokens", "documents_tokens", "attachments_tokens",
        "headroom_tokens",
    }
    assert expected_keys.issubset(plan.keys())
    assert plan["headroom_tokens"] == plan["input_budget"] - plan["total_input_tokens"]


def test_last_ditch_trim_handles_multiple_rounds():
    # Many mid-size docs that individually fit but collectively overflow even
    # after proportional scaling — exercises the last-ditch while loop.
    docs = [DocumentSegment(label=f"d{i}", text="word " * 500) for i in range(6)]
    result = plan_and_compact_context(
        model_name="test-model",
        model_config={"context_window": 1_500},
        system_prompt="sys",
        user_message="hi",
        history=[],
        documents=docs,
        attachments=[],
        response_reserve=200,
    )
    # Should not be fatal — we should have compacted enough to fit.
    assert not result.fatal
    assert result.plan.total_input_tokens <= result.plan.input_budget


# ---------------------------------------------------------------------------
# find_oversize_documents
# ---------------------------------------------------------------------------


def test_find_oversize_documents_flags_giants():
    from app.services.context_budget import find_oversize_documents

    # A 50k-token doc against a 16k-window model is clearly oversize.
    docs = [
        {"uuid": "a", "title": "small.txt", "token_count": 500},
        {"uuid": "b", "title": "huge.pdf", "token_count": 50_000},
    ]
    oversize = find_oversize_documents(
        documents=docs,
        model_name="gpt-3.5",  # 16k context per fallback table
    )
    assert [o.uuid for o in oversize] == ["b"]
    assert oversize[0].title == "huge.pdf"
    assert oversize[0].token_count == 50_000


def test_find_oversize_documents_respects_model_config_override():
    from app.services.context_budget import find_oversize_documents

    docs = [{"uuid": "a", "title": "doc.txt", "token_count": 50_000}]
    # Override the window to 1M — same doc is now small enough.
    oversize = find_oversize_documents(
        documents=docs,
        model_name="gpt-3.5",
        model_config={"context_window": 1_000_000},
    )
    assert oversize == []


def test_find_oversize_documents_sorted_largest_first():
    from app.services.context_budget import find_oversize_documents

    docs = [
        {"uuid": "a", "title": "medium", "token_count": 20_000},
        {"uuid": "b", "title": "huge", "token_count": 80_000},
        {"uuid": "c", "title": "big", "token_count": 30_000},
    ]
    oversize = find_oversize_documents(documents=docs, model_name="gpt-3.5")
    # All three exceed 16k - 4k reserve - 1k overhead = ~11k; largest first.
    assert [o.uuid for o in oversize] == ["b", "c", "a"]


def test_find_oversize_documents_handles_missing_token_count():
    from app.services.context_budget import find_oversize_documents

    # Documents with missing/zero token_count should never be flagged.
    docs = [{"uuid": "a", "title": "no-count"}, {"uuid": "b", "title": "zero", "token_count": 0}]
    oversize = find_oversize_documents(documents=docs, model_name="gpt-3.5")
    assert oversize == []
