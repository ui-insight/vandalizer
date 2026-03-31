"""Tests for app.tasks.document_tasks — document extraction, update, cleanup, and semantic ingestion.

Covers: _remove_images_from_markdown, perform_extraction_and_update,
update_document_fields, _check_folder_watch_automations, cleanup_document,
perform_semantic_ingestion.
"""

from unittest.mock import MagicMock, patch

import pytest

from bson import ObjectId


# ---------------------------------------------------------------------------
# _remove_images_from_markdown
# ---------------------------------------------------------------------------


class TestRemoveImagesFromMarkdown:
    def test_removes_inline_images(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        text = "Hello ![alt](image.png) world"
        result = _remove_images_from_markdown(text)
        assert "image.png" not in result
        assert "Hello" in result
        assert "world" in result

    def test_removes_reference_images(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        text = "Hello ![alt][ref] world\n[ref]: http://img.png"
        result = _remove_images_from_markdown(text)
        assert "http://img.png" not in result

    def test_removes_width_height_attributes(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        text = 'Text {width="100" height="200"} more'
        result = _remove_images_from_markdown(text)
        assert 'width="100"' not in result

    def test_collapses_multiple_blank_lines(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        text = "Line 1\n\n\n\n\nLine 2"
        result = _remove_images_from_markdown(text)
        assert "\n\n\n" not in result

    def test_strips_whitespace_only_lines(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        text = "Line 1\n   \nLine 2"
        result = _remove_images_from_markdown(text)
        assert "   " not in result

    def test_returns_empty_on_empty_input(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        assert _remove_images_from_markdown("") == ""

    def test_preserves_non_image_markdown(self):
        from app.tasks.document_tasks import _remove_images_from_markdown

        text = "# Heading\n\n**bold** and [link](url)"
        result = _remove_images_from_markdown(text)
        assert "# Heading" in result
        assert "**bold**" in result
        assert "[link](url)" in result


# ---------------------------------------------------------------------------
# perform_extraction_and_update
# ---------------------------------------------------------------------------


class TestPerformExtractionAndUpdate:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_empty_when_doc_not_found(self, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        result = perform_extraction_and_update(document_uuid="missing", extension="pdf")
        assert result == ""

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_from_file", return_value="Extracted text content")
    def test_extracts_text_for_pdf(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == "Extracted text content"
        # Should set raw_text and token_count
        update_call = db.smart_document.update_one.call_args_list[-1]
        update_set = update_call[0][1]["$set"]
        assert update_set["raw_text"] == "Extracted text content"
        assert update_set["processing"] is False
        assert update_set["token_count"] > 0

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.convert_to_markdown", return_value="| col1 | col2 |")
    def test_uses_convert_to_markdown_for_xlsx(self, mock_convert, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "data.xlsx"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="xlsx")

        assert result == "| col1 | col2 |"
        mock_convert.assert_called_once()

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_from_file", side_effect=RuntimeError("corrupt file"))
    def test_handles_extraction_error_gracefully(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "bad.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == ""
        # Should have set processing to False and raw_text to ""
        update_call = db.smart_document.update_one.call_args_list[-1]
        update_set = update_call[0][1]["$set"]
        assert update_set["processing"] is False

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_from_file", return_value="text")
    def test_sets_processing_status_to_extracting(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "f.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        # First update should set processing=True, task_status=extracting
        first_update = db.smart_document.update_one.call_args_list[0]
        assert first_update[0][1]["$set"]["task_status"] == "extracting"


# ---------------------------------------------------------------------------
# update_document_fields
# ---------------------------------------------------------------------------


class TestUpdateDocumentFields:
    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_marks_document_complete(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        update_document_fields(document_uuid="doc-1")

        db.smart_document.update_one.assert_called_once()
        update_set = db.smart_document.update_one.call_args[0][1]["$set"]
        assert update_set["task_status"] == "complete"

    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_early_when_doc_not_found(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.update_one.return_value = MagicMock(matched_count=0)

        update_document_fields(document_uuid="missing")

        mock_check.assert_not_called()

    @patch("app.tasks.document_tasks._check_folder_watch_automations", side_effect=RuntimeError("boom"))
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_catches_folder_watch_errors(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        # Should not raise
        update_document_fields(document_uuid="doc-1")


# ---------------------------------------------------------------------------
# _check_folder_watch_automations
# ---------------------------------------------------------------------------


class TestCheckFolderWatchAutomations:
    def test_returns_early_when_doc_not_found(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = None

        _check_folder_watch_automations(db, "doc-1")
        db.automation.find.assert_not_called()

    def test_returns_early_when_folder_is_root(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "folder": "0"}

        _check_folder_watch_automations(db, "doc-1")
        db.automation.find.assert_not_called()

    def test_returns_early_when_no_automations_match(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "folder": "folder-abc"}
        db.automation.find.return_value = []

        _check_folder_watch_automations(db, "doc-1")

    def test_skips_automation_with_non_matching_file_type(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "folder": "f1", "extension": "txt", "title": "test.txt",
        }
        db.automation.find.return_value = [{
            "_id": ObjectId(),
            "name": "PDF only",
            "action_type": "workflow",
            "action_id": str(ObjectId()),
            "trigger_config": {"file_types": ["pdf"]},
        }]

        _check_folder_watch_automations(db, "doc-1")

        # Should not create any trigger event or call workflow
        db.workflow.find_one.assert_not_called()

    def test_skips_automation_matching_exclude_pattern(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "folder": "f1", "extension": "pdf", "title": "DRAFT_report.pdf",
        }
        db.automation.find.return_value = [{
            "_id": ObjectId(),
            "name": "Skip drafts",
            "action_type": "workflow",
            "action_id": str(ObjectId()),
            "trigger_config": {"file_types": [], "exclude_patterns": "DRAFT_*"},
        }]

        _check_folder_watch_automations(db, "doc-1")
        db.workflow.find_one.assert_not_called()

    @patch("app.services.passive_triggers.create_folder_watch_trigger", return_value={"_id": "evt-1"})
    def test_creates_trigger_event_for_workflow_automation(self, mock_create_trigger):
        from app.tasks.document_tasks import _check_folder_watch_automations

        wf_oid = ObjectId()
        db = MagicMock()
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "folder": "f1", "extension": "pdf", "title": "report.pdf",
        }
        db.automation.find.return_value = [{
            "_id": ObjectId(),
            "name": "Auto extract",
            "action_type": "workflow",
            "action_id": str(wf_oid),
            "trigger_config": {},
        }]
        db.workflow.find_one.return_value = {"_id": wf_oid, "name": "My WF"}

        _check_folder_watch_automations(db, "doc-1")

        mock_create_trigger.assert_called_once()


# ---------------------------------------------------------------------------
# cleanup_document
# ---------------------------------------------------------------------------


class TestCleanupDocument:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_sets_error_status(self, mock_get_db):
        from app.tasks.document_tasks import cleanup_document

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        cleanup_document(document_uuid="doc-1")

        update_set = db.smart_document.update_one.call_args[0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert update_set["processing"] is False
        assert "error_message" in update_set

    @patch("app.tasks.document_tasks.get_sync_db")
    def test_handles_missing_document(self, mock_get_db):
        from app.tasks.document_tasks import cleanup_document

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.update_one.return_value = MagicMock(matched_count=0)

        # Should not raise
        cleanup_document(document_uuid="missing")


# ---------------------------------------------------------------------------
# perform_semantic_ingestion
# ---------------------------------------------------------------------------


class TestPerformSemanticIngestion:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_empty_when_doc_not_found(self, mock_get_db):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        result = perform_semantic_ingestion(raw_text="text", document_uuid="missing", user_id="user1")
        assert result == ""

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_ingests_document_and_returns_uuid(self, mock_get_db, MockSettings, MockDM):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Report.pdf", "path": "uploads/report.pdf",
        }

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        MockDM.return_value = dm_instance

        result = perform_semantic_ingestion(raw_text="content", document_uuid="doc-1", user_id="user1")

        assert result == "doc-1"
        dm_instance.add_document.assert_called_once_with(
            user_id="user1",
            document_name="Report.pdf",
            document_id="doc-1",
            doc_path="uploads/report.pdf",
            raw_text="content",
        )

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_sets_task_status_to_readying_then_complete(self, mock_get_db, MockSettings, MockDM):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Doc", "path": "p",
        }
        MockSettings.return_value = MagicMock(chromadb_persist_dir="/data")
        MockDM.return_value = MagicMock()

        perform_semantic_ingestion(raw_text="text", document_uuid="doc-1", user_id="u1")

        # First update: readying, second: complete
        updates = db.smart_document.update_one.call_args_list
        assert updates[0][0][1]["$set"]["task_status"] == "readying"
        assert updates[1][0][1]["$set"]["task_status"] == "complete"
