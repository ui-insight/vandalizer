"""Unit tests for the time-saved counter.

Covers the accrual helpers (async + sync), the calibration table, format_duration,
and the no-op safety paths (unknown event_type, missing user, system user).
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.time_saved import (
    _MINUTES_BY_EVENT_TYPE,
    accrue_time_saved,
    accrue_time_saved_sync,
    format_duration,
    minutes_for,
)


class _AnyCompare:
    """Sentinel for Beanie field references (same pattern as test_continuity)."""

    def __eq__(self, other): return _AnyCompare()
    def __ne__(self, other): return _AnyCompare()
    def __bool__(self): return True
    def __hash__(self): return 0


def _patch_user(found):
    """Replace User in time_saved with a MagicMock whose find_one returns `found`."""
    klass = MagicMock()
    klass.find_one = AsyncMock(return_value=found)
    klass.user_id = _AnyCompare()
    return patch("app.services.time_saved.User", new=klass)


# ---------------------------------------------------------------------------
# Calibration table
# ---------------------------------------------------------------------------

def test_calibration_table_has_expected_event_types():
    """v0 covers workflow_run, extraction, search_set_run, chat_message."""
    assert "workflow_run" in _MINUTES_BY_EVENT_TYPE
    assert "extraction" in _MINUTES_BY_EVENT_TYPE
    assert "search_set_run" in _MINUTES_BY_EVENT_TYPE
    assert "chat_message" in _MINUTES_BY_EVENT_TYPE


def test_calibration_is_conservative():
    """Sanity: every entry is a positive integer; no implausible values."""
    for event_type, mins in _MINUTES_BY_EVENT_TYPE.items():
        assert isinstance(mins, int), f"{event_type} should be int, got {type(mins)}"
        assert 1 <= mins <= 60, f"{event_type}={mins} feels outside conservative range"


def test_minutes_for_known_event():
    assert minutes_for("workflow_run") == 15
    assert minutes_for("chat_message") == 1


def test_minutes_for_unknown_event_returns_zero():
    assert minutes_for("not_a_real_event") == 0
    assert minutes_for("") == 0


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

def test_format_duration_under_hour():
    assert format_duration(47) == "47m"
    assert format_duration(1) == "1m"


def test_format_duration_exact_hour():
    assert format_duration(60) == "1h"
    assert format_duration(120) == "2h"


def test_format_duration_hours_and_minutes():
    assert format_duration(247) == "4h 7m"
    assert format_duration(75) == "1h 15m"


def test_format_duration_zero_and_negative():
    assert format_duration(0) == "0m"
    assert format_duration(-5) == "0m"
    assert format_duration(None) == "0m"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# accrue_time_saved (async)
# ---------------------------------------------------------------------------

async def test_accrue_increments_user_total():
    user = MagicMock()
    user.user_id = "alice"
    user.time_saved_minutes_total = 100
    user.save = AsyncMock()

    with _patch_user(user):
        credited = await accrue_time_saved("alice", "workflow_run")

    assert credited == 15
    assert user.time_saved_minutes_total == 115
    user.save.assert_awaited()


async def test_accrue_handles_none_starting_total():
    """Defensive: legacy users may have None for time_saved_minutes_total."""
    user = MagicMock()
    user.user_id = "alice"
    user.time_saved_minutes_total = None
    user.save = AsyncMock()

    with _patch_user(user):
        credited = await accrue_time_saved("alice", "extraction")

    assert credited == 6
    assert user.time_saved_minutes_total == 6


async def test_accrue_skips_unknown_event_type():
    user = MagicMock()
    user.save = AsyncMock()

    with _patch_user(user):
        credited = await accrue_time_saved("alice", "imagined_event")

    assert credited == 0
    user.save.assert_not_called()


async def test_accrue_skips_system_user():
    klass = MagicMock()
    klass.find_one = AsyncMock()
    with patch("app.services.time_saved.User", new=klass):
        credited = await accrue_time_saved("system", "workflow_run")

    assert credited == 0
    klass.find_one.assert_not_called()


async def test_accrue_skips_empty_user_id():
    klass = MagicMock()
    klass.find_one = AsyncMock()
    with patch("app.services.time_saved.User", new=klass):
        credited = await accrue_time_saved("", "workflow_run")

    assert credited == 0
    klass.find_one.assert_not_called()


async def test_accrue_skips_missing_user():
    with _patch_user(None):
        credited = await accrue_time_saved("ghost", "workflow_run")

    assert credited == 0


async def test_accrue_multi_event_sums():
    user = MagicMock()
    user.user_id = "alice"
    user.time_saved_minutes_total = 0
    user.save = AsyncMock()

    stack = ExitStack()
    stack.enter_context(_patch_user(user))
    with stack:
        c1 = await accrue_time_saved("alice", "workflow_run")
        c2 = await accrue_time_saved("alice", "extraction")
        c3 = await accrue_time_saved("alice", "chat_message")

    assert c1 == 15
    assert c2 == 6
    assert c3 == 1
    assert user.time_saved_minutes_total == 22


# ---------------------------------------------------------------------------
# accrue_time_saved_sync (pymongo)
# ---------------------------------------------------------------------------

def test_sync_accrue_uses_inc_for_atomicity():
    """Sync helper must use $inc — read-modify-write would race across workers."""
    db = MagicMock()
    credited = accrue_time_saved_sync(db, "alice", "workflow_run")

    assert credited == 15
    db.user.update_one.assert_called_once()
    args, _ = db.user.update_one.call_args
    assert args[0] == {"user_id": "alice"}
    assert args[1] == {"$inc": {"time_saved_minutes_total": 15}}


def test_sync_accrue_skips_unknown_event():
    db = MagicMock()
    credited = accrue_time_saved_sync(db, "alice", "imagined_event")

    assert credited == 0
    db.user.update_one.assert_not_called()


def test_sync_accrue_skips_system_user():
    db = MagicMock()
    credited = accrue_time_saved_sync(db, "system", "workflow_run")

    assert credited == 0
    db.user.update_one.assert_not_called()


def test_sync_accrue_skips_empty_user():
    db = MagicMock()
    credited = accrue_time_saved_sync(db, "", "workflow_run")

    assert credited == 0
    db.user.update_one.assert_not_called()
