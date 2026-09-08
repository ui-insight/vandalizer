"""A detected regression has to reach a human and change what the badge claims.

Before this, `quality_monitor` responded to a regression by writing a
`QualityAlert` — a row only the admin Quality tab renders — enqueueing a shadow
optimizer run, and leaving the item advertising the tier it held before the
drop. The code comment said it plainly: it "Does NOT un-verify." So the person
who owns the item, and who will use it again tomorrow, was told nothing, and
every surface kept endorsing something the system had already decided was
broken.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import quality_service

NOW = datetime.datetime(2026, 8, 28, tzinfo=datetime.timezone.utc)


def _meta(**kw) -> MagicMock:
    """A stand-in for VerifiedItemMetadata. Beanie Documents cannot be
    constructed without an initialized collection, so the rest of this suite
    mocks them the same way — with every attribute set explicitly, because a
    bare MagicMock attribute is truthy and would fake a pending review.
    """
    meta = MagicMock()
    meta.item_kind = "search_set"
    meta.item_id = "ss-1"
    meta.display_name = "NIH Award Terms"
    meta.quality_score = 62.0
    meta.quality_tier = "fair"
    meta.regression_pending_review = False
    meta.regression_detected_at = None
    meta.regression_severity = None
    meta.regression_baseline_score = None
    for key, value in kw.items():
        setattr(meta, key, value)
    meta.save = AsyncMock()
    return meta


class TestFlagging:
    @pytest.mark.asyncio
    async def test_warning_flags_and_notifies_but_does_not_email(self):
        meta = _meta()
        notify = AsyncMock()
        send_email = AsyncMock()
        with (
            patch.object(quality_service, "_item_owner_user_id",
                         new=AsyncMock(return_value="u-1")),
            patch("app.services.notification_service.create_notification", new=notify),
            patch("app.services.email_service.send_email", new=send_email),
        ):
            await quality_service.flag_quality_regression(
                meta=meta, severity="warning",
                previous_score=80.0, current_score=62.0, detected_at=NOW,
            )

        assert meta.regression_pending_review is True
        assert meta.regression_severity == "warning"
        assert meta.regression_baseline_score == 80.0
        assert meta.regression_detected_at == NOW
        meta.save.assert_awaited()

        notify.assert_awaited_once()
        kwargs = notify.await_args.kwargs
        assert kwargs["user_id"] == "u-1"
        assert kwargs["kind"] == "quality_regression"
        assert kwargs["severity"] == "warning"
        assert kwargs["link"] == "/?extraction=ss-1"
        send_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_critical_also_emails_the_owner(self):
        meta = _meta()
        user = MagicMock(email="pi@example.edu", name="Dr. Smith", user_id="u-1")
        send_email = AsyncMock()
        with (
            patch.object(quality_service, "_item_owner_user_id",
                         new=AsyncMock(return_value="u-1")),
            patch("app.services.notification_service.create_notification", new=AsyncMock()),
            patch("app.models.user.User") as user_cls,
            patch("app.services.email_service.send_email", new=send_email),
        ):
            user_cls.find_one = AsyncMock(return_value=user)
            await quality_service.flag_quality_regression(
                meta=meta, severity="critical",
                previous_score=90.0, current_score=55.0, detected_at=NOW,
            )

        send_email.assert_awaited_once()
        to, subject, html = send_email.await_args.args[:3]
        assert to == "pi@example.edu"
        assert "NIH Award Terms" in subject
        assert "90" in html and "55" in html

    @pytest.mark.asyncio
    async def test_a_missing_owner_does_not_break_the_monitor(self):
        """Nightly monitoring must not abort a whole pass because one item has
        no resolvable owner — the flag still gets set."""
        meta = _meta()
        with (
            patch.object(quality_service, "_item_owner_user_id",
                         new=AsyncMock(return_value=None)),
            patch("app.services.notification_service.create_notification",
                  new=AsyncMock()) as notify,
        ):
            await quality_service.flag_quality_regression(
                meta=meta, severity="critical",
                previous_score=90.0, current_score=55.0, detected_at=NOW,
            )
        assert meta.regression_pending_review is True
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_lose_the_flag(self):
        meta = _meta()
        with (
            patch.object(quality_service, "_item_owner_user_id",
                         new=AsyncMock(return_value="u-1")),
            patch("app.services.notification_service.create_notification",
                  new=AsyncMock(side_effect=RuntimeError("mongo down"))),
        ):
            await quality_service.flag_quality_regression(
                meta=meta, severity="warning",
                previous_score=80.0, current_score=62.0, detected_at=NOW,
            )
        assert meta.regression_pending_review is True

    @pytest.mark.asyncio
    async def test_a_second_smaller_drop_does_not_lower_the_recovery_bar(self):
        """Two drops in a row must not make recovery easier than one drop did."""
        meta = _meta()
        with (
            patch.object(quality_service, "_item_owner_user_id",
                         new=AsyncMock(return_value=None)),
        ):
            await quality_service.flag_quality_regression(
                meta=meta, severity="critical",
                previous_score=90.0, current_score=60.0, detected_at=NOW,
            )
            await quality_service.flag_quality_regression(
                meta=meta, severity="warning",
                previous_score=60.0, current_score=48.0, detected_at=NOW,
            )
        assert meta.regression_baseline_score == 90.0


class TestClearing:
    @pytest.mark.asyncio
    async def test_recovery_clears_the_flag_without_a_human(self):
        meta = _meta(
            regression_pending_review=True, regression_severity="critical",
            regression_baseline_score=90.0, regression_detected_at=NOW,
        )
        latest = MagicMock(score=91.0, grade=None)
        sys_cfg = MagicMock()
        sys_cfg.get_quality_config.return_value = {
            "quality_tiers": {"excellent": {"min_score": 90}}
        }
        with (
            patch.object(quality_service, "_get_latest_run",
                         new=AsyncMock(return_value=latest)),
            patch("app.services.quality_service.SystemConfig") as sys_config_cls,
            patch("app.services.quality_service.ValidationRun") as run_cls,
            patch("app.services.quality_service.VerifiedItemMetadata") as meta_cls,
        ):
            sys_config_cls.get_config = AsyncMock(return_value=sys_cfg)
            run_cls.find = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=4)))
            meta_cls.find_one = AsyncMock(return_value=meta)
            await quality_service.update_quality_metadata("search_set", "ss-1")

        assert meta.regression_pending_review is False
        assert meta.regression_baseline_score is None

    @pytest.mark.asyncio
    async def test_a_partial_recovery_leaves_the_flag_up(self):
        meta = _meta(
            regression_pending_review=True, regression_baseline_score=90.0,
        )
        latest = MagicMock(score=75.0, grade=None)
        sys_cfg = MagicMock()
        sys_cfg.get_quality_config.return_value = {
            "quality_tiers": {"good": {"min_score": 70}}
        }
        with (
            patch.object(quality_service, "_get_latest_run",
                         new=AsyncMock(return_value=latest)),
            patch("app.services.quality_service.SystemConfig") as sys_config_cls,
            patch("app.services.quality_service.ValidationRun") as run_cls,
            patch("app.services.quality_service.VerifiedItemMetadata") as meta_cls,
        ):
            sys_config_cls.get_config = AsyncMock(return_value=sys_cfg)
            run_cls.find = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=4)))
            meta_cls.find_one = AsyncMock(return_value=meta)
            await quality_service.update_quality_metadata("search_set", "ss-1")

        assert meta.regression_pending_review is True

    @pytest.mark.asyncio
    async def test_clear_regression_review_is_idempotent(self):
        flagged = _meta(regression_pending_review=True, regression_baseline_score=90.0)
        with patch("app.services.quality_service.VerifiedItemMetadata") as meta_cls:
            meta_cls.find_one = AsyncMock(return_value=flagged)
            assert await quality_service.clear_regression_review("search_set", "ss-1") is True
            assert flagged.regression_pending_review is False
            assert await quality_service.clear_regression_review("search_set", "ss-1") is False

    @pytest.mark.asyncio
    async def test_clearing_an_unknown_item_is_not_an_error(self):
        with patch("app.services.quality_service.VerifiedItemMetadata") as meta_cls:
            meta_cls.find_one = AsyncMock(return_value=None)
            assert await quality_service.clear_regression_review("workflow", "nope") is False


class TestOwnerLookup:
    @pytest.mark.asyncio
    async def test_search_set_and_kb_resolve_by_uuid(self):
        with patch("app.models.search_set.SearchSet") as ss_cls:
            ss_cls.find_one = AsyncMock(return_value=MagicMock(user_id="owner-a"))
            assert await quality_service._item_owner_user_id("search_set", "ss-1") == "owner-a"
        with patch("app.models.knowledge.KnowledgeBase") as kb_cls:
            kb_cls.find_one = AsyncMock(return_value=MagicMock(user_id="owner-b"))
            assert await quality_service._item_owner_user_id("knowledge_base", "kb-1") == "owner-b"

    @pytest.mark.asyncio
    async def test_a_deleted_item_returns_none(self):
        with patch("app.models.search_set.SearchSet") as ss_cls:
            ss_cls.find_one = AsyncMock(return_value=None)
            assert await quality_service._item_owner_user_id("search_set", "gone") is None

    @pytest.mark.asyncio
    async def test_a_malformed_workflow_id_returns_none_instead_of_raising(self):
        """Workflow ids are ObjectIds, and a bad one must not take down a
        nightly pass that is otherwise fine."""
        assert await quality_service._item_owner_user_id("workflow", "not-an-objectid") is None

    @pytest.mark.asyncio
    async def test_unknown_kind_returns_none(self):
        assert await quality_service._item_owner_user_id("document", "d-1") is None


class TestTheFlagSurvivesTheResponseSchema:
    """`_attach_quality` emitted the field, but `SearchSetResponse` didn't
    declare it — and Pydantic's default `extra="ignore"` drops undeclared keys
    on the way out. The extraction header badge therefore received `undefined`
    and never showed a regression, which is this feature's headline behaviour.
    The Quality Pulse card kept working because it reads a separate dict
    endpoint, which is what would hide this in manual testing."""

    def test_the_response_model_declares_it(self):
        from app.schemas.extractions import SearchSetResponse

        assert "regression_pending_review" in SearchSetResponse.model_fields

    def test_a_flagged_value_survives_serialization(self):
        from app.schemas.extractions import SearchSetResponse

        resp = SearchSetResponse(
            id="1", title="t", uuid="u", status="ready", set_type="extraction",
            regression_pending_review=True,
        )
        assert resp.model_dump()["regression_pending_review"] is True

    def test_it_defaults_false_for_every_other_response_path(self):
        from app.schemas.extractions import SearchSetResponse

        resp = SearchSetResponse(
            id="1", title="t", uuid="u", status="ready", set_type="extraction",
        )
        assert resp.model_dump()["regression_pending_review"] is False
