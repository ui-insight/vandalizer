"""Unit tests for the trial-funnel UX fixes.

Covers: renewal returning a working way back in (magic links in the response
and the confirmation email), the honest waitlist estimate, and the
activation-email-failed flag lifecycle on resend.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import demo_service
from app.services.email_service import trial_extended_email
from tests.conftest import fake_model


def _settings() -> SimpleNamespace:
    return SimpleNamespace(frontend_url="https://example.test", redis_host="localhost")


def _app(**overrides) -> SimpleNamespace:
    app = SimpleNamespace(
        id="app-oid-1",
        uuid="app-1",
        name="Ada",
        email="ada@example.test",
        status="active",
        user_id="ada@example.test",
        waitlist_position=None,
        expires_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc),
        post_questionnaire_token="tok-1",
        trial_extensions_used=0,
        recapture_step=0,
        recapture_next_at=None,
        expired_at=None,
        activation_email_failed=False,
    )
    for key, value in overrides.items():
        setattr(app, key, value)
    app.save = AsyncMock()
    return app


# ---------------------------------------------------------------------------
# Renewal returns a way back in
# ---------------------------------------------------------------------------


async def test_self_extend_returns_and_emails_separate_magic_links():
    """Magic-login tokens are one-time, so the email CTA and the renewal
    screen's Enter button must each get their own."""
    app = _app()
    user = SimpleNamespace(user_id="ada@example.test", demo_status=None,
                           demo_expires_at=None)
    user.save = AsyncMock()

    links = AsyncMock(side_effect=["https://x/magic?1", "https://x/magic?2"])
    captured = {}

    def _email(name, expires, frontend_url, magic_link=None):
        captured["magic_link"] = magic_link
        return "subj", "html"

    with (
        patch.object(demo_service, "DemoApplication", fake_model(find_one_result=app)),
        patch.object(demo_service, "User", fake_model(find_one_result=user)),
        patch.object(demo_service, "_create_magic_login_token", links),
        patch.object(demo_service, "trial_extended_email", _email),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)),
    ):
        result = await demo_service.self_extend_trial("tok-1", None, _settings())

    assert result["ok"] is True
    assert links.await_count == 2
    assert captured["magic_link"] == "https://x/magic?1"
    assert result["login_url"] == "https://x/magic?2"
    assert result["login_url"] != captured["magic_link"]


def test_trial_extended_email_prefers_magic_link():
    _, html = trial_extended_email("Ada", "Sep 01", "https://x", magic_link="https://x/magic?t")
    assert 'href="https://x/magic?t"' in html


def test_trial_extended_email_falls_back_to_login():
    _, html = trial_extended_email("Ada", "Sep 01", "https://x")
    assert 'href="https://x/login"' in html


# ---------------------------------------------------------------------------
# Honest waitlist estimate
# ---------------------------------------------------------------------------


async def test_estimate_wait_is_minutes_when_slots_free():
    apps = fake_model()
    apps.find.return_value.count = AsyncMock(return_value=10)  # 40 slots free
    pending = _app(status="pending", waitlist_position=3)
    with patch.object(demo_service, "DemoApplication", apps):
        text = await demo_service.estimate_wait_text(pending)
    assert "15 minutes" in text


async def test_estimate_wait_is_honest_when_full():
    apps = fake_model()
    apps.find.return_value.count = AsyncMock(
        return_value=demo_service.MAX_ACTIVE_DEMOS
    )
    pending = _app(status="pending", waitlist_position=1)
    with patch.object(demo_service, "DemoApplication", apps):
        text = await demo_service.estimate_wait_text(pending)
    assert "full" in text
    assert "day" not in text  # the old fake "N day(s)" formula is gone


async def test_estimate_wait_none_for_active():
    assert await demo_service.estimate_wait_text(_app(status="active")) is None


# ---------------------------------------------------------------------------
# activation_email_failed lifecycle on resend
# ---------------------------------------------------------------------------


async def test_resend_failure_sets_flag():
    app = _app(activation_email_failed=False)
    user = SimpleNamespace(user_id="ada@example.test")
    with (
        patch.object(demo_service, "DemoApplication", fake_model(find_one_result=app)),
        patch.object(demo_service, "User", fake_model(find_one_result=user)),
        patch.object(demo_service, "_create_magic_login_token",
                     AsyncMock(return_value="https://x/magic?r")),
        patch.object(demo_service, "send_email", AsyncMock(return_value=False)),
    ):
        result = await demo_service.resend_credentials("app-1", _settings())

    assert result["status"] == "send_failed"
    assert app.activation_email_failed is True
    app.save.assert_awaited()


async def test_resend_success_clears_flag():
    app = _app(activation_email_failed=True)
    user = SimpleNamespace(user_id="ada@example.test")
    with (
        patch.object(demo_service, "DemoApplication", fake_model(find_one_result=app)),
        patch.object(demo_service, "User", fake_model(find_one_result=user)),
        patch.object(demo_service, "_create_magic_login_token",
                     AsyncMock(return_value="https://x/magic?r")),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)),
    ):
        result = await demo_service.resend_credentials("app-1", _settings())

    assert result["status"] == "sent"
    assert app.activation_email_failed is False
    app.save.assert_awaited()
