"""The budget estimate must never come in under what the model actually charges.

tiktoken is OpenAI's tokenizer. `_encoding_for()` handed `cl100k_base` to every
model whose name did not look like GPT-4o/4.1/o-series, which on this deployment
is 100% of them — Qwen has its own ~151k-vocab BPE. The estimate was therefore
measured with the wrong ruler, and always in the unsafe direction: the planner
believed there was room when there was not, so a 36-page proposal was passed to
a model that rejected it, and `choose_document_model()` — comparing the same
optimistic number against the same budget — saw headroom and declined to route.
The one feature built to handle oversized documents was disabled by the
arithmetic error it was supposed to react to.

These tests assert the *direction* of the error, not a magic constant. Ground
truth is the model's own `prompt_tokens`, which every successful response
carries in its `usage` chunk and which costs nothing to collect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.context_budget import (
    DEFAULT_TOKEN_SAFETY_MARGIN,
    DocumentSegment,
    count_raw_tokens,
    count_tokens,
    estimate_input_tokens,
    find_oversize_documents,
    plan_and_compact_context,
    token_safety_margin,
)


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

# (model, planner's pre-fix estimate, prompt_tokens the model reported)
#
# Harvested from 97 end-to-end runs against live model servers — every run
# that produced BOTH a `context_budget` chunk (the planner's belief) and a
# `usage` chunk (what the server actually charged), deduplicated to 26 distinct
# observations. Three models, request sizes spanning 307 to 46,916 tokens.
#
# The estimate is under in all 97. It is never once equal or over.
#
# The ratio is not monotonic in request size — 1.042 at 307 tokens, 1.173 at
# 2.2k, 1.076 at 47k. Later measurement against the models directly showed why,
# and it is not size: the divergence is driven by *content*. cl100k and the
# Qwen vocabulary agree exactly on flowing prose (1.000) and diverge sharply on
# numbers and tables (1.171 on a real budget justification, 1.455 on a
# synthetic currency table). The rows below vary because the documents behind
# them vary, not because the requests were bigger or smaller.
#
# That is why these observations pin down the *direction* of the error and not
# a safe constant: no constant is safe across that range, which is what
# motivated exact tokenization (see test_exact_tokenizer.py). These rows now
# guard the fallback path used for models whose vocabulary we do not have.
OBSERVED_UNDERCOUNTS: list[tuple[str, int, int]] = [
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2154, 2527),   # 1.1732 — worst observed
    ("Qwen/Qwen3-VL-8B-Instruct", 2154, 2527),        # 1.1732
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2282, 2661),   # 1.1661
    ("Qwen/Qwen3-VL-8B-Instruct", 2282, 2661),        # 1.1661
    ("Qwen/Qwen3-VL-8B-Instruct", 2284, 2663),        # 1.1659
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2284, 2663),   # 1.1659
    ("Qwen/Qwen3-VL-8B-Instruct", 2287, 2666),        # 1.1657
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2287, 2666),   # 1.1657
    ("Qwen/Qwen3-VL-8B-Instruct", 2288, 2667),        # 1.1656
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2288, 2667),   # 1.1656
    ("Qwen/Qwen3-VL-8B-Instruct", 2292, 2671),        # 1.1654
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2292, 2671),   # 1.1654
    ("Qwen/Qwen3-VL-8B-Instruct", 2294, 2673),        # 1.1652
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2294, 2673),   # 1.1652
    ("Qwen/Qwen3-VL-8B-Instruct", 2297, 2676),        # 1.1650
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2297, 2676),   # 1.1650
    ("Qwen/Qwen3-VL-8B-Instruct", 2298, 2677),        # 1.1649
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2298, 2677),   # 1.1649
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2694, 3078),   # 1.1425
    ("Qwen/Qwen3-VL-8B-Instruct", 2694, 3078),        # 1.1425
    ("Qwen/Qwen3-VL-8B-Instruct", 2721, 3105),        # 1.1411
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 2721, 3105),   # 1.1411
    ("Qwen/Qwen3.5-9B", 46914, 50492),                # 1.0763 — largest request
    ("Qwen/Qwen3.5-9B", 46916, 50494),                # 1.0763
    ("Qwen/Qwen3-VL-8B-Instruct", 307, 320),          # 1.0423 — smallest request
    ("Qwen/Qwen3-VL-30B-A3B-Instruct", 307, 320),     # 1.0423
]


def _corrected(model: str, raw_estimate: int) -> int:
    """What the planner now believes, given what it used to believe.

    The margin is applied uniformly across every component, so scaling a
    recorded whole-request total reproduces the corrected total without needing
    to reconstruct the original request text.
    """
    return int(raw_estimate * token_safety_margin(model) + 0.999)


class TestAgainstRecordedGroundTruth:
    """The property that matters: never guess low. Direction, not magnitude."""

    def test_the_bug_is_real_in_every_recorded_run(self):
        """Guards the premise. If this ever fails, the fixture is stale."""
        for model, raw_estimate, actual in OBSERVED_UNDERCOUNTS:
            assert raw_estimate < actual, (
                f"{model}: recorded estimate {raw_estimate} was not under "
                f"{actual}; the observation set no longer shows the bug"
            )

    def test_corrected_estimate_never_undercounts_the_model(self):
        """The regression. Asserts direction against real `prompt_tokens`."""
        for model, raw_estimate, actual in OBSERVED_UNDERCOUNTS:
            corrected = _corrected(model, raw_estimate)
            assert corrected >= actual, (
                f"{model}: corrected estimate {corrected} is still under the "
                f"{actual} tokens the model reported — the planner would again "
                f"believe a request fits when it does not"
            )

    def test_margin_is_not_wastefully_larger_than_the_evidence(self):
        """Conservative is safe; absurdly conservative routes far too early.

        Being optimistic costs a hard failure, so the margin is deliberately
        above the worst observation (1.1732). But a margin of, say, 3x would
        push every ordinary document onto a bigger model for nothing. Two
        sanity bounds so a future edit cannot drift in either direction
        unnoticed.
        """
        margin = token_safety_margin("Qwen/Qwen3-VL-8B-Instruct")
        assert margin > 1.1732, "margin does not cover the worst observation"
        assert margin <= 1.5, "margin is far beyond anything measured"

    def test_headroom_over_the_worst_observation_is_real_but_modest(self):
        worst_model, worst_raw, worst_actual = OBSERVED_UNDERCOUNTS[0]
        corrected = _corrected(worst_model, worst_raw)
        # Covers it, and does not overshoot by more than a quarter again.
        assert worst_actual <= corrected <= int(worst_actual * 1.25)


class TestMarginSelection:
    def test_non_openai_models_get_the_default_margin(self):
        for name in (
            "Qwen/Qwen3-VL-8B-Instruct",
            "Qwen/Qwen3.5-9B",
            "meta-llama/Llama-3.1-70B",
            "mistral-large",
            "claude-sonnet-4",
        ):
            assert token_safety_margin(name) == DEFAULT_TOKEN_SAFETY_MARGIN

    def test_models_tiktoken_actually_measures_are_not_inflated(self):
        """cl100k/o200k *are* these models' real tokenizers, so the count is
        exact and a margin would only cause premature routing."""
        for name in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "o1", "o3-mini", "o4"):
            assert token_safety_margin(name) == 1.0

    def test_unknown_or_empty_model_is_treated_as_non_openai(self):
        """Failing safe: an unrecognised name is far more likely to be a
        self-hosted model than an OpenAI one."""
        assert token_safety_margin("") == DEFAULT_TOKEN_SAFETY_MARGIN
        assert token_safety_margin("some-new-model") == DEFAULT_TOKEN_SAFETY_MARGIN

    def test_deployment_can_tune_the_margin_per_model(self):
        """A deployment that has measured its own models should be able to say
        so rather than living with a global guess."""
        cfg = {"token_safety_margin": 1.35}
        assert token_safety_margin("Qwen/Qwen3.5-9B", cfg) == 1.35

    def test_per_model_override_applies_to_openai_models_too(self):
        assert token_safety_margin("gpt-4o", {"token_safety_margin": 1.1}) == 1.1

    def test_a_margin_below_one_is_rejected(self):
        """Below 1.0 re-creates the bug by configuration. The planner would
        again believe there is room when there is not."""
        for bad in (0.5, 0, -1):
            assert token_safety_margin(
                "Qwen/Qwen3.5-9B", {"token_safety_margin": bad}
            ) == DEFAULT_TOKEN_SAFETY_MARGIN

    def test_a_garbage_margin_falls_back_to_the_default(self):
        for bad in ("", None, "abc", [], {}):
            assert token_safety_margin(
                "Qwen/Qwen3.5-9B", {"token_safety_margin": bad}
            ) == DEFAULT_TOKEN_SAFETY_MARGIN


# ---------------------------------------------------------------------------
# The margin has to actually reach the numbers the planner uses
# ---------------------------------------------------------------------------


@dataclass
class _FakePart:
    content: str


@dataclass
class _FakeMessage:
    parts: list = field(default_factory=list)


def _msg(text: str) -> _FakeMessage:
    return _FakeMessage(parts=[_FakePart(content=text)])


class TestMarginReachesTheCallers:
    def test_count_tokens_inflates_for_a_self_hosted_model(self):
        text = "The proposed work addresses coastal resilience. " * 200
        openai_count = count_tokens(text, "gpt-4o")
        qwen_count = count_tokens(text, "Qwen/Qwen3-VL-8B-Instruct")
        assert qwen_count > openai_count

    def test_estimate_input_tokens_inflates_end_to_end(self):
        """The planner's own entry point, not just the helper underneath it."""
        kwargs = dict(
            system_prompt="You are a research assistant.",
            user_message="Summarise the budget justification.",
            history=[_msg("earlier question"), _msg("earlier answer")],
            documents=[DocumentSegment(label="doc:a", text="Body text. " * 500)],
            attachments=[],
        )
        openai_est = estimate_input_tokens(model_name="gpt-4o", **kwargs)
        qwen_est = estimate_input_tokens(
            model_name="Qwen/Qwen3-VL-8B-Instruct", **kwargs
        )
        assert qwen_est > openai_est
        # The margin scales counted text; the scaffold allowance is a flat
        # addition on top and is identical for both, so it has to come off
        # before the ratio means anything.
        from app.services.context_budget import REQUEST_SCAFFOLD_TOKENS

        qwen_text = qwen_est - REQUEST_SCAFFOLD_TOKENS
        openai_text = openai_est - REQUEST_SCAFFOLD_TOKENS
        assert qwen_text >= int(openai_text * DEFAULT_TOKEN_SAFETY_MARGIN * 0.98)

    def test_per_model_config_reaches_estimate_input_tokens(self):
        kwargs = dict(
            system_prompt="",
            user_message="hello",
            history=[],
            documents=[DocumentSegment(label="doc:a", text="Body text. " * 500)],
            attachments=[],
        )
        default_est = estimate_input_tokens(
            model_name="Qwen/Qwen3.5-9B", **kwargs
        )
        tuned_est = estimate_input_tokens(
            model_name="Qwen/Qwen3.5-9B",
            model_config={"token_safety_margin": 1.45},
            **kwargs,
        )
        assert tuned_est > default_est

    def test_empty_text_stays_zero_regardless_of_margin(self):
        assert count_tokens("", "Qwen/Qwen3.5-9B") == 0


