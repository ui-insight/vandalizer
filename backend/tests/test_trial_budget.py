"""Unit tests for the trial LLM spend cap (app/services/trial_budget.py) and
its enforcement at metering-scope entry (app/services/metering.py).

DB access is stubbed at the module boundary, matching the metering test
conventions: no Mongo, assertions on behavior of the check itself.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import TrialBudgetExceededError
from app.services import metering, trial_budget
from tests.conftest import fake_model


def _settings(*, enabled: bool = True, budget: int = 1000) -> SimpleNamespace:
    return SimpleNamespace(
        enable_trial_system=enabled,
        trial_token_budget=budget,
        trial_global_monthly_tokens=0,  # fleet ceiling has its own test module
        redis_host="localhost",
    )


# ---------------------------------------------------------------------------
# _budget — the enforcement gate
# ---------------------------------------------------------------------------


def test_budget_zero_when_trial_system_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_settings", lambda: _settings(enabled=False, budget=5000)
    )
    assert trial_budget._budget() == 0


def test_budget_reads_setting_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_settings", lambda: _settings(enabled=True, budget=5000)
    )
    assert trial_budget._budget() == 5000


def test_budget_never_negative(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_settings", lambda: _settings(enabled=True, budget=-5)
    )
    assert trial_budget._budget() == 0


# ---------------------------------------------------------------------------
# effective_budget — per-user override vs deployment default
# ---------------------------------------------------------------------------


def test_effective_budget_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    assert trial_budget.effective_budget(None) == 2000


def test_effective_budget_prefers_user_override(monkeypatch):
    """Top-ups raise the per-user value; it must win over the default."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    assert trial_budget.effective_budget(6000) == 6000


def test_effective_budget_user_zero_disables_the_cap(monkeypatch):
    """An admin release sets 0 — that user is no longer metered."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    assert trial_budget.effective_budget(0) == 0


def test_effective_budget_zero_when_deployment_disabled(monkeypatch):
    """A per-user value can't switch metering on where it's globally off."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 0)
    assert trial_budget.effective_budget(5000) == 0


# ---------------------------------------------------------------------------
# get_trial_usage — the meter's data source
# ---------------------------------------------------------------------------


async def test_usage_disabled_for_non_trial_user(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    usage = await trial_budget.get_trial_usage(
        SimpleNamespace(user_id="u-1", is_demo_user=False, trial_token_budget=None, email_verified=True)
    )
    assert usage["enabled"] is False
    assert usage["budget"] == 0


async def test_usage_reports_remaining_and_percent(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=1500))
    usage = await trial_budget.get_trial_usage(
        SimpleNamespace(user_id="u-1", is_demo_user=True, trial_token_budget=None, email_verified=True)
    )
    assert usage == {
        "enabled": True,
        "budget": 2000,
        "used": 1500,
        "remaining": 500,
        "percent": 75,
        "email_verified": True,
    }


async def test_usage_clamps_an_overshoot(monkeypatch):
    """The last operation can run past the ceiling; the meter must not lie."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=2400))
    usage = await trial_budget.get_trial_usage(
        SimpleNamespace(user_id="u-1", is_demo_user=True, trial_token_budget=None, email_verified=True)
    )
    assert usage["remaining"] == 0
    assert usage["percent"] == 100


async def test_usage_uses_the_topped_up_budget(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=2000))
    usage = await trial_budget.get_trial_usage(
        SimpleNamespace(user_id="u-1", is_demo_user=True, trial_token_budget=6000, email_verified=True)
    )
    assert usage["budget"] == 6000
    assert usage["remaining"] == 4000


async def test_check_async_respects_a_topped_up_budget(monkeypatch):
    """A user who topped up is under budget again and must not be blocked."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 2000)
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=2500))
    user = SimpleNamespace(is_demo_user=True, trial_token_budget=4000, email_verified=True)
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        await trial_budget.check_async("u-1")  # no raise


# ---------------------------------------------------------------------------
# check_async
# ---------------------------------------------------------------------------


async def test_check_async_noop_when_trial_system_is_off(monkeypatch):
    """The master switch short-circuits before any DB access.

    This is the *trial system* switch, not the per-account budget:
    TRIAL_TOKEN_BUDGET=0 means "don't cap individuals" and deliberately leaves
    verification and the fleet ceiling running (see test_trial_verification).
    """
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: False)
    users = fake_model()
    with patch("app.models.user.User", users):
        await trial_budget.check_async("u-1")
    users.find_one.assert_not_awaited()


