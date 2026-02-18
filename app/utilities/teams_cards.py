#!/usr/bin/env python3
"""Adaptive Card builders for Teams notifications.

Cards are plain JSON dicts — no external dependency needed.
Uses Adaptive Card schema v1.4 which is widely supported in Teams.
"""

from __future__ import annotations

import os
from datetime import datetime

BASE_URL = os.environ.get("VANDALIZER_BASE_URL", "https://vandalizer.uidaho.edu")


def build_work_item_card(work_item, result=None) -> dict:
    """Build an Adaptive Card for a processed work item.

    Shows subject, key metadata, summary, and action buttons.
    """
    facts = [
        {"title": "Source", "value": work_item.source or "unknown"},
        {"title": "Category", "value": work_item.triage_category or "Unclassified"},
        {"title": "Status", "value": work_item.status or "unknown"},
    ]
    if work_item.sender_email:
        facts.append({"title": "From", "value": work_item.sender_email})
    if work_item.attachment_count:
        facts.append({"title": "Attachments", "value": str(work_item.attachment_count)})

    # Sensitivity badge
    sensitivity_text = ""
    if work_item.sensitivity_flags:
        flags = ", ".join(work_item.sensitivity_flags)
        sensitivity_text = f"**Sensitivity:** {flags}"

    body = [
        {
            "type": "TextBlock",
            "text": work_item.subject or "(no subject)",
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

    # Add summary
    summary = work_item.triage_summary or ""
    if result and result.final_output:
        output = result.final_output.get("output")
        if isinstance(output, str):
            summary = output[:500]
    if summary:
        body.append({
            "type": "TextBlock",
            "text": summary[:500],
            "wrap": True,
            "maxLines": 5,
        })

    # Case folder link
    if work_item.case_folder_url:
        body.append({
            "type": "TextBlock",
            "text": f"[View case folder]({work_item.case_folder_url})",
            "wrap": True,
        })

    actions = [
        {
            "type": "Action.OpenUrl",
            "title": "View Details",
            "url": f"{BASE_URL}/office/workitems/{work_item.uuid}",
        },
    ]

    # Approval button for items awaiting review
    if work_item.status == "awaiting_review":
        actions.append({
            "type": "Action.OpenUrl",
            "title": "Approve & Continue",
            "url": f"{BASE_URL}/office/workitems/{work_item.uuid}/approve",
        })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }


def build_exception_card(work_item, error: str) -> dict:
    """Build a card for a failed or blocked work item."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Processing Failed: {work_item.subject or work_item.uuid[:8]}",
                "weight": "Bolder",
                "size": "Medium",
                "color": "Attention",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Source", "value": work_item.source},
                    {"title": "Category", "value": work_item.triage_category or "N/A"},
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
            {
                "type": "Action.OpenUrl",
                "title": "View & Fix",
                "url": f"{BASE_URL}/office/workitems/{work_item.uuid}",
            },
        ],
    }


def build_daily_digest_card(work_items: list, stats: dict) -> dict:
    """Build a daily digest Adaptive Card.

    Args:
        work_items: List of recent WorkItem instances (up to 10 for display).
        stats: Dict with total, completed, failed, awaiting_review counts.
    """
    today = datetime.utcnow().strftime("%B %d, %Y")

    body = [
        {
            "type": "TextBlock",
            "text": f"Daily Digest — {today}",
            "weight": "Bolder",
            "size": "Medium",
        },
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

    # Add a list of recent items
    if work_items:
        body.append({
            "type": "TextBlock",
            "text": "Recent Items",
            "weight": "Bolder",
            "separator": True,
        })
        for wi in work_items[:8]:
            status_icon = {
                "completed": "✓",
                "failed": "✗",
                "awaiting_review": "⏳",
                "processing": "⟳",
            }.get(wi.status, "·")

            body.append({
                "type": "TextBlock",
                "text": f"{status_icon} **{wi.subject or wi.uuid[:8]}** — {wi.triage_category or wi.source}",
                "wrap": True,
                "spacing": "Small",
            })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Open Dashboard",
                "url": f"{BASE_URL}/office/dashboard",
            },
        ],
    }


def _stat_column(label: str, value: str) -> dict:
    """Helper: build a stat column for the digest card."""
    return {
        "type": "Column",
        "width": "stretch",
        "items": [
            {"type": "TextBlock", "text": value, "size": "ExtraLarge", "weight": "Bolder", "horizontalAlignment": "Center"},
            {"type": "TextBlock", "text": label, "size": "Small", "horizontalAlignment": "Center", "isSubtle": True},
        ],
    }
