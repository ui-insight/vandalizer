"""Unit tests for the trial-funnel UX fixes.

Covers: the top-up returning a working way back in (magic links in the response
and the confirmation email), and the activation-email-failed flag lifecycle on
resend.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import demo_service
from app.services.email_service import trial_topup_email
from tests.conftest import fake_model


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        frontend_url="https://example.test",
        redis_host="localhost",
        trial_token_budget=2_000_000,
        trial_topup_tokens=2_000_000,
        enable_trial_system=True,
    )


def _app(**overrides) -> SimpleNamespace:
    app = SimpleNamespace(
        id="app-oid-1",
        uuid="app-1",
        name="Ada",
        email="ada@example.test",
        status="active",
        user_id="ada@example.test",
        waitlist_position=None,
        expires_at=None,
        post_questionnaire_token="tok-1",
        trial_extensions_used=0,
        recapture_step=0,
        recapture_next_at=None,
        expired_at=None,
        activation_email_failed=False,
        budget_warning_sent=False,
    )
    for key, value in overrides.items():
        setattr(app, key, value)
    app.save = AsyncMock()
    return app


# ---------------------------------------------------------------------------
# The top-up returns a way back in
# ---------------------------------------------------------------------------


async def test_self_topup_returns_and_emails_separate_magic_links():
    """Magic-login tokens are one-time, so the email CTA and the top-up
    screen's Enter button must each get their own."""
    app = _app()
    user = SimpleNamespace(
        user_id="ada@example.test",
        demo_status=None,
        demo_expires_at=None,
        trial_token_budget=2_000_000,
    )
    user.save = AsyncMock()

    links = AsyncMock(side_effect=["https://x/magic?1", "https://x/magic?2"])
    captured = {}

    def _email(name, new_budget, frontend_url, magic_link=None):
        captured["magic_link"] = magic_link
        captured["new_budget"] = new_budget
        return "subj", "html"

    with (
        patch.object(demo_service, "DemoApplication", fake_model(find_one_result=app)),
        patch.object(demo_service, "User", fake_model(find_one_result=user)),
        patch.object(demo_service, "_create_magic_login_token", links),
        patch.object(demo_service, "trial_topup_email", _email),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)),
        patch.object(
            demo_service.trial_budget, "tokens_used_async", AsyncMock(return_value=0)
        ),
    ):
        result = await demo_service.self_topup_trial("tok-1", None, _settings())

    assert result["ok"] is True
    assert links.await_count == 2
    assert captured["magic_link"] == "https://x/magic?1"
    assert result["login_url"] == "https://x/magic?2"
    assert result["login_url"] != captured["magic_link"]
    # The grant is reported in tokens, and the account is usable again.
    assert result["tokens_granted"] == 2_000_000
    assert result["tokens_budget"] == 4_000_000
    assert captured["new_budget"] == 4_000_000
    assert app.status == "active"
    assert app.budget_warning_sent is False  # a fresh window warns again


def test_trial_topup_email_prefers_magic_link():
    _, html = trial_topup_email(
        "Ada", 4_000_000, "https://x", magic_link="https://x/magic?t"
    )
    assert 'href="https://x/magic?t"' in html
    assert "4,000,000" in html  # the balance is legible, not raw


def test_trial_topup_email_falls_back_to_login():
    _, html = trial_topup_email("Ada", 4_000_000, "https://x")
    assert 'href="https://x/login"' in html


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


# ---------------------------------------------------------------------------
# activation_email_failed lifecycle on the admin bulk resend
# ---------------------------------------------------------------------------


async def _bulk_resend(app, *, send_ok: bool) -> dict:
    user = SimpleNamespace(user_id=app.user_id, last_login_at=None, demo_expires_at=None)
    user.save = AsyncMock()
    with (
        patch.object(demo_service, "DemoApplication", fake_model([app])),
        patch.object(demo_service, "User", fake_model(find_one_result=user)),
        patch.object(demo_service, "_create_magic_login_token",
                     AsyncMock(return_value="https://x/magic?b")),
        patch.object(demo_service, "send_email", AsyncMock(return_value=send_ok)),
    ):
        return await demo_service.bulk_resend_credentials(_settings())


async def test_bulk_resend_success_clears_flag():
    app = _app(activation_email_failed=True)
    result = await _bulk_resend(app, send_ok=True)
    assert result["sent"] == 1
    assert app.activation_email_failed is False


async def test_bulk_resend_failure_sets_flag():
    app = _app(activation_email_failed=False)
    result = await _bulk_resend(app, send_ok=False)
    assert result["failed"] == 1
    assert app.activation_email_failed is True
