"""Tests for ExtractionEngine pure helper methods — chunking, consensus,
draft hints, field prompts, and entity filtering."""

from app.services.extraction_engine import ExtractionEngine
from app.models.system_config import _deep_merge, _apply_legacy_strategy


def _engine():
    """Create an ExtractionEngine with no system config (pure methods only)."""
    return ExtractionEngine(system_config_doc={})


# ---------------------------------------------------------------------------
# _chunk_keys
# ---------------------------------------------------------------------------

class TestChunkKeys:
    def test_even_split(self):
        result = _engine()._chunk_keys(["a", "b", "c", "d"], 2)
        assert result == [["a", "b"], ["c", "d"]]

    def test_uneven_split(self):
        result = _engine()._chunk_keys(["a", "b", "c", "d", "e"], 2)
        assert result == [["a", "b"], ["c", "d"], ["e"]]

    def test_chunk_larger_than_keys(self):
        result = _engine()._chunk_keys(["a", "b"], 10)
        assert result == [["a", "b"]]

    def test_single_key(self):
        result = _engine()._chunk_keys(["a"], 1)
        assert result == [["a"]]

    def test_empty_keys(self):
        result = _engine()._chunk_keys([], 5)
        assert result == []


# ---------------------------------------------------------------------------
# _merge_chunk_results
# ---------------------------------------------------------------------------

class TestMergeChunkResults:
    def test_merges_two_dicts(self):
        result = _engine()._merge_chunk_results([{"A": "1"}, {"B": "2"}])
        assert result == [{"A": "1", "B": "2"}]

    def test_first_non_empty_wins(self):
        result = _engine()._merge_chunk_results([{"A": "first"}, {"A": "second"}])
        assert result == [{"A": "first"}]

    def test_empty_value_overwritten(self):
        result = _engine()._merge_chunk_results([{"A": None}, {"A": "real"}])
        assert result == [{"A": "real"}]

    def test_empty_string_overwritten(self):
        result = _engine()._merge_chunk_results([{"A": ""}, {"A": "real"}])
        assert result == [{"A": "real"}]

    def test_empty_list_overwritten(self):
        result = _engine()._merge_chunk_results([{"A": []}, {"A": "real"}])
        assert result == [{"A": "real"}]

    def test_empty_dict_overwritten(self):
        result = _engine()._merge_chunk_results([{"A": {}}, {"A": "real"}])
        assert result == [{"A": "real"}]

    def test_empty_input(self):
        assert _engine()._merge_chunk_results([]) == []

    def test_non_dict_items_ignored(self):
        result = _engine()._merge_chunk_results(["not a dict", {"A": "1"}])
        assert result == [{"A": "1"}]


# ---------------------------------------------------------------------------
# _majority_vote — consensus logic for extraction output
# ---------------------------------------------------------------------------

class TestMajorityVote:
    def test_unanimous_agreement(self):
        result = _engine()._majority_vote(
            ["Name"], [{"Name": "Alice"}, {"Name": "Alice"}, {"Name": "Alice"}]
        )
        assert result == {"Name": "Alice"}

    def test_two_out_of_three(self):
        result = _engine()._majority_vote(
            ["Name"], [{"Name": "Alice"}, {"Name": "Alice"}, {"Name": "Bob"}]
        )
        assert result == {"Name": "Alice"}

    def test_all_different_picks_first_most_common(self):
        """When all three disagree, Counter picks one (implementation-defined but deterministic)."""
        result = _engine()._majority_vote(
            ["Name"], [{"Name": "A"}, {"Name": "B"}, {"Name": "C"}]
        )
        assert result["Name"] in ("A", "B", "C")

    def test_none_values_handled(self):
        result = _engine()._majority_vote(
            ["Name"], [{"Name": None}, {"Name": None}, {"Name": "Alice"}]
        )
        assert result == {"Name": None}

    def test_multiple_keys(self):
        result = _engine()._majority_vote(
            ["Name", "Age"],
            [
                {"Name": "Alice", "Age": "30"},
                {"Name": "Alice", "Age": "31"},
                {"Name": "Bob", "Age": "30"},
            ],
        )
        assert result["Name"] == "Alice"
        assert result["Age"] == "30"

    def test_complex_values(self):
        """Test with list values (JSON-serialized for comparison)."""
        result = _engine()._majority_vote(
            ["Tags"],
            [
                {"Tags": ["a", "b"]},
                {"Tags": ["a", "b"]},
                {"Tags": ["c"]},
            ],
        )
        assert result == {"Tags": ["a", "b"]}

    def test_missing_key_treated_as_none(self):
        result = _engine()._majority_vote(
            ["Name"], [{"Name": "Alice"}, {}, {}]
        )
        assert result == {"Name": None}  # two Nones beat one Alice


