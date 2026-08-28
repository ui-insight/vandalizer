"""Unit tests for the trial verification gate and the fleet-wide ceiling.

Self-registration hands out a session immediately, so an unconfirmed address
is what stands between "anyone can type an email" and unmetered spend on the
deployment's keys. The per-account budget bounds one signup; the fleet ceiling
bounds the bill when many sign up at once (the job the old 50-concurrent-trials
cap was quietly doing).
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import TrialBudgetExceededError, TrialUnverifiedError
from app.services import demo_service, trial_budget
from tests.conftest import fake_model


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        frontend_url="https://example.test",
        redis_host="localhost",
        trial_token_budget=2_000_000,
        trial_topup_tokens=2_000_000,
        trial_global_monthly_tokens=100_000_000,
        enable_trial_system=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# The verification gate
# ---------------------------------------------------------------------------


async def test_unverified_trial_user_cannot_spend(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=False
    )
    used = AsyncMock(return_value=0)
    monkeypatch.setattr(trial_budget, "tokens_used_async", used)

    with patch("app.models.user.User", fake_model(find_one_result=user)):
        with pytest.raises(TrialUnverifiedError) as exc:
            await trial_budget.check_async("u-1")

    assert exc.value.status_code == 403
    # Checked before the ledger: cheaper, and the more actionable message.
    used.assert_not_awaited()


async def test_verified_trial_user_under_budget_passes(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=10))
    monkeypatch.setattr(
        trial_budget, "_fleet_paused_async", AsyncMock(return_value=False)
    )
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=True
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        await trial_budget.check_async("u-1")  # no raise


async def test_verification_never_gates_a_regular_user(monkeypatch):
    """Staff arrive by bootstrap, invite, or SSO — never asked to confirm."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    user = SimpleNamespace(
        is_demo_user=False, trial_token_budget=None, email_verified=False
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        await trial_budget.check_async("u-1")  # no raise


def test_unverified_trial_user_cannot_spend_sync(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    db = MagicMock()
    db.user.find_one.return_value = {
        "is_demo_user": True, "trial_token_budget": None, "email_verified": False,
    }
    with patch("app.tasks.get_sync_db", return_value=db):
        with pytest.raises(TrialUnverifiedError):
            trial_budget.check_sync("u-1")
    db.llm_usage.aggregate.assert_not_called()


def test_chat_surfaces_unverified_as_a_warning():
    from app.services.chat_service import _classify_stream_error

    severity, message = _classify_stream_error(
        TrialUnverifiedError(trial_budget.UNVERIFIED_MESSAGE)
    )
    assert severity == "warning"
    assert message == trial_budget.UNVERIFIED_MESSAGE


# ---------------------------------------------------------------------------
# Fleet-wide monthly ceiling
# ---------------------------------------------------------------------------


async def test_fleet_pause_blocks_a_user_who_is_personally_under_budget(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=10))
    monkeypatch.setattr(
        trial_budget, "_fleet_paused_async", AsyncMock(return_value=True)
    )
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=True
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        with pytest.raises(TrialBudgetExceededError) as exc:
            await trial_budget.check_async("u-1")

    assert exc.value.message == trial_budget.FLEET_PAUSED_MESSAGE


