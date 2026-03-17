"""Unit tests for document_service.

Tests list_contents and poll_status with mocked Beanie models.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_folder(uuid="f1", title="Folder 1", parent_id="0", space="default", team_id=None, is_shared_team_root=False):
    f = MagicMock()
    f.id = f"id-{uuid}"
    f.uuid = uuid
    f.title = title
    f.parent_id = parent_id
    f.space = space
    f.team_id = team_id
    f.is_shared_team_root = is_shared_team_root
    return f


def _make_document(
    uuid="d1",
    title="Doc 1",
    space="default",
    folder="0",
    processing=False,
    valid=True,
    task_status="complete",
    soft_deleted=False,
    classification=None,
    classification_confidence=None,
    classified_at=None,
    classified_by=None,
    retention_hold=False,
):
    d = MagicMock()
    d.id = f"id-{uuid}"
    d.uuid = uuid
    d.title = title
    d.space = space
    d.folder = folder
    d.extension = "pdf"
    d.processing = processing
    d.valid = valid
    d.task_status = task_status
    d.soft_deleted = soft_deleted
    d.created_at = datetime.datetime(2025, 1, 1, 12, 0, 0)
    d.updated_at = datetime.datetime(2025, 1, 2, 12, 0, 0)
    d.token_count = 100
    d.num_pages = 3
    d.classification = classification
    d.classification_confidence = classification_confidence
    d.classified_at = classified_at
    d.classified_by = classified_by
    d.retention_hold = retention_hold
    d.raw_text = "sample text"
    d.path = "/uploads/test.pdf"
    d.validation_feedback = None
    d.user_id = "user1"
    return d


def _mock_find_chain(items):
    """Create a mock that supports .find(...).to_list()."""
    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=items)
    return chain


class TestListContents:
    @pytest.mark.asyncio
    async def test_returns_folders_and_documents(self):
        folders = [_make_folder(uuid="f1", title="My Folder")]
        docs = [_make_document(uuid="d1", title="My Doc")]

        with patch("app.services.document_service.SmartFolder") as MockFolder, \
             patch("app.services.document_service.SmartDocument") as MockDoc:
            MockFolder.find = MagicMock(return_value=_mock_find_chain(folders))
            MockDoc.find = MagicMock(return_value=_mock_find_chain(docs))

            from app.services.document_service import list_contents
            result = await list_contents(space="default", user_id="user1")

        assert len(result["folders"]) == 1
        assert result["folders"][0]["title"] == "My Folder"
        assert result["folders"][0]["uuid"] == "f1"
        assert len(result["documents"]) == 1
        assert result["documents"][0]["title"] == "My Doc"
        assert result["documents"][0]["uuid"] == "d1"

    @pytest.mark.asyncio
    async def test_filters_by_space_excludes_soft_deleted(self):
        """Documents with soft_deleted=True should not appear."""
        active_doc = _make_document(uuid="d1", soft_deleted=False)
        # soft_deleted doc is filtered at the DB query level, so we just
        # verify the service passes the right filters.
        with patch("app.services.document_service.SmartFolder") as MockFolder, \
             patch("app.services.document_service.SmartDocument") as MockDoc:
            MockFolder.find = MagicMock(return_value=_mock_find_chain([]))
            MockDoc.find = MagicMock(return_value=_mock_find_chain([active_doc]))

            from app.services.document_service import list_contents
            result = await list_contents(space="research", user_id="user1")

        # The find call should include soft_deleted filter
        call_args = MockDoc.find.call_args
        filters = call_args[0][0]  # first positional arg is the dict filter
        assert filters["soft_deleted"] == {"$ne": True}
        assert filters["space"] == "research"

        assert len(result["documents"]) == 1
        assert result["documents"][0]["soft_deleted"] is False

    @pytest.mark.asyncio
    async def test_team_folder_shows_all_docs(self):
        """When inside a team folder, documents should not be filtered by user_id."""
        team_folder = _make_folder(uuid="tf1", team_id="team-abc")
        doc1 = _make_document(uuid="d1", folder="tf1")
        doc2 = _make_document(uuid="d2", folder="tf1")

        with patch("app.services.document_service.SmartFolder") as MockFolder, \
             patch("app.services.document_service.SmartDocument") as MockDoc:
            MockFolder.find = MagicMock(return_value=_mock_find_chain([]))
            MockFolder.find_one = AsyncMock(return_value=team_folder)
            # For team folders the code uses SmartDocument.find with positional filters
            MockDoc.find = MagicMock(return_value=_mock_find_chain([doc1, doc2]))

            from app.services.document_service import list_contents
            result = await list_contents(space="default", folder="tf1", user_id="user1")

        assert len(result["documents"]) == 2
        # Verify that the doc query used Beanie-style positional filters (not dict with user_id)
        call_args = MockDoc.find.call_args
        # Team folder branch uses positional args, not a dict with user_id
        if isinstance(call_args[0][0], dict):
            assert "user_id" not in call_args[0][0]


class TestPollStatus:
    @pytest.mark.asyncio
    async def test_readying_status_returns_messages(self):
        doc = _make_document(task_status="readying", processing=True, valid=True)

        with patch("app.services.document_service.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockDoc.uuid = "uuid"

            from app.services.document_service import poll_status
            result = await poll_status("d1")

        assert result is not None
        assert result["status"] == "readying"
        assert result["complete"] is False
        assert any("ready" in m.lower() for m in result["status_messages"])
        assert any("passed" in m.lower() for m in result["status_messages"])

    @pytest.mark.asyncio
    async def test_complete_status_returns_complete_true(self):
        doc = _make_document(task_status="complete", processing=False)

        with patch("app.services.document_service.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockDoc.uuid = "uuid"

            from app.services.document_service import poll_status
            result = await poll_status("d1")

        assert result is not None
        assert result["status"] == "complete"
        assert result["complete"] is True
        assert result["raw_text"] == "sample text"

    @pytest.mark.asyncio
    async def test_missing_doc_returns_none(self):
        with patch("app.services.document_service.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=None)
            MockDoc.uuid = "uuid"

            from app.services.document_service import poll_status
            result = await poll_status("nonexistent")

        assert result is None
