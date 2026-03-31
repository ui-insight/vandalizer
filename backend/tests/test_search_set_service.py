"""Tests for app.services.search_set_service — SearchSet and SearchSetItem CRUD.

Mocks Beanie models to test business logic without MongoDB.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_search_set(uuid="ss-uuid", title="Grant Fields", user_id="user1", team_id=None, extraction_config=None, item_order=None):
    ss = MagicMock()
    ss.id = PydanticObjectId()
    ss.uuid = uuid
    ss.title = title
    ss.user_id = user_id
    ss.team_id = team_id
    ss.set_type = "extraction"
    ss.extraction_config = extraction_config or {}
    ss.item_order = item_order or []
    ss.save = AsyncMock()
    ss.insert = AsyncMock()
    ss.delete = AsyncMock()
    ss.get_items = AsyncMock(return_value=[])
    return ss


def _make_item(searchphrase="PI Name", searchset="ss-uuid", searchtype="extraction", is_optional=False, enum_values=None):
    item = MagicMock()
    item.id = PydanticObjectId()
    item.searchphrase = searchphrase
    item.searchset = searchset
    item.searchtype = searchtype
    item.title = searchphrase
    item.is_optional = is_optional
    item.enum_values = enum_values or []
    item.user_id = "user1"
    item.save = AsyncMock()
    item.insert = AsyncMock()
    item.delete = AsyncMock()
    return item


# ---------------------------------------------------------------------------
# create_search_set
# ---------------------------------------------------------------------------


class TestCreateSearchSet:
    @pytest.mark.asyncio
    async def test_creates_and_inserts(self):
        with patch("app.services.search_set_service.SearchSet") as MockSS:
            mock_ss = _make_search_set()
            MockSS.return_value = mock_ss

            from app.services.search_set_service import create_search_set

            result = await create_search_set("My Set", "user1", "extraction")

        assert result is mock_ss
        mock_ss.insert.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_search_sets
# ---------------------------------------------------------------------------


class TestListSearchSets:
    @pytest.mark.asyncio
    async def test_returns_all_when_no_user(self):
        mock_find = MagicMock()
        mock_find.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        with patch("app.services.search_set_service.SearchSet") as MockSS:
            MockSS.find.return_value = mock_find

            from app.services.search_set_service import list_search_sets

            result = await list_search_sets(user=None)

        assert result == []

    @pytest.mark.asyncio
    async def test_scopes_to_user_own_when_mine(self):
        user = MagicMock()
        user.user_id = "alice"
        user.current_team = PydanticObjectId()

        mock_find = MagicMock()
        mock_find.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        with patch("app.services.search_set_service.SearchSet") as MockSS:
            MockSS.find.return_value = mock_find

            from app.services.search_set_service import list_search_sets

            result = await list_search_sets(user=user, scope="mine")

        assert result == []
        call_args = MockSS.find.call_args[0][0]
        assert call_args["user_id"] == "alice"

    @pytest.mark.asyncio
    async def test_team_scope_returns_empty_without_team(self):
        user = MagicMock()
        user.user_id = "alice"
        user.current_team = None

        from app.services.search_set_service import list_search_sets

        result = await list_search_sets(user=user, scope="team")
        assert result == []


# ---------------------------------------------------------------------------
# get_search_set / update / delete
# ---------------------------------------------------------------------------


class TestSearchSetCRUD:
    @pytest.mark.asyncio
    async def test_get_search_set_found(self):
        ss = _make_search_set()
        with patch("app.services.search_set_service.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)

            from app.services.search_set_service import get_search_set

            result = await get_search_set("ss-uuid")
        assert result is ss

    @pytest.mark.asyncio
    async def test_get_search_set_not_found(self):
        with patch("app.services.search_set_service.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=None)

            from app.services.search_set_service import get_search_set

            result = await get_search_set("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_search_set_title(self):
        ss = _make_search_set(title="Old Title")
        with patch("app.services.search_set_service.get_search_set", new_callable=AsyncMock, return_value=ss):
            from app.services.search_set_service import update_search_set

            result = await update_search_set("ss-uuid", title="New Title")

        assert result.title == "New Title"
        ss.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_returns_none_when_not_found(self):
        with patch("app.services.search_set_service.get_search_set", new_callable=AsyncMock, return_value=None):
            from app.services.search_set_service import update_search_set

            result = await update_search_set("missing", title="X")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_search_set(self):
        ss = _make_search_set()
        mock_find = MagicMock()
        mock_find.delete = AsyncMock()

        with (
            patch("app.services.search_set_service.get_search_set", new_callable=AsyncMock, return_value=ss),
            patch("app.services.search_set_service.SearchSetItem") as MockItem,
        ):
            MockItem.find.return_value = mock_find

            from app.services.search_set_service import delete_search_set

            result = await delete_search_set("ss-uuid")

        assert result is True
        ss.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        with patch("app.services.search_set_service.get_search_set", new_callable=AsyncMock, return_value=None):
            from app.services.search_set_service import delete_search_set

            result = await delete_search_set("missing")
        assert result is False


# ---------------------------------------------------------------------------
# clone_search_set
# ---------------------------------------------------------------------------


class TestCloneSearchSet:
    @pytest.mark.asyncio
    async def test_clone_creates_copy(self):
        original = _make_search_set(uuid="orig", title="Original")
        original.get_items = AsyncMock(return_value=[_make_item(searchphrase="PI Name")])

        clone_ss = _make_search_set(uuid="clone-uuid", title="Original (Copy)")

        with (
            patch("app.services.search_set_service.get_search_set", new_callable=AsyncMock, return_value=original),
            patch("app.services.search_set_service.SearchSet") as MockSS,
            patch("app.services.search_set_service.SearchSetItem") as MockItem,
            patch("app.models.user.User") as MockUser,
        ):
            MockSS.return_value = clone_ss
            mock_item = _make_item()
            MockItem.return_value = mock_item
            MockUser.find_one = AsyncMock(return_value=None)

            from app.services.search_set_service import clone_search_set

            result = await clone_search_set("orig", "user2")

        assert result is clone_ss
        clone_ss.insert.assert_awaited_once()
        mock_item.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clone_returns_none_when_not_found(self):
        with patch("app.services.search_set_service.get_search_set", new_callable=AsyncMock, return_value=None):
            from app.services.search_set_service import clone_search_set

            result = await clone_search_set("missing", "user1")
        assert result is None


# ---------------------------------------------------------------------------
# Item CRUD
# ---------------------------------------------------------------------------


class TestSearchSetItemCRUD:
    @pytest.mark.asyncio
    async def test_add_item(self):
        with patch("app.services.search_set_service.SearchSetItem") as MockItem:
            mock_item = _make_item()
            MockItem.return_value = mock_item

            from app.services.search_set_service import add_item

            result = await add_item("ss-uuid", "PI Name")

        assert result is mock_item
        mock_item.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_item(self):
        item = _make_item(searchphrase="Old")

        with patch("app.services.search_set_service.SearchSetItem") as MockItem:
            MockItem.get = AsyncMock(return_value=item)

            from app.services.search_set_service import update_item

            result = await update_item(str(PydanticObjectId()), searchphrase="New", is_optional=True)

        assert result.searchphrase == "New"
        assert result.is_optional is True
        item.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_item_not_found(self):
        with patch("app.services.search_set_service.SearchSetItem") as MockItem:
            MockItem.get = AsyncMock(return_value=None)

            from app.services.search_set_service import update_item

            result = await update_item(str(PydanticObjectId()), searchphrase="X")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_item(self):
        item = _make_item()

        with patch("app.services.search_set_service.get_search_set_item", new_callable=AsyncMock, return_value=item):
            from app.services.search_set_service import delete_item

            result = await delete_item(str(PydanticObjectId()))

        assert result is True
        item.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_item_not_found(self):
        with patch("app.services.search_set_service.get_search_set_item", new_callable=AsyncMock, return_value=None):
            from app.services.search_set_service import delete_item

            result = await delete_item(str(PydanticObjectId()))
        assert result is False

    @pytest.mark.asyncio
    async def test_reorder_items(self):
        ss = _make_search_set()

        with patch("app.services.search_set_service.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)

            from app.services.search_set_service import reorder_items

            result = await reorder_items("ss-uuid", ["id1", "id2", "id3"])

        assert result is True
        assert ss.item_order == ["id1", "id2", "id3"]
        ss.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reorder_returns_false_when_not_found(self):
        with patch("app.services.search_set_service.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=None)

            from app.services.search_set_service import reorder_items

            result = await reorder_items("missing", ["id1"])
        assert result is False

    @pytest.mark.asyncio
    async def test_get_extraction_keys(self):
        items = [_make_item(searchphrase="PI Name"), _make_item(searchphrase="Award Amount")]

        with patch("app.services.search_set_service.SearchSetItem") as MockItem:
            mock_find = MagicMock()
            mock_find.to_list = AsyncMock(return_value=items)
            MockItem.find.return_value = mock_find

            from app.services.search_set_service import get_extraction_keys

            result = await get_extraction_keys("ss-uuid")

        assert result == ["PI Name", "Award Amount"]
