"""The drift check's re-execution path: the frozen baseline actually runs.

Before this, "drift monitoring" compared two scalars — the pinned score vs
whatever the item's latest unrelated validation run scored — and the stored
official_baseline dict was inert payload. These pin the helper that replays
an extraction baseline's frozen test cases against the current config.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.quality_service import reexecute_official_baseline


def _meta(kind="search_set", baseline=None, item_id="65aa00000000000000000001"):
    return SimpleNamespace(item_kind=kind, official_baseline=baseline, item_id=item_id)


@pytest.mark.asyncio
async def test_non_extraction_kinds_and_missing_baselines_return_none():
    assert await reexecute_official_baseline(_meta(kind="workflow", baseline={"x": 1})) is None
    assert await reexecute_official_baseline(_meta(baseline=None)) is None


@pytest.mark.asyncio
async def test_replays_frozen_cases_against_current_config():
    baseline = {
        "num_runs": 2,
        "test_cases": [
            # Snapshot-style entry: expectations live in per-field result rows,
            # source text is recovered from the stored ExtractionTestCase.
            {
                "test_case_uuid": "tc-1",
                "label": "Award letter",
                "fields": [
                    {"field_name": "PI Name", "expected": "Smith"},
                    {"field_name": "Amount", "expected": "$1,000"},
                    {"field_name": "Optional", "expected": ""},
                ],
            },
            # Examiner-added entry: everything inline.
            {
                "label": "Curated case",
                "source_text": "PI: Jones. Amount: $2,000.",
                "expected_values": {"PI Name": "Jones"},
            },
            # Not executable: no source text anywhere.
            {"label": "Orphan", "fields": [{"field_name": "PI Name", "expected": "X"}]},
        ],
    }
    ss = SimpleNamespace(uuid="ss-uuid-1")
    tc = SimpleNamespace(uuid="tc-1", source_text="PI: Smith. Amount: $1,000.")

    # Patch the whole Document class — the field expression
    # (ExtractionTestCase.uuid == ...) only works after init_beanie.
    mock_tc_cls = MagicMock()
    mock_tc_cls.find_one = AsyncMock(return_value=tc)

    with (
        patch("app.models.search_set.SearchSet.get", new_callable=AsyncMock, return_value=ss),
        patch("app.models.extraction_test_case.ExtractionTestCase", mock_tc_cls),
        patch(
            "app.services.extraction_validation_service.run_validation_v2",
            new_callable=AsyncMock, return_value={"score": 71.5},
        ) as mock_v2,
    ):
        result = await reexecute_official_baseline(_meta(baseline=baseline))

    assert result == {"score": 71.5}
    args = mock_v2.await_args
    assert args.args[0] == "ss-uuid-1"
    sources = args.args[2]
    # The orphan entry is skipped; the two executable cases run.
    assert [s["label"] for s in sources] == ["Award letter", "Curated case"]
    assert sources[0]["source_text"] == "PI: Smith. Amount: $1,000."
    # Expectations come from the FROZEN baseline rows, empty ones excluded.
    assert sources[0]["expected_values"] == {"PI Name": "Smith", "Amount": "$1,000"}
    assert sources[1]["expected_values"] == {"PI Name": "Jones"}
    # The baseline's own replicate count is replayed so the sample-size
    # discount matches — fewer replicates would read as false drift.
    assert args.kwargs["num_runs"] == 2


@pytest.mark.asyncio
async def test_nothing_executable_returns_none_instead_of_empty_run():
    baseline = {"test_cases": [{"label": "Orphan", "fields": []}]}
    with (
        patch(
            "app.models.search_set.SearchSet.get",
            new_callable=AsyncMock, return_value=SimpleNamespace(uuid="ss-1"),
        ),
        patch(
            "app.services.extraction_validation_service.run_validation_v2",
            new_callable=AsyncMock,
        ) as mock_v2,
    ):
        assert await reexecute_official_baseline(_meta(baseline=baseline)) is None
    mock_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_search_set_returns_none():
    with patch("app.models.search_set.SearchSet.get", new_callable=AsyncMock, return_value=None):
        assert await reexecute_official_baseline(_meta(baseline={"test_cases": []})) is None
