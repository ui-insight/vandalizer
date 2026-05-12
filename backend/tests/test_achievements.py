"""Unit tests for Sprint 3 achievement drops — milestone awards + briefing surface.

Covers the curated milestone table, award_if_not_held idempotency,
threshold detection, and the briefing selector's dedup behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.achievements import (
    _MILESTONES,
    _TIME_SAVED_THRESHOLDS,
    award_if_not_held,
    check_time_saved_thresholds,
    check_time_saved_thresholds_sync,
    known_milestone_ids,
    milestone_def,
)


class _AnyCompare:
    def __eq__(self, other): return _AnyCompare()
    def __ne__(self, other): return _AnyCompare()
    def __le__(self, other): return _AnyCompare()
    def __ge__(self, other): return _AnyCompare()
    def __bool__(self): return True
    def __hash__(self): return 0


def _patch_user(found):
    klass = MagicMock()
    klass.find_one = AsyncMock(return_value=found)
    klass.user_id = _AnyCompare()
    return patch("app.services.achievements.User", new=klass)


# ---------------------------------------------------------------------------
# Curated milestone table
# ---------------------------------------------------------------------------

def test_v0_milestones_present():
    assert "first_extraction" in _MILESTONES
    assert "first_workflow" in _MILESTONES
    assert "time_saved_60" in _MILESTONES
    assert "time_saved_300" in _MILESTONES


def test_milestone_copy_is_factual_no_exclamations():
    """Audience-mechanics rule: no exclamation points, factual tone."""
    for mid, defn in _MILESTONES.items():
        assert "headline" in defn and defn["headline"], f"{mid} missing headline"
        assert "body" in defn and defn["body"], f"{mid} missing body"
        assert "!" not in defn["headline"], f"{mid} headline has !"
        assert "!" not in defn["body"], f"{mid} body has !"


def test_milestone_def_lookup():
    assert milestone_def("first_extraction") is not None
    assert milestone_def("nonexistent") is None


def test_known_milestone_ids_covers_table():
    assert set(known_milestone_ids()) == set(_MILESTONES.keys())


def test_threshold_table_matches_milestone_ids():
    """Every threshold milestone in _TIME_SAVED_THRESHOLDS must be defined."""
    for milestone_id in _TIME_SAVED_THRESHOLDS.values():
        assert milestone_id in _MILESTONES


# ---------------------------------------------------------------------------
# award_if_not_held
# ---------------------------------------------------------------------------

async def test_award_first_time_returns_true():
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = []
    user.save = AsyncMock()

    with _patch_user(user):
        result = await award_if_not_held("alice", "first_extraction")

    assert result is True
    assert "first_extraction" in user.achievements_unlocked
    user.save.assert_awaited()


async def test_award_idempotent():
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = ["first_extraction"]
    user.save = AsyncMock()

    with _patch_user(user):
        result = await award_if_not_held("alice", "first_extraction")

    assert result is False
    user.save.assert_not_called()


async def test_award_unknown_milestone_returns_false():
    with _patch_user(MagicMock()):
        result = await award_if_not_held("alice", "imagined_milestone")

    assert result is False


async def test_award_skips_system_user():
    with _patch_user(None):
        result = await award_if_not_held("system", "first_extraction")
    assert result is False


async def test_award_skips_empty_user_id():
    with _patch_user(None):
        result = await award_if_not_held("", "first_extraction")
    assert result is False


async def test_award_missing_user_returns_false():
    with _patch_user(None):
        result = await award_if_not_held("ghost", "first_extraction")
    assert result is False


async def test_award_handles_none_achievements_list():
    """Defensive: legacy users may have None for achievements_unlocked."""
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = None
    user.save = AsyncMock()

    with _patch_user(user):
        result = await award_if_not_held("alice", "first_workflow")

    assert result is True
    assert user.achievements_unlocked == ["first_workflow"]


# ---------------------------------------------------------------------------
# check_time_saved_thresholds (async)
# ---------------------------------------------------------------------------

async def test_threshold_check_awards_when_crossed():
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = []
    user.save = AsyncMock()

    with _patch_user(user):
        awarded = await check_time_saved_thresholds("alice", 60)

    assert "time_saved_60" in awarded


async def test_threshold_check_no_award_below_threshold():
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = []
    user.save = AsyncMock()

    with _patch_user(user):
        awarded = await check_time_saved_thresholds("alice", 30)

    assert awarded == []


async def test_threshold_check_idempotent_for_already_held():
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = ["time_saved_60"]
    user.save = AsyncMock()

    with _patch_user(user):
        awarded = await check_time_saved_thresholds("alice", 90)

    assert "time_saved_60" not in awarded


async def test_threshold_check_awards_higher_tier_when_crossed():
    user = MagicMock()
    user.user_id = "alice"
    user.achievements_unlocked = ["time_saved_60"]  # already past first tier
    user.save = AsyncMock()

    with _patch_user(user):
        awarded = await check_time_saved_thresholds("alice", 320)  # past 300

    assert "time_saved_300" in awarded


# ---------------------------------------------------------------------------
# check_time_saved_thresholds_sync (pymongo)
# ---------------------------------------------------------------------------

def test_sync_threshold_uses_conditional_push():
    db = MagicMock()
    db.user.update_one.return_value = MagicMock(modified_count=1)

    awarded = check_time_saved_thresholds_sync(db, "alice", 65)

    assert "time_saved_60" in awarded
    # Verify the conditional-push shape: the filter must include the
    # "doesn't already have it" guard so concurrent workers can't double-add.
    args, _ = db.user.update_one.call_args
    assert args[0]["user_id"] == "alice"
    assert "$ne" in str(args[0]) or "achievements_unlocked" in args[0]
    assert args[1] == {"$push": {"achievements_unlocked": "time_saved_60"}}


def test_sync_threshold_below_threshold_does_not_push():
    db = MagicMock()
    awarded = check_time_saved_thresholds_sync(db, "alice", 30)

    assert awarded == []
    db.user.update_one.assert_not_called()


def test_sync_threshold_skips_system_user():
    db = MagicMock()
    awarded = check_time_saved_thresholds_sync(db, "system", 1000)

    assert awarded == []
    db.user.update_one.assert_not_called()


def test_sync_threshold_skips_no_modify():
    """If $push didn't modify (already held), don't return the milestone id."""
    db = MagicMock()
    db.user.update_one.return_value = MagicMock(modified_count=0)

    awarded = check_time_saved_thresholds_sync(db, "alice", 65)

    assert awarded == []


# ---------------------------------------------------------------------------
# Briefing selector (_select_achievements)
# ---------------------------------------------------------------------------

async def test_briefing_selector_returns_unlocked_items():
    from app.services.briefing_service import _select_achievements

    user = MagicMock()
    user.achievements_unlocked = ["first_extraction", "time_saved_60"]
    user.briefing_items_shown_ids = []

    items = await _select_achievements(user)

    assert len(items) == 2
    ids = [it.source_id for it in items]
    assert "achievement:first_extraction" in ids
    assert "achievement:time_saved_60" in ids
    assert all(it.category == "achievement" for it in items)
    assert all(it.urgency == 2 for it in items)


async def test_briefing_selector_dedups_against_shown():
    from app.services.briefing_service import _select_achievements

    user = MagicMock()
    user.achievements_unlocked = ["first_extraction", "first_workflow"]
    user.briefing_items_shown_ids = ["achievement:first_extraction"]

    items = await _select_achievements(user)

    assert len(items) == 1
    assert items[0].source_id == "achievement:first_workflow"


async def test_briefing_selector_caps_at_two():
    from app.services.briefing_service import _select_achievements

    user = MagicMock()
    user.achievements_unlocked = ["first_extraction", "first_workflow", "time_saved_60", "time_saved_300"]
    user.briefing_items_shown_ids = []

    items = await _select_achievements(user)

    assert len(items) == 2


async def test_briefing_selector_skips_unknown_milestone_id():
    from app.services.briefing_service import _select_achievements

    user = MagicMock()
    user.achievements_unlocked = ["legacy_removed_milestone", "first_extraction"]
    user.briefing_items_shown_ids = []

    items = await _select_achievements(user)

    assert len(items) == 1
    assert items[0].source_id == "achievement:first_extraction"


async def test_briefing_selector_empty_when_nothing_unlocked():
    from app.services.briefing_service import _select_achievements

    user = MagicMock()
    user.achievements_unlocked = []
    user.briefing_items_shown_ids = []

    items = await _select_achievements(user)
    assert items == []