class TestStillDeclinesWhenNothingFits:
    """Erring high must not turn a graceful decline into a crash.

    Routing rescues the request that fits *some* model. A document too large
    for every configured model has no rescue, and the planner's job there is to
    say so in a way the caller can turn into advice — not to raise, and not to
    silently ship a truncated document.
    """

    def test_a_giant_document_is_trimmed_and_says_so(self):
        """Not fatal — trimmable content gets trimmed. What matters is that the
        trim is *reported*, because the silent version of this is the bug."""
        result = plan_and_compact_context(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            model_config={"context_window": 32_768},
            system_prompt="You are a research assistant.",
            user_message="Summarise this.",
            history=[],
            documents=[
                DocumentSegment(label="doc:giant", text="budget narrative " * 40_000)
            ],
            attachments=[],
        )
        assert not result.fatal
        assert result.plan.total_input_tokens <= result.plan.input_budget
        assert [a.kind for a in result.actions] == ["documents_trimmed"]
        assert result.actions[0].tokens_dropped > 0

    def test_an_untrimmable_request_declines_with_an_explanation(self):
        """The genuinely-impossible case: the non-compactable floor alone
        exceeds the budget, so there is nothing left to give. It must return a
        reasoned refusal the caller can show, not raise."""
        result = plan_and_compact_context(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            model_config={"context_window": 2_048},
            system_prompt="You are a research assistant. " * 200,
            user_message="Summarise this. " * 200,
            history=[],
            documents=[DocumentSegment(label="doc:a", text="body " * 5_000)],
            attachments=[],
        )
        assert result.fatal
        assert [a.kind for a in result.actions] == ["over_budget"]
        detail = result.actions[0].detail
        assert "larger model" in detail, "the decline should say what to do next"

    def test_the_margin_did_not_break_convergence(self):
        """The last-ditch loop is capped at 50 rounds. Truncation slices by raw
        token offsets while the budget is margin-inflated, so a botched
        conversion between the two would show up as a request that never gets
        under budget within the cap."""
        result = plan_and_compact_context(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            model_config={"context_window": 32_768},
            system_prompt="You are a research assistant.",
            user_message="Summarise this.",
            history=[],
            documents=[
                DocumentSegment(label="doc:a", text="coastal resilience " * 8_000),
                DocumentSegment(label="doc:b", text="award narrative " * 8_000),
            ],
            attachments=[],
        )
        # Compactable content, so this one should actually come in under budget.
        assert not result.fatal
        assert result.plan.total_input_tokens <= result.plan.input_budget

    def test_a_fitting_request_is_still_left_alone(self):
        """The margin must not make the planner start trimming ordinary
        requests that have plenty of room."""
        result = plan_and_compact_context(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            model_config={"context_window": 32_768},
            system_prompt="You are a research assistant.",
            user_message="What is the total requested?",
            history=[],
            documents=[DocumentSegment(label="doc:a", text="short body. " * 100)],
            attachments=[],
        )
        assert not result.fatal
        assert result.actions == []


