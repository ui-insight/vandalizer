"""Tests for the promotional-email kill switch.

`settings.promotional_emails_enabled` gates the three scheduled campaigns
(demo recapture drips, onboarding drips, inactivity nudges) and nothing else.
Transactional mail is deliberately out of scope here.

Also covers the recapture opt-out: recapture is the only campaign that used to
ignore `email_preferences`, so the check that it now honors "nudges" — and ends
the sequence rather than deferring it — is worth locking in.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import demo_service, engagement_service
from tests.conftest import fake_model as _fake_model


def _settings(*, promotional: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        promotional_emails_enabled=promotional,
        frontend_url="https://example.test",
    )


# (processor, module, attribute holding the model it queries for recipients)
CAMPAIGNS = [
    (demo_service.process_recapture_drips, demo_service, "DemoApplication"),
    (engagement_service.process_onboarding_drips, engagement_service, "User"),
    (engagement_service.process_inactivity_nudges, engagement_service, "User"),
]


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("processor,module,model_attr", CAMPAIGNS)
async def test_disabled_switch_sends_nothing(processor, module, model_attr):
    """With the switch off, each processor returns 0 without querying at all."""
    model = _fake_model()
    with patch.object(module, model_attr, model):
        sent = await processor(_settings(promotional=False))

    assert sent == 0
    model.find.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("processor,module,model_attr", CAMPAIGNS)
async def test_enabled_switch_still_runs(processor, module, model_attr):
    """With the switch on, the processor proceeds to query for due recipients."""
    model = _fake_model()
    with patch.object(module, model_attr, model):
        sent = await processor(_settings(promotional=True))

    assert sent == 0
    model.find.assert_called_once()


# ---------------------------------------------------------------------------
# Recapture opt-out
# ---------------------------------------------------------------------------


def _demo_app() -> SimpleNamespace:
    app = SimpleNamespace(
        uuid="app-1",
        name="Ada",
        email="ada@example.test",
        status="active",
        user_id="u-1",
        recapture_step=0,
        recapture_next_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    app.save = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_recapture_honors_nudge_opt_out():
    """An opted-out user gets no recapture mail and the sequence is retired."""
    app = _demo_app()
    user = SimpleNamespace(
        user_id="u-1", last_login_at=None, email_preferences={"nudges": False}
    )

    with (
        patch.object(demo_service, "DemoApplication", _fake_model([app])),
        patch.object(demo_service, "User", _fake_model(find_one_result=user)),
        patch.object(demo_service, "send_email", AsyncMock()) as send,
    ):
        sent = await demo_service.process_recapture_drips(_settings())

    assert sent == 0
    send.assert_not_awaited()
    # Retired, not deferred — otherwise it stays due on every daily run.
    assert app.recapture_next_at is None
    assert app.recapture_step == 0
    app.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_recapture_sends_when_not_opted_out():
    """The default (no preference recorded) still sends and advances the step."""
    app = _demo_app()
    user = SimpleNamespace(user_id="u-1", last_login_at=None, email_preferences={})

    with (
        patch.object(demo_service, "DemoApplication", _fake_model([app])),
        patch.object(demo_service, "User", _fake_model(find_one_result=user)),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)) as send,
    ):
        sent = await demo_service.process_recapture_drips(_settings())

    assert sent == 1
    send.assert_awaited_once()
    assert send.await_args.kwargs["email_type"] == "recapture"
    assert app.recapture_step == 1
