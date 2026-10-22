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
    @pytest.mark.parametrize("claim_won", [True, False])
    def test_queues_valid_trigger_event(self, mock_get_db, mock_execute, claim_won):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db
        db.workflow_trigger_event.update_one.return_value.modified_count = int(claim_won)

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [{"_id": event["documents"][0], "title": "test.pdf", "extension": "pdf", "raw_text": "text"}]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": event["documents"][0]}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=True),
            patch("app.services.passive_triggers.check_workflow_budget", return_value=(True, None)),
            patch("app.services.passive_triggers.check_throttling", return_value=(True, None)),
        ):
            result = process_pending_triggers()

        assert result["processed"] == int(claim_won)
        if claim_won:
            mock_execute.delay.assert_called_once_with(str(event["_id"]))
        else:
            mock_execute.delay.assert_not_called()
        assert db.workflow_trigger_event.update_one.call_args.args[0]["status"] == "pending"

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_defers_when_input_still_extracting(self, mock_get_db, mock_execute):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()])
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [
            {"_id": event["documents"][0], "raw_text": "", "processing": True},
        ]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": event["documents"][0]}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=True),
            patch("app.services.passive_triggers.check_workflow_budget", return_value=(True, None)),
            patch("app.services.passive_triggers.check_throttling", return_value=(True, None)),
        ):
            result = process_pending_triggers()

        assert result["processed"] == 0
        mock_execute.delay.assert_not_called()
        # Event deferred (process_after bumped), not queued or skipped.
        last_set = db.workflow_trigger_event.update_one.call_args[0][1]["$set"]
        assert "process_after" in last_set
        assert "status" not in last_set

    @patch("app.tasks.passive_tasks.execute_workflow_passive")
    @patch("app.tasks.passive_tasks.get_sync_db")
    @pytest.mark.parametrize("processing", [False, True])
    def test_skips_when_input_extraction_failed_or_timed_out(self, mock_get_db, mock_execute, processing):
        from app.tasks.passive_tasks import process_pending_triggers

        db = MagicMock()
        mock_get_db.return_value = db

        wf = _make_workflow()
        event = _make_event(workflow_oid=wf["_id"], trigger_type="folder_watch", documents=[ObjectId()],
                            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=6))
        cursor = MagicMock()
        cursor.limit.return_value = [event]
        db.workflow_trigger_event.find.return_value = cursor
        db.workflow.find_one.return_value = wf
        db.smart_document.find.return_value = [
            {"_id": event["documents"][0], "raw_text": "", "processing": processing},
        ]

        with (
            patch("app.services.passive_triggers.apply_file_filters", return_value=[{"_id": event["documents"][0]}]),
            patch("app.services.passive_triggers.evaluate_conditions", return_value=True),
            patch("app.services.passive_triggers.check_workflow_budget", return_value=(True, None)),
            patch("app.services.passive_triggers.check_throttling", return_value=(True, None)),
        ):
            result = process_pending_triggers()

        assert result["processed"] == 0
        mock_execute.delay.assert_not_called()
        last_set = db.workflow_trigger_event.update_one.call_args[0][1]["$set"]
        assert last_set["status"] == "skipped"

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
            {"_id": event["documents"][0], "title": "t.pdf", "extension": "pdf", "raw_text": "text"},
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


