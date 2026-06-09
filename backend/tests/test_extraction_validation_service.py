"""Tests for app.services.extraction_validation_service scoring helpers.

Focus: the optional/no-expected-value field handling that must stay consistent
with the optimizer's tuning scorer (extraction_tuning_service). Both paths
exclude any field with no expected value from accuracy so the certified score
and the optimizer headline measure the same thing.
"""

import pytest

from app.services.extraction_validation_service import _compute_field_metrics


@pytest.mark.asyncio
async def test_optional_field_with_no_expected_is_excluded_from_accuracy():
    m = await _compute_field_metrics(
        "Co-PI", ["", ""], expected=None,
        sys_config_doc={}, model="test-model",
        field_meta={"is_optional": True},
    )
    assert m["accuracy"] is None


@pytest.mark.asyncio
async def test_required_field_with_no_expected_is_also_excluded_from_accuracy():
    # Parity with the tuning scorer: a field with no expected value contributes
    # nothing to accuracy regardless of whether it's flagged optional. If these
    # two paths diverged, the certified score and the optimizer headline would
    # measure different field sets.
    m = await _compute_field_metrics(
        "PI Name", ["Smith", "Smith"], expected="",
        sys_config_doc={}, model="test-model",
        field_meta={"is_optional": False},
    )
    assert m["accuracy"] is None


@pytest.mark.asyncio
async def test_field_with_expected_value_is_scored():
    perfect = await _compute_field_metrics(
        "PI Name", ["Smith", "Smith"], expected="Smith",
        sys_config_doc={}, model="test-model", field_meta={},
    )
    assert perfect["accuracy"] == 1.0

    half = await _compute_field_metrics(
        "PI Name", ["Smith", "Jones"], expected="Smith",
        sys_config_doc={}, model="test-model", field_meta={},
    )
    assert half["accuracy"] == 0.5
