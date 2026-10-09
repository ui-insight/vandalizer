"""A long run someone started bells them when it finishes (#994).

v5 belled failures but not completions, so an RA who started a run over a
folder of documents and moved on had no way to know it was done.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services import run_notifications
from app.services.run_notifications import notify_extraction_completed, notify_workflow_completed

NOW = datetime.datetime.now(datetime.timezone.utc)


def _ago(seconds):
    return NOW - datetime.timedelta(seconds=seconds)


def _result(**overrides):
    base = {"_id": "res-1", "status": "completed", "start_time": _ago(120), "workflow": "wf-1"}
    base.update(overrides)
    return base


def _sent(fn, **kwargs):
    with patch.object(run_notifications, "create_notification_sync") as create:
        fn(MagicMock(), **kwargs)
    return create.call_args.kwargs if create.called else None


class TestWorkflowCompleted:
    def test_a_long_run_bells_the_person_who_started_it(self):
        sent = _sent(
            notify_workflow_completed, user_id="ra-1",
            workflow_doc={"_id": "wf-1", "name": "NOA Summary"},
            result_doc=_result(document_title="award-123.pdf"),
        )
        assert sent["user_id"] == "ra-1"
        assert sent["kind"] == "workflow_completed"
        assert sent["title"] == "Workflow finished: NOA Summary"
        assert sent["body"] == "Results are ready for award-123.pdf."
        assert sent["link"] == "/?workflow=wf-1"
        assert sent["coalesce_key"] == "workflow_completed:res-1"

    def test_runs_in_one_batch_collect_into_one_entry(self):
        sent = _sent(
            notify_workflow_completed, user_id="ra-1",
            workflow_doc={"_id": "wf-1", "name": "NOA Summary"},
            result_doc=_result(batch_id="batch-9"),
        )
        assert sent["coalesce_key"] == "workflow_completed:batch-9"
        assert sent["group_title"] == "Workflow finished {count}×: NOA Summary"

    @pytest.mark.parametrize("why,user,result", [
        ("finished while being watched", "ra-1", _result(start_time=_ago(10))),
        ("an automation run", "ra-1", _result(is_passive=True)),
        ("an automation run by id", "ra-1", _result(automation_id="auto-1")),
        ("canceled, not completed", "ra-1", _result(status="canceled")),
        ("nobody started it", None, _result()),
        ("a system run", "system", _result()),
        ("no start time", "ra-1", _result(start_time=None)),
    ])
    def test_no_bell(self, why, user, result):
        assert _sent(notify_workflow_completed, user_id=user, workflow_doc={"_id": "wf-1"}, result_doc=result) is None, why

    def test_a_naive_start_time_is_read_as_utc(self):
        naive = (NOW - datetime.timedelta(seconds=90)).replace(tzinfo=None)
        assert _sent(notify_workflow_completed, user_id="ra-1", workflow_doc={"_id": "wf-1"}, result_doc=_result(start_time=naive))

    def test_a_failure_writing_the_bell_never_raises(self):
        with patch.object(run_notifications, "create_notification_sync", side_effect=RuntimeError("mongo down")):
            notify_workflow_completed(MagicMock(), user_id="ra-1", workflow_doc={"_id": "wf-1"}, result_doc=_result())


class TestExtractionCompleted:
    def _db(self):
        db = MagicMock()
        db.search_set.find_one.return_value = {"title": "NIH Award Terms"}
        return db

    def test_a_long_extraction_bells_with_its_document_count(self):
        with patch.object(run_notifications, "create_notification_sync") as create:
            notify_extraction_completed(
                self._db(), user_id="ra-1", activity={"_id": "act-1", "status": "running", "started_at": _ago(45)},
                search_set_uuid="ss-1", document_count=12,
            )
        sent = create.call_args.kwargs
        assert sent["kind"] == "extraction_completed"
        assert sent["title"] == "Extraction finished: NIH Award Terms"
        assert sent["body"] == "Values extracted from 12 documents are ready."
        assert sent["coalesce_key"] == "extraction_completed:act-1"

    @pytest.mark.parametrize("why,activity", [
        ("quick", {"_id": "a", "status": "running", "started_at": _ago(5)}),
        ("a retry of a run that already finished", {"_id": "a", "status": "completed", "started_at": _ago(500)}),
    ])
    def test_no_bell(self, why, activity):
        with patch.object(run_notifications, "create_notification_sync") as create:
            notify_extraction_completed(self._db(), user_id="ra-1", activity=activity, search_set_uuid="ss-1", document_count=1)
        assert not create.called, why


def test_the_workflow_task_bells_the_runs_launcher_from_inside_the_finalize_claim():
    from app.tasks import workflow_tasks

    db = MagicMock()
    db.workflow_result.find_one.return_value = _result()
    with patch.object(workflow_tasks, "_activity_owner", return_value="ra-7"), \
         patch("app.services.run_notifications.create_notification_sync") as create:
        workflow_tasks._notify_run_completed(db, "507f1f77bcf86cd799439011", {"_id": "wf-1", "name": "X"}, "507f1f77bcf86cd799439012")
    assert create.call_args.kwargs["user_id"] == "ra-7"
