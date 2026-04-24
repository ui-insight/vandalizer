"""Tests for pure helpers in app.services.support_service.

The full ticket lifecycle (create/update/reply) hits MongoDB and Redis and
is covered by router-level tests. Here we exercise the ISO-UTC timestamp
helper and the two pydantic-to-dict serializers — the parts the UI
inspects on every list/detail call.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from app.services.support_service import (
    _iso_utc,
    _ticket_summary,
    _ticket_to_dict,
)


class TestIsoUtc:
    def test_none_passes_through(self):
        assert _iso_utc(None) is None

    def test_naive_datetime_gets_utc_offset_added(self):
        result = _iso_utc(datetime.datetime(2026, 3, 5, 10, 15, 0))
        assert result == "2026-03-05T10:15:00+00:00"

    def test_already_aware_datetime_preserved(self):
        est = datetime.timezone(datetime.timedelta(hours=-5))
        result = _iso_utc(datetime.datetime(2026, 3, 5, 10, 15, 0, tzinfo=est))
        assert result == "2026-03-05T10:15:00-05:00"


def _enum(value: str) -> SimpleNamespace:
    """Stand-in for an Enum that has a `.value` attribute."""
    return SimpleNamespace(value=value)


def _message(content: str = "hi", is_support_reply: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=f"msg-{content[:3]}",
        user_id="alice",
        user_name="Alice",
        content=content,
        is_support_reply=is_support_reply,
        created_at=datetime.datetime(2026, 3, 5, 10, 0, 0),
    )


def _attachment(filename: str = "f.pdf") -> SimpleNamespace:
    return SimpleNamespace(
        uuid="att-1",
        filename=filename,
        file_type="application/pdf",
        uploaded_by="alice",
        message_uuid="msg-hi",
        created_at=datetime.datetime(2026, 3, 5, 10, 5, 0),
    )


def _ticket(messages=None, attachments=None) -> SimpleNamespace:
    return SimpleNamespace(
        uuid="t-1",
        subject="Need help",
        status=_enum("open"),
        priority=_enum("normal"),
        user_id="alice",
        user_name="Alice",
        user_email="alice@example.edu",
        team_id="team-1",
        assigned_to=None,
        messages=messages or [],
        attachments=attachments or [],
        read_by=["alice"],
        category="bug",
        created_at=datetime.datetime(2026, 3, 5, 9, 0, 0),
        updated_at=datetime.datetime(2026, 3, 5, 11, 0, 0),
        closed_at=None,
    )


class TestTicketToDict:
    def test_basic_shape_with_no_messages_or_attachments(self):
        d = _ticket_to_dict(_ticket())
        assert d["uuid"] == "t-1"
        assert d["status"] == "open"
        assert d["priority"] == "normal"
        assert d["messages"] == []
        assert d["attachments"] == []
        assert d["message_count"] == 0
        assert d["closed_at"] is None
        # Timestamps should be ISO strings with a timezone offset.
        assert d["created_at"].endswith("+00:00")

    def test_messages_and_attachments_serialized(self):
        msgs = [_message("first"), _message("second reply", is_support_reply=True)]
        atts = [_attachment("notes.pdf")]
        d = _ticket_to_dict(_ticket(messages=msgs, attachments=atts))
        assert d["message_count"] == 2
        assert d["messages"][1]["is_support_reply"] is True
        assert d["attachments"][0]["filename"] == "notes.pdf"
        assert d["attachments"][0]["created_at"].endswith("+00:00")


class TestTicketSummary:
    def test_empty_ticket_fields_are_none(self):
        s = _ticket_summary(_ticket())
        assert s["message_count"] == 0
        assert s["last_message_preview"] is None
        assert s["last_message_at"] is None
        assert s["last_message_is_support_reply"] is None
        assert s["last_message_user_id"] is None

    def test_last_message_preview_truncated_to_120_chars(self):
        long = "A" * 500
        msg = _message(long)
        s = _ticket_summary(_ticket(messages=[msg]))
        assert s["last_message_preview"] == "A" * 120
        assert s["message_count"] == 1

    def test_reflects_last_message_metadata(self):
        first = _message("older")
        last = _message("latest", is_support_reply=True)
        s = _ticket_summary(_ticket(messages=[first, last]))
        assert s["last_message_preview"] == "latest"
        assert s["last_message_is_support_reply"] is True
        assert s["last_message_user_id"] == "alice"
        assert s["read_by"] == ["alice"]
