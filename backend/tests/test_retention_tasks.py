"""Tests for async helper functions in app.tasks.retention_tasks.

Verifies scheduling, soft-delete, hard-delete, and ancillary cleanup logic.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestScheduleDeletions:
    @pytest.mark.asyncio
    async def test_finds_expired_docs_and_schedules(self):
        """Expired documents get scheduled_deletion_at set."""
        mock_config = MagicMock()
        mock_config.get_retention_config.return_value = {
            "enabled": True,
            "policies": {
                "unrestricted": {"retention_days": 30},
            },
        }

        doc = MagicMock()
        doc.scheduled_deletion_at = None
        doc.save = AsyncMock()

        mock_find_query = MagicMock()
        mock_find_query.to_list = AsyncMock(return_value=[doc])

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.models.document.SmartDocument") as MockDoc:
            MockConfig.get_config = AsyncMock(return_value=mock_config)
            MockDoc.find = MagicMock(return_value=mock_find_query)
            MockDoc.classification = "classification"
            MockDoc.created_at = "created_at"
            MockDoc.soft_deleted = "soft_deleted"
            MockDoc.retention_hold = "retention_hold"
            MockDoc.scheduled_deletion_at = "scheduled_deletion_at"

            from app.tasks.retention_tasks import _schedule_deletions
            await _schedule_deletions()

        doc.save.assert_awaited_once()
        assert doc.scheduled_deletion_at is not None

    @pytest.mark.asyncio
    async def test_disabled_config_returns_early(self):
        """When retention is disabled, no documents are processed."""
        mock_config = MagicMock()
        mock_config.get_retention_config.return_value = {
            "enabled": False,
        }

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.models.document.SmartDocument") as MockDoc:
            MockConfig.get_config = AsyncMock(return_value=mock_config)

            from app.tasks.retention_tasks import _schedule_deletions
            await _schedule_deletions()

        # SmartDocument.find should never be called
        MockDoc.find.assert_not_called()


class TestExecuteSoftDeletes:
    @pytest.mark.asyncio
    async def test_marks_docs_as_soft_deleted(self):
        """Documents past their scheduled_deletion_at are soft-deleted."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        doc = MagicMock()
        doc.scheduled_deletion_at = now - datetime.timedelta(hours=1)
        doc.soft_deleted = False
        doc.save = AsyncMock()

        mock_find_query = MagicMock()
        mock_find_query.to_list = AsyncMock(return_value=[doc])

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.document.SmartDocument") as MockDoc:
            MockDoc.find = MagicMock(return_value=mock_find_query)
            MockDoc.scheduled_deletion_at = "scheduled_deletion_at"
            MockDoc.soft_deleted = "soft_deleted"
            MockDoc.retention_hold = "retention_hold"

            from app.tasks.retention_tasks import _execute_soft_deletes
            await _execute_soft_deletes()

        doc.save.assert_awaited_once()
        assert doc.soft_deleted is True
        assert doc.soft_deleted_at is not None


class TestExecuteHardDeletes:
    @pytest.mark.asyncio
    async def test_deletes_files_chromadb_and_db(self):
        """Hard delete removes physical file, ChromaDB entries, and DB record."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        doc = MagicMock()
        doc.soft_deleted = True
        doc.soft_deleted_at = now - datetime.timedelta(days=60)
        doc.classification = "unrestricted"
        doc.path = "/tmp/test-file.pdf"
        doc.uuid = "doc-uuid-1"
        doc.retention_hold = False
        doc.delete = AsyncMock()

        mock_config = MagicMock()
        mock_config.get_retention_config.return_value = {
            "enabled": True,
            "policies": {
                "unrestricted": {"retention_days": 30, "soft_delete_grace_days": 30},
            },
        }

        mock_find_query = MagicMock()
        mock_find_query.to_list = AsyncMock(return_value=[doc])

        mock_collection = MagicMock()
        mock_chroma = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection

        import sys
        mock_chromadb_mod = MagicMock()
        mock_chromadb_mod.PersistentClient.return_value = mock_chroma

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings") as MockSettings, \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.models.document.SmartDocument") as MockDoc, \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove, \
             patch.dict(sys.modules, {"chromadb": mock_chromadb_mod}):
            MockSettings.return_value.chromadb_persist_dir = "/tmp/chroma"
            MockConfig.get_config = AsyncMock(return_value=mock_config)
            MockDoc.find = MagicMock(return_value=mock_find_query)
            MockDoc.soft_deleted = "soft_deleted"
            MockDoc.retention_hold = "retention_hold"

            from app.tasks.retention_tasks import _execute_hard_deletes
            await _execute_hard_deletes()

        mock_remove.assert_called_once_with("/tmp/test-file.pdf")
        mock_collection.delete.assert_called_once_with(where={"document_uuid": "doc-uuid-1"})
        doc.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disabled_config_returns_early(self):
        """When retention is disabled, no hard deletes are performed."""
        mock_config = MagicMock()
        mock_config.get_retention_config.return_value = {
            "enabled": False,
        }

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.models.document.SmartDocument") as MockDoc:
            MockConfig.get_config = AsyncMock(return_value=mock_config)

            from app.tasks.retention_tasks import _execute_hard_deletes
            await _execute_hard_deletes()

        MockDoc.find.assert_not_called()


class TestCleanupAncillary:
    @pytest.mark.asyncio
    async def test_deletes_old_activity_chats_workflow_results(self):
        """Old activity events, chats, and workflow results are deleted."""
        mock_config = MagicMock()
        mock_config.get_retention_config.return_value = {
            "enabled": True,
            "activity_retention_days": 180,
            "chat_retention_days": 365,
            "workflow_result_retention_days": 365,
        }

        activity_result = MagicMock()
        activity_result.deleted_count = 5
        chat_result = MagicMock()
        chat_result.deleted_count = 3
        wf_result = MagicMock()
        wf_result.deleted_count = 2

        mock_activity_query = MagicMock()
        mock_activity_query.delete = AsyncMock(return_value=activity_result)
        mock_chat_query = MagicMock()
        mock_chat_query.delete = AsyncMock(return_value=chat_result)
        mock_wf_query = MagicMock()
        mock_wf_query.delete = AsyncMock(return_value=wf_result)

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.models.activity.ActivityEvent") as MockActivity, \
             patch("app.models.chat.ChatConversation") as MockChat, \
             patch("app.models.workflow.WorkflowResult") as MockWF:
            MockConfig.get_config = AsyncMock(return_value=mock_config)
            MockActivity.find = MagicMock(return_value=mock_activity_query)
            MockActivity.created_at = "created_at"
            MockChat.find = MagicMock(return_value=mock_chat_query)
            MockChat.created_at = "created_at"
            MockWF.find = MagicMock(return_value=mock_wf_query)
            MockWF.start_time = "start_time"

            from app.tasks.retention_tasks import _cleanup_ancillary
            await _cleanup_ancillary()

        mock_activity_query.delete.assert_awaited_once()
        mock_chat_query.delete.assert_awaited_once()
        mock_wf_query.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disabled_config_returns_early(self):
        """When retention is disabled, nothing is cleaned up."""
        mock_config = MagicMock()
        mock_config.get_retention_config.return_value = {
            "enabled": False,
        }

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.models.activity.ActivityEvent") as MockActivity:
            MockConfig.get_config = AsyncMock(return_value=mock_config)

            from app.tasks.retention_tasks import _cleanup_ancillary
            await _cleanup_ancillary()

        MockActivity.find.assert_not_called()
