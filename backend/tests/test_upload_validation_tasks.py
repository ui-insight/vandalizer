"""Tests for app.tasks.upload_validation_tasks — chunk validation and summarization.

Mocks pymongo DB, LLM agents, and text splitters to test validation logic,
result aggregation, and error handling.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _get_compliance_rules
# ---------------------------------------------------------------------------


class TestGetComplianceRules:
    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_returns_custom_rules_from_compliance_config(self, mock_get_db):
        from app.tasks.upload_validation_tasks import _get_compliance_rules

        db = MagicMock()
        mock_get_db.return_value = db
        db.system_config.find_one.return_value = {
            "compliance_config": {
                "enabled": True,
                "rules": "Custom compliance rules for testing.",
            },
        }

        result = _get_compliance_rules()

        assert result == "Custom compliance rules for testing."

    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_returns_legacy_upload_compliance_when_no_new_config(self, mock_get_db):
        from app.tasks.upload_validation_tasks import _get_compliance_rules

        db = MagicMock()
        mock_get_db.return_value = db
        db.system_config.find_one.return_value = {
            "upload_compliance": "Legacy rules.",
        }

        result = _get_compliance_rules()

        assert result == "Legacy rules."

    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_returns_default_rules_when_not_configured(self, mock_get_db):
        from app.tasks.upload_validation_tasks import _get_compliance_rules

        db = MagicMock()
        mock_get_db.return_value = db
        db.system_config.find_one.return_value = {}

        result = _get_compliance_rules()

        assert "PII" in result
        assert "SSN" in result


# ---------------------------------------------------------------------------
# validate_chunk
# ---------------------------------------------------------------------------


class TestValidateChunk:
    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    def test_valid_structured_output(self, mock_get_agent):
        from app.tasks.upload_validation_tasks import validate_chunk

        mock_output = MagicMock()
        mock_output.valid = True
        mock_output.feedback = "No issues found."

        mock_result = MagicMock()
        mock_result.output = mock_output

        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent

        result = validate_chunk("doc.pdf", "compliance rules", "chunk text", 1, 3)

        assert result == {"valid": True, "feedback": "No issues found.", "index": 1}

    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    def test_valid_json_string_output(self, mock_get_agent):
        from app.tasks.upload_validation_tasks import validate_chunk

        # Plain string -- hasattr(str, "valid") is False, so we fall into
        # the json.loads branch which should parse successfully.
        mock_result = MagicMock()
        mock_result.output = '{"valid": false, "feedback": "Contains SSN"}'

        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent

        result = validate_chunk("doc.pdf", "compliance rules", "chunk text", 2, 3)

        assert result["valid"] is False
        assert result["feedback"] == "Contains SSN"
        assert result["index"] == 2

    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    def test_unparseable_output_defaults_to_valid(self, mock_get_agent):
        from app.tasks.upload_validation_tasks import validate_chunk

        mock_result = MagicMock()
        # A plain string has no .valid attr, so hasattr(output, "valid") is False.
        # "not valid json" also fails json.loads, hitting the fallback path.
        mock_result.output = "Some freeform text response"

        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent

        result = validate_chunk("doc.pdf", "rules", "chunk text", 1, 1)

        assert result["valid"] is True
        assert result["index"] == 1

    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    def test_agent_error_triggers_retry(self, mock_get_agent):
        from app.tasks.upload_validation_tasks import validate_chunk

        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = RuntimeError("LLM timeout")
        mock_get_agent.return_value = mock_agent

        # self.retry(exc=e) raises celery.exceptions.Retry when called
        # directly. We accept either Retry or RuntimeError depending on
        # how the Celery task wrapper handles it.
        with pytest.raises(Exception):
            validate_chunk("doc.pdf", "rules", "chunk", 1, 1)


# ---------------------------------------------------------------------------
# summarize_results
# ---------------------------------------------------------------------------


class TestSummarizeResults:
    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_all_valid_results(self, mock_get_db, mock_get_agent):
        from app.tasks.upload_validation_tasks import summarize_results

        db = MagicMock()
        mock_get_db.return_value = db

        mock_output = MagicMock()
        mock_output.model_dump.return_value = {
            "valid": True,
            "feedback": "All sections passed.",
        }
        mock_result = MagicMock()
        mock_result.output = mock_output
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent

        results = [
            {"valid": True, "feedback": "OK", "index": 1},
            {"valid": True, "feedback": "OK", "index": 2},
        ]

        summary = summarize_results(results, "doc-uuid", False)

        assert summary["valid"] is True
        db.smart_document.update_one.assert_called_once()
        update_args = db.smart_document.update_one.call_args[0]
        assert update_args[0] == {"uuid": "doc-uuid"}
        assert update_args[1]["$set"]["valid"] is True
        assert update_args[1]["$set"]["validating"] is False
        assert update_args[1]["$set"]["task_status"] == "complete"

    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_some_invalid_results(self, mock_get_db, mock_get_agent):
        from app.tasks.upload_validation_tasks import summarize_results

        db = MagicMock()
        mock_get_db.return_value = db

        mock_output = MagicMock()
        mock_output.model_dump.return_value = {
            "valid": False,
            "feedback": "SSN detected in chunk 2.",
        }
        mock_result = MagicMock()
        mock_result.output = mock_output
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent

        results = [
            {"valid": True, "feedback": "OK", "index": 1},
            {"valid": False, "feedback": "Contains SSN", "index": 2},
        ]

        summary = summarize_results(results, "doc-uuid", False)

        assert summary["valid"] is False
        update_args = db.smart_document.update_one.call_args[0]
        assert update_args[1]["$set"]["valid"] is False

    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_background_mode_no_task_status(self, mock_get_db, mock_get_agent):
        from app.tasks.upload_validation_tasks import summarize_results

        db = MagicMock()
        mock_get_db.return_value = db

        # Plain string output -- hasattr(str, "model_dump") is False,
        # so the code goes to the else branch: {"valid": all_valid, "feedback": str(output)}
        mock_result = MagicMock()
        mock_result.output = "All good"
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent

        results = [{"valid": True, "feedback": "OK", "index": 1}]

        summarize_results(results, "doc-uuid", True)

        update_args = db.smart_document.update_one.call_args[0]
        assert "task_status" not in update_args[1]["$set"]

    @patch("app.tasks.upload_validation_tasks._get_secure_agent")
    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_agent_error_falls_back_to_combined_feedback(self, mock_get_db, mock_get_agent):
        from app.tasks.upload_validation_tasks import summarize_results

        db = MagicMock()
        mock_get_db.return_value = db

        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = RuntimeError("LLM unavailable")
        mock_get_agent.return_value = mock_agent

        results = [
            {"valid": False, "feedback": "PII detected", "index": 1},
        ]

        summary = summarize_results(results, "doc-uuid", False)

        assert summary["valid"] is False
        assert "PII detected" in summary["feedback"]
        # Should still persist to DB despite agent error
        db.smart_document.update_one.assert_called_once()


# ---------------------------------------------------------------------------
# perform_document_validation
# ---------------------------------------------------------------------------


class TestPerformDocumentValidationPathResolution:
    """When raw_text isn't ready yet, validation reads from disk. It must
    resolve the file against upload_dir (like the extraction task) rather than
    trusting the caller's ``document_path`` — some callers pass the bare
    relative ``doc.path``, which fails to open from the worker CWD (the
    "[Errno 2] No such file" OCR failures on tasks.upload.validation)."""

    @patch("app.tasks.upload_validation_tasks.chord")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_from_file", return_value="resolved text")
    @patch("app.tasks.upload_validation_tasks._get_compliance_settings")
    @patch("app.tasks.upload_validation_tasks._get_db")
    def test_relative_path_resolved_against_upload_dir(
        self, mock_get_db, mock_settings_fn, mock_extract, MockSettings, mock_chord,
    ):
        from app.tasks.upload_validation_tasks import perform_document_validation

        db = MagicMock()
        mock_get_db.return_value = db
        # No raw_text yet -> validation must read from the file.
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "path": "vandalizer-qa@uidaho.edu/ABC.pdf", "raw_text": "",
        }
        mock_settings_fn.return_value = {
            "enabled": True, "rules": "no PII", "chunk_size": 8000, "chunk_overlap": 200,
        }
        cfg = MagicMock()
        cfg.upload_dir = "/app/static/uploads"
        MockSettings.return_value = cfg

        perform_document_validation(
            document_uuid="doc-1",
            document_path="vandalizer-qa@uidaho.edu/ABC.pdf",  # relative, as some callers pass
            background=True,
        )

        called_path = mock_extract.call_args[0][0]
        assert called_path == "/app/static/uploads/vandalizer-qa@uidaho.edu/ABC.pdf"


class TestOcrFailureLogging:
    def test_exhausted_attempts_log_warning_not_error(self):
        """OCR failure is a handled degradation (caller falls back to PyMuPDF),
        so attempt-exhaustion must log at warning, never error -> Sentry."""
        import app.services.document_readers as dr

        db = MagicMock()
        db.system_config.find_one.return_value = {
            "ocr_endpoint": "http://ocr.local/v1/ocrmd", "ocr_api_key": "",
        }
        with patch("app.tasks.get_sync_db", return_value=db), \
             patch("app.utils.encryption.decrypt_value", return_value=""), \
             patch("time.sleep"), \
             patch("builtins.open", side_effect=FileNotFoundError("no such file")), \
             patch.object(dr, "logger") as mock_logger:
            result = dr.ocr_extract_text_from_pdf("relative/gone.pdf", retries=3)

        assert result == ""
        mock_logger.error.assert_not_called()
        assert mock_logger.warning.called
