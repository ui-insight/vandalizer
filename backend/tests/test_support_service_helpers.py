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


def _message(
    content: str = "hi",
    is_support_reply: bool = False,
    edited_at: datetime.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=f"msg-{content[:3]}",
        user_id="alice",
        user_name="Alice",
        content=content,
        is_support_reply=is_support_reply,
        created_at=datetime.datetime(2026, 3, 5, 10, 0, 0),
        edited_at=edited_at,
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


def _ticket(
    messages=None,
    attachments=None,
    watchers=None,
    ticket_number: int | None = 1042,
) -> SimpleNamespace:
    return SimpleNamespace(
        uuid="t-1",
        ticket_number=ticket_number,
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
        tags=[],
        watchers=watchers if watchers is not None else [],
        created_at=datetime.datetime(2026, 3, 5, 9, 0, 0),
        updated_at=datetime.datetime(2026, 3, 5, 11, 0, 0),
        closed_at=None,
    )


class TestTicketToDict:
    async def test_basic_shape_with_no_messages_or_attachments(self):
        d = await _ticket_to_dict(_ticket())
        assert d["uuid"] == "t-1"
        assert d["ticket_number"] == 1042
        assert d["status"] == "open"
        assert d["priority"] == "normal"
        assert d["messages"] == []
        assert d["attachments"] == []
        assert d["message_count"] == 0
        assert d["closed_at"] is None
        assert d["watchers"] == []
        # Timestamps should be ISO strings with a timezone offset.
        assert d["created_at"].endswith("+00:00")

    async def test_messages_and_attachments_serialized(self):
        msgs = [_message("first"), _message("second reply", is_support_reply=True)]
        atts = [_attachment("notes.pdf")]
        d = await _ticket_to_dict(_ticket(messages=msgs, attachments=atts))
        assert d["message_count"] == 2
        assert d["messages"][1]["is_support_reply"] is True
        assert d["messages"][0]["edited_at"] is None
        assert d["attachments"][0]["filename"] == "notes.pdf"
        assert d["attachments"][0]["created_at"].endswith("+00:00")

    async def test_edited_message_surfaces_edited_at(self):
        edited = datetime.datetime(2026, 3, 5, 10, 30, 0)
        msgs = [_message("first", edited_at=edited)]
        d = await _ticket_to_dict(_ticket(messages=msgs))
        assert d["messages"][0]["edited_at"] == "2026-03-05T10:30:00+00:00"

    async def test_legacy_ticket_without_number_serializes_as_none(self):
        d = await _ticket_to_dict(_ticket(ticket_number=None))
        assert d["ticket_number"] is None


class TestTicketSummary:
    def test_empty_ticket_fields_are_none(self):
        s = _ticket_summary(_ticket())
        assert s["message_count"] == 0
        assert s["last_message_preview"] is None
        assert s["last_message_at"] is None
        assert s["last_message_is_support_reply"] is None
        assert s["last_message_user_id"] is None
        assert s["watcher_ids"] == []
        assert s["ticket_number"] == 1042

    def test_summary_for_legacy_ticket_without_number(self):
        s = _ticket_summary(_ticket(ticket_number=None))
        assert s["ticket_number"] is None

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

    def test_watcher_ids_surfaced_for_list_view(self):
        s = _ticket_summary(_ticket(watchers=["bob", "carol"]))
        # List view returns just the ids — the client uses them to decide
        # whether to show a "Watching" badge without re-fetching the user.
        assert s["watcher_ids"] == ["bob", "carol"]


# ---------------------------------------------------------------------------
# Watcher view-permission helper in the router
# ---------------------------------------------------------------------------

class TestCanViewTicket:
    def _ticket_dict(self, owner: str = "alice", watchers=None) -> dict:
        return {
            "uuid": "t-1",
            "user_id": owner,
            "watchers": [
                {"user_id": w, "name": w, "email": None} for w in (watchers or [])
            ],
        }

    def _user(self, uid: str) -> SimpleNamespace:
        return SimpleNamespace(user_id=uid)

    def test_owner_can_view(self):
        from app.routers.support import _can_view_ticket
        assert _can_view_ticket(self._ticket_dict(), self._user("alice"), False)

    def test_support_can_view_anything(self):
        from app.routers.support import _can_view_ticket
        assert _can_view_ticket(self._ticket_dict(), self._user("agent"), True)

    def test_watcher_can_view(self):
        from app.routers.support import _can_view_ticket
        t = self._ticket_dict(watchers=["bob"])
        assert _can_view_ticket(t, self._user("bob"), False)

    def test_stranger_blocked(self):
        from app.routers.support import _can_view_ticket
        assert not _can_view_ticket(self._ticket_dict(), self._user("eve"), False)