async def test_check_async_noop_without_user_id(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    users = fake_model()
    with patch("app.models.user.User", users):
        await trial_budget.check_async(None)
    users.find_one.assert_not_awaited()


async def test_check_async_ignores_regular_users(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    used = AsyncMock(return_value=999_999)
    monkeypatch.setattr(trial_budget, "tokens_used_async", used)
    user = SimpleNamespace(is_demo_user=False, trial_token_budget=None, email_verified=True)
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        await trial_budget.check_async("u-1")
    used.assert_not_awaited()


async def test_check_async_allows_under_budget_trial_user(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    monkeypatch.setattr(
        trial_budget, "tokens_used_async", AsyncMock(return_value=999)
    )
    user = SimpleNamespace(is_demo_user=True, trial_token_budget=None, email_verified=True)
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        await trial_budget.check_async("u-1")


async def test_check_async_raises_at_budget(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    monkeypatch.setattr(
        trial_budget, "tokens_used_async", AsyncMock(return_value=1000)
    )
    user = SimpleNamespace(is_demo_user=True, trial_token_budget=None, email_verified=True)
    with patch("app.models.user.User", fake_model(find_one_result=user)):
        with pytest.raises(TrialBudgetExceededError) as exc:
            await trial_budget.check_async("u-1")
    assert exc.value.status_code == 402


async def test_check_async_fails_open_on_db_error(monkeypatch):
    """An infrastructure failure in the check must never block LLM features."""
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    users = fake_model()
    users.find_one = AsyncMock(side_effect=RuntimeError("down"))
    with patch("app.models.user.User", users):
        await trial_budget.check_async("u-1")


# ---------------------------------------------------------------------------
# check_sync (Celery-side twin)
# ---------------------------------------------------------------------------


def _sync_db(*, user_doc, total: int):
    db = MagicMock()
    db.user.find_one.return_value = user_doc
    db.llm_usage.aggregate.return_value = (
        [{"_id": None, "total": total}] if total else []
    )
    return db


def test_check_sync_raises_at_budget(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    db = _sync_db(user_doc={"is_demo_user": True, "trial_token_budget": None, "email_verified": True}, total=2000)
    with patch("app.tasks.get_sync_db", return_value=db):
        with pytest.raises(TrialBudgetExceededError):
            trial_budget.check_sync("u-1")


def test_check_sync_ignores_regular_users(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    db = _sync_db(user_doc={"is_demo_user": False, "trial_token_budget": None, "email_verified": True}, total=2000)
    with patch("app.tasks.get_sync_db", return_value=db):
        trial_budget.check_sync("u-1")
    db.llm_usage.aggregate.assert_not_called()


def test_check_sync_fails_open_on_db_error(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    with patch("app.tasks.get_sync_db", side_effect=RuntimeError("down")):
        trial_budget.check_sync("u-1")


# ---------------------------------------------------------------------------
# Enforcement at metering-scope entry
# ---------------------------------------------------------------------------


async def test_metered_async_blocks_over_budget_user(monkeypatch):
    monkeypatch.setattr(
        "app.services.trial_budget.check_async",
        AsyncMock(side_effect=TrialBudgetExceededError()),
    )
    with pytest.raises(TrialBudgetExceededError):
        async with metering.metered_async("chat", user_id="u-1"):
            pytest.fail("scope body must not run once the budget is exhausted")
    # The scope must not leak when entry is refused.
    assert metering.current_scope() is None


async def test_metered_async_skips_check_without_user(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr("app.services.trial_budget.check_async", check)
    async with metering.metered_async("title_gen"):
        pass
    check.assert_not_awaited()


def test_metered_sync_blocks_over_budget_user(monkeypatch):
    monkeypatch.setattr(
        "app.services.trial_budget.check_sync",
        MagicMock(side_effect=TrialBudgetExceededError()),
    )
    with pytest.raises(TrialBudgetExceededError):
        with metering.metered("workflow", user_id="u-1"):
            pytest.fail("scope body must not run once the budget is exhausted")
    assert metering.current_scope() is None


# ---------------------------------------------------------------------------
# Chat surfaces the cutoff as a friendly stream error, not a bug
# ---------------------------------------------------------------------------


def test_chat_stream_classifier_handles_budget_error():
    from app.services.chat_service import _classify_stream_error

    severity, message = _classify_stream_error(
        TrialBudgetExceededError(trial_budget.EXCEEDED_MESSAGE)
    )
    assert severity == "warning"
    assert message == trial_budget.EXCEEDED_MESSAGE
