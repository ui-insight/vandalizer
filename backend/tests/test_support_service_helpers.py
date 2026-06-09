"""Tests for pure helpers in app.services.support_service.

The full ticket lifecycle (create/update/reply) hits MongoDB and Redis and
is covered by router-level tests. Here we exercise the ISO-UTC timestamp
helper and the two pydantic-to-dict serializers — the parts the UI
inspects on every list/detail call.
"""

from __future__ import annotations

import datetime
import re
from types import SimpleNamespace

from app.services.support_service import (
    _build_search_clause,
    _iso_utc,
    _ticket_summary,
    _ticket_to_dict,
    user_matches_support_contact,
)
from app.routers.support import (
    _drop_visible_helpers,
    _strip_for_non_support,
    _view,
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
    is_internal_note: bool = False,
    edited_at: datetime.datetime | None = None,
    user_id: str = "alice",
) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=f"msg-{content[:3]}",
        user_id=user_id,
        user_name=user_id.title(),
        content=content,
        is_support_reply=is_support_reply,
        is_internal_note=is_internal_note,
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


class TestInternalNotesSerialization:
    """Internal notes are agent-to-agent annotations. The service emits the
    raw view (every message + helper fields) and the router strips them for
    non-support callers — these tests cover the service half."""

    async def test_internal_note_flag_propagates_to_dict(self):
        msgs = [
            _message("customer ping"),
            _message("note for team", is_support_reply=True, is_internal_note=True, user_id="agent"),
        ]
        d = await _ticket_to_dict(_ticket(messages=msgs))
        assert d["messages"][0]["is_internal_note"] is False
        assert d["messages"][1]["is_internal_note"] is True

    def test_summary_carries_last_visible_helper_fields(self):
        # Customer ping, then an internal note from an agent. The "true last"
        # message is the note; the "last visible" is the customer ping. The
        # router uses these helper fields to swap into last_message_* for the
        # ticket owner so they don't see a phantom timestamp.
        first = _message("customer ping")
        note = _message("agent note", is_support_reply=True, is_internal_note=True, user_id="agent")
        s = _ticket_summary(_ticket(messages=[first, note]))
        assert s["last_message_preview"] == "agent note"
        assert s["last_message_is_internal_note"] is True
        assert s["last_visible_message_preview"] == "customer ping"
        assert s["last_visible_message_is_support_reply"] is False
        assert s["last_visible_message_user_id"] == "alice"
        assert s["visible_message_count"] == 1
        assert s["message_count"] == 2

    def test_summary_when_no_internal_note_present(self):
        first = _message("customer ping")
        reply = _message("agent reply", is_support_reply=True)
        s = _ticket_summary(_ticket(messages=[first, reply]))
        # No internal note → flag is False and the visible-helpers track the
        # absolute last message.
        assert s["last_message_is_internal_note"] is False
        assert s["last_visible_message_preview"] == "agent reply"
        assert s["visible_message_count"] == 2

    def test_summary_with_only_internal_note_has_no_visible_message(self):
        # Edge case: a ticket whose only message is somehow an internal note —
        # the customer should see "no messages" rather than a phantom preview.
        note = _message("just a note", is_support_reply=True, is_internal_note=True, user_id="agent")
        s = _ticket_summary(_ticket(messages=[note]))
        assert s["last_visible_message_preview"] is None
        assert s["last_visible_message_at"] is None
        assert s["visible_message_count"] == 0


# ---------------------------------------------------------------------------
# Support-contact matching — decides who counts as a support agent
# ---------------------------------------------------------------------------


