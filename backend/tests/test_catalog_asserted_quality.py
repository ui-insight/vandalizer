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
    # A real row's quality fields default to None; a bare MagicMock attribute
    # would read as a measured score.
    m.quality_score = None
    m.quality_grade = None
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


# ---------------------------------------------------------------------------
# Legacy gold/silver/bronze seeds land on the measured vocabulary (#908)
# ---------------------------------------------------------------------------


def test_normalize_tier_maps_legacy_names_and_passes_others_through():
    from scripts.seed_catalog import normalize_tier

    assert normalize_tier("gold") == "excellent"
    assert normalize_tier("silver") == "good"
    assert normalize_tier("bronze") == "fair"
    assert normalize_tier("excellent") == "excellent"
    assert normalize_tier(None) is None


@pytest.mark.asyncio
async def test_seed_retier_rewrites_a_legacy_tier_on_an_existing_row_even_when_seed_omits_it():
    """A row a 1.0 catalog stamped "gold" is fixed on the next seed run even
    if the new seed file carries no tier of its own."""
    meta = _existing_meta()
    meta.quality_tier = "silver"
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata("workflow", "id-1", "Name", "desc")
    assert meta.quality_tier == "good"


@pytest.mark.asyncio
async def test_seed_normalizes_a_legacy_tier_passed_by_an_old_seed_file():
    meta = _existing_meta()
    meta.quality_tier = None
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata("workflow", "id-1", "Name", "desc", quality_tier="gold")
    assert meta.quality_tier == "excellent"


@pytest.mark.asyncio
async def test_an_asserted_seed_tier_never_overrides_a_tier_measured_here():
    """A seed asserting "excellent" must not relabel a row this install
    validated at 62 — it would display as a measured "Excellent (62%)"."""
    meta = _existing_meta()
    meta.quality_tier = "fair"
    meta.quality_score = 62.0
    meta.quality_grade = "D"
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata(
            "workflow", "id-1", "Name", "desc", quality_tier="excellent", quality_grade="A",
        )
    assert (meta.quality_tier, meta.quality_score, meta.quality_grade) == ("fair", 62.0, "D")


@pytest.mark.asyncio
async def test_a_seed_shipping_a_measured_score_still_updates_the_tier():
    meta = _existing_meta()
    meta.quality_tier = "fair"
    meta.quality_score = 62.0
    with patch("scripts.seed_catalog.VerifiedItemMetadata") as MockVM:
        MockVM.find_one = _find_one_returning(meta)
        await upsert_verified_metadata(
            "workflow", "id-1", "Name", "desc", quality_tier="excellent", quality_score=91.0,
        )
    assert (meta.quality_tier, meta.quality_score) == ("excellent", 91.0)


def test_catalog_reads_map_legacy_tiers():
    """Rows the seeds no longer cover keep their old tier names forever; every
    read maps them so filters, the spotlight and sort still see them."""
    from app.services.verification_service import normalize_tier as svc_normalize

    assert svc_normalize("gold") == "excellent"
    assert svc_normalize("bronze") == "fair"
    assert svc_normalize("good") == "good"
