"""Module 10 (Collaboration & Governance) grading.

Regression coverage for the bug where the final module could only be passed
once an admin/examiner approved the user's workflow — every certifying user was
blocked on a person, and submissions arrived unannounced. Passing is now gated
on submitting for verification; approval only adds stars.

The model symbols are patched wholesale so the validator can run without an
initialized Beanie connection.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import certification_service as cs


def _query(items):
    """Mimic a Beanie query: an object with an async `.to_list()`."""
    q = MagicMock()
    q.to_list = AsyncMock(return_value=items)
    return q


def _model(items):
    """Stand in for a Beanie model class: `.find(...)` returns a query."""
    m = MagicMock()
    m.find.return_value = _query(items)
    return m


def _request(status="submitted"):
    return SimpleNamespace(item_kind="workflow", submitter_user_id="alice", status=status)


async def _run(workflows, requests):
    with patch.object(cs, "Workflow", _model(workflows)), \
         patch.object(cs, "VerificationRequest", _model(requests)):
        return await cs._validate_governance("alice")


async def test_fails_with_no_submission():
    out = await _run([SimpleNamespace(verified=False)], [])
    assert out["passed"] is False
    assert out["stars"] == 0


async def test_passes_on_submission_without_approval():
    out = await _run([SimpleNamespace(verified=False)], [_request("submitted")])
    assert out["passed"] is True
    assert out["stars"] == 1
    assert "approval is not required" in out["checks"][0]["detail"]


async def test_passes_while_in_review():
    out = await _run([SimpleNamespace(verified=False)], [_request("in_review")])
    assert out["passed"] is True


async def test_approval_earns_the_second_star():
    out = await _run([SimpleNamespace(verified=True)], [_request("approved")])
    assert out["passed"] is True
    assert out["stars"] == 2


async def test_two_approvals_earn_the_third_star():
    out = await _run(
        [SimpleNamespace(verified=True), SimpleNamespace(verified=True)],
        [_request("approved"), _request("approved")],
    )
    assert out["stars"] == 3


async def test_preexisting_verified_workflows_still_count_for_stars():
    """Verified before the queue existed (or seeded) — no request record."""
    out = await _run(
        [SimpleNamespace(verified=True), SimpleNamespace(verified=True)],
        [_request("submitted")],
    )
    assert out["passed"] is True
    assert out["stars"] == 3