# ---------------------------------------------------------------------------
# _build_draft_hint
# ---------------------------------------------------------------------------

class TestBuildDraftHint:
    def test_empty_list_returns_none(self):
        assert _engine()._build_draft_hint([]) is None

    def test_none_returns_none(self):
        assert _engine()._build_draft_hint(None) is None

    def test_single_dict_in_list(self):
        result = _engine()._build_draft_hint([{"A": "1", "B": "2"}])
        assert result == {"A": "1", "B": "2"}

    def test_bare_dict(self):
        result = _engine()._build_draft_hint({"A": "1"})
        assert result == {"A": "1"}

    def test_single_dict_returned_as_is(self):
        """Single-dict lists are returned directly without filtering empty values."""
        result = _engine()._build_draft_hint([{"A": "val", "B": None, "C": "", "D": []}])
        assert result == {"A": "val", "B": None, "C": "", "D": []}

    def test_empty_values_skipped_during_merge(self):
        """When merging multiple dicts, empty values are skipped."""
        result = _engine()._build_draft_hint([{"A": None}, {"A": "real", "B": "val"}])
        assert result == {"A": "real", "B": "val"}

    def test_multiple_dicts_merged(self):
        result = _engine()._build_draft_hint([{"A": "1"}, {"B": "2"}])
        assert result == {"A": "1", "B": "2"}

    def test_first_non_empty_wins(self):
        result = _engine()._build_draft_hint([{"A": "first"}, {"A": "second"}])
        assert result == {"A": "first"}

    def test_all_empty_single_dict_returned(self):
        """Single-dict list returns dict directly, even if all values empty."""
        result = _engine()._build_draft_hint([{"A": None, "B": ""}])
        assert result == {"A": None, "B": ""}

    def test_all_empty_multi_dict_returns_none(self):
        """When merging multiple dicts and all values are empty, returns None."""
        result = _engine()._build_draft_hint([{"A": None}, {"B": ""}])
        assert result is None


# ---------------------------------------------------------------------------
# _build_fields_prompt
# ---------------------------------------------------------------------------

class TestBuildFieldsPrompt:
    def test_simple_keys(self):
        result = _engine()._build_fields_prompt(["Name", "Date"])
        assert result == "Name, Date"

    def test_with_enum_values(self):
        meta = {"Status": {"enum_values": ["Active", "Inactive"]}}
        result = _engine()._build_fields_prompt(["Status"], meta)
        assert "allowed values: Active, Inactive" in result

    def test_with_optional(self):
        meta = {"Notes": {"is_optional": True}}
        result = _engine()._build_fields_prompt(["Notes"], meta)
        assert "optional" in result

    def test_with_enum_and_optional(self):
        meta = {"Status": {"enum_values": ["A", "B"], "is_optional": True}}
        result = _engine()._build_fields_prompt(["Status"], meta)
        assert "allowed values: A, B" in result
        assert "optional" in result

    def test_no_metadata(self):
        result = _engine()._build_fields_prompt(["Name"], None)
        assert result == "Name"

    def test_mixed_keys(self):
        meta = {"Status": {"enum_values": ["A", "B"]}}
        result = _engine()._build_fields_prompt(["Name", "Status", "Date"], meta)
        assert "Name" in result
        assert "allowed values" in result
        assert "Date" in result


# ---------------------------------------------------------------------------
# _filter_empty_entities
# ---------------------------------------------------------------------------

