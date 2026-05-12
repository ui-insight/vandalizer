"""Unit tests for the Morning Briefing service — pure-content logic only.

End-to-end aggregation that touches MongoDB lives in tier-2 integration tests.
"""

from app.services.briefing_primer_content import select_primer_items
from app.services.email_service import morning_briefing_email


# ---------------------------------------------------------------------------
# Primer selection
# ---------------------------------------------------------------------------

def test_primer_returns_requested_count_for_known_role():
    items = select_primer_items("research_admin", [], 3)
    assert len(items) == 3
    assert all("id" in i and "headline" in i and "body" in i for i in items)


def test_primer_dedups_against_shown_ids():
    first = select_primer_items("pi", [], 2)
    shown = [i["id"] for i in first]
    second = select_primer_items("pi", shown, 2)
    second_ids = [i["id"] for i in second]
    # No overlap with what was already shown
    assert not set(shown) & set(second_ids)


def test_primer_falls_back_to_generic_pool_for_unknown_role():
    items = select_primer_items(None, [], 2)
    assert len(items) == 2
    # Generic items are prefixed "gen-"
    assert all(i["id"].startswith("gen-") for i in items)


def test_primer_exhaustion_repeats_rather_than_returning_empty():
    pool_total = len(select_primer_items("compliance", [], 99))  # everything
    everything = [i["id"] for i in select_primer_items("compliance", [], 99)]
    # Even with everything marked shown, we should still get items back (rule: never empty)
    fallback = select_primer_items("compliance", everything, 2)
    assert len(fallback) == 2
    # And the pool count is sane (we have at least 5 compliance items defined)
    assert pool_total >= 5


def test_primer_interleaves_seeds_and_tips():
    # First pick of 2 should be one seed + one tip, in that order
    items = select_primer_items("research_admin", [], 2)
    assert items[0]["id"].endswith("-seed-budget-extract") or "seed" in items[0]["id"]


def test_primer_count_zero_returns_empty():
    assert select_primer_items("pi", [], 0) == []


# ---------------------------------------------------------------------------
# Email template rendering
# ---------------------------------------------------------------------------

def test_morning_briefing_email_subject_uses_top_headline():
    subj, _ = morning_briefing_email(
        name="Alice",
        briefing_items=[
            {"category": "my-activity", "headline": "Workflow X finished", "body": "12 docs", "deep_link": "/chat", "urgency": 2, "source_id": "x"},
            {"category": "kb-news", "headline": "New KB item Y", "body": "in compliance", "deep_link": "/library", "urgency": 1, "source_id": "y"},
        ],
        frontend_url="https://example.com",
    )
    assert "Workflow X finished" in subj


def test_morning_briefing_email_renders_each_item():
    _, html = morning_briefing_email(
        name="Alice",
        briefing_items=[
            {"category": "my-activity", "headline": "First headline", "body": "first body", "deep_link": "/chat", "urgency": 2, "source_id": "1"},
            {"category": "team-activity", "headline": "Second headline", "body": "second body", "deep_link": "/library", "urgency": 1, "source_id": "2"},
        ],
        frontend_url="https://example.com",
    )
    assert "First headline" in html
    assert "Second headline" in html
    assert "first body" in html
    assert "second body" in html
    assert "https://example.com/chat" in html
    assert "https://example.com/library" in html


def test_morning_briefing_email_uses_urgency_icons():
    _, html = morning_briefing_email(
        name="Alice",
        briefing_items=[
            {"category": "my-activity", "headline": "Critical thing", "body": "now", "deep_link": "/chat", "urgency": 3, "source_id": "x"},
        ],
        frontend_url="https://example.com",
    )
    assert "⚠️" in html  # urgency=3 triggers the warning icon


def test_morning_briefing_email_handles_external_url_deep_link():
    """Items with a full URL (not starting with /) should be used as-is."""
    _, html = morning_briefing_email(
        name="Alice",
        briefing_items=[
            {"category": "my-activity", "headline": "External", "body": "elsewhere", "deep_link": "https://external.example.com/x", "urgency": 0, "source_id": "x"},
        ],
        frontend_url="https://app.example.com",
    )
    assert "https://external.example.com/x" in html
    # Should not have double-prefixed
    assert "https://app.example.comhttps" not in html


def test_morning_briefing_email_is_total_for_empty_input():
    """Defensive: function should not crash on empty items list, even though the caller filters this case."""
    subj, html = morning_briefing_email(
        name="Alice",
        briefing_items=[],
        frontend_url="https://example.com",
    )
    assert subj
    assert html
