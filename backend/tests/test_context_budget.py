"""Tests for the chat context-budget planner."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.context_budget import (
    DEFAULT_CONTEXT_WINDOW,
    DocumentSegment,
    count_message_tokens,
    count_tokens,
    estimate_input_tokens,
    input_budget_for,
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


def test_find_oversize_documents_corrects_a_stored_count_for_an_exact_model(
    tmp_path,
):
    """A stored `token_count` is always a tiktoken figure, whatever the model.

    Exact tokenization made `token_safety_margin` return 1.0 for models whose
    vocabulary is on disk, which is right when the planner counts the text
    itself. It is wrong here: this consumer never sees the text, only a
    tiktoken count taken at ingestion. Passing that through uncorrected makes
    the pre-flight check under-warn by exactly the divergence the exact
    counting exists to remove, so a workflow that will overflow is not flagged
    before it runs.
    """
    import json

    from app.services.context_budget import find_oversize_documents

    snap = (
        tmp_path / "hub" / "models--Qwen--Qwen3-VL-8B-Instruct" / "snapshots" / "r1"
    )
    snap.mkdir(parents=True)
    (snap / "tokenizer.json").write_text(json.dumps({
        "version": "1.0", "truncation": None, "padding": None,
        "added_tokens": [], "normalizer": None,
        "pre_tokenizer": {"type": "Whitespace"}, "post_processor": None,
        "decoder": None,
        "model": {"type": "WordLevel", "vocab": {"[UNK]": 0}, "unk_token": "[UNK]"},
    }))

    # 32,768 window -> 8,192 reserve -> 23,552 budget after 1,024 overhead.
    # A stored 23,000 looks like it fits, and does not once corrected.
    docs = [{"uuid": "a", "title": "proposal.pdf", "token_count": 23_000}]
    oversize = find_oversize_documents(
        documents=docs,
        model_name="Qwen/Qwen3-VL-8B-Instruct",
        model_config={
            "context_window": 32_768,
            "tokenizer_cache_root": str(tmp_path),
        },
    )
    assert [o.uuid for o in oversize] == ["a"], (
        "a stored tiktoken count was compared against the budget with no "
        "divergence allowance, so an overflowing document was not flagged"
    )


def test_find_oversize_documents_does_not_inflate_for_openai_models():
    """tiktoken *is* the tokenizer there, so the stored count is already exact
    and inflating it would flag documents that genuinely fit."""
    from app.services.context_budget import find_oversize_documents

    docs = [{"uuid": "a", "title": "doc.txt", "token_count": 23_000}]
    assert find_oversize_documents(
        documents=docs,
        model_name="gpt-4o",
        model_config={"context_window": 32_768},
    ) == []


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


class TestEstimateInputTokens:
    """Routing has to ask "would this fit?" before a context is built.

    Answering that by running the planner would trim the very documents we're
    trying to measure, so the estimate is computed separately — and it has to
    match what the planner counts, or routing fires on the wrong requests.
    """

    def _pieces(self):
        return dict(
            system_prompt="You are a helpful assistant.",
            user_message="What is the total budget?",
            history=[],
            documents=[DocumentSegment(label="d", text="word " * 500)],
            attachments=[],
        )

    def test_counts_every_component(self):
        total = estimate_input_tokens(model_name="m", **self._pieces())
        assert total > 500  # the document alone is ~500 words

    def test_agrees_with_the_planner_on_a_request_that_fits(self):
        """The estimate is only useful if it matches the number the planner
        would have produced — otherwise routing triggers at the wrong size."""
        pieces = self._pieces()
        estimate = estimate_input_tokens(model_name="m", **pieces)
        planned = plan_and_compact_context(
            model_name="m", model_config={"context_window": 128000}, **pieces
        )
        assert not planned.actions, "fixture must fit, or the planner trims it"
        assert abs(estimate - planned.plan.total_input_tokens) <= 64

    def test_empty_request_is_not_negative(self):
        assert estimate_input_tokens(
            model_name="m", system_prompt="", user_message="",
            history=[], documents=[], attachments=[],
        ) >= 0


class TestInputBudgetFor:
    def test_subtracts_the_response_reserve_from_the_window(self):
        assert input_budget_for("m", {"context_window": 32768}) == 32768 - 8192

    def test_a_bigger_window_yields_a_bigger_budget(self):
        small = input_budget_for("m", {"context_window": 32768})
        large = input_budget_for("m", {"context_window": 262144})
        assert large > small * 5

    def test_never_returns_zero_or_less(self):
        assert input_budget_for("m", {"context_window": 1}) >= 1


# ---------------------------------------------------------------------------
# resolve_response_reserve
# ---------------------------------------------------------------------------


def test_response_reserve_defaults_to_quarter_window_capped_at_8k():
    from app.services.context_budget import resolve_response_reserve

    assert resolve_response_reserve(16_000) == 4_000
    assert resolve_response_reserve(1_000_000) == 8_192  # capped
    assert resolve_response_reserve(1_000) == 1_024      # floored


def test_response_reserve_honors_per_model_override():
    from app.services.context_budget import resolve_response_reserve

    assert resolve_response_reserve(128_000, {"response_reserve_tokens": 32_768}) == 32_768
    # Unset/blank/invalid falls back to the scaled default.
    assert resolve_response_reserve(128_000, {"response_reserve_tokens": 0}) == 8_192
    assert resolve_response_reserve(128_000, {"response_reserve_tokens": "nope"}) == 8_192


def test_find_oversize_documents_honors_reserve_override():
    from app.services.context_budget import find_oversize_documents

    # 128k window: default reserve 8k leaves ~119k, so a 100k doc fits. Raise
    # the reserve to 64k and the same doc no longer does — the pre-flight must
    # use the same reserve the request will actually send.
    #
    # The margin is pinned to 1.0 so this measures the reserve and nothing else.
    # Stored counts are raw tiktoken figures and are inflated by the model's
    # safety margin at read time, which for an unknown model would push this
    # 100k document over the budget on its own — correctly, but for a different
    # reason than this test is about. That path is covered in
    # test_token_safety_margin.py.
    docs = [{"uuid": "a", "title": "big.pdf", "token_count": 100_000}]
    cfg = {"context_window": 128_000, "token_safety_margin": 1.0}
    assert find_oversize_documents(documents=docs, model_name="m", model_config=cfg) == []

    cfg_wide_reserve = {
        "context_window": 128_000,
        "response_reserve_tokens": 64_000,
        "token_safety_margin": 1.0,
    }
    flagged = find_oversize_documents(
        documents=docs, model_name="m", model_config=cfg_wide_reserve,
    )
    assert [o.uuid for o in flagged] == ["a"]


# ---------------------------------------------------------------------------
# find_context_overflow
# ---------------------------------------------------------------------------


def _nasa_package():
    """Four docs that each fit a 65k-window model but total 92k — the shape of
    the support ticket that motivated the combined check."""
    return [
        {"uuid": "a", "title": "ECIPES_Amend23.pdf", "token_count": 12_000},
        {"uuid": "b", "title": "Earth Science Overview.pdf", "token_count": 15_000},
        {"uuid": "c", "title": "SummaryOfSolicitation.pdf", "token_count": 25_000},
        {"uuid": "d", "title": "proposers_guide.pdf", "token_count": 40_119},
    ]


def test_find_context_overflow_flags_combined_package():
    from app.services.context_budget import find_context_overflow

    overflow = find_context_overflow(
        documents=_nasa_package(),
        # Margin pinned to 1.0 so this measures combination and nothing else;
        # the margin's own effect is covered below.
        model_config={"context_window": 65_536, "token_safety_margin": 1.0},
        model_name="m",
    )
    assert overflow is not None
    assert overflow.kind == "combined"
    assert overflow.total_tokens == 92_119
    # Every doc is named, largest first — they are all part of the problem.
    assert [d.uuid for d in overflow.documents] == ["d", "c", "b", "a"]


def test_find_context_overflow_returns_none_when_package_fits():
    from app.services.context_budget import find_context_overflow

    assert find_context_overflow(
        documents=_nasa_package(),
        model_name="m",
        model_config={"context_window": 262_144},
    ) is None


def test_find_context_overflow_single_doc_takes_precedence():
    from app.services.context_budget import find_context_overflow

    docs = [
        {"uuid": "a", "title": "small", "token_count": 500},
        {"uuid": "b", "title": "giant", "token_count": 90_000},
    ]
    overflow = find_context_overflow(
        documents=docs, model_name="m", model_config={"context_window": 65_536},
    )
    assert overflow is not None
    # Only the doc that is individually too big gets named — converting the
    # small one to a KB would not help.
    assert overflow.kind == "single"
    assert [d.uuid for d in overflow.documents] == ["b"]


def test_find_context_overflow_corrects_stored_tiktoken_counts():
    """A package that fits raw but not once the divergence is allowed for.

    Stored `token_count` values are tiktoken figures, and tiktoken reads low
    for every non-OpenAI model. Without the allowance this check passes a
    workflow that the gateway then rejects mid-run -- the exact failure the
    combined check was added to prevent, and worst for budget workbooks, which
    are both the likeliest thing to push a package over and the content
    tiktoken under-counts most.
    """
    from app.services.context_budget import find_context_overflow

    # The input budget for a 65,536-token window is 56,320 once the response
    # reserve and overhead are taken out. 50,000 raw fits it; at the 1.5
    # default the same package is 75,000, which does not.
    docs = [
        {"uuid": "a", "title": "Narrative.pdf", "token_count": 25_000},
        {"uuid": "b", "title": "Budget_Justification.xlsx", "token_count": 25_000},
    ]

    assert find_context_overflow(
        documents=docs,
        model_name="qwen-local",
        model_config={"context_window": 65_536, "token_safety_margin": 1.0},
    ) is None

    overflow = find_context_overflow(
        documents=docs,
        model_name="qwen-local",
        model_config={"context_window": 65_536},
    )
    assert overflow is not None
    assert overflow.kind == "combined"
    assert overflow.total_tokens == 75_000


def test_find_context_overflow_does_not_inflate_for_openai_models():
    """tiktoken *is* their tokenizer, so the stored figure is already exact."""
    from app.services.context_budget import find_context_overflow

    docs = [{"uuid": "a", "title": "doc", "token_count": 30_000}]
    assert find_context_overflow(
        documents=docs, model_name="gpt-4o", model_config={"context_window": 65_536},
    ) is None

def test_find_context_overflow_empty_input():
    from app.services.context_budget import find_context_overflow

    assert find_context_overflow(documents=[], model_name="m") is None


# ---------------------------------------------------------------------------
# Truncation must slice with the vocabulary that did the counting
# ---------------------------------------------------------------------------


class _DenseTokenizer:
    """A self-consistent vocabulary denser than cl100k: one token per two
    characters, where tiktoken averages roughly one per three on prose.

    Self-consistency is the point — ``encode(decode(ids))`` returns ``ids`` —
    because the bug under test is a disagreement between the ruler that counts
    and the ruler that slices, and a fake whose halves disagree with each other
    cannot distinguish the two.
    """

    def encode(self, text, add_special_tokens=False):
        class _Encoded:
            ids = list(range(len(text) // 2))

        return _Encoded()

    def decode(self, ids):
        return "ab" * len(ids)


def _dense_model(monkeypatch):
    from app.services import context_budget as cb

    monkeypatch.setattr(cb, "resolve_exact_tokenizer", lambda *a, **k: _DenseTokenizer())
    return cb


def test_truncation_slices_with_the_tokenizer_that_counted(monkeypatch):
    """The budget is denominated in the counting vocabulary's tokens.

    Slicing a tiktoken list by that number is a unit error. The two rulers
    differ by up to ~1.5x on the numeric content this product handles, so the
    head and tail slices overlapped and the "truncated" text came back *longer*
    than the original — with a negative reported loss, which the last-ditch
    loop reads as an untrimmable segment and answers by dropping the whole
    document.
    """
    cb = _dense_model(monkeypatch)
    text = "Budget line 12,345.67 for FY2026 indirect 58% MTDC exclusion. " * 400

    total = cb.count_tokens(text, "qwen-local", {})
    assert cb.token_safety_margin("qwen-local", {}) == 1.0

    for keep in (0.95, 0.90, 0.75, 0.50, 0.30):
        allowed = int(total * keep)
        out, loss = cb._truncate_text_to_tokens(
            text, allowed, "qwen-local", model_config={}
        )
        assert cb.count_tokens(out, "qwen-local", {}) <= allowed, (
            f"keeping {keep:.0%} overshot its budget — the slice was taken in "
            f"another vocabulary's units"
        )
        assert loss >= 0, f"keeping {keep:.0%} reported a negative loss"
        assert len(out) <= len(text), f"keeping {keep:.0%} grew the text"


def test_truncation_leaves_text_alone_when_the_budget_already_covers_it(
    monkeypatch,
):
    """A budget wider than the token list is not a trim.

    Head and tail would overlap and reproduce the whole text, and adding the
    marker would make it longer still. Returning the text untouched with a zero
    loss is the honest answer; a negative loss is never one.
    """
    cb = _dense_model(monkeypatch)
    text = "short enough already"

    out, loss = cb._truncate_text_to_tokens(
        text, 10_000, "qwen-local", model_config={}
    )
    assert out == text
    assert loss == 0


def test_truncation_never_reports_a_negative_loss(monkeypatch):
    """``dropped += loss`` and the ``loss <= 0`` drop rule both depend on it."""
    cb = _dense_model(monkeypatch)
    text = "Budget line 12,345.67 for FY2026. " * 200
    total = cb.count_tokens(text, "qwen-local", {})

    for allowed in (1, 2, total // 3, total - 1, total, total + 1, total * 3):
        _, loss = cb._truncate_text_to_tokens(
            text, allowed, "qwen-local", model_config={}
        )
        assert loss >= 0, f"allowed={allowed} produced loss={loss}"


def _write_tokenizer(tmp_path, model_slug, body):
    import json

    snap = tmp_path / "hub" / f"models--{model_slug}" / "snapshots" / "r1"
    snap.mkdir(parents=True)
    (snap / "tokenizer.json").write_text(json.dumps(body))
    return snap


_MINIMAL_VOCAB = {
    "version": "1.0",
    "added_tokens": [],
    "normalizer": None,
    "pre_tokenizer": {"type": "Whitespace"},
    "post_processor": None,
    "decoder": None,
    "model": {"type": "WordLevel", "vocab": {"[UNK]": 0}, "unk_token": "[UNK]"},
}


def test_a_tokenizer_carrying_truncation_does_not_cap_every_count(tmp_path):
    """`Tokenizer.from_file` restores a truncation stanza and `encode` then
    silently caps.

    A vocabulary specifying ``max_length`` would make every document count as
    at most that many tokens — a worse under-count than the estimate this
    replaces, and undetectable downstream, because a resolved tokenizer sets
    the safety margin to 1.0.
    """
    from app.services import context_budget as cb

    body = dict(_MINIMAL_VOCAB)
    body["truncation"] = {
        "direction": "Right", "max_length": 8, "strategy": "LongestFirst",
        "stride": 0,
    }
    body["padding"] = None
    _write_tokenizer(tmp_path, "Fake--Capped", body)

    cb._find_vocabulary.cache_clear()
    cb._load_tokenizer.cache_clear()

    text = " ".join(f"word{i}" for i in range(200))
    count = cb.count_tokens(
        text, "Fake/Capped", {"tokenizer_cache_root": str(tmp_path)}
    )
    assert count > 8, (
        f"a truncation stanza capped the count at {count}; every document "
        f"would look like it fits"
    )


def test_a_tokenizer_that_cannot_encode_is_treated_as_absent(tmp_path, monkeypatch):
    """Presence of a tokenizer is read downstream as proof the count is exact.

    One that loads but cannot encode satisfied ``resolve_exact_tokenizer`` —
    setting the margin to 1.0 — while counting quietly fell back to tiktoken,
    yielding a raw estimate with the safety margin switched off. That is the
    hard-failing under-count this module exists to prevent.
    """
    from app.services import context_budget as cb

    _write_tokenizer(tmp_path, "Fake--Broken", dict(_MINIMAL_VOCAB, padding=None,
                                                    truncation=None))
    cb._find_vocabulary.cache_clear()
    cb._load_tokenizer.cache_clear()

    class _Broken:
        def encode(self, *a, **k):
            raise RuntimeError("corrupt vocabulary")

        def no_truncation(self):
            pass

        def no_padding(self):
            pass

    import tokenizers

    monkeypatch.setattr(
        tokenizers.Tokenizer, "from_file", staticmethod(lambda *a, **k: _Broken())
    )
    cb._load_tokenizer.cache_clear()

    cfg = {"tokenizer_cache_root": str(tmp_path)}
    assert cb.resolve_exact_tokenizer("Fake/Broken", cfg) is None, (
        "an unusable tokenizer was reported as available, which suppresses "
        "the safety margin while counting falls back to an estimate"
    )
    assert cb.token_safety_margin("Fake/Broken", cfg) > 1.0, (
        "the margin stayed at 1.0 for a model whose count is not exact"
    )


# ---------------------------------------------------------------------------
# Configuration: what wins, and how discovery is turned off
# ---------------------------------------------------------------------------


def test_an_exact_count_is_not_multiplied_by_a_stale_configured_margin(tmp_path, monkeypatch):
    """The guidance for a model with no local vocabulary is to configure a
    margin. When that deployment later mounts its model cache — the headline
    feature — those models start counting exactly, and the configured number
    becomes a second correction applied to a figure that needs none: every
    budget inflated, and every trim over-aggressive by the same factor through
    raw_usable.
    """
    from app.services import context_budget as cb

    _write_tokenizer(tmp_path, "Fake--Exact", dict(_MINIMAL_VOCAB, truncation=None, padding=None))
    cb._find_vocabulary.cache_clear()
    cb._load_tokenizer.cache_clear()

    cfg = {"tokenizer_cache_root": str(tmp_path), "token_safety_margin": 1.35}
    assert cb.token_safety_margin("Fake/Exact", cfg) == 1.0, (
        "a configured margin was applied on top of an exact count"
    )


def test_a_configured_margin_still_wins_for_an_estimated_model(tmp_path):
    """The setting is not ignored — it is the whole point for models whose
    count is an estimate."""
    from app.services import context_budget as cb

    cfg = {"tokenizer_cache_root": str(tmp_path), "token_safety_margin": 1.35}
    assert cb.token_safety_margin("some/hosted-model", cfg) == 1.35


def test_an_emptied_cache_root_turns_discovery_off(tmp_path, monkeypatch):
    """`TOKENIZER_CACHE_ROOT=` is how an operator opts out. Collapsing "unset"
    and "set to empty" made it fall through to the hardcoded /hf-cache and
    quietly ignore them.
    """
    from app.services import context_budget as cb

    _write_tokenizer(tmp_path, "Fake--Findable", dict(_MINIMAL_VOCAB, truncation=None, padding=None))
    cb._find_vocabulary.cache_clear()
    cb._load_tokenizer.cache_clear()
    cb._settings_tokenizer_cache_root.cache_clear()

    # The default root has to be findable for this to discriminate: otherwise
    # an ignored opt-out and an honoured one both return None, for different
    # reasons, and the test proves nothing.
    monkeypatch.setattr(cb, "DEFAULT_TOKENIZER_CACHE_ROOT", str(tmp_path))

    # Present when the root points at it...
    assert cb.resolve_exact_tokenizer(
        "Fake/Findable", {"tokenizer_cache_root": str(tmp_path)},
    ) is not None

    # ...and gone when the operator empties the root, rather than silently
    # falling through to the default and loading it anyway.
    assert cb.resolve_exact_tokenizer(
        "Fake/Findable", {"tokenizer_cache_root": ""},
    ) is None

    monkeypatch.setattr(cb, "_settings_tokenizer_cache_root", lambda: "")
    assert cb.resolve_exact_tokenizer("Fake/Findable", {}) is None


def test_an_unreadable_settings_object_still_falls_back_to_the_default(tmp_path, monkeypatch):
    """None means "no answer" and must not be mistaken for "no root"."""
    from app.services import context_budget as cb

    _write_tokenizer(tmp_path, "Fake--Defaulted", dict(_MINIMAL_VOCAB, truncation=None, padding=None))
    cb._find_vocabulary.cache_clear()
    cb._load_tokenizer.cache_clear()
    monkeypatch.setattr(cb, "DEFAULT_TOKENIZER_CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(cb, "_settings_tokenizer_cache_root", lambda: None)

    # Falls back to the default and finds it, rather than reading the failure
    # as an operator opt-out.
    assert cb.resolve_exact_tokenizer("Fake/Defaulted", {}) is not None
