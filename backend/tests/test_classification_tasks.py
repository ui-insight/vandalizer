"""Tests for the _classify async function in app.tasks.classification_tasks.

Mocks database init, models, and classification service functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestClassifyTask:
    @pytest.mark.asyncio
    async def test_document_not_found_returns_early(self):
        mock_classify = AsyncMock()
        mock_apply = AsyncMock()

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.document.SmartDocument") as MockDoc, \
             patch("app.models.system_config.SystemConfig"), \
             patch("app.services.classification_service.classify_document", mock_classify), \
             patch("app.services.classification_service.apply_classification", mock_apply):
            MockDoc.find_one = AsyncMock(return_value=None)

            from app.tasks.classification_tasks import _classify

            await _classify("nonexistent-uuid")

            mock_classify.assert_not_called()
            mock_apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_classification_disabled_applies_default(self):
        doc = MagicMock()
        doc.classification = None

        mock_config = MagicMock()
        mock_config.get_classification_config.return_value = {
            "enabled": False,
            "auto_classify_on_upload": False,
            "default_classification": "internal",
        }

        mock_classify = AsyncMock()
        mock_apply = AsyncMock()

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.document.SmartDocument") as MockDoc, \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.services.classification_service.classify_document", mock_classify), \
             patch("app.services.classification_service.apply_classification", mock_apply):
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockConfig.get_config = AsyncMock(return_value=mock_config)

            from app.tasks.classification_tasks import _classify

            await _classify("doc-uuid")

            mock_classify.assert_not_called()
            mock_apply.assert_awaited_once_with(
                doc,
                classification="internal",
                confidence=1.0,
                classified_by="default",
            )

    @pytest.mark.asyncio
    async def test_classification_enabled_classifies_and_applies(self):
        doc = MagicMock()
        doc.classification = None

        mock_config = MagicMock()
        mock_config.get_classification_config.return_value = {
            "enabled": True,
            "auto_classify_on_upload": True,
            "default_classification": "unrestricted",
        }

        classify_result = {
            "classification": "ferpa",
            "confidence": 0.88,
            "reason": "Student records",
        }

        mock_classify = AsyncMock(return_value=classify_result)
        mock_apply = AsyncMock()

        with patch("app.database.init_db", new_callable=AsyncMock), \
             patch("app.config.Settings"), \
             patch("app.models.document.SmartDocument") as MockDoc, \
             patch("app.models.system_config.SystemConfig") as MockConfig, \
             patch("app.services.classification_service.classify_document", mock_classify), \
             patch("app.services.classification_service.apply_classification", mock_apply):
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockConfig.get_config = AsyncMock(return_value=mock_config)

            from app.tasks.classification_tasks import _classify

            await _classify("doc-uuid")

            mock_classify.assert_awaited_once_with(doc)
            mock_apply.assert_awaited_once_with(
                doc,
                classification="ferpa",
                confidence=0.88,
                classified_by="auto",
            )


class TestClassifyTaskErrorHandling:
    """The auto-classify task is best-effort: a model failure must not crash
    the task (unhandled -> Sentry) or stamp a guessed classification."""

    def test_model_http_error_is_swallowed(self):
        """A 401 (misconfigured API key) is a ModelHTTPError — permanent, so it
        must not retry and must not propagate; the doc stays unclassified."""
        from pydantic_ai.exceptions import ModelHTTPError
        from app.tasks.classification_tasks import classify_document_task

        err = ModelHTTPError(status_code=401, model_name="gpt-4o-mini", body={"code": "invalid_api_key"})
        with patch("app.tasks.classification_tasks._classify", MagicMock()), \
             patch("app.tasks.classification_tasks.run_task_async", side_effect=err):
            # Returns cleanly (no exception raised out of the task).
            assert classify_document_task("doc-uuid") is None

    def test_transient_model_error_retries(self):
        """A ModelAPIError (connection blip) is transient — the task retries it
        with the original exception."""
        from pydantic_ai.exceptions import ModelAPIError
        from app.tasks.classification_tasks import classify_document_task

        err = ModelAPIError(model_name="gpt-4o-mini", message="Connection error.")
        sentinel = RuntimeError("retry-called")
        with patch("app.tasks.classification_tasks._classify", MagicMock()), \
             patch("app.tasks.classification_tasks.run_task_async", side_effect=err), \
             patch.object(classify_document_task, "retry", side_effect=sentinel) as mock_retry:
            with pytest.raises(RuntimeError, match="retry-called"):
                classify_document_task("doc-uuid")
        mock_retry.assert_called_once()
        assert mock_retry.call_args.kwargs.get("exc") is err