class TestFilterEmptyEntities:
    def test_keeps_non_empty(self):
        result = _engine()._filter_empty_entities([{"A": "value"}])
        assert result == [{"A": "value"}]

    def test_removes_all_none(self):
        result = _engine()._filter_empty_entities([{"A": None, "B": None}])
        assert result == []

    def test_removes_all_empty_strings(self):
        result = _engine()._filter_empty_entities([{"A": "", "B": ""}])
        assert result == []

    def test_removes_empty_dict(self):
        result = _engine()._filter_empty_entities([{}])
        assert result == []

    def test_mixed(self):
        result = _engine()._filter_empty_entities([
            {"A": None, "B": ""},
            {"A": "value"},
            {},
        ])
        assert result == [{"A": "value"}]

    def test_keeps_entity_with_one_value(self):
        result = _engine()._filter_empty_entities([{"A": None, "B": "real"}])
        assert len(result) == 1

    def test_empty_list_and_dict_values_count_as_empty(self):
        result = _engine()._filter_empty_entities([{"A": [], "B": {}}])
        assert result == []


# ---------------------------------------------------------------------------
# _normalize_to_dict
# ---------------------------------------------------------------------------

class TestNormalizeToDict:
    def test_list_of_dicts(self):
        result = _engine()._normalize_to_dict([{"A": "1"}, {"B": "2"}])
        assert result == {"A": "1", "B": "2"}

    def test_bare_dict(self):
        result = _engine()._normalize_to_dict({"A": "1"})
        assert result == {"A": "1"}

    def test_empty_list(self):
        assert _engine()._normalize_to_dict([]) == {}

    def test_later_dict_overwrites(self):
        result = _engine()._normalize_to_dict([{"A": "1"}, {"A": "2"}])
        assert result == {"A": "2"}


# ---------------------------------------------------------------------------
# _resolve_model
# ---------------------------------------------------------------------------

class TestResolveModel:
    def test_config_model_wins(self):
        result = _engine()._resolve_model({"model": "config-model"}, "arg-model")
        assert result == "config-model"

    def test_arg_model_fallback(self):
        result = _engine()._resolve_model({"model": ""}, "arg-model")
        assert result == "arg-model"

    def test_available_models_fallback(self):
        engine = ExtractionEngine(system_config_doc={
            "available_models": [{"name": "fallback-model"}]
        })
        result = engine._resolve_model({"model": ""}, None)
        assert result == "fallback-model"

    def test_empty_when_nothing_available(self):
        result = _engine()._resolve_model({"model": ""}, None)
        assert result == ""


# ---------------------------------------------------------------------------
# _deep_merge and _apply_legacy_strategy (from system_config)
# ---------------------------------------------------------------------------

class TestDeepMerge:
    def test_flat_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3}}
        result = _deep_merge(base, override)
        assert result == {"x": {"a": 1, "b": 3}}

    def test_override_replaces_non_dict_with_non_dict(self):
        base = {"a": "old"}
        override = {"a": "new"}
        _deep_merge(base, override)
        assert base["a"] == "new"

    def test_override_replaces_dict_with_non_dict(self):
        base = {"a": {"nested": True}}
        override = {"a": "flat now"}
        _deep_merge(base, override)
        assert base["a"] == "flat now"

    def test_new_keys_added(self):
        base = {}
        override = {"new_key": "value"}
        _deep_merge(base, override)
        assert base["new_key"] == "value"


class TestApplyLegacyStrategy:
    def test_two_pass(self):
        config = {"mode": "", "one_pass": {"thinking": False, "structured": False}}
        _apply_legacy_strategy(config, "two_pass")
        assert config["mode"] == "two_pass"

    def test_one_pass_thinking(self):
        config = {"mode": "", "one_pass": {"thinking": False, "structured": False}}
        _apply_legacy_strategy(config, "one_pass_thinking")
        assert config["mode"] == "one_pass"
        assert config["one_pass"]["thinking"] is True
        assert config["one_pass"]["structured"] is True

    def test_one_pass_no_thinking(self):
        config = {"mode": "", "one_pass": {"thinking": True, "structured": False}}
        _apply_legacy_strategy(config, "one_pass_no_thinking")
        assert config["mode"] == "one_pass"
        assert config["one_pass"]["thinking"] is False
        assert config["one_pass"]["structured"] is True

    def test_unknown_strategy_ignored(self):
        config = {"mode": "original"}
        _apply_legacy_strategy(config, "unknown_strategy")
        assert config["mode"] == "original"
