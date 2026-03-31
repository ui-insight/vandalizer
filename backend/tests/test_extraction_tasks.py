"""Tests for app.tasks.extraction_tasks.

Covers normalize_results, _build_extraction_ingestion_text,
_get_user_model_name, and the perform_extraction_task Celery task.
"""

from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

_ACTIVITY_ID = str(ObjectId())
_SS_UUID = "ss-uuid"


# ---------------------------------------------------------------------------
# normalize_results
# ---------------------------------------------------------------------------


class TestNormalizeResults:
    def test_dict_input_returns_copy(self):
        from app.tasks.extraction_tasks import normalize_results

        data = {"name": "Alice", "age": "30"}
        result = normalize_results(data)
        assert result == {"name": "Alice", "age": "30"}
        # Should be a copy, not the same object
        assert result is not data

    def test_single_item_list_returns_flat_dict(self):
        from app.tasks.extraction_tasks import normalize_results

        data = [{"name": "Alice", "role": "PI"}]
        result = normalize_results(data)
        assert result == {"name": "Alice", "role": "PI"}

    def test_multi_item_list_joins_unique_values(self):
        from app.tasks.extraction_tasks import normalize_results

        data = [
            {"name": "Alice", "dept": "CS"},
            {"name": "Bob", "dept": "CS"},
        ]
        result = normalize_results(data)
        assert result["name"] == "Alice, Bob"
        # Duplicate values should be deduplicated
        assert result["dept"] == "CS"

    def test_skips_none_and_empty_values(self):
        from app.tasks.extraction_tasks import normalize_results

        data = [
            {"name": "Alice", "notes": None},
            {"name": "Bob", "notes": ""},
        ]
        result = normalize_results(data)
        assert "notes" not in result

    def test_expected_keys_filled_with_none(self):
        from app.tasks.extraction_tasks import normalize_results

        data = {"name": "Alice"}
        result = normalize_results(data, expected_keys=["name", "email", "phone"])
        assert result["name"] == "Alice"
        assert result["email"] is None
        assert result["phone"] is None

    def test_non_dict_non_list_returns_empty(self):
        from app.tasks.extraction_tasks import normalize_results

        assert normalize_results("invalid") == {}
        assert normalize_results(42) == {}
        assert normalize_results(None) == {}

    def test_list_with_non_dict_items_skips_them(self):
        from app.tasks.extraction_tasks import normalize_results

        data = [{"name": "Alice"}, "garbage", 42, {"role": "PI"}]
        result = normalize_results(data)
        assert result["name"] == "Alice"
        assert result["role"] == "PI"

    def test_deduplicates_identical_values(self):
        from app.tasks.extraction_tasks import normalize_results

        data = [
            {"name": "Alice"},
            {"name": "Alice"},
            {"name": "Alice"},
        ]
        result = normalize_results(data)
        assert result["name"] == "Alice"


# ---------------------------------------------------------------------------
# _build_extraction_ingestion_text
# ---------------------------------------------------------------------------


class TestBuildExtractionIngestionText:
    def test_includes_document_titles(self):
        from app.tasks.extraction_tasks import _build_extraction_ingestion_text

        docs = [
            {"title": "Grant Proposal", "raw_text": "Some text"},
            {"title": "Budget Sheet", "raw_text": "More text"},
        ]
        result = _build_extraction_ingestion_text(docs, ["PI Name"])
        assert "Grant Proposal" in result
        assert "Budget Sheet" in result

    def test_includes_keys(self):
        from app.tasks.extraction_tasks import _build_extraction_ingestion_text

        docs = [{"title": "Doc1", "raw_text": "text"}]
        result = _build_extraction_ingestion_text(docs, ["PI Name", "Amount"])
        assert "PI Name" in result
        assert "Amount" in result

    def test_truncates_long_raw_text(self):
        from app.tasks.extraction_tasks import _build_extraction_ingestion_text

        long_text = "x" * 1000
        docs = [{"title": "Doc", "raw_text": long_text}]
        result = _build_extraction_ingestion_text(docs, [])
        # Should contain at most 500 chars of the raw text
        assert "x" * 500 in result
        assert "x" * 501 not in result

    def test_handles_missing_raw_text(self):
        from app.tasks.extraction_tasks import _build_extraction_ingestion_text

        docs = [{"title": "Doc1"}]
        result = _build_extraction_ingestion_text(docs, [])
        assert "Doc1" in result

    def test_empty_docs_and_keys(self):
        from app.tasks.extraction_tasks import _build_extraction_ingestion_text

        result = _build_extraction_ingestion_text([], [])
        assert "Documents selected" in result


# ---------------------------------------------------------------------------
# _get_user_model_name
# ---------------------------------------------------------------------------