class TestExecuteWorkflowPassiveMissingFixedDocument:
    """An automation run has the same fixed-document check as a manual run:
    a document deleted from Files fails the run and the trigger event by
    name, before any step is built."""

    @patch("app.services.workflow_engine.build_workflow_engine")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_fails_event_and_result_by_name(self, mock_get_db, mock_build):
        from app.tasks.passive_tasks import execute_workflow_passive

        event_id, wf_id, result_id = ObjectId(), ObjectId(), ObjectId()
        db = MagicMock()
        mock_get_db.return_value = db
        db.workflow_trigger_event.find_one.return_value = {
            "_id": event_id, "workflow": wf_id, "status": "queued", "documents": [], "trigger_type": "folder_watch",
        }
        db.workflow.find_one.return_value = {
            "_id": wf_id, "user_id": "u1", "steps": [],
            "input_config": {"trigger_type": "folder_watch",
                             "fixed_documents": [{"uuid": "gone", "title": "Award Terms.pdf"}]},
        }
        db.system_config.find_one.return_value = {}
        db.smart_document.find.return_value = []
        db.smart_document.find_one.return_value = None
        db.workflow_result.insert_one.return_value.inserted_id = result_id

        out = execute_workflow_passive(str(event_id))

        assert "Award Terms.pdf" in out["error"]
        mock_build.assert_not_called()
        result_set = db.workflow_result.update_one.call_args[0][1]["$set"]
        assert result_set["status"] == "error"
        assert result_set["error_payload"]["code"] == "fixed_documents_missing"
        event_set = db.workflow_trigger_event.update_one.call_args[0][1]["$set"]
        assert event_set["status"] == "failed"
        assert "deleted from Files" in event_set["error"]


class TestExecuteWorkflowPassiveRecordsItsAutomation:
    """The run records the automation and trigger event that produced it, so
    the stale-run reaper (tasks.activity.reap_stale_workflow_runs) can bell
    the person who set the schedule rather than whoever owns the workflow
    (#835). Exercised through the fixed-document-missing path, which fails
    after the WorkflowResult is inserted and before any step is built."""

    @patch("app.services.workflow_engine.build_workflow_engine")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_result_doc_carries_automation_and_trigger_event_ids(self, mock_get_db, _build):
        from app.tasks.passive_tasks import execute_workflow_passive

        event_id, wf_id, auto_id = ObjectId(), ObjectId(), ObjectId()
        db = MagicMock()
        mock_get_db.return_value = db
        db.workflow_trigger_event.find_one.return_value = {
            "_id": event_id, "workflow": wf_id, "status": "queued", "documents": [], "trigger_type": "schedule",
            "trigger_context": {"automation_id": str(auto_id), "automation_name": "Nightly"},
        }
        db.workflow.find_one.return_value = {
            "_id": wf_id, "user_id": "u1", "steps": [],
            "input_config": {"fixed_documents": [{"uuid": "gone", "title": "Gone.pdf"}]},
        }
        db.system_config.find_one.return_value = {}
        db.smart_document.find.return_value = []
        db.smart_document.find_one.return_value = None
        db.workflow_result.insert_one.return_value.inserted_id = ObjectId()

        execute_workflow_passive(str(event_id))

        inserted = db.workflow_result.insert_one.call_args[0][0]
        assert inserted["automation_id"] == str(auto_id)
        assert inserted["trigger_event_id"] == str(event_id)
        assert inserted["is_passive"] is True
        # The trigger context is still copied whole (older code read it there).
        assert inserted["input_context"]["automation_id"] == str(auto_id)

    @patch("app.services.workflow_engine.build_workflow_engine")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_a_folder_watch_run_without_an_automation_records_none(self, mock_get_db, _build):
        from app.tasks.passive_tasks import execute_workflow_passive

        event_id, wf_id = ObjectId(), ObjectId()
        db = MagicMock()
        mock_get_db.return_value = db
        db.workflow_trigger_event.find_one.return_value = {
            "_id": event_id, "workflow": wf_id, "status": "queued", "documents": [], "trigger_type": "folder_watch",
        }
        db.workflow.find_one.return_value = {
            "_id": wf_id, "user_id": "u1", "steps": [],
            "input_config": {"fixed_documents": [{"uuid": "gone", "title": "Gone.pdf"}]},
        }
        db.system_config.find_one.return_value = {}
        db.smart_document.find.return_value = []
        db.smart_document.find_one.return_value = None
        db.workflow_result.insert_one.return_value.inserted_id = ObjectId()

        execute_workflow_passive(str(event_id))

        inserted = db.workflow_result.insert_one.call_args[0][0]
        assert inserted["automation_id"] is None
        assert inserted["trigger_event_id"] == str(event_id)


