"""Completing a certification module from chat needs the learner's approval.

Support ticket: a learner gave Module 3's four reflection answers, and chat's
first action was "Completing certification module" — before the answers were
saved, and without the learner asking. Completion awards course credit, so it
now goes through the same preview→approve handshake as other writes, and the
approval card appears only once the module's check passes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_tools
from app.services.chat_tools import complete_certification_module

PASSING = {"passed": True, "stars": 2, "checks": [{"name": "answers", "passed": True, "detail": ""}]}
FAILING = {"passed": False, "stars": 0, "checks": [{"name": "answers", "passed": False, "detail": "No saved answers"}]}
COMPLETION = {
    "module_id": "foundations", "stars": 2, "xp_earned": 100, "total_xp": 250,
    "level": "builder", "level_up": True, "certified": False,
}


def _context(turn: int, pending: list | None = None):
    conversation = SimpleNamespace(uuid="conv-1", pending_confirmations=list(pending or []), save=AsyncMock())
    ctx = MagicMock()
    ctx.tool_call_id = f"call-{turn}"
    ctx.deps = SimpleNamespace(user_id="user1", team_id="team1", user=MagicMock(user_id="user1"), conversation=conversation, turn_marker=turn)
    return ctx


@pytest.fixture(autouse=True)
def _new_request():
    """Each call is a new completion request unless a test says otherwise."""
    with patch("app.services.certification_service.completion_recorded", new=AsyncMock(return_value=False)) as recorded:
        yield recorded


def _service(check: dict):
    return (
        patch("app.services.certification_service.validate_module", new=AsyncMock(return_value=check)),
        patch("app.services.certification_service.complete_module", new=AsyncMock(return_value=dict(COMPLETION))),
    )


@pytest.mark.asyncio
async def test_a_module_whose_check_fails_gets_no_approval_card():
    validate, complete = _service(FAILING)
    ctx = _context(turn=4)
    with validate, complete as completed:
        result = await complete_certification_module(ctx, "foundations", confirmed=True)
    assert "isn't ready to complete" in result["error"]
    assert result["validation"]["checks"][0]["detail"] == "No saved answers"
    assert not result.get("needs_confirmation")
    assert ctx.deps.conversation.pending_confirmations == []
    completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_passing_module_asks_for_approval_and_awards_nothing():
    validate, complete = _service(PASSING)
    ctx = _context(turn=4)
    with validate, complete as completed:
        result = await complete_certification_module(ctx, "foundations")
    assert result["needs_confirmation"] is True
    assert result["preview"] == 'Complete "Foundations" and record it on your certification. Its check passes with 2 stars.'
    assert "Complete module" in result["assistant_instruction"]
    completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_cannot_approve_its_own_completion_in_the_same_turn():
    """confirmed=true with no card shown on an earlier turn is still only a card."""
    validate, complete = _service(PASSING)
    with validate, complete as completed:
        result = await complete_certification_module(_context(turn=4), "foundations", confirmed=True, expected_attempts=0)
    assert result["needs_confirmation"] is True
    completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_learners_approval_completes_the_module():
    validate, complete = _service(PASSING)
    with validate, complete as completed:
        preview_ctx = _context(turn=4)
        await complete_certification_module(preview_ctx, "foundations")
        armed = preview_ctx.deps.conversation.pending_confirmations
        result = await complete_certification_module(_context(turn=6, pending=armed), "foundations", confirmed=True, expected_attempts=0)
    completed.assert_awaited_once()
    assert result["xp_earned"] == 100 and result["title"] == "Foundations"


@pytest.mark.asyncio
async def test_a_retry_of_a_recorded_completion_replays_it_without_a_new_check(_new_request):
    """A recorded request returns its original result, even after the answers
    changed: re-checking them first said a completed module "isn't ready"."""
    _new_request.return_value = True
    validate, complete = _service(FAILING)
    with validate as validated, complete as completed:
        result = await complete_certification_module(_context(turn=6), "foundations", request_id="a" * 32)
    validated.assert_not_awaited()
    completed.assert_awaited_once()
    assert completed.await_args.kwargs["request_id"] == "a" * 32
    assert result["xp_earned"] == 100 and not result.get("needs_confirmation")


@pytest.mark.asyncio
async def test_a_live_retry_is_looked_up_by_its_derived_request_identity(_new_request):
    """With no request_id, the identity derived from the turn and tool call is
    the one checked for a recorded completion."""
    validate, complete = _service(PASSING)
    with validate, complete:
        await complete_certification_module(_context(turn=4), "foundations")
    user_id, module_id, request_id = _new_request.await_args.args
    assert (user_id, module_id) == ("user1", "foundations") and len(request_id) == 32


def test_saving_answers_no_longer_tells_chat_to_complete():
    import inspect

    source = inspect.getsource(chat_tools.submit_certification_assessment)
    assert "to bank the XP" not in source
    assert "call complete_certification_module only if they" in source