class TestGetUserModelName:
    def test_returns_user_configured_model(self):
        from app.tasks.extraction_tasks import _get_user_model_name

        db = MagicMock()
        db.system_config.find_one.return_value = {
            "available_models": [
                {"name": "gpt-4", "tag": "fast"},
                {"name": "claude-3", "tag": "smart"},
            ]
        }
        db.user_model_config.find_one.return_value = {"user_id": "user1", "name": "claude-3"}

        result = _get_user_model_name("user1", db)
        assert result == "claude-3"

    def test_falls_back_to_default_when_no_user_config(self):
        from app.tasks.extraction_tasks import _get_user_model_name

        db = MagicMock()
        db.system_config.find_one.return_value = {
            "available_models": [{"name": "gpt-4"}]
        }
        db.user_model_config.find_one.return_value = None

        result = _get_user_model_name("user1", db)
        assert result == "gpt-4"

    def test_falls_back_when_stored_model_is_stale(self):
        from app.tasks.extraction_tasks import _get_user_model_name

        db = MagicMock()
        db.system_config.find_one.return_value = {
            "available_models": [{"name": "gpt-4"}]
        }
        db.user_model_config.find_one.return_value = {"name": "deleted-model"}

        result = _get_user_model_name("user1", db)
        assert result == "gpt-4"

    def test_returns_empty_when_no_models_configured(self):
        from app.tasks.extraction_tasks import _get_user_model_name

        db = MagicMock()
        db.system_config.find_one.return_value = {"available_models": []}
        db.user_model_config.find_one.return_value = None

        result = _get_user_model_name(None, db)
        assert result == ""

    def test_matches_by_tag(self):
        from app.tasks.extraction_tasks import _get_user_model_name

        db = MagicMock()
        db.system_config.find_one.return_value = {
            "available_models": [{"name": "claude-opus-4-20250514", "tag": "opus"}]
        }
        db.user_model_config.find_one.return_value = {"name": "opus"}

        result = _get_user_model_name("user1", db)
        assert result == "claude-opus-4-20250514"


# ---------------------------------------------------------------------------
# perform_extraction_task
# ---------------------------------------------------------------------------


class TestPerformExtractionTask:
    @patch("app.tasks.extraction_tasks._get_db")
    def test_updates_activity_to_running_then_completed(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db

        activity = {"_id": ObjectId(_ACTIVITY_ID), "user_id": "user1", "type": "extraction"}
        db.activity_event.find_one.return_value = activity
        db.system_config.find_one.return_value = {"available_models": [{"name": "gpt-4"}]}
        db.user_model_config.find_one.return_value = None

        engine_instance = MagicMock()
        engine_instance.extract.return_value = {"PI": "Alice"}
        engine_instance.tokens_in = 100
        engine_instance.tokens_out = 50

        with patch("app.services.extraction_engine.ExtractionEngine", return_value=engine_instance):
            from app.tasks.extraction_tasks import perform_extraction_task

            result = perform_extraction_task(
                activity_id=_ACTIVITY_ID,
                searchset_uuid="ss-uuid",
                document_uuids=["doc-1"],
                keys=["PI"],
                root_path="/app",
            )

        assert result["status"] == "completed"
        assert db.activity_event.update_one.call_count >= 2

    @patch("app.tasks.extraction_tasks._get_db")
    def test_marks_activity_failed_on_exception(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db

        activity = {"_id": ObjectId(_ACTIVITY_ID), "user_id": "user1"}
        db.activity_event.find_one.return_value = activity
        db.system_config.find_one.return_value = {"available_models": [{"name": "gpt-4"}]}
        db.user_model_config.find_one.return_value = None

        engine_instance = MagicMock()
        engine_instance.extract.side_effect = RuntimeError("LLM timeout")

        with patch("app.services.extraction_engine.ExtractionEngine", return_value=engine_instance):
            from app.tasks.extraction_tasks import perform_extraction_task

            with pytest.raises(RuntimeError, match="LLM timeout"):
                perform_extraction_task(
                    activity_id=_ACTIVITY_ID,
                    searchset_uuid="ss-uuid",
                    document_uuids=["doc-1"],
                    keys=["PI"],
                    root_path="/app",
                )

        last_update = db.activity_event.update_one.call_args_list[-1]
        update_doc = last_update[0][1]["$set"]
        assert update_doc["status"] == "failed"
        assert "LLM timeout" in update_doc["error"]

    @patch("app.tasks.extraction_tasks._get_db")
    def test_handles_missing_activity_gracefully(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db
        db.activity_event.find_one.return_value = None
        db.system_config.find_one.return_value = {"available_models": [{"name": "gpt-4"}]}
        db.user_model_config.find_one.return_value = None

        engine_instance = MagicMock()
        engine_instance.extract.return_value = {"PI": "Alice"}
        engine_instance.tokens_in = 10
        engine_instance.tokens_out = 5

        with patch("app.services.extraction_engine.ExtractionEngine", return_value=engine_instance):
            from app.tasks.extraction_tasks import perform_extraction_task

            result = perform_extraction_task(
                activity_id=str(ObjectId()),
                searchset_uuid="ss-uuid",
                document_uuids=["doc-1"],
                keys=["PI"],
                root_path="/app",
            )
        assert result["status"] == "completed"