class TestUserMatchesSupportContact:
    """Support contacts are typed by hand in the admin UI, so the matcher must
    tolerate the admin entering the email instead of the user_id, or using
    different casing — otherwise a configured agent silently can't see tickets.
    """

    def _user(self, user_id: str, email: str = "") -> SimpleNamespace:
        return SimpleNamespace(user_id=user_id, email=email)

    def test_exact_user_id_match(self):
        contact = {"user_id": "jdoe", "email": "jdoe@uidaho.edu", "name": "J Doe"}
        assert user_matches_support_contact(contact, self._user("jdoe"))

    def test_match_is_case_insensitive(self):
        # Registration lowercases user_id; an admin typing "JDoe" must still match.
        contact = {"user_id": "JDoe", "email": "", "name": "J Doe"}
        assert user_matches_support_contact(contact, self._user("jdoe"))

    def test_contact_entered_by_email_matches_on_email(self):
        # Admin typed the email into the user_id box (a common mistake) — still
        # resolves because we compare emails too.
        contact = {"user_id": "", "email": "jdoe@uidaho.edu", "name": "J Doe"}
        user = self._user("jdoe", email="jdoe@uidaho.edu")
        assert user_matches_support_contact(contact, user)

    def test_short_username_contact_matches_oauth_upn_via_email(self):
        # OAuth account: user_id is the full UPN, but the contact's email lines
        # up with the account email.
        contact = {"user_id": "jdoe", "email": "jdoe@uidaho.edu", "name": "J Doe"}
        user = self._user("jdoe@uidaho.edu", email="jdoe@uidaho.edu")
        assert user_matches_support_contact(contact, user)

    def test_no_match_for_unrelated_user(self):
        contact = {"user_id": "jdoe", "email": "jdoe@uidaho.edu", "name": "J Doe"}
        assert not user_matches_support_contact(
            contact, self._user("eve", email="eve@uidaho.edu")
        )

    def test_blank_contact_fields_do_not_match_blank_user_fields(self):
        # Empty strings must not collapse into a match (both sides drop blanks).
        contact = {"user_id": "", "email": "", "name": "Nobody"}
        assert not user_matches_support_contact(contact, self._user("", email=""))


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


# ---------------------------------------------------------------------------
# Search clause builder — powers the Support Center search box
# ---------------------------------------------------------------------------


class TestBuildSearchClause:
    def test_empty_string_returns_none(self):
        assert _build_search_clause("") is None
        assert _build_search_clause("   ") is None
        assert _build_search_clause(None) is None

    def test_text_search_covers_subject_user_and_message(self):
        clause = _build_search_clause("alice")
        assert clause is not None
        fields = [next(iter(c)) for c in clause["$or"]]
        assert "subject" in fields
        assert "user_name" in fields
        assert "user_email" in fields
        assert "messages.content" in fields
        # All field clauses are case-insensitive regex.
        for entry in clause["$or"]:
            for field, value in entry.items():
                if field == "ticket_number":
                    continue
                assert value == {"$regex": "alice", "$options": "i"}

    def test_numeric_search_adds_ticket_number_match(self):
        clause = _build_search_clause("1024")
        assert clause is not None
        ticket_number_clauses = [
            c for c in clause["$or"] if "ticket_number" in c
        ]
        assert ticket_number_clauses == [{"ticket_number": 1024}]

    def test_hash_prefixed_number_also_hits_ticket_number(self):
        # Agents copy "#1024" from the UI — both should work.
        clause = _build_search_clause("#1024")
        assert clause is not None
        assert {"ticket_number": 1024} in clause["$or"]

    def test_regex_specials_are_escaped(self):
        # A user typing ".*" must not match every ticket — escape regex specials.
        clause = _build_search_clause(".*")
        assert clause is not None
        for entry in clause["$or"]:
            for field, value in entry.items():
                if field == "ticket_number":
                    continue
                # Escaped pattern contains backslashes, not raw "." or "*".
                assert value["$regex"] == re.escape(".*")


# ---------------------------------------------------------------------------
# Attachment delete-permission helper
# ---------------------------------------------------------------------------


class TestCanDeleteAttachment:
    def _att(self, uploaded_by: str = "alice") -> dict:
        return {"uuid": "att-1", "filename": "screen.png", "uploaded_by": uploaded_by}

    def _user(self, uid: str) -> SimpleNamespace:
        return SimpleNamespace(user_id=uid)

    def test_uploader_can_delete_own_attachment(self):
        from app.routers.support import _can_delete_attachment
        assert _can_delete_attachment(self._att("alice"), self._user("alice"), False)

    def test_non_uploader_non_support_cannot_delete(self):
        # The end-user sitting on a ticket can't nuke someone else's evidence.
        from app.routers.support import _can_delete_attachment
        assert not _can_delete_attachment(
            self._att("alice"), self._user("bob"), False,
        )

    def test_support_can_delete_anyone_attachment(self):
        # Agents need this to clean up accidental/sensitive uploads.
        from app.routers.support import _can_delete_attachment
        assert _can_delete_attachment(self._att("alice"), self._user("agent"), True)


