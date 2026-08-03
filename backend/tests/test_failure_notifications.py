"""Tests for app.services.failure_notifications.

These emitters run inside Celery tasks that have already done real work, so the
behaviors worth locking in are the ones that keep them from causing damage:
they never raise, they never fire mid-retry, and they address the right user.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bson import ObjectId

from app.services.failure_notifications import (
    is_final_attempt,
    notify_automation_failed,
    notify_document_failed,
    notify_extraction_failed,
    notify_workflow_failed,
)


def _task(retries: int = 0, max_retries: int | None = 3):
    return SimpleNamespace(
        request=SimpleNamespace(retries=retries), max_retries=max_retries,
    )


# ---------------------------------------------------------------------------
# is_final_attempt
# ---------------------------------------------------------------------------


class TestIsFinalAttempt:
    def test_non_transient_error_is_final_immediately(self):
        # ValueError isn't in autoretry_for, so Celery will not retry it.
        assert is_final_attempt(_task(retries=0), ValueError("bad input")) is True

    def test_transient_error_with_budget_left_is_not_final(self):
        assert is_final_attempt(_task(retries=1), ConnectionError("blip")) is False

    def test_transient_error_with_budget_spent_is_final(self):
        assert is_final_attempt(_task(retries=3), ConnectionError("blip")) is True

    def test_unlimited_retries_is_never_final(self):
        assert is_final_attempt(
            _task(retries=99, max_retries=None), TimeoutError("slow"),
        ) is False

    def test_task_without_request_is_treated_as_final(self):
        # Better a notification the user can act on than silence.
        assert is_final_attempt(object(), ConnectionError("blip")) is True


# ---------------------------------------------------------------------------
# notify_workflow_failed
# ---------------------------------------------------------------------------


class TestNotifyWorkflowFailed:
    def test_notifies_workflow_owner_with_deep_link(self):
        wf_id = ObjectId()
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_workflow_failed(
                MagicMock(),
                workflow_doc={"_id": wf_id, "name": "Budget Review", "user_id": "alice"},
                error=RuntimeError("step 2 blew up"),
            )

        kwargs = create.call_args.kwargs
        assert kwargs["user_id"] == "alice"
        assert kwargs["kind"] == "workflow_failed"
        assert kwargs["title"] == "Workflow failed: Budget Review"
        assert kwargs["link"] == f"/?workflow={wf_id}"
        assert "step 2 blew up" in kwargs["body"]
        assert kwargs["coalesce_key"] == f"workflow_failed:{wf_id}"

    def test_explicit_user_id_wins_over_workflow_owner(self):
        # An automation's owner set the schedule and need not own the workflow.
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_workflow_failed(
                MagicMock(),
                workflow_doc={"_id": ObjectId(), "name": "WF", "user_id": "alice"},
                error="boom",
                user_id="bob",
            )

        assert create.call_args.kwargs["user_id"] == "bob"

    def test_automation_run_is_titled_as_an_automation(self):
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_workflow_failed(
                MagicMock(),
                workflow_doc={"_id": ObjectId(), "name": "WF", "user_id": "alice"},
                error="boom",
                automation_name="Nightly intake",
            )

        kwargs = create.call_args.kwargs
        assert kwargs["title"] == "Automation failed: Nightly intake"
        assert "WF" in kwargs["body"]

    def test_no_recipient_means_no_notification(self):
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_workflow_failed(MagicMock(), workflow_doc={}, error="boom")

        create.assert_not_called()

    def test_never_raises_when_the_write_fails(self):
        with patch(
            "app.services.failure_notifications.create_notification_sync",
            side_effect=RuntimeError("mongo down"),
        ):
            notify_workflow_failed(
                MagicMock(),
                workflow_doc={"_id": ObjectId(), "name": "WF", "user_id": "alice"},
                error="boom",
            )  # must not raise


# ---------------------------------------------------------------------------
# notify_extraction_failed
# ---------------------------------------------------------------------------


class TestNotifyExtractionFailed:
    def test_resolves_set_title_from_the_database(self):
        db = MagicMock()
        db.search_set.find_one.return_value = {"title": "NSF Budget Fields"}

        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_extraction_failed(
                db, user_id="alice", search_set_uuid="ss-1", error="LLM timeout",
            )

        kwargs = create.call_args.kwargs
        assert kwargs["title"] == "Extraction failed: NSF Budget Fields"
        assert kwargs["link"] == "/?extraction=ss-1"
        assert kwargs["kind"] == "extraction_failed"

    def test_falls_back_when_the_set_is_gone(self):
        db = MagicMock()
        db.search_set.find_one.return_value = None

        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_extraction_failed(
                db, user_id="alice", search_set_uuid="ss-1", error="boom",
            )

        assert create.call_args.kwargs["title"] == "Extraction failed: Extraction"

    def test_no_user_means_no_notification(self):
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_extraction_failed(
                MagicMock(), user_id=None, search_set_uuid="ss-1", error="boom",
            )

        create.assert_not_called()


# ---------------------------------------------------------------------------
# notify_document_failed
# ---------------------------------------------------------------------------


class TestNotifyDocumentFailed:
    def test_coalesces_per_user_not_per_document(self):
        # A 50-file upload with a dozen bad files should read as one row.
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_document_failed(
                MagicMock(),
                doc={"uuid": "d-1", "title": "grant.pdf", "user_id": "alice"},
                error="encrypted PDF",
            )

        kwargs = create.call_args.kwargs
        assert kwargs["coalesce_key"] == "document_failed:alice"
        assert kwargs["group_title"] == "{count} documents failed to process"
        assert kwargs["item_id"] == "d-1"
        assert kwargs["link"] == "/?mode=files"

    def test_missing_document_is_a_no_op(self):
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_document_failed(MagicMock(), doc=None, error="boom")

        create.assert_not_called()


# ---------------------------------------------------------------------------
# notify_automation_failed
# ---------------------------------------------------------------------------


class TestNotifyAutomationFailed:
    def test_notifies_owner_with_detail_prefix(self):
        auto_id = ObjectId()
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_automation_failed(
                MagicMock(),
                automation={"_id": auto_id, "name": "Nightly intake", "user_id": "alice"},
                error="bad cron expression",
                detail="The schedule could not be evaluated.",
            )

        kwargs = create.call_args.kwargs
        assert kwargs["user_id"] == "alice"
        assert kwargs["kind"] == "automation_failed"
        assert kwargs["title"] == "Automation failed: Nightly intake"
        assert kwargs["body"].startswith("The schedule could not be evaluated.")
        assert "bad cron expression" in kwargs["body"]
        assert kwargs["link"] == f"/?mode=automations&automation={auto_id}"

    def test_empty_error_still_produces_a_readable_body(self):
        with patch(
            "app.services.failure_notifications.create_notification_sync"
        ) as create:
            notify_automation_failed(
                MagicMock(),
                automation={"_id": ObjectId(), "name": "A", "user_id": "alice"},
                error=None,
            )

        assert create.call_args.kwargs["body"] == "No error detail was recorded."
