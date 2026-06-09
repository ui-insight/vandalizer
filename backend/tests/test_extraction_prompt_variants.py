"""Tests for the prompt-variant config knob added in Phase 1B.

Verifies that:
- Each named variant produces a distinct system prompt
- Unknown variants fall back to default (no exception)
- The `prompt_variant` flows through dispatch to the structured / fallback
  extraction calls
"""

from unittest.mock import MagicMock, patch

from app.services.extraction_engine import (
    ExtractionEngine,
    PROMPT_VARIANTS,
    _resolve_prompt,
)


# ---------------------------------------------------------------------------
# Pure variant resolution
# ---------------------------------------------------------------------------


def test_each_variant_produces_distinct_prompt():
    """default / strict / instructive each have meaningfully different wording."""
    labels = ["the document", "the document", "the document"]
    out = {v: _resolve_prompt(v, labels[i]) for i, v in enumerate(PROMPT_VARIANTS)}
    # Three variants, three distinct prompt strings
    assert len(set(out.values())) == 3


def test_default_variant_preserves_historical_wording():
    """The default variant must not drift — the candidate sweep depends on it
    being the historical reference. If this test breaks, re-tune the sweep
    deliberately instead of silently changing behavior."""
    prompt = _resolve_prompt("default", "the document")
    assert "precise entity extraction assistant" in prompt
    assert "Do not infer types" in prompt
    assert "Return a JSON object" in prompt


def test_strict_variant_emphasises_verbatim():
    prompt = _resolve_prompt("strict", "the document")
    assert "EXACT" in prompt or "verbatim" in prompt.lower()
    assert "infer" in prompt.lower()  # rule about not inferring


def test_instructive_variant_describes_approach():
    prompt = _resolve_prompt("instructive", "the document")
    # Instructive variant gives the model step-by-step guidance
    assert "Approach" in prompt or "approach" in prompt
    assert "Output" in prompt or "output" in prompt


def test_unknown_variant_falls_back_to_default():
    """Unknown variants must not crash — fall through to default."""
    fallback = _resolve_prompt("nonsense-variant", "the document")
    default = _resolve_prompt("default", "the document")
    assert fallback == default


def test_none_variant_falls_back_to_default():
    fallback = _resolve_prompt(None, "the document")
    default = _resolve_prompt("default", "the document")
    assert fallback == default


def test_source_label_substituted_into_every_variant():
    """The {source_label} clause is appended by the variant fn — verify all
    variants honor it so the engine knows to say "the document" vs "the image"
    consistently."""
    for variant in PROMPT_VARIANTS:
        prompt = _resolve_prompt(variant, "the page image")
        assert "the page image" in prompt, f"variant={variant} dropped source_label"


# ---------------------------------------------------------------------------
# prompt_variant flow through _dispatch_extraction
# ---------------------------------------------------------------------------


def test_dispatch_passes_prompt_variant_to_single_pass():
    """A one_pass config with prompt_variant='strict' must thread that variant
    down to _extract_structured. We mock the structured call and assert on
    its kwarg."""
    engine = ExtractionEngine(system_config_doc={})

    with patch.object(engine, "_extract_structured", return_value=[]) as mock_extract:
        engine._dispatch_extraction(
            content="sample text",
            keys=["field1"],
            model_name="m",
            config={
                "mode": "one_pass",
                "one_pass": {"thinking": False, "structured": True},
                "prompt_variant": "strict",
            },
        )

    mock_extract.assert_called_once()
    assert mock_extract.call_args.kwargs.get("prompt_variant") == "strict"


def test_dispatch_passes_prompt_variant_to_two_pass():
    """Two-pass config must thread prompt_variant into both pass-1 and pass-2
    extraction calls."""
    engine = ExtractionEngine(system_config_doc={})

    with patch.object(engine, "_extract_structured", return_value=[{"f": "x"}]) as mock_structured, \
         patch.object(engine, "_extract_fallback_json", return_value=[{"f": "x"}]) as mock_fallback:
        engine._dispatch_extraction(
            content="sample text",
            keys=["field1"],
            model_name="m",
            config={
                "mode": "two_pass",
                "two_pass": {
                    "pass_1": {"structured": False, "thinking": False, "model": "m"},
                    "pass_2": {"structured": True, "thinking": False, "model": "m"},
                },
                "prompt_variant": "instructive",
            },
        )

    # Pass 1 went through fallback (structured=False); pass 2 went through structured
    assert mock_fallback.call_args.kwargs.get("prompt_variant") == "instructive"
    assert mock_structured.call_args.kwargs.get("prompt_variant") == "instructive"


def test_dispatch_defaults_prompt_variant_when_unset():
    """No prompt_variant in config = 'default' threaded down (engine
    contract: prompt_variant always has a value at the dispatch boundary)."""
    engine = ExtractionEngine(system_config_doc={})

    with patch.object(engine, "_extract_structured", return_value=[]) as mock_extract:
        engine._dispatch_extraction(
            content="sample text",
            keys=["f"],
            model_name="m",
            config={"mode": "one_pass", "one_pass": {"structured": True, "thinking": False}},
        )

    assert mock_extract.call_args.kwargs.get("prompt_variant") == "default"
