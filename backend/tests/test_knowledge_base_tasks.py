"""Tests for app.tasks.knowledge_base_tasks — KB document and URL ingestion.

Mocks pymongo DB and DocumentManager to test ingestion logic,
error handling, and KB stat recalculation.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(
    uuid="src-uuid",
    kb_uuid="kb-uuid",
    document_uuid="doc-uuid",
    url=None,
    status="pending",
    **extra,
):
    source = {
        "uuid": uuid,
        "knowledge_base_uuid": kb_uuid,
        "document_uuid": document_uuid,
        "status": status,
        **extra,
    }
    if url is not None:
        source["url"] = url
    return source


def _make_doc(uuid="doc-uuid", raw_text="Some document text content.", title="test.pdf"):
    return {
        "uuid": uuid,
        "raw_text": raw_text,
        "title": title,
    }


# ---------------------------------------------------------------------------
# _recalculate_kb
# ---------------------------------------------------------------------------


class TestRecalculateKb:
    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_empty_sources_sets_status_empty(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import _recalculate_kb

        db = MagicMock()
        db.knowledge_base_sources.find.return_value = []

        _recalculate_kb(db, "kb-uuid")

        db.knowledge_bases.update_one.assert_called_once()
        update_args = db.knowledge_bases.update_one.call_args[0]
        assert update_args[0] == {"uuid": "kb-uuid"}
        assert update_args[1]["$set"]["status"] == "empty"
        assert update_args[1]["$set"]["total_sources"] == 0

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_all_ready_sets_status_ready(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import _recalculate_kb

        db = MagicMock()
        db.knowledge_base_sources.find.return_value = [
            {"status": "ready", "chunk_count": 10},
            {"status": "ready", "chunk_count": 5},
        ]

        _recalculate_kb(db, "kb-uuid")

        update_args = db.knowledge_bases.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "ready"
        assert update_args[1]["$set"]["total_sources"] == 2
        assert update_args[1]["$set"]["sources_ready"] == 2
        assert update_args[1]["$set"]["total_chunks"] == 15

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_all_failed_sets_status_error(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import _recalculate_kb

        db = MagicMock()
        db.knowledge_base_sources.find.return_value = [
            {"status": "error", "chunk_count": 0},
        ]

        _recalculate_kb(db, "kb-uuid")

        update_args = db.knowledge_bases.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "error"
        assert update_args[1]["$set"]["sources_failed"] == 1

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_mixed_sources_sets_status_building(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import _recalculate_kb

        db = MagicMock()
        db.knowledge_base_sources.find.return_value = [
            {"status": "ready", "chunk_count": 10},
            {"status": "processing", "chunk_count": 0},
        ]

        _recalculate_kb(db, "kb-uuid")

        update_args = db.knowledge_bases.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "building"


# ---------------------------------------------------------------------------
# kb_ingest_document
# ---------------------------------------------------------------------------


class TestKbIngestDocument:
    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_source_not_found_returns_early(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_document

        db = MagicMock()
        mock_get_db.return_value = db
        db.knowledge_base_sources.find_one.return_value = None

        kb_ingest_document("nonexistent-src")

        db.knowledge_base_sources.update_one.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_document_not_found_sets_error(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_document

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source()
        db.knowledge_base_sources.find_one.return_value = source
        db.smart_document.find_one.return_value = None
        db.knowledge_base_sources.find.return_value = [source]

        kb_ingest_document("src-uuid")

        # Should be called twice: once for "processing", once for "error"
        calls = db.knowledge_base_sources.update_one.call_args_list
        assert len(calls) >= 2
        error_call = calls[1][0]
        assert error_call[1]["$set"]["status"] == "error"
        assert "Document not found" in error_call[1]["$set"]["error_message"]

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_empty_raw_text_sets_error(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_document

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source()
        db.knowledge_base_sources.find_one.return_value = source
        db.smart_document.find_one.return_value = _make_doc(raw_text="   ")
        db.knowledge_base_sources.find.return_value = [source]

        kb_ingest_document("src-uuid")

        calls = db.knowledge_base_sources.update_one.call_args_list
        error_call = calls[1][0]
        assert error_call[1]["$set"]["status"] == "error"
        assert "no text content" in error_call[1]["$set"]["error_message"]

    @patch("app.services.document_manager.get_document_manager")
    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_successful_ingestion_sets_ready(self, mock_get_db, mock_get_dm):
        from app.tasks.knowledge_base_tasks import kb_ingest_document

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source()
        doc = _make_doc()
        db.knowledge_base_sources.find_one.return_value = source
        db.smart_document.find_one.return_value = doc
        db.knowledge_base_sources.find.return_value = [source]

        mock_dm_instance = MagicMock()
        mock_dm_instance.add_to_kb.return_value = 42
        mock_get_dm.return_value = mock_dm_instance

        kb_ingest_document("src-uuid")

        mock_dm_instance.add_to_kb.assert_called_once_with(
            kb_uuid="kb-uuid",
            source_id="src-uuid",
            source_name="test.pdf",
            raw_text="Some document text content.",
        )

        # Last update before _recalculate_kb should set status=ready
        calls = db.knowledge_base_sources.update_one.call_args_list
        ready_call = calls[-1][0]
        assert ready_call[1]["$set"]["status"] == "ready"
        assert ready_call[1]["$set"]["chunk_count"] == 42

    @patch("app.services.document_manager.get_document_manager")
    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_ingestion_error_sets_error_and_reraises(self, mock_get_db, mock_get_dm):
        from app.tasks.knowledge_base_tasks import kb_ingest_document

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source()
        doc = _make_doc()
        db.knowledge_base_sources.find_one.return_value = source
        db.smart_document.find_one.return_value = doc
        db.knowledge_base_sources.find.return_value = [source]

        mock_dm_instance = MagicMock()
        mock_dm_instance.add_to_kb.side_effect = RuntimeError("ChromaDB down")
        mock_get_dm.return_value = mock_dm_instance

        with pytest.raises(RuntimeError, match="ChromaDB down"):
            kb_ingest_document("src-uuid")

        # Should have set error status
        calls = db.knowledge_base_sources.update_one.call_args_list
        error_call = [c for c in calls if c[0][1].get("$set", {}).get("status") == "error"]
        assert len(error_call) == 1
        assert "ChromaDB down" in error_call[0][0][1]["$set"]["error_message"]


# ---------------------------------------------------------------------------
# kb_ingest_url
# ---------------------------------------------------------------------------


class TestKbIngestUrl:
    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_source_not_found_returns_early(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_url

        db = MagicMock()
        mock_get_db.return_value = db
        db.knowledge_base_sources.find_one.return_value = None

        kb_ingest_url("nonexistent-src")

        db.knowledge_base_sources.update_one.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_no_url_sets_error(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_url

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source(url="")
        db.knowledge_base_sources.find_one.return_value = source
        db.knowledge_base_sources.find.return_value = [source]

        kb_ingest_url("src-uuid")

        calls = db.knowledge_base_sources.update_one.call_args_list
        error_call = calls[1][0]
        assert error_call[1]["$set"]["status"] == "error"
        assert "No URL specified" in error_call[1]["$set"]["error_message"]

    @patch("app.services.document_manager.get_document_manager")
    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_successful_url_ingestion(self, mock_get_db, mock_get_dm):
        from app.tasks.knowledge_base_tasks import kb_ingest_url

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source(url="https://example.com/page")
        db.knowledge_base_sources.find_one.return_value = source
        db.knowledge_base_sources.find.return_value = [source]

        mock_dm_instance = MagicMock()
        mock_dm_instance.add_to_kb.return_value = 7
        mock_get_dm.return_value = mock_dm_instance

        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Example Page</title></head><body><p>Hello world</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response), \
             patch("app.utils.url_validation.validate_outbound_url"):
            kb_ingest_url("src-uuid")

        mock_dm_instance.add_to_kb.assert_called_once()
        call_kwargs = mock_dm_instance.add_to_kb.call_args
        assert call_kwargs[1]["kb_uuid"] == "kb-uuid"
        assert call_kwargs[1]["source_id"] == "src-uuid"

        # Should have set ready status
        calls = db.knowledge_base_sources.update_one.call_args_list
        ready_call = calls[-1][0]
        assert ready_call[1]["$set"]["status"] == "ready"
        assert ready_call[1]["$set"]["chunk_count"] == 7

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_empty_page_content_sets_error(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_url

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source(url="https://example.com/empty")
        db.knowledge_base_sources.find_one.return_value = source
        db.knowledge_base_sources.find.return_value = [source]

        mock_response = MagicMock()
        mock_response.text = "<html><body><script>only scripts</script></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response), \
             patch("app.utils.url_validation.validate_outbound_url"):
            kb_ingest_url("src-uuid")

        calls = db.knowledge_base_sources.update_one.call_args_list
        error_call = calls[1][0]
        assert error_call[1]["$set"]["status"] == "error"
        assert "Failed to fetch URL content" in error_call[1]["$set"]["error_message"]

    @patch("app.tasks.knowledge_base_tasks._get_db")
    def test_url_fetch_error_sets_error_and_reraises(self, mock_get_db):
        from app.tasks.knowledge_base_tasks import kb_ingest_url

        db = MagicMock()
        mock_get_db.return_value = db

        source = _make_source(url="https://example.com/fail")
        db.knowledge_base_sources.find_one.return_value = source
        db.knowledge_base_sources.find.return_value = [source]

        with patch("httpx.get", side_effect=ConnectionError("Network down")), \
             patch("app.utils.url_validation.validate_outbound_url"):
            with pytest.raises(ConnectionError, match="Network down"):
                kb_ingest_url("src-uuid")

        calls = db.knowledge_base_sources.update_one.call_args_list
        error_call = [c for c in calls if c[0][1].get("$set", {}).get("status") == "error"]
        assert len(error_call) == 1
        assert "Network down" in error_call[0][0][1]["$set"]["error_message"]
