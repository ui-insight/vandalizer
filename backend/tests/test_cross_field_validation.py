"""Tests for CrossFieldValidator from app.services.cross_field_validation.

Pure function tests — no mocking needed.
"""

import pytest

from app.services.cross_field_validation import CrossFieldValidator


@pytest.fixture
def validator():
    return CrossFieldValidator()


class TestSumEquals:
    def test_sum_matches_target(self, validator):
        data = {"a": 10, "b": 20, "total": 30}
        rule = {
            "type": "sum_equals",
            "source_fields": ["a", "b"],
            "target_field": "total",
        }
        results = validator.validate(data, [rule])
        assert len(results) == 1
        assert results[0]["passed"] is True

    def test_sum_does_not_match_target(self, validator):
        data = {"a": 10, "b": 20, "total": 50}
        rule = {
            "type": "sum_equals",
            "source_fields": ["a", "b"],
            "target_field": "total",
        }
        results = validator.validate(data, [rule])
        assert len(results) == 1
        assert results[0]["passed"] is False


class TestConditionalRequired:
    def test_condition_met_required_present(self, validator):
        data = {"status": "active", "reason": "some reason"}
        rule = {
            "type": "conditional_required",
            "condition_field": "status",
            "condition_value": "active",
            "required_field": "reason",
        }
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True

    def test_condition_met_required_missing(self, validator):
        data = {"status": "active"}
        rule = {
            "type": "conditional_required",
            "condition_field": "status",
            "condition_value": "active",
            "required_field": "reason",
        }
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False

    def test_condition_not_met(self, validator):
        data = {"status": "inactive"}
        rule = {
            "type": "conditional_required",
            "condition_field": "status",
            "condition_value": "active",
            "required_field": "reason",
        }
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True
        assert "skipped" in results[0]["message"]


class TestRangeCheck:
    def test_in_range(self, validator):
        data = {"score": 75}
        rule = {"type": "range_check", "field": "score", "min": 0, "max": 100}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True

    def test_below_min(self, validator):
        data = {"score": -5}
        rule = {"type": "range_check", "field": "score", "min": 0, "max": 100}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False

    def test_above_max(self, validator):
        data = {"score": 150}
        rule = {"type": "range_check", "field": "score", "min": 0, "max": 100}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False


class TestCrossReference:
    def test_contains_match(self, validator):
        data = {"full_name": "John Smith", "last_name": "Smith"}
        rule = {
            "type": "cross_reference",
            "field_a": "full_name",
            "field_b": "last_name",
            "match_type": "contains",
        }
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True

    def test_equals_match(self, validator):
        data = {"field_x": "hello", "field_y": "hello"}
        rule = {
            "type": "cross_reference",
            "field_a": "field_x",
            "field_b": "field_y",
            "match_type": "equals",
        }
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True

    def test_mismatch(self, validator):
        data = {"field_x": "hello", "field_y": "world"}
        rule = {
            "type": "cross_reference",
            "field_a": "field_x",
            "field_b": "field_y",
            "match_type": "equals",
        }
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False


class TestDateOrder:
    def test_correct_order(self, validator):
        data = {"start": "2024-01-01", "end": "2024-12-31"}
        rule = {"type": "date_order", "field_a": "start", "field_b": "end"}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True

    def test_reversed_order(self, validator):
        data = {"start": "2025-06-01", "end": "2024-01-01"}
        rule = {"type": "date_order", "field_a": "start", "field_b": "end"}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False

    def test_unparseable_date(self, validator):
        data = {"start": "not-a-date", "end": "2024-12-31"}
        rule = {"type": "date_order", "field_a": "start", "field_b": "end"}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False
        assert "Cannot parse" in results[0]["message"]


class TestCustomExpression:
    def test_simple_arithmetic_true(self, validator):
        data = {"a": 8, "b": 5}
        rule = {"type": "custom_expression", "expression": "a + b > 10"}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True

    def test_simple_arithmetic_false(self, validator):
        data = {"a": 3, "b": 2}
        rule = {"type": "custom_expression", "expression": "a + b > 10"}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is False

    def test_string_comparison(self, validator):
        data = {"status": "approved"}
        rule = {"type": "custom_expression", "expression": "status == 'approved'"}
        results = validator.validate(data, [rule])
        assert results[0]["passed"] is True


# ---------------------------------------------------------------------------
# Tri-state status and parser robustness (added in validation-uplift work)
# ---------------------------------------------------------------------------


