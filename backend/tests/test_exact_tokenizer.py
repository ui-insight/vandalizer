"""Count with the model's own vocabulary instead of estimating with OpenAI's.

The safety margin this replaces was a heuristic standing in for a quantity that
is exactly computable. Measured against the models' own `prompt_tokens`, the
divergence between `cl100k_base` and the real Qwen vocabulary is entirely
content-dependent — 1.000 on flowing prose, 1.171 on a real budget
justification, 1.455 on dense currency tables. No single constant covers that
range without either under-counting budget documents (a hard failure, and
budget justifications are this product's core content) or wasting a third of
the window on prose.

Tokenization is CPU work: it needs the vocabulary, not the model weights and
not the GPU. `tokenizers` is already a dependency and is a compiled Rust
extension, and vLLM already leaves `tokenizer.json` on disk for every model it
serves, so exactness costs no new dependency, no download, and no GPU claim.

These tests build their own tiny vocabulary rather than reading the deployment
cache, so they run anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.context_budget import (
    DEFAULT_TOKEN_SAFETY_MARGIN,
    count_tokens,
    estimate_input_tokens,
    resolve_exact_tokenizer,
    token_safety_margin,
)


# ---------------------------------------------------------------------------
# A real, tiny tokenizer on disk
# ---------------------------------------------------------------------------


def _write_tokenizer(dirpath: Path) -> Path:
    """A genuine word-level tokenizer.json — small, but really loadable.

    Deliberately not a mock. The thing under test is whether a vocabulary file
    on disk is found and used, and a fake loader would not prove that.
    """
    vocab = {"[UNK]": 0, "budget": 1, "justification": 2, "total": 3, "##s": 4}
    spec = {
        "version": "1.0",
        "truncation": None,
        "padding": None,
        "added_tokens": [],
        "normalizer": None,
        "pre_tokenizer": {"type": "Whitespace"},
        "post_processor": None,
        "decoder": None,
        "model": {"type": "WordLevel", "vocab": vocab, "unk_token": "[UNK]"},
    }
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "tokenizer.json"
    path.write_text(json.dumps(spec))
    return path


@pytest.fixture
def vocab_dir(tmp_path: Path) -> Path:
    """An HF-cache-shaped tree for one model."""
    snap = (
        tmp_path
        / "hub"
        / "models--Qwen--Qwen3-VL-8B-Instruct"
        / "snapshots"
        / "abc123"
    )
    _write_tokenizer(snap)
    return tmp_path


class TestResolvingTheVocabulary:
    def test_finds_a_models_vocabulary_in_the_cache(self, vocab_dir):
        tok = resolve_exact_tokenizer(
            "Qwen/Qwen3-VL-8B-Instruct",
            {"tokenizer_cache_root": str(vocab_dir)},
        )
        assert tok is not None

    def test_the_deployment_setting_is_used_when_no_model_config_says_otherwise(
        self, vocab_dir
    ):
        """A deployment that mounts its cache somewhere else must be able to
        say so once, rather than per model.

        Without this the only lever is `tokenizer_cache_root` on every model,
        and the hardcoded default is a path that exists on exactly one host.
        """
        from app.services import context_budget

        context_budget._settings_tokenizer_cache_root.cache_clear()
        with patch.object(
            context_budget,
            "_settings_tokenizer_cache_root",
            return_value=str(vocab_dir),
        ):
            assert (
                resolve_exact_tokenizer("Qwen/Qwen3-VL-8B-Instruct", {}) is not None
            )

    def test_the_model_config_still_beats_the_deployment_setting(self, vocab_dir):
        """Per-model wins, so one misconfigured model can be corrected without
        moving the whole deployment's cache."""
        from app.services import context_budget

        context_budget._settings_tokenizer_cache_root.cache_clear()
        with patch.object(
            context_budget,
            "_settings_tokenizer_cache_root",
            return_value=str(vocab_dir),
        ):
            assert resolve_exact_tokenizer(
                "Qwen/Qwen3-VL-8B-Instruct",
                {"tokenizer_cache_root": "/nowhere-at-all"},
            ) is None

    def test_an_explicit_path_on_the_model_config_wins(self, tmp_path):
        path = _write_tokenizer(tmp_path / "custom")
        tok = resolve_exact_tokenizer(
            "anything/at-all", {"tokenizer_path": str(path)}
        )
        assert tok is not None

    def test_returns_none_when_the_model_has_no_vocabulary(self, vocab_dir):
        """Hosted models have no local vocabulary, and that is not an error —
        it is the signal to fall back to estimating."""
        assert resolve_exact_tokenizer(
            "claude-sonnet-4", {"tokenizer_cache_root": str(vocab_dir)}
        ) is None

    def test_returns_none_when_the_cache_does_not_exist(self):
        assert resolve_exact_tokenizer(
            "Qwen/Qwen3-VL-8B-Instruct",
            {"tokenizer_cache_root": "/nonexistent/path"},
        ) is None

    def test_a_corrupt_vocabulary_falls_back_rather_than_raising(self, tmp_path):
        """A broken file must degrade to estimation, not take chat down."""
        bad = tmp_path / "tokenizer.json"
        bad.write_text("{ this is not valid tokenizer json")
        assert resolve_exact_tokenizer(
            "some/model", {"tokenizer_path": str(bad)}
        ) is None

    def test_resolution_is_cached(self, vocab_dir):
        """Loading a real vocabulary costs milliseconds and megabytes; doing it
        per request would make this change the performance problem it is
        supposed to avoid."""
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        first = resolve_exact_tokenizer("Qwen/Qwen3-VL-8B-Instruct", cfg)
        second = resolve_exact_tokenizer("Qwen/Qwen3-VL-8B-Instruct", cfg)
        assert first is second


