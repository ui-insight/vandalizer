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
