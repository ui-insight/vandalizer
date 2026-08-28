"""Unit tests for the token-metered trial lifecycle (demo_service).

The trial is a budget, not a clock: registration grants tokens, the hourly
sweep warns at ~80% and marks the account exhausted at 100%, and exhaustion is
soft (the workspace stays browsable; only LLM spend is gated). These tests
cover begin_self_serve_trial, sweep_trial_budgets, the clock-era migration,
and the grant arithmetic behind top-ups.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import demo_service
from tests.conftest import fake_model


def _constructible_fake_model(docs=None, *, find_one_result=None):
    """fake_model + a working constructor, for services that insert documents."""
    cls = fake_model(docs, find_one_result=find_one_result)
    created: list = []

    def _init(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        # Defaults the model declares that a kwargs-only stand-in would miss.
        self.activation_email_failed = getattr(self, "activation_email_failed", False)
        self.budget_warning_sent = getattr(self, "budget_warning_sent", False)
        self.insert = AsyncMock()
        self.save = AsyncMock()
        created.append(self)

    cls.__init__ = _init
    cls.created = created
    return cls


def _settings(budget: int = 2_000_000, topup: int = 2_000_000) -> SimpleNamespace:
    return SimpleNamespace(
        frontend_url="https://example.test",
        redis_host="localhost",
        trial_token_budget=budget,
        trial_topup_tokens=topup,
        trial_global_monthly_tokens=0,  # fleet ceiling off; covered separately
        enable_trial_system=True,
    )


def _user(**overrides) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="u-1",
        email="Ada@Example.EDU",
        name="Ada",
        is_demo_user=False,
        demo_status=None,
        demo_expires_at=None,
        trial_token_budget=None,
        email_verified=False,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    user.save = AsyncMock()
    return user


def _app(**overrides) -> SimpleNamespace:
    app = SimpleNamespace(
        uuid="app-1",
        name="Ada",
        email="ada@example.edu",
        status="active",
        user_id="u-1",
        activated_at=None,
        expires_at=None,
        expired_at=None,
        post_questionnaire_token=None,
        budget_warning_sent=False,
        activation_email_failed=False,
        trial_extensions_used=0,
        recapture_step=0,
        recapture_next_at=None,
    )
    for key, value in overrides.items():
        setattr(app, key, value)
    app.save = AsyncMock()
    return app


# ---------------------------------------------------------------------------
# begin_self_serve_trial — budget, not clock
# ---------------------------------------------------------------------------


async def test_begin_trial_grants_budget_and_no_expiry():
    user = _user()
    apps = _constructible_fake_model(find_one_result=None)

    with (
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(demo_service, "_create_magic_login_token",
                     AsyncMock(return_value="https://x/magic?v")),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)),
    ):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert user.is_demo_user is True
    assert user.demo_status == "active"
    assert user.trial_token_budget == 2_000_000
    assert user.demo_expires_at is None  # the clock is gone
    user.save.assert_awaited_once()

    assert len(apps.created) == 1
    app = apps.created[0]
    assert app.status == "active"
    assert app.user_id == "u-1"
    assert app.email == "ada@example.edu"
    assert app.organization == "example.edu"
    assert getattr(app, "expires_at", None) is None
    app.insert.assert_awaited_once()


async def test_begin_trial_adopts_pending_application():
    """A pending applicant who registers directly keeps one record."""
    user = _user()
    pending = _app(status="pending", user_id=None)
    apps = _constructible_fake_model(find_one_result=pending)

    with (
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(demo_service, "send_verification_email", AsyncMock()),
    ):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert apps.created == []  # adopted, not duplicated
    assert pending.status == "active"
    assert pending.user_id == "u-1"
    assert pending.expires_at is None
    pending.save.assert_awaited_once()


async def test_begin_trial_does_not_revive_an_exhausted_application():
    """Reviving a finished run would hand a second budget to the same person."""
    user = _user()
    finished = _app(status="exhausted")
    apps = _constructible_fake_model(find_one_result=finished)

    with (
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(demo_service, "_create_magic_login_token",
                     AsyncMock(return_value="https://x/magic?v")),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)),
    ):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert finished.status == "exhausted"
    finished.save.assert_not_awaited()
    assert len(apps.created) == 1
    assert apps.created[0].status == "active"


# ---------------------------------------------------------------------------
# grant_tokens — the arithmetic behind top-ups and admin restarts
# ---------------------------------------------------------------------------


async def test_grant_tokens_adds_to_the_existing_ceiling():
    user = _user(is_demo_user=True, trial_token_budget=2_000_000)
    with patch.object(
        demo_service.trial_budget, "tokens_used_async", AsyncMock(return_value=500_000)
    ):
        new_budget = await demo_service.grant_tokens(user, 2_000_000)

    assert new_budget == 4_000_000
    assert user.trial_token_budget == 4_000_000
    assert user.demo_status == "active"
    assert user.demo_expires_at is None


async def test_grant_tokens_is_worth_full_amount_after_an_overshoot():
    """A last operation that ran past the ceiling must not eat the top-up."""
    user = _user(is_demo_user=True, trial_token_budget=2_000_000)
    with patch.object(
        demo_service.trial_budget,
        "tokens_used_async",
        AsyncMock(return_value=2_100_000),
    ):
        new_budget = await demo_service.grant_tokens(user, 2_000_000)

    assert new_budget == 4_100_000  # anchored on used, not the stale budget


# ---------------------------------------------------------------------------
# sweep_trial_budgets — warning, then soft exhaustion
# ---------------------------------------------------------------------------


def _usage(used: int, budget: int) -> dict:
    return {
        "enabled": True,
        "budget": budget,
        "used": used,
        "remaining": max(0, budget - used),
        "percent": min(100, round(used * 100 / budget)),
    }


async def _run_sweep(app, user, usage):
    with (
        patch.object(
            demo_service, "_adopt_clock_era_trial_users", AsyncMock(return_value=0)
        ),
        patch.object(demo_service, "DemoApplication", fake_model([app])),
        patch.object(demo_service, "User", fake_model(find_one_result=user)),
        patch.object(
            demo_service.trial_budget, "get_trial_usage", AsyncMock(return_value=usage)
        ),
        patch.object(demo_service, "send_email", AsyncMock(return_value=True)) as send,
    ):
        result = await demo_service.sweep_trial_budgets(_settings())
    return result, send


async def test_sweep_warns_once_at_eighty_percent():
    app = _app()
    user = _user(is_demo_user=True, demo_status="active")

    result, send = await _run_sweep(app, user, _usage(1_600_000, 2_000_000))

    assert result == {"warned": 1, "exhausted": 0}
    assert app.budget_warning_sent is True
    assert app.status == "active"  # still usable
    send.assert_awaited_once()


async def test_sweep_does_not_rewarn():
    app = _app(budget_warning_sent=True)
    user = _user(is_demo_user=True, demo_status="active")

    result, send = await _run_sweep(app, user, _usage(1_900_000, 2_000_000))

    assert result == {"warned": 0, "exhausted": 0}
    send.assert_not_awaited()


async def test_sweep_stays_quiet_below_threshold():
    app = _app()
    user = _user(is_demo_user=True, demo_status="active")

    result, send = await _run_sweep(app, user, _usage(500_000, 2_000_000))

    assert result == {"warned": 0, "exhausted": 0}
    assert app.budget_warning_sent is False
    send.assert_not_awaited()


async def test_sweep_exhaustion_is_soft_and_mints_a_topup_token():
    app = _app()
    user = _user(is_demo_user=True, demo_status="active")

    result, send = await _run_sweep(app, user, _usage(2_000_000, 2_000_000))

    assert result == {"warned": 0, "exhausted": 1}
    assert app.status == "exhausted"
    # Soft: never "locked" — the workspace stays readable, only spend is gated.
    assert user.demo_status == "exhausted"
    assert app.post_questionnaire_token  # the top-up screen needs it
    send.assert_awaited_once()


async def test_sweep_skips_users_whose_cap_is_disabled():
    app = _app()
    user = _user(is_demo_user=True, demo_status="active")
    disabled = {"enabled": False, "budget": 0, "used": 0, "remaining": 0, "percent": 0}

    result, send = await _run_sweep(app, user, disabled)

    assert result == {"warned": 0, "exhausted": 0}
    send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Clock-era migration
# ---------------------------------------------------------------------------


async def test_migration_clears_expiry_and_sets_budget():
    past = datetime.datetime(2026, 8, 1)  # naive, as Mongo returns it
    legacy = _user(is_demo_user=True, demo_status="active", demo_expires_at=past)
    users = fake_model([legacy])
    apps = _constructible_fake_model(docs=[SimpleNamespace(user_id="u-1")])

    with (
        patch.object(demo_service, "User", users),
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(demo_service.trial_budget, "_budget", lambda: 2_000_000),
    ):
        migrated = await demo_service._adopt_clock_era_trial_users(
            datetime.datetime.now(datetime.timezone.utc)
        )

    assert migrated == 1
    assert legacy.demo_expires_at is None  # a lapsed clock can never lock them
    assert legacy.trial_token_budget == 2_000_000
    assert apps.created == []  # already linked


async def test_migration_mints_application_for_orphan_user():
    orphan = _user(
        is_demo_user=True, demo_status="active", trial_token_budget=2_000_000
    )
    users = fake_model([orphan])
    apps = _constructible_fake_model(docs=[], find_one_result=None)

    with (
        patch.object(demo_service, "User", users),
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(demo_service.trial_budget, "_budget", lambda: 2_000_000),
    ):
        migrated = await demo_service._adopt_clock_era_trial_users(
            datetime.datetime.now(datetime.timezone.utc)
        )

    assert migrated == 1
    assert len(apps.created) == 1
    assert apps.created[0].status == "active"
    assert apps.created[0].user_id == "u-1"


async def test_sweep_runs_migration_first():
    """Migrated users must be visible to the same sweep that adopted them."""
    migrate = AsyncMock(return_value=0)
    with (
        patch.object(demo_service, "_adopt_clock_era_trial_users", migrate),
        patch.object(demo_service, "DemoApplication", fake_model([])),
    ):
        result = await demo_service.sweep_trial_budgets(_settings())

    assert result == {"warned": 0, "exhausted": 0}
    migrate.assert_awaited_once()


def test_email_domain_buckets():
    assert demo_service._email_domain("ada@Example.EDU") == "example.edu"
    assert demo_service._email_domain("") == "self-registered"
    assert demo_service._email_domain("no-at-sign") == "no-at-sign"


# ---------------------------------------------------------------------------
# Feedback-prompt scheduling survives the loss of the clock
# ---------------------------------------------------------------------------


async def test_trial_start_comes_from_activation_when_there_is_no_clock():
    """In-app check-in prompts are scheduled in trial days; with no expiry to
    work backwards from, the application's activation date is the anchor."""
    from app.services import feedback_prompt_service

    activated = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
    user = _user(is_demo_user=True, demo_expires_at=None)
    with patch(
        "app.models.demo.DemoApplication",
        fake_model(find_one_result=SimpleNamespace(activated_at=activated)),
    ):
        started = await feedback_prompt_service._trial_started_at(user)

    assert started == activated


