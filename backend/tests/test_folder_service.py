"""Unit tests for folder_service helpers that don't need MongoDB."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import folder_service


def _doc(uuid):
    d = MagicMock()
    d.uuid = uuid
    return d


class TestExpandFoldersToDocumentUuids:
    @pytest.mark.asyncio
    async def test_recurses_and_filters_unviewable(self):
        """Walks subfolders and drops documents the user can't view."""
        user = MagicMock(user_id="u1", is_admin=False)
        root = MagicMock(uuid="root")
        child = MagicMock(uuid="child")

        # First find() (parents=[root]) returns one subfolder; second returns none.
        folder_find = MagicMock()
        folder_find.to_list = AsyncMock(side_effect=[[child], []])

        doc_find = MagicMock()
        doc_find.to_list = AsyncMock(return_value=[_doc("d1"), _doc("blocked"), _doc("d2")])
        doc_find_fn = MagicMock(return_value=doc_find)

        with patch.object(folder_service.access_control, "get_team_access_context", AsyncMock(return_value=MagicMock())), \
             patch.object(folder_service.access_control, "get_authorized_folder", AsyncMock(return_value=root)), \
             patch.object(folder_service.access_control, "can_view_document", side_effect=lambda d, u, t, allow_admin=False: d.uuid != "blocked"), \
             patch.object(folder_service, "SmartFolder", MagicMock(find=MagicMock(return_value=folder_find))), \
             patch.object(folder_service, "SmartDocument", MagicMock(find=doc_find_fn)):
            result = await folder_service.expand_folders_to_document_uuids(["root"], user)

            # Both subtree folders queried for documents; blocked doc filtered out.
            assert result == ["d1", "d2"]
            queried = doc_find_fn.call_args[0][0]["folder"]["$in"]
            assert set(queried) == {"root", "child"}

    @pytest.mark.asyncio
    async def test_unauthorized_root_raises(self):
        user = MagicMock(user_id="u1", is_admin=False)
        with patch.object(folder_service.access_control, "get_team_access_context", AsyncMock(return_value=MagicMock())), \
             patch.object(folder_service.access_control, "get_authorized_folder", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Folder not found"):
                await folder_service.expand_folders_to_document_uuids(["missing"], user)


def _matches(doc: dict, query: dict) -> bool:
    """The subset of MongoDB matching the expansion query uses: equality
    (a missing field equals None), ``$in`` and ``$ne``."""
    for field, cond in query.items():
        value = doc.get(field)
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
        elif value != cond:
            return False
    return True


class TestExpansionSkipsDeletedDocuments:
    """A ticked folder used to run a workflow on documents retention had
    soft-deleted. The query itself is applied here to a set of stored rows, so
    a dropped filter fails the test."""

    @pytest.mark.asyncio
    async def test_only_live_documents_are_returned(self):
        user = MagicMock(user_id="u1", is_admin=False)
        rows = [
            {"uuid": "plain", "folder": "root"},
            {"uuid": "deleted", "folder": "root", "soft_deleted": True},
            {"uuid": "kept", "folder": "root", "soft_deleted": False},
            {"uuid": "elsewhere", "folder": "other"},
        ]

        def find(query):
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[_doc(r["uuid"]) for r in rows if _matches(r, query)])
            return cursor

        folder_find = MagicMock()
        folder_find.to_list = AsyncMock(return_value=[])
        with patch.object(folder_service.access_control, "get_team_access_context", AsyncMock(return_value=MagicMock())), \
             patch.object(folder_service.access_control, "get_authorized_folder", AsyncMock(return_value=MagicMock(uuid="root"))), \
             patch.object(folder_service.access_control, "can_view_document", MagicMock(return_value=True)), \
             patch.object(folder_service, "SmartFolder", MagicMock(find=MagicMock(return_value=folder_find))), \
             patch.object(folder_service, "SmartDocument", MagicMock(find=find)):
            result = await folder_service.expand_folders_to_document_uuids(["root"], user)

        assert result == ["plain", "kept"]
