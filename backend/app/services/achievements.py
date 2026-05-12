"""First-time milestone acknowledgments awarded at the events that earn them.

Achievements are *acknowledgments of real work* — not points, not scores, not
levels. They surface in the next morning's briefing under the `achievement`
category, once each. Copy is factual and editorial; this file's `_MILESTONES`
table is the canonical source.

Two award patterns:
- Discrete: a specific event fires (first extraction, first workflow). Call
  `award_if_not_held(user_id, milestone_id)` at the site.
- Threshold: a cumulative counter crosses a boundary (time saved >= 60 min).
  Call `check_time_saved_thresholds(user_id, new_total)` after the counter
  is updated. Idempotent — same threshold can't fire twice.

Surfaces only in the briefing for now (no bell notification). Adding the bell
later would be one additional `create_notification` call inside the award
function — deferred until we see whether briefing-only is enough.
"""

from typing import Iterable, Optional

from app.models.user import User


# Each milestone: stable id -> display copy. Tone is factual, no exclamation
# points (per audience-mechanics feedback — research administrators on workday
# tasks find game mechanics patronizing).
_MILESTONES: dict[str, dict] = {
    "first_extraction": {
        "headline": "Your first extraction landed",
        "body": "Structured data pulled from a real document with a visible quality score. This is the difference from copy-pasting into a chatbot.",
        "deep_link": "/activity",
    },
    "first_workflow": {
        "headline": "Your first workflow finished",
        "body": "A reusable pipeline now runs on demand. Reuse it on a folder of documents or hand it to a teammate.",
        "deep_link": "/activity",
    },
    "time_saved_60": {
        "headline": "You've crossed an hour saved",
        "body": "Estimated from your extractions, workflows, and chat queries. The number is conservative — see the badge tooltip for methodology.",
        "deep_link": None,
    },
    "time_saved_300": {
        "headline": "5 hours saved",
        "body": "You're past the point where most trial users have decided this tool is part of their work.",
        "deep_link": None,
    },
}


# Threshold milestones: maps minutes-threshold to milestone_id.
# Order doesn't matter; each is checked independently.
_TIME_SAVED_THRESHOLDS: dict[int, str] = {
    60: "time_saved_60",
    300: "time_saved_300",
}


def milestone_def(milestone_id: str) -> Optional[dict]:
    """Return the display copy for a milestone, or None if unknown."""
    return _MILESTONES.get(milestone_id)


def known_milestone_ids() -> Iterable[str]:
    return _MILESTONES.keys()


async def award_if_not_held(user_id: str, milestone_id: str) -> bool:
    """Award a milestone to a user if they don't already hold it.

    Returns True on first award, False if already held or unknown milestone.
    Idempotent: safe to call from any number of hook sites.
    """
    if not user_id or user_id == "system":
        return False
    if milestone_id not in _MILESTONES:
        return False

    user = await User.find_one(User.user_id == user_id)
    if not user:
        return False

    held = user.achievements_unlocked or []
    if milestone_id in held:
        return False

    user.achievements_unlocked = held + [milestone_id]
    await user.save()
    return True


async def check_time_saved_thresholds(user_id: str, new_total_minutes: int) -> list[str]:
    """Award any threshold milestones the user has just crossed.

    Returns the list of milestone IDs newly awarded (may be empty).
    Safe to call after every `accrue_time_saved` increment — idempotent
    because award_if_not_held is.
    """
    awarded: list[str] = []
    for threshold, milestone_id in _TIME_SAVED_THRESHOLDS.items():
        if new_total_minutes >= threshold:
            if await award_if_not_held(user_id, milestone_id):
                awarded.append(milestone_id)
    return awarded


def check_time_saved_thresholds_sync(db, user_id: str, new_total_minutes: int) -> list[str]:
    """Sync (pymongo) variant for Celery-task hooks.

    Atomically appends each newly-crossed milestone via `$addToSet` so concurrent
    workers can't double-award.
    """
    if not user_id or user_id == "system":
        return []
    awarded: list[str] = []
    for threshold, milestone_id in _TIME_SAVED_THRESHOLDS.items():
        if new_total_minutes >= threshold:
            result = db.user.update_one(
                {"user_id": user_id, "achievements_unlocked": {"$ne": milestone_id}},
                {"$push": {"achievements_unlocked": milestone_id}},
            )
            if result.modified_count:
                awarded.append(milestone_id)
    return awarded
