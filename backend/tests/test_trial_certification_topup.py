"""Trial learners can finish certification and top up in the app.

Support ticket: a fresh trial account ran out of AI tokens in Module 1 of 11
during certification. The only way back was an emailed link the address
couldn't receive, and the "Create extraction" approval just clicked was lost.
Certification chat is now outside the per-account budget (still inside the
fleet ceiling), and a signed-in trial user can top up in the app.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import TrialBudgetExceededError, TrialUnverifiedError
from app.services import demo_service, metering, trial_budget
from tests.conftest import fake_model


def _trial_user(**overrides):
    fields = {"user_id": "u-1", "is_demo_user": True, "trial_token_budget": None, "email_verified": True}
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture
def capped(monkeypatch):
    monkeypatch.setattr(trial_budget, "_trial_system_on", lambda: True)
    monkeypatch.setattr(trial_budget, "_budget", lambda: 1000)
    monkeypatch.setattr(trial_budget, "_fleet_paused_async", AsyncMock(return_value=False))
    monkeypatch.setattr(trial_budget, "_fleet_paused_sync", lambda: False)


# ---------------------------------------------------------------------------
# Certification chat is outside the per-account budget
# ---------------------------------------------------------------------------


async def test_certification_chat_runs_past_an_exhausted_budget(capped, monkeypatch):
    monkeypatch.setattr(trial_budget, "tokens_used_async", AsyncMock(return_value=5000))
    with patch("app.models.user.User", fake_model(find_one_result=_trial_user())):
        await trial_budget.check_async("u-1", "certification_chat")  # no raise
        with pytest.raises(TrialBudgetExceededError):
            await trial_budget.check_async("u-1", "chat")


async def test_certification_chat_still_needs_a_confirmed_address(capped):
    with patch("app.models.user.User", fake_model(find_one_result=_trial_user(email_verified=False))):
        with pytest.raises(TrialUnverifiedError):
            await trial_budget.check_async("u-1", "certification_chat")


async def test_certification_chat_still_stops_when_the_fleet_is_paused(capped, monkeypatch):
    monkeypatch.setattr(trial_budget, "_fleet_paused_async", AsyncMock(return_value=True))
    with patch("app.models.user.User", fake_model(find_one_result=_trial_user())):
        with pytest.raises(TrialBudgetExceededError) as exc:
            await trial_budget.check_async("u-1", "certification_chat")
    assert exc.value.code == "fleet_paused"


def test_sync_check_exempts_certification_and_filters_it_from_the_total(capped):
    db = MagicMock()
    db.user.find_one.return_value = {"is_demo_user": True, "trial_token_budget": None, "email_verified": True}
    db.llm_usage.aggregate.return_value = [{"_id": None, "total": 5000}]
    with patch("app.tasks.get_sync_db", return_value=db):
        trial_budget.check_sync("u-1", feature="certification_chat")
        db.llm_usage.aggregate.assert_not_called()
        with pytest.raises(TrialBudgetExceededError):
            trial_budget.check_sync("u-1", feature="extraction")
    match = db.llm_usage.aggregate.call_args.args[0][0]["$match"]
    assert match == {"user_id": "u-1", "feature": {"$nin": ["certification_chat"]}}


async def test_budget_usage_leaves_certification_out():
    records = MagicMock()
    records.find.return_value.aggregate.return_value.to_list = AsyncMock(return_value=[{"total": 1200}])
    with patch("app.models.llm_usage.LlmUsageRecord", records):
        assert await trial_budget.tokens_used_async("u-1") == 1200
    assert records.find.call_args.args[0] == {"user_id": "u-1", "feature": {"$nin": ["certification_chat"]}}


async def test_metering_passes_its_feature_to_the_gate(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr("app.services.trial_budget.check_async", check)
    monkeypatch.setattr(metering, "flush_async", AsyncMock())
    async with metering.metered_async("certification_chat", user_id="u-1"):
        pass
    check.assert_awaited_once_with("u-1", "certification_chat")


# ---------------------------------------------------------------------------
# A chat turn that runs a certification tool is metered as certification
# ---------------------------------------------------------------------------


async def test_a_turn_that_runs_a_certification_tool_is_certification():
    from app.services.chat_service import _mark_certification_turn

    conversation = SimpleNamespace(uuid="c-1", is_certification=False, set=AsyncMock())
    scope = SimpleNamespace(feature="chat")
    await _mark_certification_turn(conversation, scope, [
        {"tool_name": "search_documents"}, {"tool_name": "get_certification_progress"},
    ])
    assert scope.feature == "certification_chat"
    conversation.set.assert_awaited_once_with({"is_certification": True})


async def test_an_ordinary_turn_stays_chat():
    from app.services.chat_service import _mark_certification_turn

    conversation = SimpleNamespace(uuid="c-1", is_certification=False, set=AsyncMock())
    scope = SimpleNamespace(feature="chat")
    await _mark_certification_turn(conversation, scope, [{"tool_name": "run_extraction"}])
    assert scope.feature == "chat"
    conversation.set.assert_not_awaited()


# ---------------------------------------------------------------------------
# The chat error says the allowance is spent, so the client can offer a top-up
# ---------------------------------------------------------------------------


def test_an_exhausted_allowance_streams_a_top_up_code():
    from app.services.chat_service import _stream_error_event

    spent = TrialBudgetExceededError(trial_budget.EXCEEDED_MESSAGE)
    assert _stream_error_event(spent, "m")["code"] == "trial_budget_exhausted"
    paused = TrialBudgetExceededError(trial_budget.FLEET_PAUSED_MESSAGE, code="fleet_paused")
    assert "code" not in _stream_error_event(paused, "m")
    assert "Top up" in trial_budget.EXCEEDED_MESSAGE


# ---------------------------------------------------------------------------
# In-app top-up
# ---------------------------------------------------------------------------


def _usage(percent: int, *, verified: bool = True, enabled: bool = True) -> dict:
    return {"enabled": enabled, "budget": 1000, "used": percent * 10, "remaining": 0, "percent": percent, "email_verified": verified}


@pytest.mark.parametrize(
    ("usage", "has_app", "reason"),
    [
        (_usage(50), True, "not_low"),
        (_usage(100, verified=False), True, "email_unverified"),
        (_usage(0, enabled=False), True, "not_metered"),
        (_usage(100), False, "no_application"),
    ],
)
async def test_in_app_top_up_is_refused_with_a_reason(monkeypatch, usage, has_app, reason):
    monkeypatch.setattr(trial_budget, "get_trial_usage", AsyncMock(return_value=usage))
    grant = AsyncMock()
    monkeypatch.setattr(demo_service, "_grant_topup", grant)
    apps = fake_model(find_one_result=SimpleNamespace(id="app-1") if has_app else None)
    with patch.object(demo_service, "DemoApplication", apps):
        result = await demo_service.topup_signed_in_trial(_trial_user(), {}, SimpleNamespace(trial_topup_tokens=2000))
    assert result == {"ok": False, "reason": reason}
    grant.assert_not_awaited()


async def test_in_app_top_up_grants_without_email_or_magic_links(monkeypatch):
    monkeypatch.setattr(trial_budget, "get_trial_usage", AsyncMock(return_value=_usage(100)))
    app = SimpleNamespace(
        id="app-1", user_id="u-1", name="Learner", email="learner@test.com", status="exhausted",
        expires_at=None, expired_at=None, trial_extensions_used=0, post_questionnaire_token="old",
        budget_warning_sent=True, activation_email_failed=True, recapture_step=2, recapture_next_at=None,
        save=AsyncMock(),
    )
    send_email = AsyncMock()
    magic = AsyncMock()
    feedback = MagicMock()
    feedback.return_value.insert = AsyncMock()
    monkeypatch.setattr(demo_service, "send_email", send_email)
    monkeypatch.setattr(demo_service, "_create_magic_login_token", magic)
    monkeypatch.setattr(demo_service, "grant_tokens", AsyncMock(return_value=3000))
    monkeypatch.setattr(demo_service, "PostExperienceResponse", feedback)
    with patch.object(demo_service, "DemoApplication", fake_model(find_one_result=app)), \
         patch.object(demo_service, "User", fake_model(find_one_result=_trial_user())):
        result = await demo_service.topup_signed_in_trial(
            _trial_user(), {"what_worked": "the lessons"}, SimpleNamespace(trial_topup_tokens=2000, frontend_url="x"),
        )
    assert result["ok"] is True and result["tokens_budget"] == 3000
    send_email.assert_not_awaited()
    magic.assert_not_awaited()
    assert feedback.call_args.kwargs["responses"]["source"] == "in_app"
    assert app.post_questionnaire_token != "old"  # the emailed link can't be used again
