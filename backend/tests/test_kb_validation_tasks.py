"""Tests for app.tasks.kb_validation_tasks — Celery-level retry policy.

Focuses on generate_test_queries_task: transient LLM connection blips
(ModelAPIError "Connection error.", the oauthdev outbound-socket issue) must
trigger a Celery retry on a fresh attempt, while permanent HTTP-status errors
(ModelHTTPError, a 4xx) and non-transient bugs must propagate without retry.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError


class _RetryCalled(Exception):
    """Sentinel raised by the patched task.retry so we can detect a retry."""


class TestGenerateTestQueriesRetry:
    @patch(
        "app.tasks.kb_validation_tasks.generate_test_queries_task.retry",
        side_effect=_RetryCalled(),
    )
    @patch("app.tasks.kb_validation_tasks._generate_test_queries_async", new_callable=MagicMock)
    @patch("app.tasks.kb_validation_tasks._run_async")
    def test_model_api_error_triggers_celery_retry(self, mock_run_async, mock_gen, mock_retry):
        """A connection blip should be retried at the Celery level."""
        from app.tasks.kb_validation_tasks import generate_test_queries_task

        exc = ModelAPIError(model_name="m", message="Connection error.")
        mock_run_async.side_effect = exc
        with pytest.raises(_RetryCalled):
            generate_test_queries_task("kb-uuid", "user-1")
        mock_retry.assert_called_once()
        # The original error is threaded through so Celery records the cause.
        assert mock_retry.call_args.kwargs.get("exc") is exc

    @patch(
        "app.tasks.kb_validation_tasks.generate_test_queries_task.retry",
        side_effect=_RetryCalled(),
    )
    @patch("app.tasks.kb_validation_tasks._generate_test_queries_async", new_callable=MagicMock)
    @patch("app.tasks.kb_validation_tasks._run_async")
    def test_model_http_error_is_not_retried(self, mock_run_async, mock_gen, mock_retry):
        """A 4xx HTTP-status error won't improve on retry — re-raise it as-is."""
        from app.tasks.kb_validation_tasks import generate_test_queries_task

        mock_run_async.side_effect = ModelHTTPError(
            status_code=400, model_name="m", body="bad request"
        )
        with pytest.raises(ModelHTTPError):
            generate_test_queries_task("kb-uuid", "user-1")
        mock_retry.assert_not_called()

    @patch(
        "app.tasks.kb_validation_tasks.generate_test_queries_task.retry",
        side_effect=_RetryCalled(),
    )
    @patch("app.tasks.kb_validation_tasks._generate_test_queries_async", new_callable=MagicMock)
    @patch("app.tasks.kb_validation_tasks._run_async")
    def test_permanent_error_is_not_retried(self, mock_run_async, mock_gen, mock_retry):
        """Non-transient bugs (ValueError etc.) propagate without a retry."""
        from app.tasks.kb_validation_tasks import generate_test_queries_task

        mock_run_async.side_effect = ValueError("bad coverage value")
        with pytest.raises(ValueError):
            generate_test_queries_task("kb-uuid", "user-1")
        mock_retry.assert_not_called()