class TestTriStateStatus:
    """The validator returns status ∈ {pass, fail, unparseable}. Unparseable
    rules must not count as violations — that's the whole point of the
    tri-state."""

    def test_pass_returns_status_pass(self, validator):
        rule = {"type": "range_check", "field": "x", "min": 0, "max": 10}
        results = validator.validate({"x": 5}, [rule])
        assert results[0]["status"] == "pass"

    def test_fail_returns_status_fail(self, validator):
        rule = {"type": "range_check", "field": "x", "min": 0, "max": 10}
        results = validator.validate({"x": 99}, [rule])
        assert results[0]["status"] == "fail"

    def test_unparseable_target_is_not_a_fail(self, validator):
        rule = {
            "type": "sum_equals",
            "source_fields": ["a", "b"],
            "target_field": "total",
        }
        # Total is free-text — unparseable, not a violation
        results = validator.validate({"a": 10, "b": 20, "total": "TBD"}, [rule])
        assert results[0]["status"] == "unparseable"
        assert results[0]["passed"] is False

    def test_disabled_rule_is_skipped(self, validator):
        rule = {
            "type": "range_check",
            "field": "x",
            "min": 0,
            "max": 10,
            "enabled": False,
        }
        assert validator.validate({"x": 99}, [rule]) == []

    def test_auto_disabled_rule_is_skipped(self, validator):
        rule = {
            "type": "range_check",
            "field": "x",
            "min": 0,
            "max": 10,
            "auto_disabled": True,
        }
        assert validator.validate({"x": 99}, [rule]) == []


class TestNumberParsing:
    """Hardening that landed with the validation-uplift work — numbers should
    survive accounting parens, ranges, and "approx X" framings."""

    def test_parens_negative(self, validator):
        rule = {"type": "range_check", "field": "x", "min": -2000, "max": 0}
        results = validator.validate({"x": "(1,200)"}, [rule])
        assert results[0]["status"] == "pass"

    def test_currency_symbol(self, validator):
        rule = {"type": "range_check", "field": "x", "min": 0, "max": 2000}
        results = validator.validate({"x": "$1,234.56"}, [rule])
        assert results[0]["status"] == "pass"

    def test_range_uses_midpoint(self, validator):
        rule = {"type": "range_check", "field": "x", "min": 10, "max": 15}
        # "10-15" -> midpoint 12.5 -> in [10,15]
        results = validator.validate({"x": "10-15"}, [rule])
        assert results[0]["status"] == "pass"

    def test_approx_prefix(self, validator):
        rule = {"type": "range_check", "field": "x", "min": 0, "max": 100}
        results = validator.validate({"x": "approx 50"}, [rule])
        assert results[0]["status"] == "pass"

    def test_ambiguous_two_numbers_is_unparseable(self, validator):
        # "10 of 20" has two numbers — picking the first one is too clever;
        # validator should bail out cleanly.
        rule = {"type": "range_check", "field": "x", "min": 0, "max": 5}
        results = validator.validate({"x": "10 of 20"}, [rule])
        assert results[0]["status"] == "unparseable"


class TestDateParsing:
    def test_dateutil_fallback_handles_year_first_month_name(self, validator):
        rule = {"type": "date_order", "field_a": "start", "field_b": "end"}
        results = validator.validate({"start": "Jan 2026", "end": "Feb 2026"}, [rule])
        assert results[0]["status"] == "pass"

    def test_free_form_is_unparseable_not_fail(self, validator):
        rule = {"type": "date_order", "field_a": "start", "field_b": "end"}
        results = validator.validate({"start": "Q1 2026", "end": "2026-12-31"}, [rule])
        assert results[0]["status"] == "unparseable"


class TestSummarizeResults:
    def test_excludes_unparseable_from_violation_rate(self):
        from app.services.cross_field_validation import summarize_results

        results = [
            {"status": "pass"}, {"status": "pass"},
            {"status": "fail"},
            {"status": "unparseable"}, {"status": "unparseable"},
        ]
        summary = summarize_results(results)
        assert summary["pass"] == 2
        assert summary["fail"] == 1
        assert summary["unparseable"] == 2
        # 1 fail / 3 decisive = 0.333
        assert abs(summary["violation_rate"] - (1 / 3)) < 1e-9
        assert abs(summary["pass_rate"] - (2 / 3)) < 1e-9

    def test_all_unparseable_returns_zero_violation_and_null_pass(self):
        from app.services.cross_field_validation import summarize_results

        summary = summarize_results([{"status": "unparseable"}])
        assert summary["violation_rate"] == 0.0
        assert summary["pass_rate"] is None


