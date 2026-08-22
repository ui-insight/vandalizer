"""Hard LLM spend cap for trial accounts.

A public trial deployment lets self-served signups trigger real LLM spend on
the deployment's API keys, so trial users (``User.is_demo_user``) carry a
lifetime token budget (``TRIAL_TOKEN_BUDGET``). The check runs at
metering-scope entry (``metering.metered`` / ``metered_async``) — the one
chokepoint every attributed LLM operation passes through, in both the API
process and Celery workers — and raises ``TrialBudgetExceededError`` before an
operation's first model request once the ``llm_usage`` ledger total crosses
the budget.

Cost posture: on deployments without the trial system enabled the check is a
cached settings read and returns immediately. The budget only ever gates
``is_demo_user`` accounts. The check fails open on its own errors — a
metering-side failure must never take down LLM features — but the
budget-exceeded signal itself always propagates.
"""

from __future__ import annotations

import logging

from app.exceptions import TrialBudgetExceededError

logger = logging.getLogger(__name__)

EXCEEDED_MESSAGE = (
    "This trial account has reached its included AI usage limit. "
    "If you'd like to keep exploring, contact the team running this "
    "deployment about extending it."
)

_USAGE_PIPELINE = [{"$group": {"_id": None, "total": {"$sum": "$total_tokens"}}}]


def _budget() -> int:
    """The enforced per-trial-user token budget, or 0 when not enforced."""
    from app.dependencies import get_settings

    settings = get_settings()
    if not settings.enable_trial_system:
        return 0
    return max(0, settings.trial_token_budget)


async def tokens_used_async(user_id: str) -> int:
    from app.models.llm_usage import LlmUsageRecord

    rows = (
        await LlmUsageRecord.find(LlmUsageRecord.user_id == user_id)
        .aggregate(_USAGE_PIPELINE)
        .to_list()
    )
    return int(rows[0]["total"]) if rows else 0


async def check_async(user_id: str | None) -> None:
    """Raise TrialBudgetExceededError if `user_id` is an over-budget trial user."""
    budget = _budget()
    if not budget or not user_id:
        return
    try:
        from app.models.user import User

        user = await User.find_one(User.user_id == user_id)
        if user is None or not user.is_demo_user:
            return
        used = await tokens_used_async(user_id)
    except Exception as e:
        logger.error("Trial budget check failed for %s: %s", user_id, e)
        return
    if used >= budget:
        raise TrialBudgetExceededError(EXCEEDED_MESSAGE)


def check_sync(user_id: str | None) -> None:
    """Sync twin of check_async, for Celery-side metering scopes."""
    budget = _budget()
    if not budget or not user_id:
        return
    try:
        from app.tasks import get_sync_db

        db = get_sync_db()
        user = db.user.find_one({"user_id": user_id}, {"is_demo_user": 1})
        if not user or not user.get("is_demo_user"):
            return
        rows = list(
            db.llm_usage.aggregate(
                [{"$match": {"user_id": user_id}}, *_USAGE_PIPELINE]
            )
        )
        used = int(rows[0]["total"]) if rows else 0
    except Exception as e:
        logger.error("Trial budget check failed for %s: %s", user_id, e)
        return
    if used >= budget:
        raise TrialBudgetExceededError(EXCEEDED_MESSAGE)
