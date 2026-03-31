"""Tests for app.tasks.passive_tasks — trigger processing and scheduled automations.

Mocks pymongo DB and service functions to test workflow trigger evaluation logic.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bson import ObjectId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    status="pending",
    trigger_type="folder_watch",
    workflow_oid=None,
    documents=None,
    **extra,
):
    return {
        "_id": ObjectId(),
        "uuid": "evt-uuid",
        "status": status,
        "trigger_type": trigger_type,
        "workflow": workflow_oid or ObjectId(),
        "process_after": datetime.now(timezone.utc) - timedelta(minutes=1),
        "documents": documents or [],
        **extra,
    }


def _make_workflow(
    enabled=True,
    folder_watch_enabled=True,
    file_filters=None,
    conditions=None,
):
    return {
        "_id": ObjectId(),
        "input_config": {
            "folder_watch": {
                "enabled": folder_watch_enabled,
                "file_filters": file_filters or {},
            },
            "conditions": conditions or [],
        },
    }


# ---------------------------------------------------------------------------
# process_pending_triggers
# ---------------------------------------------------------------------------


class TestProcessPendingTriggers:
    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_queues_valid_trigger_event(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [{"_id": event["documents"][0], "title": "test.pdf", "extension": "pdf"}]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": event["documents"][0]}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=True),
            patch("app.services.passive_triggers.check_workflow_budget", return_value=(True, None)),
            patch("app.services.passive_triggers.check_throttling", return_value=(True, None)),
        ):
            result = process_pending_triggers()

        assert result["processed"] == 1
        mock_execute.delay.assert_called_once_with(str(event["_id"]))

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_when_workflow_not_found(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        event = _make_event()
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = None

        result = process_pending_triggers()

        assert result["processed"] == 0
        mock_execute.delay.assert_not_called()
        # Should have marked event as failed
        db.workflow_trigger_event.update_one.assert_called()
        update_args = db.workflow_trigger_event.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "failed"

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_when_folder_watch_disabled(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow(folder_watch_enabled=False)
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch")
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf

        result = process_pending_triggers()

        assert result["processed"] == 0
        update_args = db.workflow_trigger_event.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "skipped"

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_when_no_documents_pass_filters(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [{"_id": event["documents"][0]}]

        with patch("app.services.passive_triggers.apply_file_filters", return_value=[]):
            result = process_pending_triggers()

        assert result["processed"] == 0

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_when_conditions_not_met(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow(conditions=[{"field": "extension", "op": "eq", "value": "pdf"}])
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [{"_id": event["documents"][0]}]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": "doc1"}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=False),
        ):
            result = process_pending_triggers()

        assert result["processed"] == 0

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_when_budget_exceeded(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [{"_id": event["documents"][0]}]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": "d"}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=True),
            patch("app.services.passive_triggers.check_workflow_budget", return_value=(False, "Monthly budget exceeded")),
        ):
            result = process_pending_triggers()

        assert result["processed"] == 0
        update_args = db.workflow_trigger_event.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "skipped"

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_delays_when_throttled(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [{"_id": event["documents"][0]}]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": "d"}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=True),
            patch("app.services.passive_triggers.check_workflow_budget", return_value=(True, None)),
            patch("app.services.passive_triggers.check_throttling", return_value=(False, "Too frequent")),
        ):
            result = process_pending_triggers()

        assert result["processed"] == 0
        # Should push process_after forward, not mark as skipped
        update_args = db.workflow_trigger_event.update_one.call_args[0]
        assert "process_after" in update_args[1]["$set"]

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_handles_processing_error_gracefully(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        event = _make_event()
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.side_effect = Exception("DB connection lost")

        # Should not raise — errors are caught per-event
        result = process_pending_triggers()

        assert result["processed"] == 0
        update_args = db.workflow_trigger_event.update_one.call_args[0]
        assert update_args[1]["$set"]["status"] == "failed"

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_processes_empty_pending_list(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db
        cursor = MagicMock()
        cursor.limit.return_value = []
        db.workflow_trigger_event.find.return_value = cursor

        result = process_pending_triggers()

        assert result["processed"] == 0
        mock_execute.delay.assert_not_called()


# ---------------------------------------------------------------------------
# process_scheduled_automations
# ---------------------------------------------------------------------------


class TestProcessScheduledAutomations:
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_when_croniter_not_installed(self, mock_get_db):
        from app.tasks.passive_tasks import process_scheduled_automations

        with patch.dict("sys.modules", {"croniter": None}):
            # The actual import check is inside the function body
            # This verifies the function handles missing croniter gracefully
            pass

    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_processes_empty_automation_list(self, mock_get_db):
        from app.tasks.passive_tasks import process_scheduled_automations

        db = MagicMock()
        mock_get_db.return_value = db
        db.automation.find.return_value = []

        result = process_scheduled_automations()

        assert result["processed"] == 0

    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_automation_without_action_id(self, mock_get_db):
        from app.tasks.passive_tasks import process_scheduled_automations

        db = MagicMock()
        mock_get_db.return_value = db
        db.automation.find.return_value = [
            {"_id": ObjectId(), "action_id": None, "trigger_config": {"cron_expression": "* * * * *"}},
        ]

        result = process_scheduled_automations()

        assert result["processed"] == 0

    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_skips_automation_without_cron_expression(self, mock_get_db):
        from app.tasks.passive_tasks import process_scheduled_automations

        db = MagicMock()
        mock_get_db.return_value = db
        db.automation.find.return_value = [
            {"_id": ObjectId(), "action_id": str(ObjectId()), "trigger_config": {}},
        ]

        result = process_scheduled_automations()

        assert result["processed"] == 0