# ---------------------------------------------------------------------------
# cross_field_rules service: normalization, counters, FP demotion, suggester
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_stamps_id_and_counters(self):
        from app.services.cross_field_rules import normalize_rule

        rule = normalize_rule({"type": "sum_equals"})
        assert rule["id"]
        assert rule["enabled"] is True
        assert rule["eval_count"] == 0
        assert rule["pass_count"] == 0
        assert rule["fail_count"] == 0
        assert rule["fp_count"] == 0
        assert rule["auto_disabled"] is False

    def test_preserves_existing_counters(self):
        from app.services.cross_field_rules import normalize_rule

        rule = normalize_rule({
            "type": "sum_equals",
            "id": "fixed-id",
            "eval_count": 7,
            "fail_count": 2,
        })
        assert rule["id"] == "fixed-id"
        assert rule["eval_count"] == 7
        assert rule["fail_count"] == 2


class TestApplyEvaluationCounters:
    def test_increments_pass_and_fail(self):
        from app.services.cross_field_rules import apply_evaluation_counters, normalize_rule

        rules = [normalize_rule({"id": "r1", "type": "range_check", "field": "x", "min": 0, "max": 10})]
        results = [
            {"rule_id": "r1", "status": "pass"},
            {"rule_id": "r1", "status": "pass"},
            {"rule_id": "r1", "status": "fail"},
            {"rule_id": "r1", "status": "unparseable"},  # must not count
        ]
        changed = apply_evaluation_counters(rules, results)
        assert changed
        assert rules[0]["eval_count"] == 3
        assert rules[0]["pass_count"] == 2
        assert rules[0]["fail_count"] == 1


class TestAutoDemotion:
    def test_below_threshold_not_demoted(self):
        from app.services.cross_field_rules import apply_false_positive, normalize_rule

        rules = [normalize_rule({"id": "r1", "type": "sum_equals", "eval_count": 4, "fp_count": 0})]
        changed, rule = apply_false_positive(rules, "r1")
        assert changed
        assert rule["fp_count"] == 1
        assert rule["auto_disabled"] is False  # < FP_THRESHOLD_MIN_EVALS

    def test_crosses_threshold_auto_disables(self):
        from app.services.cross_field_rules import apply_false_positive, normalize_rule

        # 10 evals, already 3 FP; one more = 4/10 = 40% > 30%
        rules = [normalize_rule({"id": "r1", "type": "sum_equals", "eval_count": 10, "fp_count": 3})]
        _, rule = apply_false_positive(rules, "r1")
        assert rule["fp_count"] == 4
        assert rule["auto_disabled"] is True
        assert "false positive" in rule["auto_disabled_reason"].lower()


