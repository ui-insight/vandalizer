"""Tests for app.services.output_handlers — sync file saving, webhooks, notifications.

These are sync functions, so no async/await needed except where noted.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# should_send_notification (pure function)
# ---------------------------------------------------------------------------


class TestShouldSendNotification:
    def test_always_returns_true(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({}, {"conditions": "always"}) is True

    def test_success_matches_completed(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({"status": "completed"}, {"conditions": "success"}) is True

    def test_success_rejects_failed(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({"status": "failed"}, {"conditions": "success"}) is False

    def test_failure_matches_failed(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({"status": "failed"}, {"conditions": "failure"}) is True

    def test_failure_rejects_completed(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({"status": "completed"}, {"conditions": "failure"}) is False

    def test_unknown_condition_defaults_true(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({}, {"conditions": "unknown_cond"}) is True

    def test_missing_conditions_defaults_true(self):
        from app.services.output_handlers import should_send_notification

        assert should_send_notification({}, {}) is True


# ---------------------------------------------------------------------------
# compute_webhook_signature
# ---------------------------------------------------------------------------


class TestComputeWebhookSignature:
    def test_returns_timestamp_and_signature_format(self):
        from app.services.output_handlers import compute_webhook_signature

        sig = compute_webhook_signature(b'{"key": "value"}', "my-secret")
        assert sig.startswith("t=")
        assert ",v1=" in sig

    def test_deterministic_for_same_time(self):
        from app.services.output_handlers import compute_webhook_signature

        with patch("time.time", return_value=1000000):
            sig1 = compute_webhook_signature(b"payload", "secret")
            sig2 = compute_webhook_signature(b"payload", "secret")
        assert sig1 == sig2

    def test_different_secret_different_sig(self):
        from app.services.output_handlers import compute_webhook_signature

        with patch("time.time", return_value=1000000):
            sig1 = compute_webhook_signature(b"payload", "secret1")
            sig2 = compute_webhook_signature(b"payload", "secret2")
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# call_webhook
# ---------------------------------------------------------------------------


class TestCallWebhook:
    def test_post_request_with_bearer_auth(self):
        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {"name": "Test WF"}

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.services.output_handlers.httpx") as mock_httpx,
            patch("app.utils.url_validation.validate_outbound_url"),
        ):
            from app.services.output_handlers import call_webhook

            result_doc = {
                "workflow": "wf-1", "_id": "res-1", "status": "completed",
                "trigger_type": "schedule", "final_output": {"output": {"key": "val"}},
            }
            webhook_config = {
                "url": "https://example.com/hook",
                "method": "POST",
                "auth": {"type": "bearer", "token": "my-token"},
            }
            call_webhook(result_doc, webhook_config)
            mock_httpx.post.assert_called_once()
            call_args = mock_httpx.post.call_args
            assert call_args[1]["headers"]["Authorization"] == "Bearer my-token"

    def test_put_request(self):
        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {"name": "WF"}

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.services.output_handlers.httpx") as mock_httpx,
            patch("app.utils.url_validation.validate_outbound_url"),
        ):
            from app.services.output_handlers import call_webhook

            call_webhook(
                {"workflow": "wf-1", "_id": "r-1", "status": "completed",
                 "trigger_type": "manual", "final_output": {}},
                {"url": "https://example.com/hook", "method": "PUT"},
            )
            mock_httpx.put.assert_called_once()

    def test_api_key_auth(self):
        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {"name": "WF"}

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.services.output_handlers.httpx") as mock_httpx,
            patch("app.utils.url_validation.validate_outbound_url"),
        ):
            from app.services.output_handlers import call_webhook

            call_webhook(
                {"workflow": "wf-1", "_id": "r-1", "status": "ok",
                 "trigger_type": "manual", "final_output": {}},
                {"url": "https://example.com/hook", "method": "POST",
                 "auth": {"type": "api_key", "key_name": "X-Custom-Key", "api_key": "abc123"}},
            )
            call_args = mock_httpx.post.call_args
            assert call_args[1]["headers"]["X-Custom-Key"] == "abc123"

    def test_no_auth(self):
        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {"name": "WF"}

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.services.output_handlers.httpx") as mock_httpx,
            patch("app.utils.url_validation.validate_outbound_url"),
        ):
            from app.services.output_handlers import call_webhook

            call_webhook(
                {"workflow": "wf-1", "_id": "r-1", "status": "ok",
                 "trigger_type": "manual", "final_output": {}},
                {"url": "https://example.com/hook", "method": "POST"},
            )
            call_args = mock_httpx.post.call_args
            assert "Authorization" not in call_args[1]["headers"]


# ---------------------------------------------------------------------------
# _save_as_csv
# ---------------------------------------------------------------------------


class TestSaveAsCsv:
    def test_saves_list_of_dicts(self, tmp_path):
        from app.services.output_handlers import _save_as_csv

        fp = tmp_path / "test.csv"
        data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        _save_as_csv(fp, data)
        content = fp.read_text()
        assert "name,age" in content
        assert "Alice,30" in content

    def test_saves_empty_data(self, tmp_path):
        from app.services.output_handlers import _save_as_csv

        fp = tmp_path / "empty.csv"
        _save_as_csv(fp, None)
        assert fp.read_text() == ""

    def test_saves_non_dict_data_as_string(self, tmp_path):
        from app.services.output_handlers import _save_as_csv

        fp = tmp_path / "raw.csv"
        _save_as_csv(fp, "raw string data")
        assert fp.read_text() == "raw string data"


# ---------------------------------------------------------------------------
# _save_as_json
# ---------------------------------------------------------------------------


class TestSaveAsJson:
    def test_saves_dict_as_json(self, tmp_path):
        from app.services.output_handlers import _save_as_json

        fp = tmp_path / "test.json"
        _save_as_json(fp, {"key": "value", "num": 42})
        loaded = json.loads(fp.read_text())
        assert loaded["key"] == "value"
        assert loaded["num"] == 42


# ---------------------------------------------------------------------------
# _save_workflow_as_text
# ---------------------------------------------------------------------------


class TestSaveWorkflowAsText:
    def test_saves_list_of_dicts(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_text

        fp = tmp_path / "out.txt"
        data = [{"field1": "val1", "field2": "val2"}, {"field1": "val3", "field2": "val4"}]
        _save_workflow_as_text(fp, data)
        content = fp.read_text()
        assert "field1: val1" in content
        assert "---" in content

    def test_saves_single_dict(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_text

        fp = tmp_path / "out.txt"
        _save_workflow_as_text(fp, {"a": 1, "b": 2})
        content = fp.read_text()
        assert "a: 1" in content
        assert "b: 2" in content

    def test_saves_plain_string(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_text

        fp = tmp_path / "out.txt"
        _save_workflow_as_text(fp, "just a string")
        assert fp.read_text() == "just a string"

    def test_saves_none_as_empty(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_text

        fp = tmp_path / "out.txt"
        _save_workflow_as_text(fp, None)
        assert fp.read_text() == ""


# ---------------------------------------------------------------------------
# _save_workflow_as_markdown
# ---------------------------------------------------------------------------


class TestSaveWorkflowAsMarkdown:
    def test_saves_list_as_table(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_markdown

        fp = tmp_path / "out.md"
        data = [{"name": "Alice", "role": "PI"}, {"name": "Bob", "role": "Co-PI"}]
        _save_workflow_as_markdown(fp, data, "Results")
        content = fp.read_text()
        assert "# Results" in content
        assert "| name | role |" in content
        assert "Alice" in content

    def test_saves_dict_as_field_value_table(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_markdown

        fp = tmp_path / "out.md"
        _save_workflow_as_markdown(fp, {"a": 1}, "Title")
        content = fp.read_text()
        assert "| Field | Value |" in content
        assert "| a | 1 |" in content

    def test_escapes_pipes_in_values(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_markdown

        fp = tmp_path / "out.md"
        data = [{"val": "a|b"}]
        _save_workflow_as_markdown(fp, data, "T")
        content = fp.read_text()
        assert "a\\|b" in content


# ---------------------------------------------------------------------------
# send_workflow_notification
# ---------------------------------------------------------------------------


class TestSendWorkflowNotification:
    def test_email_notification_with_owner(self):
        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {"name": "My WF", "user_id": "user1"}
        mock_db.user.find_one.return_value = {"email": "owner@example.com"}

        result_doc = {"workflow": "wf-1", "status": "completed", "trigger_type": "manual"}
        notification = {"channel": "email", "recipients": [], "notify_owner": True}

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.services.output_handlers._send_email") as mock_send,
        ):
            from app.services.output_handlers import send_workflow_notification

            send_workflow_notification(result_doc, notification)
            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            assert "owner@example.com" in args[0]

    def test_skips_when_no_recipients(self):
        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {"name": "WF", "user_id": "u1"}
        mock_db.user.find_one.return_value = {"email": None}

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.services.output_handlers._send_email") as mock_send,
        ):
            from app.services.output_handlers import send_workflow_notification

            send_workflow_notification(
                {"workflow": "wf-1", "status": "completed", "trigger_type": "manual"},
                {"channel": "email", "recipients": [], "notify_owner": True},
            )
            mock_send.assert_not_called()

    def test_teams_channel_delegates(self):
        with patch("app.services.output_handlers._send_teams_notification") as mock_teams:
            from app.services.output_handlers import send_workflow_notification

            send_workflow_notification(
                {"workflow": "wf-1", "status": "completed"},
                {"channel": "teams"},
            )
            mock_teams.assert_called_once()

    def test_ignores_unsupported_channel(self):
        with (
            patch("app.services.output_handlers._send_teams_notification") as mock_teams,
            patch("app.services.output_handlers._send_email") as mock_email,
        ):
            from app.services.output_handlers import send_workflow_notification

            send_workflow_notification(
                {"workflow": "wf-1", "status": "completed"},
                {"channel": "slack"},
            )
            mock_teams.assert_not_called()
            mock_email.assert_not_called()


# ---------------------------------------------------------------------------
# save_results_to_folder
# ---------------------------------------------------------------------------


class TestSaveResultsToFolder:
    def test_saves_csv_file(self, tmp_path):
        mock_db = MagicMock()
        mock_db.smart_folder.find_one.return_value = {"uuid": "folder-1"}
        mock_db.workflow.find_one.return_value = {"name": "Test WF", "user_id": "user1"}

        result_doc = {
            "workflow": "wf-1",
            "_id": "res-1",
            "final_output": {"output": [{"key": "PI", "value": "Alice"}]},
        }
        storage_config = {"destination_folder": "folder-1", "format": "csv"}

        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.config.Settings", return_value=mock_settings),
        ):
            from app.services.output_handlers import save_results_to_folder

            path = save_results_to_folder(result_doc, storage_config)
            assert path.endswith(".csv")
            mock_db.smart_document.insert_one.assert_called_once()

    def test_raises_without_destination_folder(self):
        from app.services.output_handlers import save_results_to_folder

        with pytest.raises(ValueError, match="No destination folder"):
            save_results_to_folder({}, {})

    def test_raises_when_folder_not_found(self):
        mock_db = MagicMock()
        mock_db.smart_folder.find_one.return_value = None

        with patch("app.services.output_handlers.get_sync_db", return_value=mock_db):
            from app.services.output_handlers import save_results_to_folder

            with pytest.raises(ValueError, match="not found"):
                save_results_to_folder({}, {"destination_folder": "bad-id"})


# ---------------------------------------------------------------------------
# save_extraction_results_to_folder
# ---------------------------------------------------------------------------


class TestSaveExtractionResultsToFolder:
    def test_saves_json_extraction(self, tmp_path):
        mock_db = MagicMock()
        mock_db.smart_folder.find_one.return_value = {"uuid": "folder-1"}

        extraction_results = {"PI Name": "Alice", "Award Amount": "$50k"}
        automation = {"name": "Grant Extract", "user_id": "user1"}
        storage_config = {"destination_folder": "folder-1", "format": "json"}

        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)

        with (
            patch("app.services.output_handlers.get_sync_db", return_value=mock_db),
            patch("app.config.Settings", return_value=mock_settings),
        ):
            from app.services.output_handlers import save_extraction_results_to_folder

            path = save_extraction_results_to_folder(extraction_results, automation, storage_config)
            assert path.endswith(".json")
            content = json.loads(Path(path).read_text())
            assert content["PI Name"] == "Alice"

    def test_raises_without_destination_folder(self):
        from app.services.output_handlers import save_extraction_results_to_folder

        with pytest.raises(ValueError, match="No destination folder"):
            save_extraction_results_to_folder({}, {}, {})

    def test_raises_when_folder_not_found(self):
        mock_db = MagicMock()
        mock_db.smart_folder.find_one.return_value = None

        with patch("app.services.output_handlers.get_sync_db", return_value=mock_db):
            from app.services.output_handlers import save_extraction_results_to_folder

            with pytest.raises(ValueError, match="not found"):
                save_extraction_results_to_folder({}, {}, {"destination_folder": "missing"})


# ---------------------------------------------------------------------------
# _save_extraction_as_markdown
# ---------------------------------------------------------------------------


class TestSaveExtractionAsMarkdown:
    def test_saves_field_value_table(self, tmp_path):
        from app.services.output_handlers import _save_extraction_as_markdown

        fp = tmp_path / "extraction.md"
        _save_extraction_as_markdown(fp, {"PI": "Alice", "Amount": "$50k"}, "Grant Extract")
        content = fp.read_text()
        assert "# Grant Extract" in content
        assert "| PI | Alice |" in content
        assert "| Amount | $50k |" in content
