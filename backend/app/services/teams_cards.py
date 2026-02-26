"""Adaptive Card builders for Teams notifications.

Ported from Flask app/utilities/teams_cards.py.
Cards are plain JSON dicts — no external dependency needed.
Uses Adaptive Card schema v1.4.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

BASE_URL = os.environ.get("VANDALIZER_BASE_URL", "https://vandalizer.uidaho.edu")


def build_work_item_card(work_item_doc: dict, result_doc: dict | None = None) -> dict:
    """Build an Adaptive Card for a processed work item."""
    facts = [
        {"title": "Source", "value": work_item_doc.get("source", "unknown")},
        {"title": "Category", "value": work_item_doc.get("triage_category", "Unclassified")},
        {"title": "Status", "value": work_item_doc.get("status", "unknown")},
    ]
    if work_item_doc.get("sender_email"):
        facts.append({"title": "From", "value": work_item_doc["sender_email"]})
    if work_item_doc.get("attachment_count"):
        facts.append({"title": "Attachments", "value": str(work_item_doc["attachment_count"])})

    sensitivity_text = ""
    if work_item_doc.get("sensitivity_flags"):
        flags = ", ".join(work_item_doc["sensitivity_flags"])
        sensitivity_text = f"**Sensitivity:** {flags}"

    body = [
        {
            "type": "TextBlock",
            "text": work_item_doc.get("subject") or "(no subject)",
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {"type": "FactSet", "facts": facts},
    ]

    if sensitivity_text:
        body.append({
            "type": "TextBlock",
            "text": sensitivity_text,
            "color": "Attention",
            "wrap": True,
        })

    summary = work_item_doc.get("triage_summary", "")
    if result_doc and result_doc.get("final_output"):
        output = result_doc["final_output"].get("output")
        if isinstance(output, str):
            summary = output[:500]
    if summary:
        body.append({
            "type": "TextBlock",
            "text": summary[:500],
            "wrap": True,
            "maxLines": 5,
        })

    if work_item_doc.get("case_folder_url"):
        body.append({
            "type": "TextBlock",
            "text": f"[View case folder]({work_item_doc['case_folder_url']})",
            "wrap": True,
        })

    wi_uuid = work_item_doc.get("uuid", "")
    actions = [
        {"type": "Action.OpenUrl", "title": "View Details", "url": f"{BASE_URL}/office/workitems/{wi_uuid}"},
    ]
    if work_item_doc.get("status") == "awaiting_review":
        actions.append({
            "type": "Action.OpenUrl",
            "title": "Approve & Continue",
            "url": f"{BASE_URL}/office/workitems/{wi_uuid}/approve",
        })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }


def build_exception_card(work_item_doc: dict, error: str) -> dict:
    """Build a card for a failed or blocked work item."""
    wi_uuid = work_item_doc.get("uuid", "")[:8]
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Processing Failed: {work_item_doc.get('subject') or wi_uuid}",
                "weight": "Bolder",
                "size": "Medium",
                "color": "Attention",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Source", "value": work_item_doc.get("source", "")},
                    {"title": "Category", "value": work_item_doc.get("triage_category", "N/A")},
                    {"title": "Error", "value": error[:200]},
                ],
            },
            {
                "type": "TextBlock",
                "text": "This item requires attention. Click below to view details and reprocess.",
                "wrap": True,
            },
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "View & Fix", "url": f"{BASE_URL}/office/workitems/{work_item_doc.get('uuid', '')}"},
        ],
    }


def build_daily_digest_card(work_items: list[dict], stats: dict) -> dict:
    """Build a daily digest Adaptive Card."""
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    body = [
        {"type": "TextBlock", "text": f"Daily Digest — {today}", "weight": "Bolder", "size": "Medium"},
        {
            "type": "ColumnSet",
            "columns": [
                _stat_column("Processed", str(stats.get("total", 0))),
                _stat_column("Completed", str(stats.get("completed", 0))),
                _stat_column("Failed", str(stats.get("failed", 0))),
                _stat_column("Pending Review", str(stats.get("awaiting_review", 0))),
            ],
        },
    ]

    if work_items:
        body.append({"type": "TextBlock", "text": "Recent Items", "weight": "Bolder", "separator": True})
        for wi in work_items[:8]:
            status_icon = {
                "completed": "✓",
                "failed": "✗",
                "awaiting_review": "⏳",
                "processing": "⟳",
            }.get(wi.get("status", ""), "·")
            subject = wi.get("subject") or wi.get("uuid", "")[:8]
            category = wi.get("triage_category") or wi.get("source", "")
            body.append({
                "type": "TextBlock",
                "text": f"{status_icon} **{subject}** — {category}",
                "wrap": True,
                "spacing": "Small",
            })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [{"type": "Action.OpenUrl", "title": "Open Dashboard", "url": f"{BASE_URL}/office/dashboard"}],
    }


def _stat_column(label: str, value: str) -> dict:
    return {
        "type": "Column",
        "width": "stretch",
        "items": [
            {"type": "TextBlock", "text": value, "size": "ExtraLarge", "weight": "Bolder", "horizontalAlignment": "Center"},
            {"type": "TextBlock", "text": label, "size": "Small", "horizontalAlignment": "Center", "isSubtle": True},
        ],
    }
