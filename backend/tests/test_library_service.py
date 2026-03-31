"""Tests for app.services.library_service — Library, LibraryItem, and folder CRUD.

Mocks Beanie models to test business logic without MongoDB.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(user_id="user1"):
    user = MagicMock()
    user.user_id = user_id
    return user


def _make_library(
    scope="personal",
    title="My Library",
    owner_user_id="user1",
    items=None,
    team=None,
    description=None,
):
    lib = MagicMock()
    lib.id = PydanticObjectId()
    lib.scope = MagicMock()
    lib.scope.value = scope
    lib.title = title
    lib.description = description
    lib.owner_user_id = owner_user_id
    lib.team = team
    lib.items = items if items is not None else []
    lib.created_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    lib.updated_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    lib.save = AsyncMock()
    lib.insert = AsyncMock()
    lib.delete = AsyncMock()
    return lib


def _make_library_item(
    kind_value="workflow",
    item_id=None,
    tags=None,
    note=None,
    folder=None,
    pinned=False,
    favorited=False,
    verified=False,
    added_by_user_id="user1",
):
    item = MagicMock()
    item.id = PydanticObjectId()
    item.item_id = item_id or PydanticObjectId()
    item.kind = MagicMock()
    item.kind.value = kind_value
    item.tags = tags or []
    item.note = note
    item.folder = folder
    item.pinned = pinned
    item.favorited = favorited
    item.verified = verified
    item.added_by_user_id = added_by_user_id
    item.created_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    item.last_used_at = None
    item.save = AsyncMock()
    item.insert = AsyncMock()
    item.delete = AsyncMock()
    item.set = AsyncMock()
    return item


def _make_folder(uuid="folder-1", name="Grants", scope_value="personal", parent_id=None, owner_user_id="user1"):
    f = MagicMock()
    f.id = PydanticObjectId()
    f.uuid = uuid
    f.name = name
    f.parent_id = parent_id
    f.scope = MagicMock()
    f.scope.value = scope_value
    f.owner_user_id = owner_user_id
    f.team = None
    f.save = AsyncMock()
    f.insert = AsyncMock()
    f.delete = AsyncMock()
    return f


# ---------------------------------------------------------------------------
# get_or_create_personal_library
# ---------------------------------------------------------------------------


class TestGetOrCreatePersonalLibrary:
    @pytest.mark.asyncio
    async def test_returns_existing_library(self):
        existing = _make_library()
        with patch("app.services.library_service.Library") as MockLib:
            MockLib.find_one = AsyncMock(return_value=existing)
            from app.services.library_service import get_or_create_personal_library

            result = await get_or_create_personal_library("user1")
            assert result is existing
            MockLib.find_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_new_when_not_found(self):
        mock_lib = _make_library()
        with patch("app.services.library_service.Library") as MockLib:
            MockLib.find_one = AsyncMock(return_value=None)
            MockLib.return_value = mock_lib
            from app.services.library_service import get_or_create_personal_library

            result = await get_or_create_personal_library("user1")
            mock_lib.insert.assert_awaited_once()
            assert result is mock_lib


# ---------------------------------------------------------------------------
# get_or_create_verified_library
# ---------------------------------------------------------------------------


class TestGetOrCreateVerifiedLibrary:
    @pytest.mark.asyncio
    async def test_returns_existing_with_items(self):
        existing = _make_library(scope="verified", items=[PydanticObjectId()])
        with patch("app.services.library_service.Library") as MockLib:
            MockLib.find_one = AsyncMock(return_value=existing)
            from app.services.library_service import get_or_create_verified_library

            result = await get_or_create_verified_library()
            assert result is existing

    @pytest.mark.asyncio
    async def test_backfills_empty_verified_library(self):
        existing = _make_library(scope="verified", items=[])
        with (
            patch("app.services.library_service.Library") as MockLib,
            patch("app.services.library_service.LibraryItem") as MockItem,
        ):
            MockLib.find_one = AsyncMock(return_value=existing)
            # No verified items to backfill
            mock_find = MagicMock()
            mock_find.to_list = AsyncMock(return_value=[])
            MockItem.find = MagicMock(return_value=mock_find)

            from app.services.library_service import get_or_create_verified_library

            result = await get_or_create_verified_library()
            assert result is existing


# ---------------------------------------------------------------------------
# update_library
# ---------------------------------------------------------------------------


class TestUpdateLibrary:
    @pytest.mark.asyncio
    async def test_updates_title_and_description(self):
        lib = _make_library(title="Old", description="Old desc")
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library = AsyncMock(return_value=lib)
            from app.services.library_service import update_library

            result = await update_library(str(lib.id), user, title="New Title", description="New desc")
            assert result is not None
            assert lib.title == "New Title"
            assert lib.description == "New desc"
            lib.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_authorized(self):
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library = AsyncMock(return_value=None)
            from app.services.library_service import update_library

            result = await update_library("abc123", user, title="X")
            assert result is None


# ---------------------------------------------------------------------------
# delete_library
# ---------------------------------------------------------------------------


class TestDeleteLibrary:
    @pytest.mark.asyncio
    async def test_cascades_delete_items(self):
        item1 = _make_library_item()
        item2 = _make_library_item()
        lib = _make_library(items=[item1.id, item2.id])
        user = _make_user()
        with (
            patch("app.services.library_service.access_control") as mock_ac,
            patch("app.services.library_service.LibraryItem") as MockItem,
        ):
            mock_ac.get_authorized_library = AsyncMock(return_value=lib)
            MockItem.get = AsyncMock(side_effect=[item1, item2])

            from app.services.library_service import delete_library

            result = await delete_library(str(lib.id), user)
            assert result is True
            item1.delete.assert_awaited_once()
            item2.delete.assert_awaited_once()
            lib.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_authorized(self):
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library = AsyncMock(return_value=None)
            from app.services.library_service import delete_library

            result = await delete_library("abc123", user)
            assert result is False


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------


class TestAddItem:
    @pytest.mark.asyncio
    async def test_adds_workflow_item(self):
        lib = _make_library()
        user = _make_user()
        mock_wf = MagicMock()
        mock_wf.name = "My WF"
        mock_wf.description = "desc"
        mock_item = _make_library_item()
        item_id = str(PydanticObjectId())

        with (
            patch("app.services.library_service.access_control") as mock_ac,
            patch("app.services.library_service.LibraryItem") as MockItem,
            patch("app.services.library_service.Workflow") as MockWF,
        ):
            mock_ac.get_authorized_library = AsyncMock(return_value=lib)
            mock_ac.get_authorized_workflow = AsyncMock(return_value=mock_wf)
            MockItem.return_value = mock_item
            MockWF.get = AsyncMock(return_value=mock_wf)

            from app.services.library_service import add_item

            result = await add_item(str(lib.id), user, item_id, "workflow")
            mock_item.insert.assert_awaited_once()
            lib.save.assert_awaited_once()
            assert lib.items[-1] == mock_item.id

    @pytest.mark.asyncio
    async def test_rejects_unknown_kind(self):
        lib = _make_library()
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library = AsyncMock(return_value=lib)
            from app.services.library_service import add_item

            result = await add_item(str(lib.id), user, str(PydanticObjectId()), "unknown_kind")
            assert result is None


# ---------------------------------------------------------------------------
# remove_item
# ---------------------------------------------------------------------------


class TestRemoveItem:
    @pytest.mark.asyncio
    async def test_removes_item_from_library(self):
        item = _make_library_item()
        lib = _make_library(items=[item.id])
        user = _make_user()
        with (
            patch("app.services.library_service.access_control") as mock_ac,
            patch("app.services.library_service.LibraryItem") as MockItem,
        ):
            mock_ac.get_authorized_library = AsyncMock(return_value=lib)
            MockItem.get = AsyncMock(return_value=item)

            from app.services.library_service import remove_item

            result = await remove_item(str(lib.id), str(item.id), user)
            assert result is True
            item.delete.assert_awaited_once()
            lib.save.assert_awaited_once()
            assert item.id not in lib.items


# ---------------------------------------------------------------------------
# update_item
# ---------------------------------------------------------------------------


class TestUpdateItem:
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Beanie model class attrs not available on MagicMock")
    async def test_updates_note_and_tags(self):
        item = _make_library_item()
        mock_wf = MagicMock()
        mock_wf.name = "WF"
        mock_wf.description = "d"
        user = _make_user()
        with (
            patch("app.services.library_service.access_control") as mock_ac,
            patch("app.services.library_service.Workflow") as MockWF,
        ):
            mock_ac.get_authorized_library_item = AsyncMock(return_value=item)
            # For _dereference_item
            MockWF.get = AsyncMock(return_value=mock_wf)

            from app.services.library_service import update_item

            result = await update_item(str(item.id), user, note="updated", tags=["a", "b"])
            item.set.assert_awaited_once()
            assert item.note == "updated"
            assert item.tags == ["a", "b"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_authorized(self):
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library_item = AsyncMock(return_value=None)
            from app.services.library_service import update_item

            result = await update_item("abc", user, note="x")
            assert result is None


# ---------------------------------------------------------------------------
# touch_item
# ---------------------------------------------------------------------------


class TestTouchItem:
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Beanie model class attrs not available on MagicMock")
    async def test_updates_last_used_at(self):
        item = _make_library_item()
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library_item = AsyncMock(return_value=item)
            from app.services.library_service import touch_item

            result = await touch_item(str(item.id), user)
            assert result is True
            item.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library_item = AsyncMock(return_value=None)
            from app.services.library_service import touch_item

            result = await touch_item("nonexistent", user)
            assert result is False


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_creates_personal_folder(self):
        user = _make_user()
        mock_folder = _make_folder()
        with patch("app.services.library_service.LibraryFolder") as MockFolder:
            MockFolder.return_value = mock_folder
            from app.services.library_service import create_folder

            result = await create_folder("personal", user, "My Folder")
            mock_folder.insert.assert_awaited_once()
            assert result["name"] == "Grants"

    @pytest.mark.asyncio
    async def test_team_folder_requires_team_id(self):
        user = _make_user()
        from app.services.library_service import create_folder

        with pytest.raises(ValueError, match="team_id is required"):
            await create_folder("team", user, "Folder")


class TestDeleteFolder:
    @pytest.mark.asyncio
    async def test_deletes_folder_and_moves_items_to_root(self):
        folder = _make_folder()
        user = _make_user()
        item_in_folder = _make_library_item(folder="folder-1")
        child_folder = _make_folder(uuid="child-1", parent_id="folder-1")

        with (
            patch("app.services.library_service.access_control") as mock_ac,
            patch("app.services.library_service.LibraryItem") as MockItem,
            patch("app.services.library_service.LibraryFolder") as MockFolder,
        ):
            mock_ac.get_authorized_library_folder = AsyncMock(return_value=folder)
            mock_find_items = MagicMock()
            mock_find_items.to_list = AsyncMock(return_value=[item_in_folder])
            MockItem.find = MagicMock(return_value=mock_find_items)
            mock_find_children = MagicMock()
            mock_find_children.to_list = AsyncMock(return_value=[child_folder])
            MockFolder.find = MagicMock(return_value=mock_find_children)

            from app.services.library_service import delete_folder

            result = await delete_folder("folder-1", user)
            assert result is True
            assert item_in_folder.folder is None
            assert child_folder.parent_id is None
            folder.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_authorized(self):
        user = _make_user()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library_folder = AsyncMock(return_value=None)
            from app.services.library_service import delete_folder

            result = await delete_folder("folder-1", user)
            assert result is False


# ---------------------------------------------------------------------------
# move_items
# ---------------------------------------------------------------------------


class TestMoveItems:
    @pytest.mark.asyncio
    async def test_moves_items_to_folder(self):
        user = _make_user()
        target = _make_folder(uuid="target-folder")
        item = _make_library_item()
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library_folder = AsyncMock(return_value=target)
            mock_ac.get_authorized_library_item = AsyncMock(return_value=item)

            from app.services.library_service import move_items

            result = await move_items([str(item.id)], "target-folder", user)
            assert result is True
            assert item.folder == "target-folder"
            item.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_moves_items_to_root(self):
        user = _make_user()
        item = _make_library_item(folder="some-folder")
        with patch("app.services.library_service.access_control") as mock_ac:
            mock_ac.get_authorized_library_item = AsyncMock(return_value=item)

            from app.services.library_service import move_items

            result = await move_items([str(item.id)], None, user)
            assert result is True
            assert item.folder is None


# ---------------------------------------------------------------------------
# _resolve_team_oid
# ---------------------------------------------------------------------------


class TestResolveTeamOid:
    @pytest.mark.asyncio
    async def test_resolves_24_char_bson_id(self):
        team_oid = PydanticObjectId()
        mock_team = MagicMock()
        mock_team.id = team_oid
        with patch("app.services.library_service.Team") as MockTeam:
            MockTeam.get = AsyncMock(return_value=mock_team)
            from app.services.library_service import _resolve_team_oid

            result = await _resolve_team_oid(str(team_oid))
            assert result == team_oid

    @pytest.mark.asyncio
    async def test_falls_back_to_uuid_lookup(self):
        uuid_str = "a" * 32  # 32-char UUID
        team_oid = PydanticObjectId()
        mock_team = MagicMock()
        mock_team.id = team_oid
        with patch("app.services.library_service.Team") as MockTeam:
            MockTeam.find_one = AsyncMock(return_value=mock_team)
            from app.services.library_service import _resolve_team_oid

            result = await _resolve_team_oid(uuid_str)
            assert result == team_oid

    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(self):
        with patch("app.services.library_service.Team") as MockTeam:
            MockTeam.find_one = AsyncMock(return_value=None)
            from app.services.library_service import _resolve_team_oid

            with pytest.raises(ValueError, match="Team not found"):
                await _resolve_team_oid("x" * 32)


# ---------------------------------------------------------------------------
# _library_to_dict / _folder_to_dict helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_library_to_dict(self):
        lib = _make_library(title="Test Lib", scope="personal")
        from app.services.library_service import _library_to_dict

        result = _library_to_dict(lib)
        assert result["title"] == "Test Lib"
        assert result["scope"] == "personal"
        assert result["item_count"] == 0

    def test_folder_to_dict(self):
        folder = _make_folder(name="Grants", uuid="f1")
        from app.services.library_service import _folder_to_dict

        result = _folder_to_dict(folder, item_count=5)
        assert result["name"] == "Grants"
        assert result["uuid"] == "f1"
        assert result["item_count"] == 5
