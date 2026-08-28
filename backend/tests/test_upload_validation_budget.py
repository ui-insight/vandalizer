"""Upload compliance validation on an exhausted trial budget.

The chunk and summary tasks are attributed to the uploader so trial spend is
metered. When the budget is gone the check must degrade to "not checked" —
never a retry storm that leaves the document stuck in ``validating``.
"""

from unittest.mock import MagicMock, patch

from app.exceptions import TrialBudgetExceededError
from app.tasks import upload_validation_tasks as uv


def _budget_exhausted(user_id):
    raise TrialBudgetExceededError("nope")


def test_validate_chunk_marks_skipped_when_budget_exhausted():
    agent = MagicMock()
    with patch.object(uv, "_get_secure_agent", return_value=agent), \
         patch("app.services.trial_budget.check_sync", side_effect=_budget_exhausted):
        result = uv.validate_chunk.apply(
            args=("doc.pdf", "rules", "text", 1, 2), kwargs={"user_id": "trial-u"},
        ).get()

    assert result["skipped"] is True
    assert result["valid"] is True
    assert result["index"] == 1
    agent.run_sync.assert_not_called()


def test_validate_chunk_without_user_is_not_budget_checked():
    agent = MagicMock()
    agent.run_sync.return_value = MagicMock(output='{"valid": true, "feedback": "fine"}')
    with patch.object(uv, "_get_secure_agent", return_value=agent), \
         patch("app.services.trial_budget.check_sync", side_effect=_budget_exhausted) as chk, \
         patch("app.services.metering.flush_sync"):
        result = uv.validate_chunk.apply(args=("doc.pdf", "rules", "text", 1, 1)).get()

    chk.assert_not_called()
    assert result == {"valid": True, "feedback": "fine", "index": 1}


def test_summarize_reports_skipped_sections_without_spending_more():
    db = MagicMock()
    agent = MagicMock()
    results = [
        {"valid": True, "feedback": "ok", "index": 1},
        {"valid": True, "feedback": uv.BUDGET_SKIPPED_FEEDBACK, "index": 2, "skipped": True},
    ]
    with patch.object(uv, "_get_db", return_value=db), \
         patch.object(uv, "_get_secure_agent", return_value=agent):
        summary = uv.summarize_results.apply(
            args=(results, "doc-uuid", True), kwargs={"user_id": "trial-u"},
        ).get()

    agent.run_sync.assert_not_called()
    assert summary["valid"] is True
    assert "1 of 2 sections were not checked" in summary["feedback"]
    written = db.smart_document.update_one.call_args.args[1]["$set"]
    assert written["validating"] is False
    assert "not checked" in written["validation_feedback"]


# ---------------------------------------------------------------------------
# Any trial gate degrades the same way, not just an exhausted budget
# ---------------------------------------------------------------------------


def _unverified(user_id):
    from app.exceptions import TrialUnverifiedError

    raise TrialUnverifiedError("confirm your email")


def test_validate_chunk_marks_skipped_when_email_unverified():
    """An unverified trial user's first upload must not strand the document.

    `validate_chunk` used to catch only TrialBudgetExceededError. Adding the
    verification gate as a sibling exception meant it escaped to the task's
    retry path, the chord never fired its callback, and the document sat at
    `validating: True` forever — for every new trial user before they clicked
    the confirmation link. Both gates now share TrialSpendBlockedError.
    """
    agent = MagicMock()
    with patch.object(uv, "_get_secure_agent", return_value=agent), \
         patch("app.services.trial_budget.check_sync", side_effect=_unverified):
        result = uv.validate_chunk.apply(
            args=("doc.pdf", "rules", "text", 1, 2), kwargs={"user_id": "trial-u"},
        ).get()

    assert result["skipped"] is True
    assert result["valid"] is True
    # The feedback names the gate that actually fired, not "budget exhausted".
    assert "confirm your email" in result["feedback"].lower()
    agent.run_sync.assert_not_called()


def test_every_trial_gate_shares_one_base():
    """The degradation contract is the base class, so a future gate is covered
    without revisiting each catch site."""
    from app.exceptions import (
        TrialBudgetExceededError,
        TrialSpendBlockedError,
        TrialUnverifiedError,
    )

    assert issubclass(TrialBudgetExceededError, TrialSpendBlockedError)
    assert issubclass(TrialUnverifiedError, TrialSpendBlockedError)
