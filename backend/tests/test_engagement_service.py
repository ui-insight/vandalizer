"""Tests for inactivity-nudge datetime handling.

Motor is not configured ``tz_aware``, so datetimes stored as UTC come back out
of MongoDB naive. Every Python-side comparison against ``datetime.now(utc)`` in
this service therefore has to normalize first — one that didn't took the nightly
``tasks.engagement.process_inactivity_nudges`` run down with "can't subtract
offset-naive and offset-aware datetimes".

The promotional kill switch for this same processor is covered in
``test_promotional_email_switch.py``.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import engagement_service
from app.services.engagement_service import (
    NUDGE_COOLDOWN_DAYS,
    _as_aware_utc,
    _get_item_name,
    _get_new_catalog_items_since,
    process_inactivity_nudges,
)
from tests.conftest import fake_model


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        promotional_emails_enabled=True,
        frontend_url="https://example.test",
    )


def _naive_days_ago(days: int) -> datetime.datetime:
    """A timestamp shaped the way Mongo hands one back: UTC but naive."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - (
        datetime.timedelta(days=days)
    )


def _user(last_login_at, last_nudge_sent_at=None) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="u-1",
        name="Ada",
        email="ada@example.test",
        email_preferences={"nudges": True},
        last_login_at=last_login_at,
        last_nudge_sent_at=last_nudge_sent_at,
        last_marketing_email_at=None,
    )
    user.save = AsyncMock()
    return user


class TestAsAwareUtc:
    def test_naive_is_stamped_utc(self):
        naive = datetime.datetime(2026, 7, 1, 12, 0, 0)
        assert _as_aware_utc(naive).tzinfo is datetime.timezone.utc

    def test_aware_is_left_alone(self):
        aware = datetime.datetime(2026, 7, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        assert _as_aware_utc(aware) is aware

    def test_none_passes_through(self):
        assert _as_aware_utc(None) is None


class TestInactivityNudges:
    @pytest.mark.asyncio
    async def test_naive_last_login_sends_instead_of_raising(self):
        """Regression: naive last_login_at minus aware now() raised TypeError."""
        user = _user(_naive_days_ago(45))

        with (
            patch.object(engagement_service, "User", fake_model([user])),
            patch.object(
                engagement_service,
                "_get_new_catalog_items_since",
                AsyncMock(return_value=[{"name": "NSF Extractor", "kind": "workflow"}]),
            ),
            patch.object(
                engagement_service, "send_email", AsyncMock(return_value=True)
            ) as send,
        ):
            sent = await process_inactivity_nudges(_settings())

        assert sent == 1
        assert send.await_args.kwargs["email_type"] == "inactivity_nudge"
        # Cooldown stamp is written back aware so the next run can compare it.
        assert user.last_nudge_sent_at.tzinfo is not None
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_days_inactive_computed_from_naive_login(self):
        user = _user(_naive_days_ago(45))

        with (
            patch.object(engagement_service, "User", fake_model([user])),
            patch.object(
                engagement_service,
                "_get_new_catalog_items_since",
                AsyncMock(return_value=[{"name": "Batch Processing", "kind": "workflow"}]),
            ),
            patch.object(
                engagement_service,
                "inactivity_nudge_email",
                MagicMock(return_value=("subject", "<html/>")),
            ) as build_email,
            patch.object(engagement_service, "send_email", AsyncMock(return_value=True)),
        ):
            await process_inactivity_nudges(_settings())

        assert build_email.call_args.kwargs["days_inactive"] == 45

    @pytest.mark.asyncio
    async def test_naive_last_nudge_still_honors_cooldown(self):
        """The cooldown check reads the same naive column — and must not raise."""
        user = _user(
            _naive_days_ago(45),
            last_nudge_sent_at=_naive_days_ago(NUDGE_COOLDOWN_DAYS - 1),
        )

        with (
            patch.object(engagement_service, "User", fake_model([user])),
            patch.object(
                engagement_service, "send_email", AsyncMock(return_value=True)
            ) as send,
        ):
            sent = await process_inactivity_nudges(_settings())

        assert sent == 0
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_cooldown_sends_again(self):
        user = _user(
            _naive_days_ago(45),
            last_nudge_sent_at=_naive_days_ago(NUDGE_COOLDOWN_DAYS + 1),
        )

        with (
            patch.object(engagement_service, "User", fake_model([user])),
            patch.object(
                engagement_service,
                "_get_new_catalog_items_since",
                AsyncMock(return_value=[{"name": "NSF Extractor", "kind": "workflow"}]),
            ),
            patch.object(
                engagement_service, "send_email", AsyncMock(return_value=True)
            ) as send,
        ):
            sent = await process_inactivity_nudges(_settings())

        assert sent == 1
        send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_new_catalog_items_sends_nothing(self):
        user = _user(_naive_days_ago(45))

        with (
            patch.object(engagement_service, "User", fake_model([user])),
            patch.object(
                engagement_service,
                "_get_new_catalog_items_since",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                engagement_service, "send_email", AsyncMock(return_value=True)
            ) as send,
        ):
            sent = await process_inactivity_nudges(_settings())

        assert sent == 0
        send.assert_not_awaited()


class TestCatalogItemNames:
    @pytest.mark.asyncio
    async def test_knowledge_base_name_comes_from_title(self):
        """Regression (VANDALIZER-BACKEND-1R): KnowledgeBase has ``title``, not
        ``name``; reading ``.name`` raised AttributeError and killed the run."""
        from app.models.knowledge import KnowledgeBase

        kb = KnowledgeBase.model_construct(title="USDA General Terms & Conditions (2025)")
        with patch.object(KnowledgeBase, "get", AsyncMock(return_value=kb)):
            name = await _get_item_name("knowledge_base", "6a3ee628e1d889df955be302")

        assert name == "USDA General Terms & Conditions (2025)"

    @pytest.mark.asyncio
    async def test_one_unresolvable_item_does_not_abort_the_run(self):
        reqs = [
            SimpleNamespace(item_kind="knowledge_base", item_id="6a3ee628e1d889df955be302"),
            SimpleNamespace(item_kind="workflow", item_id="6a3ee628e1d889df955be303"),
        ]
        # The service imports VerificationRequest inside the function, so the
        # stand-in has to go on the models module, not on engagement_service.
        fake = fake_model(reqs)
        query = fake.find.return_value
        query.sort.return_value = query
        query.limit.return_value = query

        async def _name(kind, _id):
            if kind == "knowledge_base":
                raise AttributeError("'KnowledgeBase' object has no attribute 'name'")
            return "NSF Extractor"

        with (
            patch("app.models.verification.VerificationRequest", fake),
            patch.object(engagement_service, "_get_item_name", _name),
        ):
            items = await _get_new_catalog_items_since(
                datetime.datetime(2026, 6, 30, tzinfo=datetime.timezone.utc)
            )

        assert items == [
            {"name": "Untitled", "kind": "knowledge_base"},
            {"name": "NSF Extractor", "kind": "workflow"},
        ]