class TestRuleSuggester:
    def test_suggests_sum_equals_from_total_naming(self):
        from app.services.cross_field_rules import suggest_rules

        fields = [
            {"key": "Direct Costs"},
            {"key": "Indirect Costs"},
            {"key": "Equipment"},
            {"key": "Total Budget"},
        ]
        suggestions = suggest_rules(fields, [])
        sum_rules = [s for s in suggestions if s["type"] == "sum_equals"]
        assert sum_rules, suggestions
        assert sum_rules[0]["target_field"] == "Total Budget"
        # The three part-named fields land in source_fields
        assert len(sum_rules[0]["source_fields"]) >= 2

    def test_per_category_totals_do_not_double_count(self):
        """A budget matrix (Year 1/2/3 + Total per category) must yield one
        rule *per category* summing only that category's years into its own
        total — never mixing categories or summing totals together."""
        from app.services.cross_field_rules import suggest_rules

        categories = ["Equipment", "Travel", "Supplies", "Indirect Costs"]
        fields = []
        for cat in categories:
            for yr in (1, 2, 3):
                fields.append({"key": f"Budget {cat} Year {yr}"})
            fields.append({"key": f"Budget {cat} Total"})

        sum_rules = [s for s in suggest_rules(fields, []) if s["type"] == "sum_equals"]

        # Exactly one rule per category, each summing its own three years.
        assert len(sum_rules) == len(categories), sum_rules
        for cat in categories:
            rule = next(r for r in sum_rules if r["target_field"] == f"Budget {cat} Total")
            assert sorted(rule["source_fields"]) == sorted(
                f"Budget {cat} Year {yr}" for yr in (1, 2, 3)
            ), rule
            # No total field is ever used as a source (would double-count).
            assert not any("Total" in f for f in rule["source_fields"]), rule

    def test_text_field_excluded_from_sum_by_name(self):
        """A text-named field that happens to share a part token ("materials")
        must not be summed into a numeric total — the ticket bug."""
        from app.services.cross_field_rules import suggest_rules

        fields = [
            {"key": "Direct Costs"},
            {"key": "Indirect Costs"},
            {"key": "Equipment"},
            {"key": "Total Budget"},
            {"key": "Educational Materials Target Audience"},
        ]
        sum_rules = [s for s in suggest_rules(fields, []) if s["type"] == "sum_equals"]
        assert sum_rules, sum_rules
        for rule in sum_rules:
            assert "Educational Materials Target Audience" not in rule["source_fields"], rule
            assert rule["target_field"] != "Educational Materials Target Audience", rule

    def test_enum_field_excluded_from_sum(self):
        """A field with enum_values is categorical and must stay out of sums."""
        from app.services.cross_field_rules import suggest_rules

        fields = [
            {"key": "Direct Costs"},
            {"key": "Indirect Costs"},
            {"key": "Total Budget"},
            {"key": "Materials Status", "enum_values": ["Ordered", "Received"]},
        ]
        sum_rules = [s for s in suggest_rules(fields, []) if s["type"] == "sum_equals"]
        assert sum_rules, sum_rules
        assert all("Materials Status" not in r["source_fields"] for r in sum_rules), sum_rules

    def test_is_numeric_false_overrides_part_name(self):
        """A data-driven is_numeric=False verdict keeps a part-named field out
        of the sum even though its name looks numeric."""
        from app.services.cross_field_rules import suggest_rules

        fields = [
            {"key": "Direct Costs", "is_numeric": True},
            {"key": "Indirect Costs", "is_numeric": True},
            {"key": "Equipment Supplies", "is_numeric": False},
            {"key": "Total Budget", "is_numeric": True},
        ]
        sum_rules = [s for s in suggest_rules(fields, []) if s["type"] == "sum_equals"]
        assert sum_rules, sum_rules
        assert all("Equipment Supplies" not in r["source_fields"] for r in sum_rules), sum_rules

    def test_is_numeric_true_rescues_text_named_field(self):
        """A data-driven is_numeric=True verdict lets an otherwise text-named
        field participate — the sampled values say it's really a number."""
        from app.services.cross_field_rules import suggest_rules

        fields = [
            {"key": "Direct Costs", "is_numeric": True},
            {"key": "Indirect Costs", "is_numeric": True},
            # "description" would normally mark this text; the verdict overrides.
            {"key": "Supplies Description Cost", "is_numeric": True},
            {"key": "Total Budget", "is_numeric": True},
        ]
        sum_rules = [s for s in suggest_rules(fields, []) if s["type"] == "sum_equals"]
        assert any(
            "Supplies Description Cost" in r["source_fields"] for r in sum_rules
        ), sum_rules

    def test_suggests_date_order_pairs(self):
        from app.services.cross_field_rules import suggest_rules

        fields = [{"key": "Start Date"}, {"key": "End Date"}]
        suggestions = suggest_rules(fields, [])
        order = [s for s in suggestions if s["type"] == "date_order"]
        assert order
        assert order[0]["field_a"] == "Start Date"
        assert order[0]["field_b"] == "End Date"

    def test_dedupes_against_existing(self):
        from app.services.cross_field_rules import suggest_rules, normalize_rule

        fields = [{"key": "Start Date"}, {"key": "End Date"}]
        existing = [normalize_rule({
            "type": "date_order", "field_a": "Start Date", "field_b": "End Date",
        })]
        suggestions = suggest_rules(fields, existing)
        order = [s for s in suggestions if s["type"] == "date_order"]
        assert order == [], "Should not re-suggest a rule that already exists"

    def test_suggests_range_check_for_percent_fields(self):
        from app.services.cross_field_rules import suggest_rules

        fields = [{"key": "Indirect Rate Percent"}]
        suggestions = suggest_rules(fields, [])
        ranges = [s for s in suggestions if s["type"] == "range_check"]
        assert ranges
        assert ranges[0]["min"] == 0
        assert ranges[0]["max"] == 100


