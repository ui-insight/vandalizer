"""Tests for app.services.notification_service.

All the functions here are thin CRUD wrappers around the Notification Beanie
model. The interesting behaviors worth locking in are the coalesce-on-duplicate
rule and the _to_dict serialization shape.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notification_service import (
    _COALESCE_KINDS,
    _to_dict,
    create_notification,
    list_notifications,
    mark_all_read,
    mark_read,
    mark_read_for_item,
    unread_count,
)


def _notif(
    *,
    uuid: str = "n-1",
    kind: str = "support_reply",
    title: str = "New reply",
    body: str | None = "Body",
    link: str | None = "/x",
    item_kind: str | None = "ticket",
    item_id: str | None = "t-1",
    item_name: str | None = "Ticket #1",
    read: bool = False,
    created_at: datetime.datetime | None = None,
) -> SimpleNamespace:
    """A SimpleNamespace that quacks like a Notification Document."""
    n = SimpleNamespace(
        id="oid-1",
        uuid=uuid,
        kind=kind,
        title=title,
        body=body,
        link=link,
        item_kind=item_kind,
        item_id=item_id,
        item_name=item_name,
        request_uuid=None,
        read=read,
        created_at=created_at or datetime.datetime(2026, 3, 5, 12, 0, 0),
    )
    # Async save/insert methods so service calls can await them
    n.save = AsyncMock()
    n.insert = AsyncMock()
    return n


class TestToDict:
    def test_serialized_fields_match_model(self):
        now = datetime.datetime(2026, 3, 5, 12, 0, 0)
        n = _notif(created_at=now)
        d = _to_dict(n)
        assert d["uuid"] == "n-1"
        assert d["kind"] == "support_reply"
        assert d["title"] == "New reply"
        assert d["body"] == "Body"
        assert d["link"] == "/x"
        assert d["item_kind"] == "ticket"
        assert d["item_id"] == "t-1"
        assert d["item_name"] == "Ticket #1"
        assert d["read"] is False
        assert d["created_at"] == now.isoformat()

    def test_missing_created_at_is_none(self):
        n = _notif()
        n.created_at = None
        assert _to_dict(n)["created_at"] is None


class TestCoalesceKinds:
    def test_support_kinds_are_coalesced(self):
        # Regression guard: if someone drops a kind out of the frozenset we
        # want the test to flag it before a user sees duplicate bells.
        assert "support_reply" in _COALESCE_KINDS
        assert "support_new_message" in _COALESCE_KINDS
        assert "support_new_ticket" in _COALESCE_KINDS

    def test_non_support_kinds_are_not_coalesced(self):
        assert "verification_passed" not in _COALESCE_KINDS
        assert "workflow_complete" not in _COALESCE_KINDS


class TestCreateNotification:
    @pytest.mark.asyncio
    async def test_coalesces_onto_existing_unread_notification(self):
        existing = _notif(kind="support_reply", title="Old title")
        # Build a fresh AsyncMock so we can assert it was awaited
        existing.save = AsyncMock()

        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find_one = AsyncMock(return_value=existing)

            result = await create_notification(
                user_id="alice",
                kind="support_reply",
                title="Newer title",
                body="Newer body",
                item_kind="ticket",
                item_id="t-1",
            )

        # The existing record was mutated and saved — no new insert.
        existing.save.assert_awaited_once()
        assert existing.title == "Newer title"
        assert existing.body == "Newer body"
        assert result["title"] == "Newer title"

    @pytest.mark.asyncio
    async def test_creates_new_when_no_existing_found(self):
        new_n = _notif(uuid="n-new", kind="support_reply", title="Fresh")
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find_one = AsyncMock(return_value=None)
            MockN.return_value = new_n  # Notification(**kwargs) → new_n

            result = await create_notification(
                user_id="alice",
                kind="support_reply",
                title="Fresh",
                item_kind="ticket",
                item_id="t-1",
            )

        new_n.insert.assert_awaited_once()
        assert result["title"] == "Fresh"
        assert result["uuid"] == "n-new"

    @pytest.mark.asyncio
    async def test_non_coalesce_kind_always_creates(self):
        new_n = _notif(kind="verification_passed", title="Cert ready")
        with patch("app.services.notification_service.Notification") as MockN:
            # find_one should NOT be called for non-coalesce kinds
            MockN.find_one = AsyncMock()
            MockN.return_value = new_n

            await create_notification(
                user_id="alice",
                kind="verification_passed",
                title="Cert ready",
                item_kind="cert",
                item_id="c-1",
            )

        MockN.find_one.assert_not_called()
        new_n.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_item_ref_skips_coalesce(self):
        """Even a coalesce kind can't coalesce without item_kind+item_id."""
        new_n = _notif(kind="support_reply", title="No item")
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find_one = AsyncMock()
            MockN.return_value = new_n

            await create_notification(
                user_id="alice",
                kind="support_reply",
                title="No item",
                item_kind=None,
                item_id=None,
            )

        MockN.find_one.assert_not_called()
        new_n.insert.assert_awaited_once()


class TestListNotifications:
    @pytest.mark.asyncio
    async def test_default_query_returns_all_for_user(self):
        notifs = [_notif(uuid="a"), _notif(uuid="b")]
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=notifs)

        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find = MagicMock(return_value=chain)
            result = await list_notifications("alice")

        assert [n["uuid"] for n in result] == ["a", "b"]
        MockN.find.assert_called_once_with({"user_id": "alice"})
        chain.sort.assert_called_once_with("-created_at")
        chain.limit.assert_called_once_with(50)

    @pytest.mark.asyncio
    async def test_unread_only_adds_filter(self):
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=[])

        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find = MagicMock(return_value=chain)
            await list_notifications("alice", unread_only=True, limit=10)

        MockN.find.assert_called_once_with({"user_id": "alice", "read": False})
        chain.limit.assert_called_once_with(10)


class TestUnreadCount:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        q = MagicMock()
        q.count = AsyncMock(return_value=7)
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find = MagicMock(return_value=q)
            assert await unread_count("alice") == 7


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_missing_notification_returns_false(self):
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find_one = AsyncMock(return_value=None)
            assert await mark_read("alice", "ghost") is False

    @pytest.mark.asyncio
    async def test_found_notification_marked_read(self):
        n = _notif()
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find_one = AsyncMock(return_value=n)
            ok = await mark_read("alice", "n-1")

        assert ok is True
        assert n.read is True
        n.save.assert_awaited_once()


class TestBulkReadHelpers:
    @pytest.mark.asyncio
    async def test_mark_read_for_item_returns_modified_count(self):
        q = MagicMock()
        q.update_many = AsyncMock(return_value=SimpleNamespace(modified_count=3))
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find = MagicMock(return_value=q)
            assert await mark_read_for_item("alice", "ticket", "t-1") == 3

    @pytest.mark.asyncio
    async def test_mark_read_for_item_handles_none_result(self):
        q = MagicMock()
        q.update_many = AsyncMock(return_value=None)
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find = MagicMock(return_value=q)
            assert await mark_read_for_item("alice", "ticket", "t-1") == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_modified_count(self):
        q = MagicMock()
        q.update_many = AsyncMock(return_value=SimpleNamespace(modified_count=5))
        with patch("app.services.notification_service.Notification") as MockN:
            MockN.find = MagicMock(return_value=q)
            assert await mark_all_read("alice") == 5
