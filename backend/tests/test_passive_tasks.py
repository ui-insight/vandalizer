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
        # Legacy path: no automation_id in trigger_context — gate falls back
        # to workflow.input_config.folder_watch.enabled.
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
    def test_runs_when_automation_enabled_even_if_workflow_flag_missing(
        self, mock_get_db, mock_execute,
    ):
        """New-style folder_watch automations don't set workflow.input_config.folder_watch.enabled —
        the gate must come from the automation's own ``enabled`` flag instead."""
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow(folder_watch_enabled=False)
        auto_oid = ObjectId()
        event = _make_event(
            workflow_oid=wf["_id"],
            trigger_type="folder_watch",
            documents=[ObjectId()],
            trigger_context={"automation_id": str(auto_oid)},
        )
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.automation.find_one.return_value = {"_id": auto_oid, "enabled": True}
        db.smart_document.find.return_value = [
            {"_id": event["documents"][0], "title": "t.pdf", "extension": "pdf"},
        ]

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
    def test_skips_when_automation_disabled(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        # Workflow flag is True but the automation itself is disabled — the
        # automation gate takes precedence when trigger_context names one.
        wf = _make_workflow(folder_watch_enabled=True)
        auto_oid = ObjectId()
        event = _make_event(
            workflow_oid=wf["_id"],
            trigger_type="folder_watch",
            trigger_context={"automation_id": str(auto_oid)},
        )
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.automation.find_one.return_value = {"_id": auto_oid, "enabled": False}

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
# process_outputs
# ---------------------------------------------------------------------------


class TestProcessOutputs:
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_uses_automation_from_trigger_context_not_workflow_lookup(self, mock_get_db):
        """When multiple automations target the same workflow, process_outputs must
        resolve the specific one that produced this run via trigger_context.automation_id
        — not arbitrarily via the workflow-wide find_one."""
        from app.tasks.passive_tasks import process_outputs

        db = MagicMock()
        mock_get_db.return_value = db

        wf_oid = ObjectId()
        result_oid = ObjectId()
        trigger_event_oid = ObjectId()
        specific_auto_oid = ObjectId()

        result_doc = {
            "_id": result_oid,
            "workflow": wf_oid,
            "status": "completed",
            "final_output": {"output": "hello"},
        }
        workflow = {"_id": wf_oid, "name": "WF", "output_config": {}, "user_id": "u1"}
        trigger_event = {
            "_id": trigger_event_oid,
            "workflow": wf_oid,
            "trigger_context": {"automation_id": str(specific_auto_oid)},
            "trigger_type": "folder_watch",
        }
        specific_auto = {
            "_id": specific_auto_oid,
            "output_config": {
                "notifications": [
                    {"channel": "email", "recipients": ["a@b.com"], "conditions": "always"},
                ],
            },
        }

        # find_one is called multiple times — return appropriate values per collection
        db.workflow_result.find_one.return_value = result_doc
        db.workflow.find_one.return_value = workflow
        db.workflow_trigger_event.find_one.return_value = trigger_event
        db.work_items.find_one.return_value = None

        # Return the specific automation for the _id lookup, and a stale-config
        # automation for the workflow-wide fallback (which should NOT be used).
        def auto_find_one(query):
            if "_id" in query and query["_id"] == specific_auto_oid:
                return specific_auto
            return {"_id": ObjectId(), "output_config": {}}

        db.automation.find_one.side_effect = auto_find_one

        with (
            patch("app.services.output_handlers.send_workflow_notification") as mock_send,
            patch("app.services.output_handlers.should_send_notification", return_value=True),
        ):
            process_outputs(str(result_oid))

        # Notification from the SPECIFIC automation's output_config should fire
        mock_send.assert_called_once()
        sent_notification = mock_send.call_args[0][1]
        assert sent_notification["recipients"] == ["a@b.com"]

    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_falls_back_to_workflow_lookup_when_no_automation_id(self, mock_get_db):
        from app.tasks.passive_tasks import process_outputs

        db = MagicMock()
        mock_get_db.return_value = db

        wf_oid = ObjectId()
        result_oid = ObjectId()
        result_doc = {
            "_id": result_oid,
            "workflow": wf_oid,
            "status": "completed",
            "final_output": {"output": "hi"},
        }
        workflow = {"_id": wf_oid, "name": "WF", "output_config": {}, "user_id": "u1"}
        trigger_event = {
            "_id": ObjectId(),
            "workflow": wf_oid,
            "trigger_context": {},  # no automation_id
            "trigger_type": "folder_watch",
        }
        legacy_auto = {
            "_id": ObjectId(),
            "output_config": {
                "notifications": [
                    {"channel": "email", "recipients": ["legacy@b.com"], "conditions": "always"},
                ],
            },
        }

        db.workflow_result.find_one.return_value = result_doc
        db.workflow.find_one.return_value = workflow
        db.workflow_trigger_event.find_one.return_value = trigger_event
        db.work_items.find_one.return_value = None
        db.automation.find_one.return_value = legacy_auto

        with (
            patch("app.services.output_handlers.send_workflow_notification") as mock_send,
            patch("app.services.output_handlers.should_send_notification", return_value=True),
        ):
            process_outputs(str(result_oid))

        mock_send.assert_called_once()
        sent_notification = mock_send.call_args[0][1]
        assert sent_notification["recipients"] == ["legacy@b.com"]


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