class TestStoredCountsStayRaw:
    """`token_count` is written once and read against many models.

    The margin is a property of the model doing the reading, so it is applied
    at comparison time, not frozen into the stored value.
    """

    def test_count_raw_tokens_carries_no_margin(self):
        """Same model, same encoding — the only variable is the margin."""
        text = "Coastal resilience planning. " * 300
        assert count_raw_tokens(text, "Qwen/Qwen3.5-9B") == count_tokens(
            text, "Qwen/Qwen3.5-9B", {"token_safety_margin": 1.0}
        )

    def test_raw_count_is_below_the_budgeting_count(self):
        text = "Coastal resilience planning. " * 300
        assert count_raw_tokens(text, "Qwen/Qwen3.5-9B") < count_tokens(
            text, "Qwen/Qwen3.5-9B"
        )


class TestPreflightOversizeCheck:
    """`find_oversize_documents` under-warned by the same margin the planner did.

    The brief listed this consumer as read-but-not-tested. A workflow that will
    fail should be flagged before it runs, and a document sitting in the band
    between the raw count and the true one was not being flagged.
    """

    # 32k window, reserve 8192, overhead 1024 -> budget 23,360.
    MODEL = "Qwen/Qwen3-VL-8B-Instruct"
    CONFIG = {"context_window": 32_768}

    def _docs(self, token_count: int) -> list[dict]:
        return [{"uuid": "u1", "title": "Proposal.pdf", "token_count": token_count}]

    def test_document_in_the_undercount_band_is_now_flagged(self):
        """22,000 raw looks like it fits; at 1.20 it is really ~26,400 and does
        not. This is precisely the case that used to run and then fail."""
        found = find_oversize_documents(
            documents=self._docs(22_000),
            model_name=self.MODEL,
            model_config=self.CONFIG,
        )
        assert [o.uuid for o in found] == ["u1"]

    def test_a_genuinely_small_document_is_still_not_flagged(self):
        """The margin must not drag ordinary documents into the warning."""
        found = find_oversize_documents(
            documents=self._docs(5_000),
            model_name=self.MODEL,
            model_config=self.CONFIG,
        )
        assert found == []

    def test_reported_count_reflects_what_the_model_will_charge(self):
        """The number shown to the user is the corrected one, so the warning
        and the failure it predicts agree."""
        found = find_oversize_documents(
            documents=self._docs(22_000),
            model_name=self.MODEL,
            model_config=self.CONFIG,
        )
        assert found[0].token_count > 22_000

    def test_openai_models_see_the_stored_count_unchanged(self):
        found = find_oversize_documents(
            documents=self._docs(22_000),
            model_name="gpt-4o",
            model_config=self.CONFIG,
        )
        assert found == []

    def test_missing_token_count_is_not_inflated_into_a_warning(self):
        found = find_oversize_documents(
            documents=[{"uuid": "u1", "title": "x", "token_count": None}],
            model_name=self.MODEL,
            model_config=self.CONFIG,
        )
        assert found == []


class TestLoudFallback:
    """A model that silently drops to a guessed margin is the alias bug.

    Verified before this existed: 'Qwen/Qwen3-VL-30B-A3B-Instruct ' (one
    trailing space) resolved no vocabulary and fell to 1.2 with no signal
    anywhere. The guess is acceptable; the silence is not.
    """

    def setup_method(self):
        from app.services import context_budget

        context_budget._ESTIMATED_MODELS_WARNED.clear()

    def test_warns_when_falling_back_to_a_guessed_margin(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            token_safety_margin("some-unknown-model")

        assert any(
            "some-unknown-model" in r.getMessage() for r in caplog.records
        ), "falling back to a guessed margin must be visible"

    def test_warns_only_once_per_model(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                token_safety_margin("some-unknown-model")

        hits = [r for r in caplog.records if "estimated" in r.getMessage()]
        assert len(hits) == 1, "per-request logging would be noise at chat volume"

    def test_does_not_warn_for_models_counted_exactly(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            token_safety_margin("gpt-4o")

        assert not [r for r in caplog.records if "estimated" in r.getMessage()]
