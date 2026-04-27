"""Tests for app.services.extraction_tuning_service._build_candidate_configs.

The candidate builder is the pure-logic heart of the auto-tune flow. It
decides which (model, config) combinations get evaluated without dispatching
any actual extraction runs, so it's cheap to test thoroughly.
"""

from __future__ import annotations

from app.services.extraction_tuning_service import _build_candidate_configs


def _model(
    model_id: str,
    *,
    tag: str | None = None,
    thinking: bool = False,
    supports_structured: bool = True,
) -> dict:
    return {
        "model_id": model_id,
        "tag": tag or model_id,
        "thinking": thinking,
        "supports_structured": supports_structured,
    }


class TestBuildCandidateConfigs:
    def test_empty_model_list_returns_empty_candidates(self):
        assert _build_candidate_configs([], num_fields=5) == []

    def test_models_missing_both_id_and_name_are_skipped(self):
        # Entries with no model_id and no name silently drop out; the net
        # result is no usable models → no candidates.
        assert _build_candidate_configs([{"tag": "ghost"}], num_fields=5) == []

    def test_name_fallback_when_model_id_absent(self):
        """A model dict with only `name` (no `model_id`) should still work."""
        cands = _build_candidate_configs([{"name": "legacy-model"}], num_fields=3)
        assert any(c["model"] == "legacy-model" for c in cands)

    def test_single_non_thinking_model_produces_expected_core_candidates(self):
        cands = _build_candidate_configs([_model("gpt-4o-mini", tag="mini")], num_fields=5)
        labels = {c["label"] for c in cands}
        # With num_fields < 12 and non-thinking model:
        #   two-pass, one-pass, one-pass-no-thinking, + 2 consensus variants = 5
        assert "mini - two-pass" in labels
        assert "mini - one-pass" in labels
        assert "mini - one-pass (fast, no thinking)" in labels
        assert "mini - two-pass + consensus (3x runs)" in labels
        assert "mini - one-pass + consensus (3x runs)" in labels
        # No chunking variants for small field sets
        assert not any("chunking" in lbl for lbl in labels)
        # Thinking variant is suppressed for non-thinking models
        assert not any("full thinking" in lbl for lbl in labels)

    def test_thinking_capable_model_adds_full_thinking_variant(self):
        cands = _build_candidate_configs([_model("claude", thinking=True)], num_fields=4)
        labels = [c["label"] for c in cands]
        assert "claude - two-pass (full thinking)" in labels
        # Full-thinking candidate wires thinking=True into both passes
        full = next(c for c in cands if "full thinking" in c["label"])
        assert full["config_override"]["two_pass"]["pass_1"]["thinking"] is True
        assert full["config_override"]["two_pass"]["pass_2"]["thinking"] is True

    def test_chunking_variants_added_when_fields_exceed_threshold(self):
        cands = _build_candidate_configs([_model("gpt")], num_fields=20)
        labels = [c["label"] for c in cands]
        assert any("chunking (8 fields/chunk)" in lbl for lbl in labels)
        assert any("chunking (5 fields/chunk)" in lbl for lbl in labels)

    def test_chunking_skipped_at_threshold_boundary(self):
        # The implementation uses strict > 12, so num_fields == 12 should
        # not produce chunking variants.
        cands = _build_candidate_configs([_model("gpt")], num_fields=12)
        assert not any("chunking" in c["label"] for c in cands)

    def test_consensus_variants_attach_to_first_model_only(self):
        cands = _build_candidate_configs(
            [_model("a", tag="A"), _model("b", tag="B")],
            num_fields=4,
        )
        consensus = [c for c in cands if "consensus" in c["label"]]
        # Exactly two consensus entries (two-pass + one-pass), both for the
        # first listed model.
        assert len(consensus) == 2
        assert all(c["model"] == "a" for c in consensus)

    def test_duplicate_labels_are_deduplicated(self):
        # Two identical models should not produce duplicate labels — the
        # seen_labels guard in _add prevents it.
        cands = _build_candidate_configs(
            [_model("gpt"), _model("gpt")],
            num_fields=4,
        )
        labels = [c["label"] for c in cands]
        assert len(labels) == len(set(labels))

    def test_one_pass_propagates_structured_and_thinking_flags(self):
        cands = _build_candidate_configs(
            [_model("m", thinking=True, supports_structured=False)],
            num_fields=3,
        )
        one_pass = next(c for c in cands if c["label"].endswith(" - one-pass"))
        assert one_pass["config_override"]["one_pass"]["thinking"] is True
        assert one_pass["config_override"]["one_pass"]["structured"] is False

    def test_every_candidate_has_required_keys(self):
        cands = _build_candidate_configs([_model("m", thinking=True)], num_fields=30)
        assert cands, "Expected at least one candidate"
        for c in cands:
            assert set(c.keys()) == {"label", "model", "config_override"}
            assert isinstance(c["label"], str) and c["label"]
            assert c["model"] == "m"
            assert isinstance(c["config_override"], dict)
            assert c["config_override"].get("mode") in ("one_pass", "two_pass")
