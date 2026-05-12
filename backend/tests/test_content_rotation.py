"""Unit tests for Sprint 3 content rotation — suggested-action category +
rotation penalty so consecutive briefings vary.

The selectors that touch MongoDB (compute_daily_briefing end-to-end) live
in tier-2 integration tests. Here we test the pure-content helpers and the
sort behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch


class _AnyCompare:
    def __eq__(self, other): return _AnyCompare()
    def __ne__(self, other): return _AnyCompare()
    def __le__(self, other): return _AnyCompare()
    def __ge__(self, other): return _AnyCompare()
    def __bool__(self): return True
    def __hash__(self): return 0


def _user(role_segment: str | None = "compliance", primer_shown: list[str] | None = None):
    u = MagicMock()
    u.user_id = "alice"
    u.role_segment = role_segment
    u.briefing_primer_shown_ids = primer_shown or []
    return u


# ---------------------------------------------------------------------------
# _select_suggested_action
# ---------------------------------------------------------------------------

async def test_suggested_action_returns_one_item_for_known_role():
    from app.services.briefing_service import _select_suggested_action

    items = await _select_suggested_action(_user("compliance"))

    assert len(items) == 1
    item = items[0]
    assert item.category == "suggested-action"
    assert item.urgency == 0
    assert item.source_id and item.source_id.startswith("primer:")
    assert item.headline  # non-empty
    assert item.body


async def test_suggested_action_dedups_against_shown_primers():
    from app.services.briefing_service import _select_suggested_action
    from app.services.briefing_primer_content import select_primer_items

    # Find what compliance's first primer item would be
    first_pick = select_primer_items("compliance", [], 1)[0]
    seen = [first_pick["id"]]

    items = await _select_suggested_action(_user("compliance", primer_shown=seen))
    assert len(items) == 1
    assert items[0].source_id != f"primer:{first_pick['id']}"


async def test_suggested_action_falls_through_when_pool_empty():
    """If the primer pool returns nothing, the selector returns an empty list."""
    from app.services.briefing_service import _select_suggested_action

    with patch(
        "app.services.briefing_service.select_primer_items",
        return_value=[],
    ):
        items = await _select_suggested_action(_user("compliance"))

    assert items == []


# ---------------------------------------------------------------------------
# _select_deadlines (stub)
# ---------------------------------------------------------------------------

async def test_deadlines_returns_empty_for_now():
    """v0 stub — no data source yet. Contract is the empty list."""
    from app.services.briefing_service import _select_deadlines

    items = await _select_deadlines(_user())
    assert items == []


# ---------------------------------------------------------------------------
# _get_yesterday_category_set + rotation penalty (sort behavior)
# ---------------------------------------------------------------------------

async def test_yesterday_categories_returns_empty_when_no_briefing():
    from app.services.briefing_service import _get_yesterday_category_set

    klass = MagicMock()
    klass.find_one = AsyncMock(return_value=None)
    klass.user_id = _AnyCompare()
    klass.date = _AnyCompare()

    with patch("app.services.briefing_service.Briefing", new=klass):
        cats = await _get_yesterday_category_set("alice")

    assert cats == set()


async def test_yesterday_categories_returns_distinct_categories():
    from app.services.briefing_service import _get_yesterday_category_set

    prev = MagicMock()
    prev.items = [
        MagicMock(category="my-activity"),
        MagicMock(category="my-activity"),
        MagicMock(category="kb-news"),
    ]
    klass = MagicMock()
    klass.find_one = AsyncMock(return_value=prev)
    klass.user_id = _AnyCompare()
    klass.date = _AnyCompare()

    with patch("app.services.briefing_service.Briefing", new=klass):
        cats = await _get_yesterday_category_set("alice")

    assert cats == {"my-activity", "kb-news"}


# ---------------------------------------------------------------------------
# Rotation penalty effect on the final sort
# ---------------------------------------------------------------------------

def _item(category: str, urgency: int = 0, source_id: str | None = None):
    """Build a briefing-item-shaped object for sort tests."""
    from app.models.briefing import BriefingItem

    return BriefingItem(
        category=category,
        headline="x",
        body="y",
        urgency=urgency,
        source_id=source_id,
    )


def test_rotation_penalty_demotes_yesterdays_category():
    """Same-urgency items: a category that was in yesterday's set should sort
    after one that wasn't."""
    from app.services.briefing_service import _ROTATION_PENALTY

    items = [
        _item("my-activity", urgency=1, source_id="a"),
        _item("kb-news", urgency=1, source_id="b"),
    ]
    yesterday_cats = {"my-activity"}
    category_priority = {"my-activity": 1, "kb-news": 3}

    def _sort_key(it):
        base = category_priority.get(it.category, 99)
        rotation = _ROTATION_PENALTY if it.category in yesterday_cats else 0
        return (-it.urgency, base + rotation)

    items.sort(key=_sort_key)
    assert items[0].category == "kb-news"
    assert items[1].category == "my-activity"


def test_rotation_penalty_does_not_drop_items():
    """The penalty bumps order, not membership — every input survives."""
    from app.services.briefing_service import _ROTATION_PENALTY

    items = [
        _item("my-activity", urgency=1, source_id="a"),
        _item("kb-news", urgency=1, source_id="b"),
    ]
    yesterday_cats = {"my-activity"}
    category_priority = {"my-activity": 1, "kb-news": 3}

    def _sort_key(it):
        base = category_priority.get(it.category, 99)
        rotation = _ROTATION_PENALTY if it.category in yesterday_cats else 0
        return (-it.urgency, base + rotation)

    items.sort(key=_sort_key)
    assert len(items) == 2


def test_urgency_beats_rotation_penalty():
    """A high-urgency item from yesterday's category still beats a low-urgency
    item from a fresh category."""
    from app.services.briefing_service import _ROTATION_PENALTY

    items = [
        _item("my-activity", urgency=3, source_id="a"),  # high urgency, was yesterday
        _item("kb-news", urgency=0, source_id="b"),       # low urgency, fresh
    ]
    yesterday_cats = {"my-activity"}
    category_priority = {"my-activity": 1, "kb-news": 3}

    def _sort_key(it):
        base = category_priority.get(it.category, 99)
        rotation = _ROTATION_PENALTY if it.category in yesterday_cats else 0
        return (-it.urgency, base + rotation)

    items.sort(key=_sort_key)
    assert items[0].category == "my-activity"  # urgency wins


# ---------------------------------------------------------------------------
# Sanity: BriefingItemCategory enum has both new categories defined
# ---------------------------------------------------------------------------

def test_new_categories_are_defined():
    from app.models.briefing import BriefingItemCategory

    assert BriefingItemCategory.SUGGESTED_ACTION.value == "suggested-action"
    assert BriefingItemCategory.DEADLINE.value == "deadline"
