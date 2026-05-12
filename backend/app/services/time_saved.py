"""Time-saved counter: per-event minutes-saved accrual on User.

Each value-generating event adds a calibrated minutes-saved estimate to
`User.time_saved_minutes_total`. Powers the workspace header badge and
(in Sprint 4) the day-12 trial recap card's conversion narrative.

Calibration is an educated guess, not a measured fact. The numbers are
conservative enough that totals should never feel implausibly large, and
isolated in `_MINUTES_BY_EVENT_TYPE` so future re-calibration is a
one-line change.

Two helpers — `accrue_time_saved` (async, Beanie) and `accrue_time_saved_sync`
(sync, pymongo) — because activity-completion paths in this codebase split
between async routers/services and sync Celery tasks.
"""

from app.models.user import User


# Calibrated minutes-saved per event type. Conservative estimates;
# multipliers (by doc count, step count, etc.) deliberately omitted to
# avoid false precision.
_MINUTES_BY_EVENT_TYPE: dict[str, int] = {
    "workflow_run": 15,    # average end-to-end workflow run on a real document
    "extraction": 6,       # single extraction over a document
    "search_set_run": 5,   # saved search firing over documents
    "chat_message": 1,     # single chat-message exchange (RAG'd answer)
}


def minutes_for(event_type: str) -> int:
    """Return the calibrated minutes for an event type, or 0 if unknown."""
    return _MINUTES_BY_EVENT_TYPE.get(event_type, 0)


async def accrue_time_saved(user_id: str, event_type: str) -> int:
    """Increment User.time_saved_minutes_total by the calibrated amount.

    Returns the minutes credited. No-op if event_type is unknown or user_id
    is empty/system — caller doesn't need to guard against this.
    """
    if not user_id or user_id == "system":
        return 0
    minutes = minutes_for(event_type)
    if not minutes:
        return 0

    user = await User.find_one(User.user_id == user_id)
    if not user:
        return 0
    new_total = (user.time_saved_minutes_total or 0) + minutes
    user.time_saved_minutes_total = new_total
    await user.save()

    # Award any threshold milestones the user just crossed. Best-effort —
    # achievement failure must not roll back the accrual.
    try:
        from app.services.achievements import check_time_saved_thresholds

        await check_time_saved_thresholds(user_id, new_total)
    except Exception:
        pass

    return minutes


def accrue_time_saved_sync(db, user_id: str, event_type: str) -> int:
    """Sync (pymongo) variant for Celery-task completion paths.

    Same contract as `accrue_time_saved` but uses an atomic `$inc` so concurrent
    workers can't race on the read-modify-write.
    """
    if not user_id or user_id == "system":
        return 0
    minutes = minutes_for(event_type)
    if not minutes:
        return 0
    db.user.update_one(
        {"user_id": user_id},
        {"$inc": {"time_saved_minutes_total": minutes}},
    )
    # Read back the post-$inc total to check threshold milestones. Best-effort —
    # achievement failure must not surface as a workflow-task failure.
    try:
        from app.services.achievements import check_time_saved_thresholds_sync

        fresh = db.user.find_one({"user_id": user_id}, {"time_saved_minutes_total": 1})
        new_total = (fresh or {}).get("time_saved_minutes_total", 0) or 0
        check_time_saved_thresholds_sync(db, user_id, new_total)
    except Exception:
        pass

    return minutes


def format_duration(minutes: int) -> str:
    """Render a minutes count as a compact label, e.g. "4h 7m" or "47m"."""
    if minutes is None or minutes <= 0:
        return "0m"
    hours, mins = divmod(int(minutes), 60)
    if hours == 0:
        return f"{mins}m"
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"
