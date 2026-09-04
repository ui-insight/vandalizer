"""Hard LLM spend cap for trial accounts — the trial IS the budget.

Trial accounts are token-metered, not time-limited: each ``is_demo_user``
carries a lifetime token budget (``User.trial_token_budget``, defaulting to
``TRIAL_TOKEN_BUDGET``, raised by feedback-priced top-ups). The check runs at
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

import datetime
import logging

from app.exceptions import (
    TrialBudgetExceededError,
    TrialSpendBlockedError,
    TrialUnverifiedError,
)

logger = logging.getLogger(__name__)

EXCEEDED_MESSAGE = (
    "This trial account has used all of its included AI tokens. "
    "A top-up link is on its way to your email — one click (and a little "
    "feedback) brings you right back."
)

UNVERIFIED_MESSAGE = (
    "Please confirm your email address before using AI features — click the "
    "sign-in link we emailed you. Need a new one? Request it from the trial "
    "status page."
)

FLEET_PAUSED_MESSAGE = (
    "Trial AI usage is paused for the moment while we top up capacity. "
    "Your workspace and everything in it are unaffected — please try again "
    "later, or contact the team running this deployment."
)

_USAGE_PIPELINE = [{"$group": {"_id": None, "total": {"$sum": "$total_tokens"}}}]

#: Redis key holding "1" while fleet-wide trial spend is over the monthly
#: ceiling. Written by the hourly sweep, read on the hot path. Carries a TTL so
#: a stopped sweep fails *open* rather than pausing trials forever.
FLEET_PAUSED_KEY = "trial:fleet_paused"
FLEET_PAUSED_TTL_SECONDS = 3 * 60 * 60


def _trial_system_on() -> bool:
    """Whether this deployment runs trials at all.

    The master switch. Every trial gate is off when this is False; no gate is
    off merely because a *different* gate was turned off.
    """
    from app.dependencies import get_settings

    return bool(get_settings().enable_trial_system)


def _budget() -> int:
    """The deployment-default per-account token budget, 0 when uncapped.

    0 means "don't cap individual accounts" and nothing more. It deliberately
    does not disable email verification or the fleet ceiling — an operator
    lifting the per-person limit is not asking to stop verifying addresses or
    to uncap the monthly bill.
    """
    from app.dependencies import get_settings

    settings = get_settings()
    if not settings.enable_trial_system:
        return 0
    return max(0, settings.trial_token_budget)


def effective_budget(user_override: int | None) -> int:
    """A trial user's budget: their per-user value (raised by top-ups) when
    set, else the deployment default. 0 = the cap is not enforced at all."""
    default = _budget()
    if not default:
        return 0
    if user_override is None:
        return default
    return max(0, user_override)


def month_start(now: datetime.datetime | None = None) -> datetime.datetime:
    """First instant of the current UTC calendar month."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def fleet_tokens_this_month() -> int:
    """Trial-attributed tokens spent fleet-wide since the start of the month."""
    from app.models.llm_usage import LlmUsageRecord
    from app.models.user import User

    trial_ids = [
        u.user_id
        for u in await User.find(
            User.is_demo_user == True  # noqa: E712 — Beanie query expression
        ).to_list()
    ]
    if not trial_ids:
        return 0
    rows = (
        await LlmUsageRecord.find(
            {
                "user_id": {"$in": trial_ids},
                "timestamp": {"$gte": month_start()},
            }
        )
        .aggregate(_USAGE_PIPELINE)
        .to_list()
    )
    return int(rows[0]["total"]) if rows else 0


async def refresh_fleet_pause(settings=None) -> dict:
    """Recompute the fleet ceiling and set/clear the Redis pause flag.

    Called by the hourly trial sweep. The flag is what the hot path reads, so
    an overrun is caught within an hour — bounded by the per-account budgets
    that are still enforced exactly in the meantime.
    """
    import redis.asyncio as aioredis

    from app.config import Settings

    settings = settings or Settings()
    ceiling = max(0, settings.trial_global_monthly_tokens)
    if not settings.enable_trial_system or not ceiling:
        return {"enabled": False, "spent": 0, "ceiling": 0, "paused": False}

    spent = await fleet_tokens_this_month()
    paused = spent >= ceiling
    try:
        r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
        try:
            if paused:
                await r.set(FLEET_PAUSED_KEY, "1", ex=FLEET_PAUSED_TTL_SECONDS)
            else:
                await r.delete(FLEET_PAUSED_KEY)
        finally:
            await r.aclose()
    except Exception as e:  # never let the flag write break the sweep
        logger.error("Failed to update trial fleet pause flag: %s", e)

    if paused:
        logger.warning(
            "Trial fleet ceiling reached: %s/%s tokens this month — new trial "
            "spend is paused until the ceiling is raised or the month rolls.",
            spent, ceiling,
        )
    return {"enabled": True, "spent": spent, "ceiling": ceiling, "paused": paused}


async def _fleet_paused_async() -> bool:
    """Read the cached fleet-pause flag. Fails open on any Redis trouble."""
    import redis.asyncio as aioredis

    from app.dependencies import get_settings

    settings = get_settings()
    if not max(0, settings.trial_global_monthly_tokens):
        return False
    try:
        r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
        try:
            return await r.get(FLEET_PAUSED_KEY) is not None
        finally:
            await r.aclose()
    except Exception as e:
        logger.error("Failed to read trial fleet pause flag: %s", e)
        return False