class TestSanitizeSumEqualsRules:
    def test_strips_text_operand_keeps_rule(self):
        from app.services.cross_field_rules import sanitize_sum_equals_rules

        meta = [
            {"key": "Direct Costs"},
            {"key": "Indirect Costs"},
            {"key": "Equipment"},
            {"key": "Total Budget"},
            {"key": "Educational Materials Target Audience"},
        ]
        rules = [{
            "type": "sum_equals",
            "source_fields": [
                "Direct Costs", "Indirect Costs", "Equipment",
                "Educational Materials Target Audience",
            ],
            "target_field": "Total Budget",
        }]
        cleaned, notes = sanitize_sum_equals_rules(meta, rules)
        assert len(cleaned) == 1
        assert "Educational Materials Target Audience" not in cleaned[0]["source_fields"]
        assert sorted(cleaned[0]["source_fields"]) == [
            "Direct Costs", "Equipment", "Indirect Costs",
        ]
        assert notes and "Educational Materials Target Audience" in notes[0]

    def test_drops_rule_when_too_few_numeric_operands(self):
        from app.services.cross_field_rules import sanitize_sum_equals_rules

        meta = [
            {"key": "Direct Costs"},
            {"key": "Total Budget"},
            {"key": "Audience Name"},
        ]
        rules = [{
            "type": "sum_equals",
            "source_fields": ["Direct Costs", "Audience Name"],
            "target_field": "Total Budget",
        }]
        cleaned, notes = sanitize_sum_equals_rules(meta, rules)
        assert cleaned == []
        assert notes and "dropped" in notes[0]

    def test_drops_rule_with_non_numeric_target(self):
        from app.services.cross_field_rules import sanitize_sum_equals_rules

        meta = [
            {"key": "Direct Costs"},
            {"key": "Indirect Costs"},
            {"key": "Project Category", "enum_values": ["A", "B"]},
        ]
        rules = [{
            "type": "sum_equals",
            "source_fields": ["Direct Costs", "Indirect Costs"],
            "target_field": "Project Category",
        }]
        cleaned, notes = sanitize_sum_equals_rules(meta, rules)
        assert cleaned == []
        assert notes and "non-numeric target" in notes[0]

    def test_leaves_clean_rule_and_other_types_untouched(self):
        from app.services.cross_field_rules import sanitize_sum_equals_rules

        meta = [
            {"key": "Direct Costs"},
            {"key": "Indirect Costs"},
            {"key": "Total Budget"},
        ]
        rules = [
            {
                "type": "sum_equals",
                "source_fields": ["Direct Costs", "Indirect Costs"],
                "target_field": "Total Budget",
            },
            {"type": "date_order", "field_a": "Start Date", "field_b": "End Date"},
        ]
        cleaned, notes = sanitize_sum_equals_rules(meta, rules)
        assert cleaned == rules
        assert notes == []

    def test_unknown_field_left_in_place(self):
        from app.services.cross_field_rules import sanitize_sum_equals_rules

        # "Renamed Field" isn't in metadata — we can't judge it, so keep it.
        meta = [{"key": "Direct Costs"}, {"key": "Total Budget"}]
        rules = [{
            "type": "sum_equals",
            "source_fields": ["Direct Costs", "Renamed Field"],
            "target_field": "Total Budget",
        }]
        cleaned, notes = sanitize_sum_equals_rules(meta, rules)
        assert cleaned == rules
        assert notes == []


class TestRuleShapeValidation:
    def test_rejects_unknown_type(self):
        from app.services.cross_field_rules import validate_rule_shape

        ok, err = validate_rule_shape({"type": "nope"})
        assert not ok
        assert "Unknown" in err

    def test_rejects_sum_equals_without_target(self):
        from app.services.cross_field_rules import validate_rule_shape

        ok, err = validate_rule_shape({"type": "sum_equals", "source_fields": ["a"]})
        assert not ok

    def test_rejects_range_check_without_bounds(self):
        from app.services.cross_field_rules import validate_rule_shape

        ok, err = validate_rule_shape({"type": "range_check", "field": "x"})
        assert not ok

    def test_accepts_valid_range(self):
        from app.services.cross_field_rules import validate_rule_shape

        ok, _ = validate_rule_shape({"type": "range_check", "field": "x", "min": 0})
        assert ok