async def test_trial_start_falls_back_to_the_legacy_clock():
    """Clock-era accounts with no application still schedule correctly."""
    from app.services import feedback_prompt_service

    expires = datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc)
    user = _user(is_demo_user=True, demo_expires_at=expires)
    with patch("app.models.demo.DemoApplication", fake_model(find_one_result=None)):
        started = await feedback_prompt_service._trial_started_at(user)

    assert started == expires - datetime.timedelta(
        days=feedback_prompt_service.TRIAL_DAYS
    )


async def test_trial_start_none_for_regular_users():
    from app.services import feedback_prompt_service

    assert await feedback_prompt_service._trial_started_at(_user()) is None


async def test_adopted_pending_application_still_gets_a_verification_email():
    """Adopting a pending record is still a first sign-in. Without the send,
    the account is gated with no link ever delivered."""
    user = _user()
    pending = SimpleNamespace(
        status="pending", user_id=None, activated_at=None, expires_at=None,
        budget_warning_sent=True,
    )
    pending.save = AsyncMock()
    apps = _constructible_fake_model(find_one_result=pending)
    sent = AsyncMock()

    with (
        patch.object(demo_service, "DemoApplication", apps),
        patch.object(demo_service, "send_verification_email", sent),
    ):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert apps.created == []  # adopted, not duplicated
    sent.assert_awaited_once()
    assert sent.await_args.args[1] is pending