# ---------------------------------------------------------------------------
# Router payload stripping — what each caller is allowed to see
# ---------------------------------------------------------------------------


def _ticket_payload_with_note(message_count: int = 2) -> dict:
    """Build a ticket dict shaped like what the service emits, including the
    last_visible_* scaffolding the router uses to strip internal notes."""
    return {
        "uuid": "t-1",
        "messages": [
            {"uuid": "m1", "content": "hi", "is_support_reply": False, "is_internal_note": False},
            {"uuid": "m2", "content": "note", "is_support_reply": True, "is_internal_note": True},
        ][:message_count],
        "message_count": message_count,
        "tags": ["billing", "p1"],
    }


def _summary_payload_with_note() -> dict:
    return {
        "uuid": "t-1",
        "message_count": 2,
        "visible_message_count": 1,
        "last_message_preview": "agent note",
        "last_message_at": "2026-03-05T10:00:00+00:00",
        "last_message_is_support_reply": True,
        "last_message_is_internal_note": True,
        "last_message_user_id": "agent",
        "last_visible_message_preview": "customer ping",
        "last_visible_message_at": "2026-03-05T09:00:00+00:00",
        "last_visible_message_is_support_reply": False,
        "last_visible_message_user_id": "alice",
        "tags": ["billing"],
    }


class TestViewStripping:
    def test_non_support_loses_tags_and_internal_notes_in_detail(self):
        payload = _ticket_payload_with_note()
        out = _view(payload, is_support=False)
        assert "tags" not in out
        # The internal note is filtered out and message_count reflects the
        # filtered count so the UI doesn't show a phantom unread.
        assert [m["uuid"] for m in out["messages"]] == ["m1"]
        assert out["message_count"] == 1

    def test_non_support_summary_swaps_in_last_visible(self):
        out = _view(_summary_payload_with_note(), is_support=False)
        # The "true last" was an internal note, so the requester sees the last
        # visible message instead — and the scaffolding fields are dropped.
        assert out["last_message_preview"] == "customer ping"
        assert out["last_message_is_support_reply"] is False
        assert out["last_message_user_id"] == "alice"
        assert out["message_count"] == 1
        assert "last_message_is_internal_note" not in out
        assert "last_visible_message_preview" not in out
        assert "tags" not in out

    def test_support_keeps_tags_and_internal_notes_but_drops_scaffolding(self):
        payload = _ticket_payload_with_note()
        out = _view(payload, is_support=True)
        # Tags and the internal note both stay for agents.
        assert out["tags"] == ["billing", "p1"]
        assert [m["uuid"] for m in out["messages"]] == ["m1", "m2"]
        assert out["message_count"] == 2

    def test_support_summary_keeps_internal_flag_drops_visible_helpers(self):
        out = _view(_summary_payload_with_note(), is_support=True)
        # Agents see the absolute-last message and a flag noting it was an
        # internal note (so the list view can label it). The visible-helpers
        # were just scaffolding for the stripping path — never leak them.
        assert out["last_message_preview"] == "agent note"
        assert out["last_message_is_internal_note"] is True
        for key in (
            "last_visible_message_preview",
            "last_visible_message_at",
            "last_visible_message_is_support_reply",
            "last_visible_message_user_id",
            "visible_message_count",
        ):
            assert key not in out

    def test_drop_visible_helpers_is_idempotent(self):
        payload = {"uuid": "t-1", "last_message_preview": "x"}
        _drop_visible_helpers(payload)
        _drop_visible_helpers(payload)
        assert payload == {"uuid": "t-1", "last_message_preview": "x"}

    def test_strip_for_non_support_handles_summary_without_messages(self):
        # Summaries don't carry the messages list; the stripper must still
        # produce a clean payload for the requester.
        out = _strip_for_non_support(_summary_payload_with_note())
        assert "messages" not in out
        assert "tags" not in out
        assert out["last_message_preview"] == "customer ping"
