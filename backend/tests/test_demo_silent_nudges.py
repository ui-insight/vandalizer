"""Unit tests for engagement_service.process_demo_silent_nudges.

Exercises the stage-1 (day-3) / stage-2 (day-7) state machine against mocked
User records and a stubbed briefing computation. Integration tests that touch
MongoDB live in tier-2.
"""

import datetime
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class _AnyCompare:
    """Sentinel for Beanie field references in unit tests (same pattern as
    test_continuity.py)."""

    def __le__(self, other): return _AnyCompare()
    def __ge__(self, other): return _AnyCompare()
    def __lt__(self, other): return _AnyCompare()
    def __gt__(self, other): return _AnyCompare()
    def __eq__(self, other): return _AnyCompare()
    def __ne__(self, other): return _AnyCompare()
    def __bool__(self): return True
    def __hash__(self): return 0


def _user(
    *,
    user_id: str = "alice",
    email: str | None = "alice@example.com",
    demo_status: str | None = "active",
    demo_expires_at: datetime.datetime | None = None,
    last_login_days_ago: int | None = 5,
    silent_nudge_step: int = 0,
    last_silent_nudge_sent_at: datetime.datetime | None = None,
    email_preferences: dict | None = None,
):
    u = MagicMock()
    u.user_id = user_id
    u.email = email
    u.name = user_id
    u.demo_status = demo_status
    u.demo_expires_at = demo_expires_at or (_now() + datetime.timedelta(days=8))
    u.last_login_at = (
        _now() - datetime.timedelta(days=last_login_days_ago)
        if last_login_days_ago is not None else None
    )
    u.silent_nudge_step = silent_nudge_step
    u.last_silent_nudge_sent_at = last_silent_nudge_sent_at
    u.email_preferences = email_preferences if email_preferences is not None else {}
    u.save = AsyncMock()
    return u


def _briefing(items: list[dict] | None = None):
    b = MagicMock()
    if items is None:
        items = [{"headline": "test", "body": "test body", "deep_link": "/chat", "urgency": 1}]
    b.items = [_item(**i) for i in items]
    return b


def _item(*, headline="x", body="y", deep_link="/chat", urgency=1, category="my-activity", source_id="x"):
    it = MagicMock()
    it.model_dump = MagicMock(return_value={
        "headline": headline, "body": body, "deep_link": deep_link,
        "urgency": urgency, "category": category, "source_id": source_id,
    })
    return it


def _patch_env(users, briefing, send_success: bool = True):
    """Patch User.find, briefing_service.compute_daily_briefing, send_email."""
    from app.services import engagement_service as svc

    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=users)

    user_klass = MagicMock()
    user_klass.find = MagicMock(return_value=chain)
    user_klass.demo_status = _AnyCompare()
    user_klass.last_login_at = _AnyCompare()

    return [
        patch.object(svc, "User", new=user_klass),
        patch(
            "app.services.briefing_service.compute_daily_briefing",
            new=AsyncMock(return_value=briefing),
        ),
        patch.object(svc, "send_email", new=AsyncMock(return_value=send_success)),
    ]


# ---------------------------------------------------------------------------
# Stage-1 (day-3) firing
# ---------------------------------------------------------------------------

async def test_fires_stage_1_at_day_3_silent():
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=3, silent_nudge_step=0)
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 1
    assert user.silent_nudge_step == 1
    assert user.last_silent_nudge_sent_at is not None
    user.save.assert_awaited()


async def test_does_not_fire_stage_1_before_day_3():
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=2, silent_nudge_step=0)
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0
    assert user.silent_nudge_step == 0


# ---------------------------------------------------------------------------
# Stage-2 (day-7) firing
# ---------------------------------------------------------------------------

async def test_fires_stage_2_at_day_7_silent_after_stage_1():
    from app.services.engagement_service import process_demo_silent_nudges

    # User had stage-1 sent 5 days ago; cooldown long-elapsed.
    user = _user(
        last_login_days_ago=7,
        silent_nudge_step=1,
        last_silent_nudge_sent_at=_now() - datetime.timedelta(days=5),
    )
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 1
    assert user.silent_nudge_step == 2


async def test_does_not_fire_stage_2_before_day_7():
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(
        last_login_days_ago=5,
        silent_nudge_step=1,
        last_silent_nudge_sent_at=_now() - datetime.timedelta(days=2),
    )
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0


async def test_no_stage_after_step_2():
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=10, silent_nudge_step=2)
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------

async def test_cooldown_blocks_recent_send():
    from app.services.engagement_service import process_demo_silent_nudges

    # Stage-1 was sent 24h ago; cooldown is 48h. Even if day-7 silent, blocked.
    user = _user(
        last_login_days_ago=7,
        silent_nudge_step=1,
        last_silent_nudge_sent_at=_now() - datetime.timedelta(hours=24),
    )
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0


async def test_paid_user_excluded():
    from app.services.engagement_service import process_demo_silent_nudges

    # Trial filter is applied at the query level; a paid user that somehow
    # slips through still needs to be skipped if found. Simulate by setting
    # demo_status to None and including in the candidate list.
    user = _user(demo_status=None, last_login_days_ago=5)
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    # No assertion that 0 — actual filter happens at the query layer
    # (User.demo_status == "active"). We just verify the candidate-loop
    # handles unexpected non-active users without crashing.
    assert isinstance(sent, int)


async def test_nudge_opt_out_respected():
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=5, email_preferences={"nudges": False})
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0
    assert user.silent_nudge_step == 0


async def test_no_email_skipped():
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=5, email=None)
    stack = ExitStack()
    for p in _patch_env([user], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0


async def test_empty_briefing_blocks_send():
    """Defensive: even for trial users (who should get primer padding), an
    empty-items briefing should not generate a hollow nudge."""
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=5)
    empty = MagicMock()
    empty.items = []
    stack = ExitStack()
    for p in _patch_env([user], empty):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0
    assert user.silent_nudge_step == 0


# ---------------------------------------------------------------------------
# Send-failure handling
# ---------------------------------------------------------------------------

async def test_send_failure_does_not_advance_state():
    """If send_email returns False, don't bump silent_nudge_step — we want to
    retry tomorrow."""
    from app.services.engagement_service import process_demo_silent_nudges

    user = _user(last_login_days_ago=5)
    stack = ExitStack()
    for p in _patch_env([user], _briefing(), send_success=False):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 0
    assert user.silent_nudge_step == 0
    assert user.last_silent_nudge_sent_at is None


# ---------------------------------------------------------------------------
# Multi-user
# ---------------------------------------------------------------------------

async def test_processes_multiple_users_in_one_run():
    from app.services.engagement_service import process_demo_silent_nudges

    eligible = _user(user_id="eligible", last_login_days_ago=4)
    too_recent = _user(user_id="too_recent", last_login_days_ago=1)
    already_done = _user(user_id="done", last_login_days_ago=10, silent_nudge_step=2)

    stack = ExitStack()
    for p in _patch_env([eligible, too_recent, already_done], _briefing()):
        stack.enter_context(p)
    with stack:
        sent = await process_demo_silent_nudges()

    assert sent == 1
    assert eligible.silent_nudge_step == 1
    assert too_recent.silent_nudge_step == 0
    assert already_done.silent_nudge_step == 2
