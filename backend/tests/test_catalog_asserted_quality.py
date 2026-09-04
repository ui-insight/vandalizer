"""A catalog tier without a measured score is an assertion, and seeds may
ship a measured baseline — but never clobber one an examiner pinned locally.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.seed_catalog import upsert_verified_metadata


def _existing_meta(pinned_by=None, baseline=None):
    m = MagicMock()
    m.official_baseline = baseline
    m.official_baseline_pinned_by_user_id = pinned_by
    m.save = AsyncMock()
    return m


def _find_one_returning(meta):
    async def _find_one(*a, **kw):
        return meta
    return _find_one


@pytest.mark.asyncio
async def test_seed_pins_a_shipped_baseline_on_existing_metadata():
    meta = _existing_meta(pinned_by=None, baseline=None)
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata(
            "search_set", "id-1", "Grant Fields", "desc",
            official_baseline={"test_cases": [{"label": "c1"}]},
            official_baseline_score=91.0,
        )
    assert meta.official_baseline == {"test_cases": [{"label": "c1"}]}
    assert meta.official_baseline_score == 91.0
    assert meta.official_baseline_pinned_by_user_id == "catalog-seed"
    meta.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_refreshes_its_own_prior_pin():
    meta = _existing_meta(pinned_by="catalog-seed", baseline={"test_cases": [{"label": "old"}]})
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata(
            "search_set", "id-1", "Grant Fields", "desc",
            official_baseline={"test_cases": [{"label": "new"}]},
            official_baseline_score=88.0,
        )
    assert meta.official_baseline == {"test_cases": [{"label": "new"}]}


@pytest.mark.asyncio
async def test_seed_never_clobbers_an_examiner_pinned_baseline():
    examiner_baseline = {"test_cases": [{"label": "examiner case"}]}
    meta = _existing_meta(pinned_by="user-42", baseline=examiner_baseline)
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata(
            "search_set", "id-1", "Grant Fields", "desc",
            official_baseline={"test_cases": [{"label": "seed case"}]},
            official_baseline_score=88.0,
        )
    assert meta.official_baseline == examiner_baseline
    assert meta.official_baseline_pinned_by_user_id == "user-42"


@pytest.mark.asyncio
async def test_seed_without_baseline_touches_nothing_baseline_shaped():
    meta = _existing_meta(pinned_by="user-42", baseline={"test_cases": []})
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata("search_set", "id-1", "Grant Fields", "desc")
    assert meta.official_baseline == {"test_cases": []}
    assert meta.official_baseline_pinned_by_user_id == "user-42"