class TestCountingWithTheRealVocabulary:
    def test_count_uses_the_models_vocabulary_when_available(self, vocab_dir):
        """Text chosen so the two tokenizers cannot agree by accident.

        Common words tokenize to one token under both the word-level test
        vocabulary and cl100k, so an obvious phrase like "budget total" passes
        this test whether or not the exact tokenizer ran at all. These strings
        are outside the test vocabulary, so it yields one [UNK] each while
        cl100k splits them into several subword pieces.
        """
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        text = "zzqqvv wwxxyy"

        exact = count_tokens(text, "Qwen/Qwen3-VL-8B-Instruct", cfg)
        fallback = count_tokens(text, "some-model-with-no-vocabulary", cfg)

        assert exact == 2, "should be one [UNK] per whitespace-delimited word"
        assert exact != fallback, (
            "the exact count is indistinguishable from the tiktoken estimate, "
            "so this test cannot prove which tokenizer ran"
        )

    def test_no_safety_margin_is_applied_when_the_count_is_exact(self, vocab_dir):
        """The margin exists to cover a tokenizer we do not have. Once we have
        it, inflating the count only causes premature routing."""
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        assert token_safety_margin("Qwen/Qwen3-VL-8B-Instruct", cfg) == 1.0

    def test_the_margin_still_applies_without_a_local_vocabulary(self, vocab_dir):
        """Hosted models keep the old behaviour, because the old problem
        remains: their tokenizer is not available to us."""
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        assert token_safety_margin("claude-sonnet-4", cfg) == (
            DEFAULT_TOKEN_SAFETY_MARGIN
        )

    def test_openai_models_still_use_tiktoken_exactly(self, vocab_dir):
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        assert token_safety_margin("gpt-4o", cfg) == 1.0

    def test_empty_text_is_zero_either_way(self, vocab_dir):
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        assert count_tokens("", "Qwen/Qwen3-VL-8B-Instruct", cfg) == 0


class TestRequestScaffoldAllowance:
    """Exact text counting is not the same as an exact request.

    The server wraps every request in a chat template and the agent framework
    adds its own preamble around the instructions. Measured directly against
    the model: the template is a flat 13 tokens, constant across a 5000x
    payload range, and a full reconstructed request came in 277 tokens under
    what the server charged.

    None of that is in the text, so counting the text perfectly still leaves
    the estimate short — in the unsafe direction. Dropping the safety margin
    without replacing it with an explicit allowance would reintroduce a smaller
    version of the very bug this replaces.
    """

    def test_estimate_exceeds_the_sum_of_its_parts(self, vocab_dir):
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        kwargs = dict(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            system_prompt="budget", user_message="total",
            history=[], attachments=[], model_config=cfg,
        )
        parts = count_tokens("budget", "Qwen/Qwen3-VL-8B-Instruct", cfg) + \
            count_tokens("total", "Qwen/Qwen3-VL-8B-Instruct", cfg)
        est = estimate_input_tokens(documents=[], **kwargs)
        assert est > parts, (
            "the estimate must allow for the chat template and framework "
            "preamble, which are sent but are not part of any counted string"
        )

    def test_the_allowance_covers_the_measured_shortfall(self, vocab_dir):
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        est = estimate_input_tokens(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            system_prompt="", user_message="", history=[],
            documents=[], attachments=[], model_config=cfg,
        )
        assert est >= 277, (
            "allowance is below the largest shortfall measured against a real "
            "server response"
        )

    def test_the_allowance_is_not_extravagant(self, vocab_dir):
        """It is a fixed cost, so on a small request it is most of the total.
        Too generous and every short chat looks bigger than it is."""
        cfg = {"tokenizer_cache_root": str(vocab_dir)}
        est = estimate_input_tokens(
            model_name="Qwen/Qwen3-VL-8B-Instruct",
            system_prompt="", user_message="", history=[],
            documents=[], attachments=[], model_config=cfg,
        )
        assert est <= 1024