@pytest.mark.parametrize("status", ["running", "completed", "failed", "pending", "skipped"])
@patch("app.tasks.passive_tasks.get_sync_db")
def test_passive_redelivery_never_reexecutes_nonqueued_event(mock_get_db, status):
    from app.tasks.passive_tasks import execute_workflow_passive
    db = mock_get_db.return_value
    event_id, result_id = ObjectId(), ObjectId()
    db.workflow_trigger_event.find_one.return_value = {
        "_id": event_id, "status": status, "workflow_result": result_id,
    }
    result = execute_workflow_passive(str(event_id))
    assert result["status"] == status
    assert result["workflow_result_id"] == str(result_id)
    db.workflow_trigger_event.update_one.assert_not_called()
    db.workflow_result.insert_one.assert_not_called()
    db.workflow.find_one.assert_not_called()


@patch("app.tasks.passive_tasks.get_sync_db")
def test_passive_concurrent_claim_loser_performs_no_steps(mock_get_db):
    from app.tasks.passive_tasks import execute_workflow_passive
    db = mock_get_db.return_value
    event_id = ObjectId()
    db.workflow_trigger_event.find_one.return_value = {"_id": event_id, "status": "queued"}
    db.workflow_trigger_event.update_one.return_value.modified_count = 0
    assert execute_workflow_passive(str(event_id))["status"] == "already_claimed"
    assert db.workflow_trigger_event.update_one.call_args.args[0] == {"_id": event_id, "status": "queued"}
    db.workflow_result.insert_one.assert_not_called()
    db.workflow.find_one.assert_not_called()


class TestExecuteWorkflowPassiveLogLevel:
    """A step error is the workflow's configuration, not a fault (Sentry
    7761609315: "Add Website is not configured: no URL", once per scheduled
    run). It still fails the run and tells the owner; it just stays out of
    Sentry's error stream, as it does in execute_workflow_task."""

    def _run(self, engine_error):
        from app.tasks.passive_tasks import execute_workflow_passive

        event_id, wf_id = ObjectId(), ObjectId()
        db = MagicMock()
        db.workflow_trigger_event.find_one.return_value = {
            "_id": event_id, "uuid": "evt-1", "workflow": wf_id, "documents": [],
            "trigger_type": "schedule", "attempt_number": 1,
            # The task claims queued events only (redelivery guard).
            "status": "queued",
        }
        db.workflow.find_one.return_value = {
            "_id": wf_id, "user_id": "u1", "steps": [], "input_config": {},
        }
        db.system_config.find_one.return_value = {}
        db.smart_document.find.return_value = []
        db.workflow_result.insert_one.return_value.inserted_id = ObjectId()
        engine = MagicMock()
        engine.execute.side_effect = engine_error

        with patch("app.tasks.passive_tasks.get_sync_db", return_value=db), \
             patch("app.services.workflow_engine.build_workflow_engine", return_value=engine), \
             patch("app.tasks.passive_tasks.logger") as log:
            execute_workflow_passive(str(event_id))

        def failed(calls):
            return [c for c in calls if "Passive execution failed" in str(c)]

        return failed(log.error.call_args_list), failed(log.warning.call_args_list), db

    def test_a_step_error_is_logged_at_warning(self):
        from app.services.workflow_engine import WorkflowStepError

        errors, warnings, db = self._run(WorkflowStepError(
            "Extraction",
            "Add Website is not configured: no URL. Open the step and enter "
            "the address of the page to fetch.",
        ))
        assert errors == []
        assert len(warnings) == 1
        # Still a failed run, and not retried.
        event_sets = [c[0][1]["$set"] for c in db.workflow_trigger_event.update_one.call_args_list]
        assert any(s.get("status") == "failed" for s in event_sets)
        assert not any(s.get("status") == "pending" for s in event_sets)

    def test_an_unexpected_crash_is_still_an_error(self):
        errors, warnings, _db = self._run(RuntimeError("boom"))
        assert len(errors) == 1
        assert warnings == []