def _fleet_paused_sync() -> bool:
    """Sync twin of _fleet_paused_async, for Celery-side metering scopes."""
    import redis

    from app.dependencies import get_settings

    settings = get_settings()
    if not max(0, settings.trial_global_monthly_tokens):
        return False
    try:
        client = redis.Redis(host=settings.redis_host, port=6379)
        try:
            return client.get(FLEET_PAUSED_KEY) is not None
        finally:
            client.close()
    except Exception as e:
        logger.error("Failed to read trial fleet pause flag: %s", e)
        return False


async def tokens_used_async(user_id: str) -> int:
    from app.models.llm_usage import LlmUsageRecord

    rows = (
        await LlmUsageRecord.find(LlmUsageRecord.user_id == user_id)
        .aggregate(_USAGE_PIPELINE)
        .to_list()
    )
    return int(rows[0]["total"]) if rows else 0


async def get_trial_usage(user) -> dict:
    """Budget/usage snapshot for one trial user — the shape the meter, the
    lifecycle emails, and the trial-end screen all read.

    ``enabled`` is False for non-trial users and cap-disabled deployments;
    the other numbers are zeroed then and must not be rendered.
    """
    def _off(email_verified: bool = True) -> dict:
        return {
            "enabled": False, "budget": 0, "used": 0, "remaining": 0,
            "percent": 0, "email_verified": email_verified,
        }

    if not getattr(user, "is_demo_user", False):
        return _off()
    # Report verification honestly even when there's no meter to draw —
    # an uncapped deployment still gates AI on it, and a banner that stays
    # hidden would leave that gate silent.
    verified = bool(getattr(user, "email_verified", False))
    budget = effective_budget(getattr(user, "trial_token_budget", None))
    if not budget:
        return _off(verified)
    used = await tokens_used_async(user.user_id)
    return {
        "enabled": True,
        "budget": budget,
        "used": used,
        "remaining": max(0, budget - used),
        "percent": min(100, round(used * 100 / budget)),
        "email_verified": bool(getattr(user, "email_verified", False)),
    }


async def check_async(user_id: str | None) -> None:
    """Gate LLM spend for a trial user: verified, under budget, fleet not paused.

    Raises TrialUnverifiedError or TrialBudgetExceededError. Non-trial users
    and deployments with the trial system off return immediately.

    The three gates are independent: turning off the per-account cap
    (``TRIAL_TOKEN_BUDGET=0``) leaves verification and the fleet ceiling in
    force, because they answer different questions.
    """
    if not _trial_system_on() or not user_id:
        return
    try:
        from app.models.user import User

        user = await User.find_one(User.user_id == user_id)
        if user is None or not user.is_demo_user:
            return
        # An unverified address can't receive the top-up link, and is what
        # makes one person into unlimited free accounts. Check it first: it's
        # the cheaper answer and the more actionable message.
        if not user.email_verified:
            raise TrialUnverifiedError(UNVERIFIED_MESSAGE)
        budget = effective_budget(user.trial_token_budget)
        # An uncapped account still counts against the fleet ceiling.
        used = await tokens_used_async(user_id) if budget else 0
        over_budget = bool(budget) and used >= budget
        fleet_paused = False if over_budget else await _fleet_paused_async()
    except TrialSpendBlockedError:
        raise
    except Exception as e:
        logger.error("Trial budget check failed for %s: %s", user_id, e)
        return
    if over_budget:
        raise TrialBudgetExceededError(EXCEEDED_MESSAGE)
    if fleet_paused:
        raise TrialBudgetExceededError(FLEET_PAUSED_MESSAGE)


def check_sync(user_id: str | None, *, extra_used: int = 0) -> None:
    """Sync twin of check_async, for Celery-side metering scopes.

    ``extra_used`` is spend that has happened but is not in the ledger yet.
    The ledger row for a scope is written by ``metering.flush_sync`` when the
    scope EXITS, so a long multi-step run's own tokens are invisible to this
    query while it is still running — a between-steps gate that re-read the
    ledger alone would see the same total at every boundary and never trip
    (#808). Callers polling mid-run pass the live scope's tokens here.
    """
    if not _trial_system_on() or not user_id:
        return
    try:
        from app.tasks import get_sync_db

        db = get_sync_db()
        user = db.user.find_one(
            {"user_id": user_id},
            {"is_demo_user": 1, "trial_token_budget": 1, "email_verified": 1},
        )
        if not user or not user.get("is_demo_user"):
            return
        if not user.get("email_verified"):
            raise TrialUnverifiedError(UNVERIFIED_MESSAGE)
        budget = effective_budget(user.get("trial_token_budget"))
        used = 0
        if budget:
            rows = list(
                db.llm_usage.aggregate(
                    [{"$match": {"user_id": user_id}}, *_USAGE_PIPELINE]
                )
            )
            used = int(rows[0]["total"]) if rows else 0
            used += max(0, int(extra_used or 0))
        over_budget = bool(budget) and used >= budget
        fleet_paused = False if over_budget else _fleet_paused_sync()
    except TrialSpendBlockedError:
        raise
    except Exception as e:
        logger.error("Trial budget check failed for %s: %s", user_id, e)
        return
    if over_budget:
        raise TrialBudgetExceededError(EXCEEDED_MESSAGE)
    if fleet_paused:
        raise TrialBudgetExceededError(FLEET_PAUSED_MESSAGE)
