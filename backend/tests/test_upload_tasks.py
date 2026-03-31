"""Tests for app.tasks.upload_tasks.dispatch_upload_tasks.

Verifies Celery task chaining, error link, and conditional dispatching
of semantic ingestion, classification, and validation tasks.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_celery():
    with patch("app.tasks.upload_tasks.celery") as mock:
        # Set up signature mocks that support | (chain) operator
        extraction_sig = MagicMock()
        update_sig = MagicMock()
        cleanup_sig = MagicMock()
        chain_result = MagicMock()
        chain_result.apply_async.return_value = MagicMock(id="task-id-123")

        extraction_sig.__or__ = MagicMock(return_value=chain_result)
        mock.signature.side_effect = lambda name, **kw: {
            "tasks.document.extraction": extraction_sig,
            "tasks.document.update": update_sig,
            "tasks.document.cleanup": cleanup_sig,
        }[name]

        mock._chain_result = chain_result
        mock._extraction_sig = extraction_sig
        mock._cleanup_sig = cleanup_sig
        yield mock


class TestDispatchUploadTasks:
    def test_returns_task_id(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        result = dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf")
        assert result == "task-id-123"

    def test_chains_extraction_then_update(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf")

        # Extraction signature created with correct kwargs
        mock_celery.signature.assert_any_call(
            "tasks.document.extraction",
            kwargs={"document_uuid": "doc-uuid", "extension": "pdf"},
            queue="documents",
        )
        # Update signature created
        mock_celery.signature.assert_any_call(
            "tasks.document.update",
            kwargs={"document_uuid": "doc-uuid"},
            queue="documents",
            immutable=True,
        )

    def test_attaches_cleanup_as_error_link(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf")

        mock_celery._chain_result.apply_async.assert_called_once()
        call_kwargs = mock_celery._chain_result.apply_async.call_args
        assert "link_error" in call_kwargs.kwargs or "link_error" in (call_kwargs[1] if len(call_kwargs) > 1 else {})

    def test_dispatches_semantic_ingestion_when_user_id_present(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf", user_id="user1")

        mock_celery.send_task.assert_any_call(
            "tasks.document.semantic_ingestion",
            kwargs={
                "raw_text": "",
                "document_uuid": "doc-uuid",
                "user_id": "user1",
            },
            queue="documents",
            countdown=10,
        )

    def test_skips_semantic_ingestion_without_user_id(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf")

        # Should not have sent semantic_ingestion
        for call in mock_celery.send_task.call_args_list:
            assert call[0][0] != "tasks.document.semantic_ingestion"

    def test_always_dispatches_classification(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf")

        mock_celery.send_task.assert_any_call(
            "tasks.document.classify",
            kwargs={"document_uuid": "doc-uuid"},
            queue="documents",
            countdown=15,
        )

    def test_always_dispatches_validation(self, mock_celery):
        from app.tasks.upload_tasks import dispatch_upload_tasks

        dispatch_upload_tasks("doc-uuid", "pdf", "/uploads/test.pdf")

        mock_celery.send_task.assert_any_call(
            "tasks.upload.validation",
            kwargs={
                "document_uuid": "doc-uuid",
                "document_path": "/uploads/test.pdf",
                "background": True,
            },
            queue="uploads",
        )
