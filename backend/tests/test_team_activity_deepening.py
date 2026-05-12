"""Unit tests for Sprint 3 team-activity deepening — digest collapse +
role-weighted ranking.

Exercises _render_team_digest (pure function) and the rendering shape.
End-to-end _select_team_activity (which touches MongoDB for memberships +
events + actor lookups) lives in tier-2 integration tests.
"""

from unittest.mock import MagicMock


def _ev(user_id: str, kind: str, ev_id: str | None = None):
    """Activity-event-shaped mock for the digest renderer."""
    e = MagicMock()
    e.user_id = user_id
    e.type = kind
    e.id = ev_id or f"ev-{user_id}-{kind}"
    return e


def _actor_info(*pairs):
    """Build actor_info dict: each pair is (user_id, name, role)."""
    return {uid: (name, role) for uid, name, role in pairs}


# ---------------------------------------------------------------------------
# _render_team_digest — content shape
# ---------------------------------------------------------------------------

def test_digest_counts_event_types():
    from app.services.briefing_service import _render_team_digest

    events = [
        _ev("alice", "workflow_run"),
        _ev("alice", "workflow_run"),
        _ev("bob", "search_set_run"),
    ]
    info = _actor_info(
        ("alice", "Alice", "compliance"),
        ("bob", "Bob", "pi"),
    )

    item = _render_team_digest(events, info)

    assert "2 workflows" in item.headline
    assert "1 extractions" in item.headline


def test_digest_counts_distinct_actors():
    """Headline says "N teammates" based on distinct actor count, not event count."""
    from app.services.briefing_service import _render_team_digest

    events = [
        _ev("alice", "workflow_run"),
        _ev("alice", "search_set_run"),  # same actor, different event
        _ev("bob", "workflow_run"),
        _ev("carol", "workflow_run"),
    ]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
    )

    item = _render_team_digest(events, info)
    assert "3 teammates" in item.headline


def test_digest_single_actor_uses_your_team_phrasing():
    from app.services.briefing_service import _render_team_digest

    events = [
        _ev("alice", "workflow_run"),
        _ev("alice", "workflow_run"),
        _ev("alice", "workflow_run"),
    ]
    info = _actor_info(("alice", "Alice", None))

    item = _render_team_digest(events, info)
    assert "Your team" in item.headline
    assert "teammates" not in item.headline


def test_digest_body_lists_first_three_actors():
    from app.services.briefing_service import _render_team_digest

    events = [
        _ev(uid, "workflow_run")
        for uid in ["alice", "bob", "carol", "dave", "eve"]
    ]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
        ("dave", "Dave", None),
        ("eve", "Eve", None),
    )

    item = _render_team_digest(events, info)

    assert "Alice" in item.body
    assert "Bob" in item.body
    assert "Carol" in item.body
    assert "2 more" in item.body  # the remaining 2 (Dave, Eve)


def test_digest_body_lists_all_when_three_or_fewer():
    from app.services.briefing_service import _render_team_digest

    events = [_ev("alice", "workflow_run"), _ev("bob", "workflow_run"), _ev("carol", "workflow_run")]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
    )

    item = _render_team_digest(events, info)
    assert "Alice" in item.body
    assert "Bob" in item.body
    assert "Carol" in item.body
    assert "more" not in item.body


def test_digest_source_id_is_date_keyed():
    """source_id includes the date so dedup works correctly across days."""
    import datetime
    from app.services.briefing_service import _render_team_digest

    events = [_ev("alice", "workflow_run"), _ev("bob", "workflow_run"), _ev("carol", "workflow_run")]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
    )

    item = _render_team_digest(events, info)

    assert item.source_id is not None
    assert item.source_id.startswith("team-digest:")
    # Extract the date portion and verify it parses
    date_part = item.source_id.split(":", 1)[1]
    datetime.date.fromisoformat(date_part)  # raises if malformed


def test_digest_uses_team_activity_category():
    from app.services.briefing_service import _render_team_digest

    events = [_ev("alice", "workflow_run"), _ev("bob", "workflow_run"), _ev("carol", "workflow_run")]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
    )

    item = _render_team_digest(events, info)
    assert item.category == "team-activity"


def test_digest_deep_link_goes_to_activity():
    from app.services.briefing_service import _render_team_digest

    events = [_ev("alice", "workflow_run"), _ev("bob", "workflow_run"), _ev("carol", "workflow_run")]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
    )

    item = _render_team_digest(events, info)
    assert item.deep_link == "/activity"


def test_digest_handles_unknown_event_type_gracefully():
    """If event types fall outside the known set, fallback to action count."""
    from app.services.briefing_service import _render_team_digest

    events = [
        _ev("alice", "quality_alert"),  # not counted into workflows/extractions/chats
        _ev("bob", "quality_alert"),
        _ev("carol", "quality_alert"),
    ]
    info = _actor_info(
        ("alice", "Alice", None),
        ("bob", "Bob", None),
        ("carol", "Carol", None),
    )

    item = _render_team_digest(events, info)
    assert "3 actions" in item.headline


# ---------------------------------------------------------------------------
# Threshold constant
# ---------------------------------------------------------------------------

def test_digest_threshold_is_three():
    """The collapse threshold is 3 — single-source-of-truth for the constant."""
    from app.services.briefing_service import TEAM_DIGEST_THRESHOLD

    assert TEAM_DIGEST_THRESHOLD == 3
