"""Tests for app.services.teams_cards.

Teams cards are plain JSON dicts following the Adaptive Cards 1.4 schema, so
the assertions here focus on structural invariants (schema/version, body
sections in the expected order, conditional blocks appearing or not).
"""

from __future__ import annotations

from app.services.teams_cards import (
    build_daily_digest_card,
    build_exception_card,
    build_work_item_card,
)


def _fact(card: dict, title: str) -> str | None:
    """Return the value of a FactSet fact with the given title, or None."""
    for block in card["body"]:
        if block.get("type") == "FactSet":
            for fact in block.get("facts", []):
                if fact["title"] == title:
                    return fact["value"]
    return None


def _has_text(card: dict, needle: str) -> bool:
    return any(
        needle in block.get("text", "")
        for block in card["body"]
        if block.get("type") == "TextBlock"
    )


class TestBuildWorkItemCard:
    def test_minimal_work_item_has_required_structure(self):
        card = build_work_item_card({"uuid": "abc123", "subject": "Hello"})
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"
        assert card["$schema"].startswith("http://adaptivecards.io/")
        # The subject should land in the title TextBlock
        assert card["body"][0]["text"] == "Hello"
        assert card["body"][0]["weight"] == "Bolder"
        # The FactSet with source/category/status always appears
        assert _fact(card, "Source") == "unknown"
        assert _fact(card, "Category") == "Unclassified"
        assert _fact(card, "Status") == "unknown"

    def test_missing_subject_falls_back_to_placeholder(self):
        card = build_work_item_card({"uuid": "abc123"})
        assert card["body"][0]["text"] == "(no subject)"

    def test_sender_and_attachment_facts_added_when_present(self):
        card = build_work_item_card({
            "uuid": "abc",
            "sender_email": "prof@uidaho.edu",
            "attachment_count": 3,
        })
        assert _fact(card, "From") == "prof@uidaho.edu"
        assert _fact(card, "Attachments") == "3"

    def test_sensitivity_flags_block_appears_with_attention_color(self):
        card = build_work_item_card({
            "uuid": "abc",
            "sensitivity_flags": ["PII", "FERPA"],
        })
        # A TextBlock with color=Attention should carry the sensitivity line
        flagged = [
            b for b in card["body"]
            if b.get("type") == "TextBlock" and b.get("color") == "Attention"
        ]
        assert flagged, "Expected a red sensitivity TextBlock"
        assert "PII, FERPA" in flagged[0]["text"]

    def test_awaiting_review_adds_approve_action(self):
        card = build_work_item_card({"uuid": "abc", "status": "awaiting_review"})
        titles = [a["title"] for a in card["actions"]]
        assert "View Details" in titles
        assert "Approve & Continue" in titles

    def test_completed_status_omits_approve_action(self):
        card = build_work_item_card({"uuid": "abc", "status": "completed"})
        titles = [a["title"] for a in card["actions"]]
        assert "Approve & Continue" not in titles

    def test_result_output_overrides_summary(self):
        card = build_work_item_card(
            {"uuid": "abc", "triage_summary": "original"},
            result_doc={"final_output": {"output": "final extraction summary"}},
        )
        assert _has_text(card, "final extraction summary")

    def test_summary_truncates_to_500_chars(self):
        long_summary = "x" * 1000
        card = build_work_item_card({"uuid": "abc", "triage_summary": long_summary})
        for block in card["body"]:
            if block.get("type") == "TextBlock" and block.get("text", "").startswith("x"):
                assert len(block["text"]) == 500
                break
        else:
            raise AssertionError("Expected a truncated summary TextBlock")

    def test_case_folder_url_adds_link_block(self):
        card = build_work_item_card({
            "uuid": "abc",
            "case_folder_url": "https://sharepoint.example/case/1",
        })
        assert _has_text(card, "View case folder")
        assert _has_text(card, "https://sharepoint.example/case/1")


class TestBuildExceptionCard:
    def test_error_shown_in_facts_and_truncated(self):
        long_err = "E" * 500
        card = build_exception_card({"uuid": "1234567890", "subject": "oops"}, long_err)
        assert card["version"] == "1.4"
        assert _fact(card, "Error") == "E" * 200  # truncated to 200
        # Title uses the subject when present
        assert "oops" in card["body"][0]["text"]

    def test_missing_subject_falls_back_to_short_uuid(self):
        card = build_exception_card({"uuid": "abcdef1234567890"}, "boom")
        # Title should mention the first 8 chars of the uuid
        assert "abcdef12" in card["body"][0]["text"]

    def test_attention_color_on_title(self):
        card = build_exception_card({"uuid": "x", "subject": "s"}, "err")
        assert card["body"][0].get("color") == "Attention"


class TestBuildDailyDigestCard:
    def test_stats_columns_are_rendered(self):
        card = build_daily_digest_card(
            work_items=[],
            stats={"total": 10, "completed": 7, "failed": 1, "awaiting_review": 2},
        )
        column_sets = [b for b in card["body"] if b.get("type") == "ColumnSet"]
        assert column_sets, "Expected a ColumnSet for stats"
        # Flatten all inner TextBlock values from the column set
        values = []
        for col in column_sets[0]["columns"]:
            for inner in col["items"]:
                values.append(inner["text"])
        assert "10" in values
        assert "7" in values
        assert "1" in values
        assert "2" in values

    def test_empty_work_items_omits_recent_section(self):
        card = build_daily_digest_card([], {})
        # No "Recent Items" header should appear
        assert not _has_text(card, "Recent Items")

    def test_work_items_render_with_status_icons(self):
        wi_list = [
            {"uuid": "a" * 16, "subject": "Done",   "status": "completed",        "triage_category": "grade_change"},
            {"uuid": "b" * 16, "subject": "Fail",   "status": "failed",           "triage_category": "vendor_setup"},
            {"uuid": "c" * 16, "subject": "Review", "status": "awaiting_review",  "triage_category": "transcript_request"},
            {"uuid": "d" * 16, "subject": "Going",  "status": "processing",       "triage_category": "other"},
            {"uuid": "e" * 16,                       "status": "unknown"},  # fallback icon
        ]
        card = build_daily_digest_card(wi_list, {"total": 5})
        body_texts = [b.get("text", "") for b in card["body"] if b.get("type") == "TextBlock"]
        assert any("✓" in t and "Done" in t for t in body_texts)
        assert any("✗" in t and "Fail" in t for t in body_texts)
        assert any("⏳" in t and "Review" in t for t in body_texts)
        assert any("⟳" in t and "Going" in t for t in body_texts)
        # Unknown status uses "·" and falls back to first 8 chars of uuid as subject
        assert any("·" in t and "eeeeeeee" in t for t in body_texts)

    def test_work_items_capped_at_eight_entries(self):
        wi_list = [{"uuid": f"u{i:02d}", "subject": f"Item {i}", "status": "completed"} for i in range(20)]
        card = build_daily_digest_card(wi_list, {})
        item_lines = [
            b for b in card["body"]
            if b.get("type") == "TextBlock" and b.get("text", "").startswith("✓")
        ]
        assert len(item_lines) == 8

    def test_dashboard_action_present(self):
        card = build_daily_digest_card([], {})
        titles = [a["title"] for a in card["actions"]]
        assert "Open Dashboard" in titles