async def test_personal_budget_message_wins_over_the_fleet_message(monkeypatch):
    """Someone out of their own tokens gets the top-up message, which is the
    one they can act on — not the fleet notice."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=5000))
    fleet = AsyncMock(return_value=True)
    monkeypatch.setattr(trial_budget, "_fleet_paused_async", fleet)
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=True
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        with pytest.raises(TrialBudgetExceededError) as exc:
            await trial_budget.check_async("u-1")

    assert exc.value.message == trial_budget.EXCEEDED_MESSAGE
    fleet.assert_not_awaited()  # not even consulted


def test_month_start_is_the_first_utc_instant():
    now = datetime.datetime(2026, 8, 24, 17, 30, tzinfo=datetime.timezone.utc)
    assert trial_budget.month_start(now) == datetime.datetime(
        2026, 8, 1, tzinfo=datetime.timezone.utc
    )


async def test_refresh_fleet_pause_disabled_when_ceiling_is_zero():
    result = await trial_budget.refresh_fleet_pause(
        _settings(trial_global_monthly_tokens=0)
    )
    assert result == {"enabled": False, "spent": 0, "ceiling": 0, "paused": False}


async def test_refresh_fleet_pause_sets_the_flag_when_over(monkeypatch):
    monkeypatch.setattr(
        trial_budget, "fleet_tokens_this_month", AsyncMock(return_value=150_000_000)
    )
    redis = MagicMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.aclose = AsyncMock()
    with patch("redis.asyncio.from_url", return_value=redis):
        result = await trial_budget.refresh_fleet_pause(_settings())

    assert result["paused"] is True
    redis.set.assert_awaited_once()
    redis.delete.assert_not_awaited()


async def test_refresh_fleet_pause_clears_the_flag_when_under(monkeypatch):
    monkeypatch.setattr(
        trial_budget, "fleet_tokens_this_month", AsyncMock(return_value=1_000)
    )
    redis = MagicMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.aclose = AsyncMock()
    with patch("redis.asyncio.from_url", return_value=redis):
        result = await trial_budget.refresh_fleet_pause(_settings())

    assert result["paused"] is False
    redis.delete.assert_awaited_once()
    redis.set.assert_not_awaited()


async def test_fleet_pause_read_fails_open(monkeypatch):
    """Redis trouble must never take down LLM features for everyone."""
    monkeypatch.setattr(
        "app.dependencies.get_settings", lambda: _settings()
    )
    with patch("redis.asyncio.from_url", side_effect=RuntimeError("down")):
        assert await trial_budget._fleet_paused_async() is False


# ---------------------------------------------------------------------------
# Registration sends the confirm-your-email link
# ---------------------------------------------------------------------------


async def test_registration_emails_the_verification_link():
    user = SimpleNamespace(
        user_id="u-1", email="ada@example.edu", name="Ada",
        is_demo_user=False, demo_status=None, demo_expires_at=None,
        trial_token_budget=None, email_verified=False,
    )
    user.save = AsyncMock()

    # Beanie's ExpressionField comparisons need the conftest stand-in; a plain
    # class would fall through to the uninitialized real Document.
    apps = fake_model(find_one_result=None)

    def _init(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.activation_email_failed = False
        self.insert = AsyncMock()
        self.save = AsyncMock()

    apps.__init__ = _init

    with (
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(
            demo_service, "_create_magic_login_token",
            AsyncMock(return_value="https://x/magic?v"),
        ),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)) as send,
    ):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert user.email_verified is False  # not verified until they click
    send.assert_awaited_once()
    assert send.await_args.kwargs["email_type"] == "verify_email"


async def test_verification_email_failure_is_recorded():
    user = SimpleNamespace(
        user_id="u-1", email="ada@example.edu", name="Ada", email_verified=False
    )
    user.save = AsyncMock()
    app = SimpleNamespace(
        email="ada@example.edu", name="Ada", activation_email_failed=False
    )
    app.save = AsyncMock()

    with (
        patch.object(
            demo_service, "_create_magic_login_token",
            AsyncMock(return_value="https://x/magic?v"),
        ),
        patch.object(demo_service, "send_email", AsyncMock(return_value=False)),
    ):
        sent = await demo_service.send_verification_email(user, app, _settings())

    assert sent is False
    assert app.activation_email_failed is True


async def test_verification_email_skipped_when_already_verified():
    user = SimpleNamespace(user_id="u-1", email="a@b.c", name="A", email_verified=True)
    app = SimpleNamespace(email="a@b.c", name="A", activation_email_failed=False)
    with patch.object(demo_service, "send_email", AsyncMock()) as send:
        assert await demo_service.send_verification_email(user, app, _settings()) is True
    send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Migration grandfathers existing trials past the new gate
# ---------------------------------------------------------------------------


def _trial_user(**overrides) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="u-1", email="ada@example.edu", name="Ada",
        is_demo_user=True, demo_status="active", demo_expires_at=None,
        trial_token_budget=2_000_000, email_verified=False,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    user.save = AsyncMock()
    return user


async def _sweep(user, *, linked=True):
    apps = [SimpleNamespace(user_id="u-1")] if linked else []
    cls = fake_model(apps)
    if not linked:
        # The unlinked path mints an application, so the stand-in needs a
        # constructor as well as the query methods.
        def _init(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.insert = AsyncMock()
            self.save = AsyncMock()

        cls.__init__ = _init
        cls.find_one = AsyncMock(return_value=None)
    with (
        patch.object(demo_service, "User", fake_model([user])),
        patch.object(demo_service, "DemoApplication", cls),
        patch.object(trial_budget, "_budget", lambda: 2_000_000),
    ):
        return await demo_service._adopt_clock_era_trial_users(
            datetime.datetime.now(datetime.timezone.utc)
        )


async def test_migration_marks_clock_era_trials_verified():
    """Retroactively cutting off AI for people mid-trial would be a worse
    failure than the narrow abuse the gate exists to stop.

    A clock-era account is one that still carries an expiry.
    """
    legacy = _trial_user(
        demo_expires_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc),
    )
    assert await _sweep(legacy) == 1
    assert legacy.email_verified is True
    assert legacy.demo_expires_at is None  # clock retired in the same pass


async def test_migration_grandfathers_users_that_never_got_an_application():
    """The other clock-era population: registration once set only the User
    flags, so these have no DemoApplication to link."""
    orphan = _trial_user()
    await _sweep(orphan, linked=False)
    assert orphan.email_verified is True


async def test_migration_does_not_verify_a_signup_made_under_the_token_model():
    """The gate would disarm itself otherwise.

    This sweep runs hourly, not once at deploy. A new signup has no expiry and
    a linked application, so an unbounded grandfather clause would verify
    every account that never clicked its link at the next tick — and the
    feature would be decorative within the hour.
    """
    fresh = _trial_user()  # no expiry, application linked — the new shape
    await _sweep(fresh)
    assert fresh.email_verified is False


# ---------------------------------------------------------------------------
# The three gates are independent
#
# They answer different questions — "is this address real", "has this person
# had their share", "can the deployment afford this month" — so turning one
# off must not turn the others off. TRIAL_TOKEN_BUDGET=0 previously
# short-circuited the whole check, silently disabling verification and the
# fleet ceiling along with the per-account cap.
# ---------------------------------------------------------------------------


async def test_uncapped_budget_still_requires_verification(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 0)  # per-account uncapped
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=False
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        with pytest.raises(TrialUnverifiedError):
            await trial_budget.check_async("u-1")


async def test_uncapped_budget_still_honors_the_fleet_ceiling(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 0)
    monkeypatch.setattr(
        trial_budget, "_fleet_paused_async", AsyncMock(return_value=True)
    )
    used = AsyncMock(return_value=0)
    monkeypatch.setattr(trial_budget, "tokens_used_async", used)
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=True
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        with pytest.raises(TrialBudgetExceededError) as exc:
            await trial_budget.check_async("u-1")

    assert exc.value.message == trial_budget.FLEET_PAUSED_MESSAGE
    # No per-account ledger read when there is no per-account cap to compare to.
    used.assert_not_awaited()


async def test_uncapped_and_verified_and_fleet_ok_passes(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 0)
    monkeypatch.setattr(
        trial_budget, "_fleet_paused_async", AsyncMock(return_value=False)
    )
    user = SimpleNamespace(
        is_demo_user=True, trial_token_budget=None, email_verified=True
    )
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        await trial_budget.check_async("u-1")  # no raise


def test_uncapped_budget_still_requires_verification_sync(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 0)
    db = MagicMock()
    db.user.find_one.return_value = {
        "is_demo_user": True, "trial_token_budget": None, "email_verified": False,
    }
    with patch("app.tasks.get_sync_db", return_value=db):
        with pytest.raises(TrialUnverifiedError):
            trial_budget.check_sync("u-1")


async def test_trial_system_off_disables_every_gate(monkeypatch):
    """The master switch is the one thing that turns all of them off."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: False)
    fleet = AsyncMock(return_value=True)
    monkeypatch.setattr(trial_budget, "_fleet_paused_async", fleet)
    users = fake_model()
    with patch("app.models.user.User", users):
        await trial_budget.check_async("u-1")  # no raise
    users.find_one.assert_not_awaited()
    fleet.assert_not_awaited()


async def test_usage_reports_verification_even_when_uncapped(monkeypatch):
    """The banner reads this; hiding it would leave the gate silent."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 0)
    usage = await trial_budget.get_trial_usage(
        SimpleNamespace(user_id="u-1", is_demo_user=True,
                        trial_token_budget=None, email_verified=False)
    )
    assert usage["enabled"] is False  # no meter to draw
    assert usage["email_verified"] is False  # but the gate is still on
