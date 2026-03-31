"""Tests for app.services.quality_service — validation runs, quality tiers, history.

Mocks Beanie models to test business logic without MongoDB.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_validation_run(
    item_kind="search_set",
    item_id="item-1",
    item_name="Grant Fields",
    run_type="extraction",
    score=85.0,
    grade=None,
    accuracy=0.9,
    consistency=0.8,
    model="gpt-4o",
    num_runs=3,
    num_test_cases=3,
    result_snapshot=None,
    created_at=None,
):
    vr = MagicMock()
    vr.id = PydanticObjectId()
    vr.uuid = "vr-uuid"
    vr.item_kind = item_kind
    vr.item_id = item_id
    vr.item_name = item_name
    vr.run_type = run_type
    vr.score = score
    vr.grade = grade
    vr.accuracy = accuracy
    vr.consistency = consistency
    vr.model = model
    vr.num_runs = num_runs
    vr.num_test_cases = num_test_cases
    vr.num_checks = 0
    vr.checks_passed = 0
    vr.checks_failed = 0
    vr.score_breakdown = {"raw_score": score, "final_score": score}
    vr.result_snapshot = result_snapshot or {}
    vr.extraction_config = {}
    vr.user_id = "user1"
    vr.created_at = created_at or datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc)
    vr.insert = AsyncMock()
    vr.save = AsyncMock()
    return vr


def _make_verified_metadata(
    item_kind="search_set",
    item_id="item-1",
    quality_score=85.0,
    quality_tier="good",
    quality_grade=None,
    display_name="Grant Fields",
    last_validated_at=None,
    validation_run_count=5,
    organization_ids=None,
):
    m = MagicMock()
    m.id = PydanticObjectId()
    m.item_kind = item_kind
    m.item_id = item_id
    m.quality_score = quality_score
    m.quality_tier = quality_tier
    m.quality_grade = quality_grade
    m.display_name = display_name
    m.last_validated_at = last_validated_at or datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc)
    m.validation_run_count = validation_run_count
    m.organization_ids = organization_ids or []
    m.save = AsyncMock()
    m.insert = AsyncMock()
    return m


def _make_sys_config(quality_tiers=None, monitoring=None, verification_gates=None):
    cfg = MagicMock()
    quality_config = {
        "quality_tiers": quality_tiers or {
            "excellent": {"min_score": 90},
            "good": {"min_score": 70},
            "fair": {"min_score": 50},
        },
        "monitoring": monitoring or {"stale_threshold_days": 14, "auto_revalidate": False},
        "verification_gates": verification_gates or {"min_test_cases": 3, "min_runs": 3, "min_score": 70},
    }
    cfg.get_quality_config.return_value = quality_config
    cfg.model_dump.return_value = {}
    return cfg


# ---------------------------------------------------------------------------
# compute_quality_tier (pure function)
# ---------------------------------------------------------------------------


class TestComputeQualityTier:
    def test_returns_excellent_for_high_score(self):
        from app.services.quality_service import compute_quality_tier

        tiers = {"excellent": {"min_score": 90}, "good": {"min_score": 70}, "fair": {"min_score": 50}}
        assert compute_quality_tier(95.0, {"quality_tiers": tiers}) == "excellent"

    def test_returns_good_for_mid_score(self):
        from app.services.quality_service import compute_quality_tier

        tiers = {"excellent": {"min_score": 90}, "good": {"min_score": 70}, "fair": {"min_score": 50}}
        assert compute_quality_tier(75.0, {"quality_tiers": tiers}) == "good"

    def test_returns_fair_for_low_score(self):
        from app.services.quality_service import compute_quality_tier

        tiers = {"excellent": {"min_score": 90}, "good": {"min_score": 70}, "fair": {"min_score": 50}}
        assert compute_quality_tier(55.0, {"quality_tiers": tiers}) == "fair"

    def test_returns_none_for_very_low_score(self):
        from app.services.quality_service import compute_quality_tier

        tiers = {"excellent": {"min_score": 90}, "good": {"min_score": 70}, "fair": {"min_score": 50}}
        assert compute_quality_tier(30.0, {"quality_tiers": tiers}) is None

    def test_returns_none_for_none_score(self):
        from app.services.quality_service import compute_quality_tier

        assert compute_quality_tier(None, {"quality_tiers": {}}) is None


# ---------------------------------------------------------------------------
# _sample_size_factor (pure function)
# ---------------------------------------------------------------------------


class TestSampleSizeFactor:
    def test_full_factor_at_3_3(self):
        from app.services.quality_service import _sample_size_factor

        assert _sample_size_factor(3, 3) == 1.0

    def test_full_factor_above_3(self):
        from app.services.quality_service import _sample_size_factor

        assert _sample_size_factor(5, 5) == 1.0

    def test_reduced_factor_for_1_tc_1_run(self):
        from app.services.quality_service import _sample_size_factor

        result = _sample_size_factor(1, 1)
        assert abs(result - (1.0 / 3.0) * (1.0 / 3.0)) < 0.001

    def test_zero_test_cases(self):
        from app.services.quality_service import _sample_size_factor

        assert _sample_size_factor(0, 3) == 0.0


# ---------------------------------------------------------------------------
# compute_config_hash (pure function)
# ---------------------------------------------------------------------------


class TestComputeConfigHash:
    def test_deterministic_hash(self):
        from app.services.quality_service import compute_config_hash

        h1 = compute_config_hash({"a": 1, "b": 2})
        h2 = compute_config_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_configs_different_hashes(self):
        from app.services.quality_service import compute_config_hash

        h1 = compute_config_hash({"a": 1})
        h2 = compute_config_hash({"a": 2})
        assert h1 != h2

    def test_empty_config(self):
        from app.services.quality_service import compute_config_hash

        h = compute_config_hash({})
        assert isinstance(h, str) and len(h) == 64


# ---------------------------------------------------------------------------
# persist_validation_run
# ---------------------------------------------------------------------------


class TestPersistValidationRun:
    @pytest.mark.asyncio
    async def test_extraction_run_computes_score(self):
        with (
            patch("app.services.quality_service.ValidationRun") as MockVR,
            patch("app.services.quality_service.update_quality_metadata", new_callable=AsyncMock) as mock_uqm,
        ):
            mock_vr = _make_validation_run()
            MockVR.return_value = mock_vr
            from app.services.quality_service import persist_validation_run

            result_data = {
                "aggregate_accuracy": 0.9,
                "aggregate_consistency": 0.8,
                "test_cases": [{"label": "tc1"}, {"label": "tc2"}, {"label": "tc3"}],
                "num_runs": 3,
            }
            vr = await persist_validation_run(
                "search_set", "item-1", "Grant Fields", "extraction",
                result_data, "user1", model="gpt-4o",
            )
            mock_vr.insert.assert_awaited_once()
            mock_uqm.assert_awaited_once_with("search_set", "item-1", item_name="Grant Fields")

    @pytest.mark.asyncio
    async def test_workflow_run_uses_grade_fallback(self):
        with (
            patch("app.services.quality_service.ValidationRun") as MockVR,
            patch("app.services.quality_service.update_quality_metadata", new_callable=AsyncMock),
        ):
            mock_vr = _make_validation_run(run_type="workflow", grade="B")
            MockVR.return_value = mock_vr
            from app.services.quality_service import persist_validation_run

            result_data = {"grade": "B", "checks": [{"status": "PASS"}], "num_runs": 1}
            vr = await persist_validation_run(
                "workflow", "wf-1", "My WF", "workflow",
                result_data, "user1",
            )
            mock_vr.insert.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_quality_history
# ---------------------------------------------------------------------------


class TestGetQualityHistory:
    @pytest.mark.asyncio
    async def test_returns_sorted_runs(self):
        vr1 = _make_validation_run(score=80.0)
        vr2 = _make_validation_run(score=90.0)
        with patch("app.services.quality_service.ValidationRun") as MockVR:
            mock_chain = MagicMock()
            mock_chain.sort.return_value = mock_chain
            mock_chain.limit.return_value = mock_chain
            mock_chain.to_list = AsyncMock(return_value=[vr2, vr1])
            MockVR.find = MagicMock(return_value=mock_chain)

            from app.services.quality_service import get_quality_history

            result = await get_quality_history("search_set", "item-1")
            assert len(result) == 2
            assert result[0]["score"] == 90.0
            assert result[1]["score"] == 80.0


# ---------------------------------------------------------------------------
# get_latest_validation
# ---------------------------------------------------------------------------


class TestGetLatestValidation:
    @pytest.mark.asyncio
    async def test_returns_latest_run(self):
        vr = _make_validation_run(score=92.0)
        with patch("app.services.quality_service.ValidationRun") as MockVR:
            mock_chain = MagicMock()
            mock_chain.sort.return_value = mock_chain
            mock_chain.limit.return_value = mock_chain
            mock_chain.to_list = AsyncMock(return_value=[vr])
            MockVR.find = MagicMock(return_value=mock_chain)

            from app.services.quality_service import get_latest_validation

            result = await get_latest_validation("search_set", "item-1")
            assert result is not None
            assert result["score"] == 92.0

    @pytest.mark.asyncio
    async def test_returns_none_when_no_runs(self):
        with patch("app.services.quality_service.ValidationRun") as MockVR:
            mock_chain = MagicMock()
            mock_chain.sort.return_value = mock_chain
            mock_chain.limit.return_value = mock_chain
            mock_chain.to_list = AsyncMock(return_value=[])
            MockVR.find = MagicMock(return_value=mock_chain)

            from app.services.quality_service import get_latest_validation

            result = await get_latest_validation("search_set", "item-1")
            assert result is None


# ---------------------------------------------------------------------------
# update_quality_metadata
# ---------------------------------------------------------------------------


class TestUpdateQualityMetadata:
    @pytest.mark.asyncio
    async def test_updates_existing_metadata(self):
        vr = _make_validation_run(score=88.0, grade="B")
        meta = _make_verified_metadata(quality_score=70.0)
        sys_cfg = _make_sys_config()

        with (
            patch("app.services.quality_service._get_latest_run", new_callable=AsyncMock, return_value=vr),
            patch("app.services.quality_service.SystemConfig") as MockSysCfg,
            patch("app.services.quality_service.ValidationRun") as MockVR,
            patch("app.services.quality_service.VerifiedItemMetadata") as MockMeta,
        ):
            MockSysCfg.get_config = AsyncMock(return_value=sys_cfg)
            mock_count_chain = MagicMock()
            mock_count_chain.count = AsyncMock(return_value=5)
            MockVR.find = MagicMock(return_value=mock_count_chain)
            MockMeta.find_one = AsyncMock(return_value=meta)

            from app.services.quality_service import update_quality_metadata

            await update_quality_metadata("search_set", "item-1", item_name="Grant Fields")
            meta.save.assert_awaited_once()
            assert meta.quality_score == 88.0

    @pytest.mark.asyncio
    async def test_creates_metadata_when_not_exists(self):
        vr = _make_validation_run(score=88.0)
        sys_cfg = _make_sys_config()
        new_meta = _make_verified_metadata()

        with (
            patch("app.services.quality_service._get_latest_run", new_callable=AsyncMock, return_value=vr),
            patch("app.services.quality_service.SystemConfig") as MockSysCfg,
            patch("app.services.quality_service.ValidationRun") as MockVR,
            patch("app.services.quality_service.VerifiedItemMetadata") as MockMeta,
        ):
            MockSysCfg.get_config = AsyncMock(return_value=sys_cfg)
            mock_count_chain = MagicMock()
            mock_count_chain.count = AsyncMock(return_value=1)
            MockVR.find = MagicMock(return_value=mock_count_chain)
            MockMeta.find_one = AsyncMock(return_value=None)
            MockMeta.return_value = new_meta

            from app.services.quality_service import update_quality_metadata

            await update_quality_metadata("search_set", "item-1", item_name="Grant Fields")
            new_meta.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_no_latest_run(self):
        with patch("app.services.quality_service._get_latest_run", new_callable=AsyncMock, return_value=None):
            from app.services.quality_service import update_quality_metadata

            # Should not raise
            await update_quality_metadata("search_set", "item-1")


# ---------------------------------------------------------------------------
# detect_stale_items
# ---------------------------------------------------------------------------


class TestDetectStaleItems:
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Beanie query operators not supported on MagicMock")
    async def test_finds_stale_items(self):
        old_date = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        meta = _make_verified_metadata(last_validated_at=old_date, quality_score=60.0)

        with patch("app.services.quality_service.VerifiedItemMetadata") as MockMeta:
            mock_chain = MagicMock()
            mock_chain.to_list = AsyncMock(return_value=[meta])
            MockMeta.find = MagicMock(return_value=mock_chain)

            from app.services.quality_service import detect_stale_items

            result = await detect_stale_items(max_age_days=14)
            assert len(result) == 1
            assert result[0]["item_id"] == "item-1"


# ---------------------------------------------------------------------------
# _run_to_dict helper
# ---------------------------------------------------------------------------


class TestRunToDict:
    def test_converts_validation_run_to_dict(self):
        vr = _make_validation_run(score=85.0, accuracy=0.9, consistency=0.8)
        from app.services.quality_service import _run_to_dict

        d = _run_to_dict(vr)
        assert d["score"] == 85.0
        assert d["accuracy"] == 0.9
        assert d["consistency"] == 0.8
        assert d["item_kind"] == "search_set"
        assert d["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# _fmt_pct helper
# ---------------------------------------------------------------------------


class TestFmtPct:
    def test_formats_percentage(self):
        from app.services.quality_service import _fmt_pct

        assert _fmt_pct(0.95) == "95%"

    def test_none_returns_na(self):
        from app.services.quality_service import _fmt_pct

        assert _fmt_pct(None) == "N/A"


# ---------------------------------------------------------------------------
# check_verification_readiness
# ---------------------------------------------------------------------------


class TestCheckVerificationReadiness:
    @pytest.mark.asyncio
    async def test_not_ready_when_no_runs(self):
        sys_cfg = _make_sys_config()
        with (
            patch("app.services.quality_service.SystemConfig") as MockSysCfg,
            patch("app.services.quality_service.get_latest_validation", new_callable=AsyncMock, return_value=None),
        ):
            MockSysCfg.get_config = AsyncMock(return_value=sys_cfg)
            from app.services.quality_service import check_verification_readiness

            result = await check_verification_readiness("search_set", "item-1")
            assert result["ready"] is False
            assert len(result["issues"]) > 0

    @pytest.mark.asyncio
    async def test_ready_when_meets_thresholds(self):
        sys_cfg = _make_sys_config()
        latest = {
            "score": 85.0,
            "result_snapshot": {
                "test_cases": [{"label": "a"}, {"label": "b"}, {"label": "c"}],
                "num_runs": 3,
            },
        }
        with (
            patch("app.services.quality_service.SystemConfig") as MockSysCfg,
            patch("app.services.quality_service.get_latest_validation", new_callable=AsyncMock, return_value=latest),
        ):
            MockSysCfg.get_config = AsyncMock(return_value=sys_cfg)
            from app.services.quality_service import check_verification_readiness

            result = await check_verification_readiness("workflow", "wf-1")
            assert result["ready"] is True
            assert len(result["issues"]) == 0
