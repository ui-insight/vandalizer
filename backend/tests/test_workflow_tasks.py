"""Tests for Celery workflow tasks — execute_workflow_task,
execute_task_step_test, and resume_workflow_after_approval.

Mocks pymongo (_get_db) and build_workflow_engine to test orchestration
logic without MongoDB or real LLM calls.

Note: Celery tasks with bind=True receive `self` automatically. We call
the underlying function directly via .__wrapped__ or the task object.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_real_beanie_or_smtp():
    """The approval-pause path initialises Beanie on a throwaway loop and sends
    mail. Neither has a server under pytest, and every unmocked attempt burns
    the 5 s Mongo server-selection timeout per Beanie call — the four
    approval tests went from well under a second to ~10 s each."""
    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.services.email_service.send_email", new=AsyncMock(return_value=True)):
        yield


def _fake_oid():
    return ObjectId()


def _mock_db(
    workflow_doc=None,
    result_doc=None,
    sys_config=None,
    step_docs=None,
    task_docs=None,
    smart_docs=None,
    search_set_items=None,
    approval_doc=None,
):
    """Build a fake pymongo database object."""
    db = MagicMock()

    db.workflow.find_one.return_value = workflow_doc
    db.workflow_result.find_one.side_effect = lambda *a, **kw: result_doc
    # The pickup's delivery counter ($inc + read-back). A real int matters:
    # it is compared against MAX_DELIVERY_ATTEMPTS.
    db.workflow_result.find_one_and_update.return_value = {"delivery_attempts": 1}
    db.system_config.find_one.return_value = sys_config or {}
    db.approval_request.find_one.return_value = approval_doc

    _steps = {s["_id"]: s for s in (step_docs or [])}
    _tasks = {t["_id"]: t for t in (task_docs or [])}
    _docs = {d["uuid"]: d for d in (smart_docs or [])}

    db.workflow_step.find_one.side_effect = lambda q, *a, **k: _steps.get(q.get("_id"))
    db.workflow_step_task.find_one.side_effect = lambda q, *a, **k: _tasks.get(q.get("_id"))
    db.smart_document.find_one.side_effect = lambda q, *a, **k: _docs.get(q.get("uuid"))
    db.smart_document.find.side_effect = lambda q, *a, **k: [
        _docs[u] for u in ((q.get("uuid") or {}).get("$in") or []) if u in _docs
    ]
    db.search_set_item.find.return_value = search_set_items or []
    db.search_set.find_one.return_value = None

    return db


def _make_workflow_doc(wf_id=None, user_id="user1", step_ids=None):
    return {
        "_id": wf_id or _fake_oid(),
        "name": "Test Workflow",
        "user_id": user_id,
        "steps": step_ids or [],
        "num_executions": 0,
        "resource_config": {"model": "gpt-4o"},
    }


def _make_result_doc(result_id=None, workflow_id=None, session_id="sess1"):
    return {
        "_id": result_id or _fake_oid(),
        "workflow": workflow_id or _fake_oid(),
        "session_id": session_id,
        "status": "queued",
        "num_steps_completed": 0,
        "num_steps_total": 2,
        "input_context": {"doc_uuids": ["uuid1"]},
    }


# ---------------------------------------------------------------------------
# execute_workflow_task
# ---------------------------------------------------------------------------

class TestExecuteWorkflowTask:
    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_successful_execution(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "test"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Final output", [{"name": "Doc", "output": ["uuid1"]}])
        mock_engine.usage = MagicMock(tokens_in=100, tokens_out=50)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow") as mock_val, \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            result = execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )

        assert result["status"] == "completed"
        # Verify running status was set
        first_update = db.workflow_result.update_one.call_args_list[0]
        assert first_update[0][1]["$set"]["status"] == "running"
        # Verify num_executions incremented
        db.workflow.update_one.assert_called_once()

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_completion_does_not_overwrite_a_cancelled_run(
        self, mock_build, mock_get_db,
    ):
        """Cancellation flips the row out-of-band and revokes the worker, but a
        step already in flight can finish before the revoke lands. Writing
        "completed" unconditionally undid the user's stop, so a batch they
        halted reported success — and on a batch that was the *only* thing
        stopping it, since batch runs carried no task id to revoke.
        """
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "test"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Final output", [{"name": "Doc", "output": ["uuid1"]}])
        mock_engine.usage = MagicMock(tokens_in=100, tokens_out=50)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )

        completed = [
            c for c in db.workflow_result.update_one.call_args_list
            if c[0][1].get("$set", {}).get("status") == "completed"
        ]
        assert completed, "no completion write was issued at all"
        for call in completed:
            assert call[0][0].get("status") == {"$ne": "canceled"}, (
                "the completion write was not guarded, so it would resurrect a "
                "run the user stopped"
            )

    @patch("app.tasks.workflow_tasks._get_db")
    def test_missing_workflow_raises(self, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        db = _mock_db(workflow_doc=None, result_doc={"_id": _fake_oid()})
        mock_get_db.return_value = db

        with pytest.raises(ValueError, match="not found"):
            execute_workflow_task(
                workflow_result_id=str(_fake_oid()),
                workflow_id=str(_fake_oid()),
                trigger_step_data={"doc_uuids": []},
                model="gpt-4o",
            )

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_execution_error_sets_error_status(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.side_effect = RuntimeError("LLM crashed")
        mock_build.return_value = mock_engine

        with pytest.raises(RuntimeError):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": []},
                model="gpt-4o",
            )

        error_calls = [c for c in db.workflow_result.update_one.call_args_list
                      if c[0][1].get("$set", {}).get("status") == "error"]
        assert len(error_calls) >= 1

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_step_failure_marks_run_failed_without_retry(self, mock_build, mock_get_db):
        """A failed step (blocked URL, HTTP error, ...) must fail the run —
        not surface the error text as a completed deliverable — and must not
        re-raise (deterministic failure, no Celery retry)."""
        from app.services.workflow_engine import WorkflowStepError
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.side_effect = WorkflowStepError(
            "API", "Blocked URL: URL resolves to blocked IP range: 127.0.0.1",
        )
        mock_build.return_value = mock_engine

        result = execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": []},
            model="gpt-4o",
        )

        assert result["status"] == "error"
        error_calls = [c for c in db.workflow_result.update_one.call_args_list
                       if c[0][1].get("$set", {}).get("status") == "error"]
        assert len(error_calls) == 1
        error_msg = error_calls[0][0][1]["$set"]["error"]
        assert "API step failed" in error_msg
        assert "blocked IP range" in error_msg
        # Never marked completed, and no final_output written.
        completed_calls = [c for c in db.workflow_result.update_one.call_args_list
                           if c[0][1].get("$set", {}).get("status") == "completed"]
        assert completed_calls == []

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_approval_pause(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ({
            "_approval_pause": True,
            "_review_instructions": "Check this",
            "_assigned_to_user_ids": ["reviewer1"],
            "_data_for_review": {"key": "value"},
            "output": {"key": "value"},
        }, [])
        mock_node = MagicMock()
        mock_node.name = "Approval"
        mock_engine.get_topological_order.return_value = [MagicMock(), mock_node]
        mock_build.return_value = mock_engine

        result = execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": []},
            model="gpt-4o",
        )

        assert result["status"] == "pending_approval"
        db.approval_request.insert_one.assert_called_once()
        approval_data = db.approval_request.insert_one.call_args[0][0]
        assert approval_data["status"] == "pending"

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_approval_pause_failure_sets_error_status(self, mock_build, mock_get_db):
        """A failure while persisting the approval must surface as an error
        status, not leave the run frozen in 'running' (the original bug)."""
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        # Simulate pymongo rejecting the artifact (e.g. non-BSON payload).
        db.approval_request.insert_one.side_effect = RuntimeError("cannot encode object")
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ({
            "_approval_pause": True,
            "_assigned_to_user_ids": ["reviewer1"],
            "_data_for_review": {"key": "value"},
            "output": {"key": "value"},
        }, [])
        mock_node = MagicMock()
        mock_node.name = "Approval"
        mock_engine.get_topological_order.return_value = [MagicMock(), mock_node]
        mock_build.return_value = mock_engine

        with pytest.raises(RuntimeError):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": []},
                model="gpt-4o",
            )

        error_calls = [c for c in db.workflow_result.update_one.call_args_list
                       if c[0][1].get("$set", {}).get("status") == "error"]
        assert len(error_calls) >= 1

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_approval_pause_sanitizes_non_bson_artifact(self, mock_build, mock_get_db):
        """Non-BSON review artifacts (e.g. bytes) are coerced before insert so
        the pause never crashes on an unencodable payload."""
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ({
            "_approval_pause": True,
            "_assigned_to_user_ids": ["reviewer1"],
            "_data_for_review": {"file": b"\x89PNG\x01\x02", "nested": [b"raw", {1, 2}]},
            "output": {"file": "x"},
        }, [])
        mock_node = MagicMock()
        mock_node.name = "Approval"
        mock_engine.get_topological_order.return_value = [MagicMock(), mock_node]
        mock_build.return_value = mock_engine

        result = execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": []},
            model="gpt-4o",
        )

        assert result["status"] == "pending_approval"
        stored = db.approval_request.insert_one.call_args[0][0]["data_for_review"]
        assert isinstance(stored["file"], str)
        # No bytes or sets survive anywhere in the stored artifact.
        assert all(not isinstance(v, (bytes, set)) for v in stored["nested"])

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_progress_writes_are_bson_safe(self, mock_build, mock_get_db):
        """steps_output writes carry whole node outputs — whatever a node
        emitted, bytes included. An unencodable write used to raise from inside
        execute() and kill an otherwise healthy run mid-step."""
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()

        def _execute(workflow_result_updater=None, **kwargs):
            workflow_result_updater({
                "steps_output.Export": {"output": b"\x89PNG", "meta": {1, 2}},
                "current_step_name": "Export",
            })
            return ("done", [])

        mock_engine.execute.side_effect = _execute
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": []},
                model="gpt-4o",
            )

        written = [c[0][1]["$set"] for c in db.workflow_result.update_one.call_args_list
                   if "steps_output.Export" in c[0][1].get("$set", {})]
        assert len(written) == 1
        step_output = written[0]["steps_output.Export"]
        assert isinstance(step_output["output"], str)
        assert isinstance(step_output["meta"], list)
        # Plain values pass through untouched.
        assert written[0]["current_step_name"] == "Export"

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_activity_tracking(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id, activity_id = _fake_oid(), _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("output", [])
        mock_engine.usage = MagicMock(tokens_in=200, tokens_out=100)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": []},
                model="gpt-4o",
                activity_id=str(activity_id),
            )

        activity_completed = [c for c in db.activity_event.update_one.call_args_list
                             if c[0][1].get("$set", {}).get("status") == "completed"]
        assert len(activity_completed) >= 1

        # Tokens are accumulated ($inc), not overwritten: a run can span several
        # execution passes (approval gates), each with its own engine, and the
        # final pass must not erase what earlier passes banked.
        token_incs = [c[0][1]["$inc"] for c in db.activity_event.update_one.call_args_list
                      if "$inc" in c[0][1]]
        assert len(token_incs) == 1
        assert token_incs[0]["tokens_input"] == 200
        assert token_incs[0]["tokens_output"] == 100
        assert token_incs[0]["total_tokens"] == 300

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_search_set_resolution(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        step_id, task_id = _fake_oid(), _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Extract", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Extraction", "data": {"search_set_uuid": "ss-123"}}],
            search_set_items=[
                {"searchphrase": "Name", "searchtype": "extraction"},
                {"searchphrase": "Date", "searchtype": "extraction"},
            ],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        db.search_set.find_one.return_value = {"uuid": "ss-123"}
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("output", [])
        mock_engine.usage = MagicMock(tokens_in=0, tokens_out=0)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )

        build_call = mock_build.call_args
        steps_data = build_call[1].get("steps_data") or build_call[0][0]
        for step in steps_data:
            for t in step.get("tasks", []):
                if t.get("name") == "Extraction":
                    assert set(t["data"]["keys"]) == {"Name", "Date"}

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_doc_text_preloading(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        step_id, task_id = _fake_oid(), _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "S1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "summarize"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "Document content here"}],
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("output", [])
        mock_engine.usage = MagicMock(tokens_in=0, tokens_out=0)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )

        build_call = mock_build.call_args
        steps_data = build_call[1].get("steps_data") or build_call[0][0]
        for step in steps_data:
            for t in step.get("tasks", []):
                if t.get("name") == "Prompt":
                    assert t["data"]["doc_texts"] == ["Document content here"]

# ---------------------------------------------------------------------------
# execute_task_step_test
# ---------------------------------------------------------------------------

class TestExecuteTaskStepTest:
    @patch("app.tasks.workflow_tasks._get_db")
    def test_prompt_step_test(self, mock_get_db):
        from app.tasks.workflow_tasks import execute_task_step_test

        db = _mock_db(smart_docs=[{"uuid": "uuid1", "raw_text": "test doc text"}])
        mock_get_db.return_value = db

        with patch("app.services.workflow_engine.llm_chat_model") as mock_llm:
            mock_llm.return_value = "LLM response"
            result = execute_task_step_test(
                task_name="Prompt",
                task_data={"prompt": "Summarize", "model": "gpt-4o"},
                doc_uuids=["uuid1"],
            )
        assert result is not None

    @patch("app.tasks.workflow_tasks._get_db")
    def test_add_document_step_test(self, mock_get_db):
        from app.tasks.workflow_tasks import execute_task_step_test

        db = _mock_db(smart_docs=[{"uuid": "uuid1", "raw_text": "hello"}])
        mock_get_db.return_value = db

        result = execute_task_step_test(
            task_name="AddDocument",
            task_data={},
            doc_uuids=["uuid1"],
        )
        assert result is not None

    @patch("app.tasks.workflow_tasks._get_db")
    def test_step_warning_is_returned_alongside_the_output(self, mock_get_db):
        """A Form Filler that could not fill a field completes with a warning;
        Test Step used to drop it and show a clean "Test Completed"."""
        from app.tasks.workflow_tasks import execute_task_step_test

        db = _mock_db(smart_docs=[{"uuid": "uuid1", "raw_text": "Rate 47%"}])
        mock_get_db.return_value = db

        with patch("app.services.workflow_engine._run_form_filler_model") as mock_model:
            mock_model.return_value = '{"rate": "47%", "cap": "Not provided in context"}'
            result = execute_task_step_test(
                task_name="FormFiller",
                task_data={"template": "Rate: {{rate}}\nCap: {{cap}}", "model": "gpt-4o"},
                doc_uuids=["uuid1"],
            )
        assert result["output"] == "Rate: 47%\nCap: [Not provided: cap]"
        assert result["step_test_warning"].startswith("1 field not found in the input")

    @patch("app.tasks.workflow_tasks._get_db")
    def test_step_without_warning_returns_bare_output(self, mock_get_db):
        from app.tasks.workflow_tasks import execute_task_step_test

        db = _mock_db(smart_docs=[{"uuid": "uuid1", "raw_text": "Rate 47%"}])
        mock_get_db.return_value = db

        with patch("app.services.workflow_engine._run_form_filler_model") as mock_model:
            mock_model.return_value = '{"rate": "47%"}'
            result = execute_task_step_test(
                task_name="FormFiller",
                task_data={"template": "Rate: {{rate}}", "model": "gpt-4o"},
                doc_uuids=["uuid1"],
            )
        assert result == "Rate: 47%"

    @patch("app.tasks.workflow_tasks._get_db")
    def test_api_step_tests_with_no_documents(self, mock_get_db):
        """An API Node's input is its own URL, headers and body — a test needs
        no document, and the editor's Test Step button now sends none
        (support ticket: the button was greyed out and unclickable)."""
        from app.tasks.workflow_tasks import execute_task_step_test

        mock_get_db.return_value = _mock_db()

        with patch("app.services.workflow_engine.httpx.Client") as mock_client:
            resp = MagicMock(status_code=200, text='{"rows": 2}', headers={})
            resp.json.return_value = {"rows": 2}
            mock_client.return_value.__enter__.return_value.request.return_value = resp
            result = execute_task_step_test(
                task_name="APINode",
                task_data={"url": "https://example.com/query", "method": "POST"},
                doc_uuids=[],
            )

        assert "rows" in str(result)

    @patch("app.tasks.workflow_tasks._get_db")
    def test_unknown_task_type_raises(self, mock_get_db):
        from app.tasks.workflow_tasks import execute_task_step_test

        db = _mock_db()
        mock_get_db.return_value = db

        with pytest.raises(ValueError, match="Unknown task type"):
            execute_task_step_test(
                task_name="FakeTask",
                task_data={},
                doc_uuids=[],
            )

    @patch("app.tasks.workflow_tasks._get_db")
    def test_select_document_preloading(self, mock_get_db):
        from app.tasks.workflow_tasks import execute_task_step_test

        db = _mock_db(smart_docs=[
            {"uuid": "uuid1", "raw_text": "doc1"},
            {"uuid": "sel-uuid", "raw_text": "selected doc text"},
        ])
        mock_get_db.return_value = db

        result = execute_task_step_test(
            task_name="AddDocument",
            task_data={"input_source": "select_document", "selected_document_uuid": "sel-uuid"},
            doc_uuids=["uuid1"],
        )
        assert result is not None


# ---------------------------------------------------------------------------
# resume_workflow_after_approval
# ---------------------------------------------------------------------------

class TestResumeWorkflowAfterApproval:
    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_successful_resume(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": {"extracted": "data"},
            },
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Resumed output", [])
        mock_build.return_value = mock_engine

        result = resume_workflow_after_approval("a1")

        assert result["status"] == "completed"
        exec_kwargs = mock_engine.execute.call_args[1]
        assert exec_kwargs["start_index"] == 2
        assert exec_kwargs["initial_output"]["output"] == {"extracted": "data"}
        db.workflow.update_one.assert_called_once()

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_pauses_again_at_second_approval(self, mock_build, mock_get_db):
        """A workflow with two gates must pause a second time. The resume path
        used to ignore the sentinel and mark the run completed, so the second
        reviewer was never asked to approve anything."""
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": {"extracted": "data"},
            },
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ({
            "_approval_pause": True,
            "_paused_step_index": 3,
            "_review_instructions": "Second review",
            "_assigned_to_user_ids": ["reviewer2"],
            "_data_for_review": {"key": "value"},
            "output": {"key": "value"},
        }, [])
        mock_build.return_value = mock_engine

        result = resume_workflow_after_approval("a1")

        assert result["status"] == "pending_approval"
        db.approval_request.insert_one.assert_called_once()
        approval_data = db.approval_request.insert_one.call_args[0][0]
        assert approval_data["status"] == "pending"
        assert approval_data["step_index"] == 3
        assert approval_data["review_instructions"] == "Second review"
        assert approval_data["assigned_to_user_ids"] == ["reviewer2"]

        statuses = [c[0][1].get("$set", {}).get("status")
                    for c in db.workflow_result.update_one.call_args_list]
        assert "completed" not in statuses
        assert "pending_approval" in statuses
        # A run still awaiting review must not count as an execution.
        db.workflow.update_one.assert_not_called()

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_pause_without_stamped_index_scans_forward(self, mock_build, mock_get_db):
        """Fallback path for a sentinel with no stamped index: the name scan is
        floored at the resume point so it can't re-select the first gate."""
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": {"extracted": "data"},
            },
        )
        mock_get_db.return_value = db

        def _node(name):
            n = MagicMock()
            n.name = name
            return n

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ({
            "_approval_pause": True,
            "_assigned_to_user_ids": ["reviewer2"],
            "_data_for_review": {"key": "value"},
            "output": {"key": "value"},
        }, [])
        mock_engine.get_topological_order.return_value = [
            _node("Document"), _node("Approval"), _node("Prompt"),
            _node("Approval"), _node("AddDocument"),
        ]
        mock_build.return_value = mock_engine

        result = resume_workflow_after_approval("a1")

        assert result["status"] == "pending_approval"
        assert db.approval_request.insert_one.call_args[0][0]["step_index"] == 3

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_keeps_steps_from_earlier_passes(self, mock_build, mock_get_db):
        """execute() only reports the steps this pass ran. Without replaying the
        pre-gate ones from steps_output, the saved run record showed a workflow
        that began at the approval gate and everything before it vanished."""
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()
        result_doc = _make_result_doc(result_id=result_id, workflow_id=wf_id)
        result_doc["steps_output"] = {
            "Document": {"output": "doc text", "input": None},
            "Extraction": {
                "output": {"amount": "$5"},
                "input": "doc text",
                "retrieved_sources": [{"document_id": "d1", "page": 2}],
                "warning": "low confidence",
            },
        }
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=result_doc,
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 2, "data_for_review": {"amount": "$5"},
            },
        )
        mock_get_db.return_value = db

        def _node(name):
            n = MagicMock()
            n.name = name
            return n

        mock_engine = MagicMock()
        mock_engine.execute.return_value = (
            "Final", [{"name": "Formatter", "output": "Final", "input": "x"}],
        )
        mock_engine.get_topological_order.return_value = [
            _node("Document"), _node("Extraction"), _node("Approval"),
            _node("Formatter"),
        ]
        mock_engine.step_output_keys.return_value = [
            "Document", "Extraction", "Approval", "Formatter",
        ]
        mock_build.return_value = mock_engine

        assert resume_workflow_after_approval("a1")["status"] == "completed"

        completed = [c for c in db.workflow_result.update_one.call_args_list
                     if c[0][1].get("$set", {}).get("status") == "completed"]
        saved = completed[0][0][1]["$set"]

        names = [s["name"] for s in saved["final_output"]["data"]]
        # Approval is absent by design: the engine returns on the pause sentinel
        # before writing that step's output, so there is nothing to replay.
        assert names == ["Document", "Extraction", "Formatter"]

        replayed = saved["final_output"]["data"][1]
        assert replayed["output"] == {"amount": "$5"}
        assert replayed["input"] == "doc text"
        assert replayed["warning"] == "low confidence"

        # Citations from pre-gate steps survive into the run record too.
        assert saved["retrieved_sources"] == [{"document_id": "d1", "page": 2}]

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_finalizes_activity(self, mock_build, mock_get_db):
        """The resume path never touched the activity, so a run that passed
        through a gate stayed "running" forever and reported no tokens."""
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id, activity_id = _fake_oid(), _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": {"extracted": "data"},
            },
        )
        db.activity_event.find_one.return_value = {"_id": activity_id}
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Resumed output", [])
        mock_engine.get_topological_order.return_value = []
        mock_engine.step_output_keys.return_value = []
        mock_engine.usage = MagicMock(tokens_in=40, tokens_out=15)
        mock_build.return_value = mock_engine

        resume_workflow_after_approval("a1")

        completed = [c for c in db.activity_event.update_one.call_args_list
                     if c[0][1].get("$set", {}).get("status") == "completed"]
        assert len(completed) == 1

        incs = [c[0][1]["$inc"] for c in db.activity_event.update_one.call_args_list
                if "$inc" in c[0][1]]
        assert incs == [{"tokens_input": 40, "tokens_output": 15, "total_tokens": 55}]

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_runs_on_the_model_the_run_started_with(self, mock_build, mock_get_db):
        """An LLM step after an approval gate must use the run's model. The
        resume path used to read a `resource_config.model` key nothing writes,
        so every resumed step silently fell back to a hardcoded model name that
        is not configured — reaching the provider with no API key (401)."""
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()
        result_doc = _make_result_doc(result_id=result_id, workflow_id=wf_id)
        result_doc["model"] = "azure-gpt-4.1"

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=result_doc,
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": {"extracted": "data"},
            },
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Resumed output", [])
        mock_build.return_value = mock_engine

        resume_workflow_after_approval("a1")

        assert mock_build.call_args[1]["model"] == "azure-gpt-4.1"

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_without_stamped_model_uses_configured_default(self, mock_build, mock_get_db):
        """Runs created before the model was snapshotted must resolve the
        configured default, never a hardcoded model name."""
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            sys_config={"available_models": [{"name": "azure-gpt-4.1"}]},
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": {"extracted": "data"},
            },
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Resumed output", [])
        mock_build.return_value = mock_engine

        resume_workflow_after_approval("a1")

        assert mock_build.call_args[1]["model"] == "azure-gpt-4.1"

    def test_default_model_resolution(self):
        from app.tasks.workflow_tasks import _default_model_from_config

        models = [{"name": "azure-gpt-4.1"}, {"name": "claude-sonnet-5"}]

        # An explicit default wins.
        assert _default_model_from_config(
            {"available_models": models, "default_model": "claude-sonnet-5"}
        ) == "claude-sonnet-5"
        # A stale default that no longer matches a model falls back to the first.
        assert _default_model_from_config(
            {"available_models": models, "default_model": "removed-model"}
        ) == "azure-gpt-4.1"
        # No models configured at all resolves to empty, not a guessed name.
        assert _default_model_from_config({}) == ""

    @patch("app.tasks.workflow_tasks._get_db")
    def test_missing_approval_raises(self, mock_get_db):
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        db = _mock_db(approval_doc=None)
        mock_get_db.return_value = db

        with pytest.raises(ValueError, match="not found"):
            resume_workflow_after_approval("nonexistent")

    @patch("app.tasks.workflow_tasks._get_db")
    def test_unapproved_raises(self, mock_get_db):
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        db = _mock_db(approval_doc={"uuid": "a1", "status": "pending"})
        mock_get_db.return_value = db

        with pytest.raises(ValueError, match="not approved"):
            resume_workflow_after_approval("a1")

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_resume_error_sets_error_status(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import resume_workflow_after_approval

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            approval_doc={
                "uuid": "a1", "status": "approved",
                "workflow_result_id": result_id, "workflow_id": wf_id,
                "step_index": 1, "data_for_review": None,
            },
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.side_effect = RuntimeError("Engine failed")
        mock_build.return_value = mock_engine

        with pytest.raises(RuntimeError):
            resume_workflow_after_approval("a1")

        error_calls = [c for c in db.workflow_result.update_one.call_args_list
                      if c[0][1].get("$set", {}).get("status") == "error"]
        assert len(error_calls) >= 1


# ---------------------------------------------------------------------------
# Approval pause — activity bookkeeping
# ---------------------------------------------------------------------------

class TestPauseActivityBookkeeping:
    def _run_to_pause(self, mock_build, mock_get_db, activity_id):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ({
            "_approval_pause": True,
            "_paused_step_index": 2,
            "_assigned_to_user_ids": ["reviewer1"],
            "_data_for_review": {"key": "value"},
            "output": {"key": "value"},
        }, [])
        mock_engine.usage = MagicMock(tokens_in=120, tokens_out=60)
        mock_build.return_value = mock_engine

        result = execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": []},
            model="gpt-4o",
            activity_id=str(activity_id),
        )
        assert result["status"] == "pending_approval"
        return db, result_id

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_pause_links_activity_to_result(self, mock_build, mock_get_db):
        """Only the completion block used to set ``workflow_result`` on the
        activity, and a paused run never reaches it — so the resume pass, which
        finds its activity by that field, came up empty and the run's activity
        was orphaned mid-flight."""
        activity_id = _fake_oid()
        db, result_id = self._run_to_pause(mock_build, mock_get_db, activity_id)

        linked = [c[0][1]["$set"] for c in db.activity_event.update_one.call_args_list
                  if "workflow_result" in c[0][1].get("$set", {})]
        assert len(linked) == 1
        assert linked[0]["workflow_result"] == result_id
        # ActivityStatus has no "paused" member; a gated run is still running.
        assert "status" not in linked[0]

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_pause_banks_tokens_spent_before_the_gate(self, mock_build, mock_get_db):
        """Pausing returned without recording usage, so every token spent on the
        pre-gate steps was lost from the run's reported total."""
        db, _ = self._run_to_pause(mock_build, mock_get_db, _fake_oid())

        incs = [c[0][1]["$inc"] for c in db.activity_event.update_one.call_args_list
                if "$inc" in c[0][1]]
        assert incs == [{"tokens_input": 120, "tokens_output": 60, "total_tokens": 180}]


# ---------------------------------------------------------------------------
# _build_steps_data — one builder for the initial run and every resume pass
# ---------------------------------------------------------------------------

class TestBuildStepsData:
    def _db_with_extraction_step(self):
        step_id, task_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            step_docs=[{"_id": step_id, "name": "Extract", "tasks": [task_id]}],
            task_docs=[{
                "_id": task_id, "name": "Extraction",
                "data": {"search_set_uuid": "ss1"},
            }],
            search_set_items=[
                {"searchphrase": "amount", "is_optional": True, "enum_values": []},
                {"searchphrase": "status", "is_optional": False,
                 "enum_values": ["open", "closed"]},
            ],
        )
        db.search_set.find_one.return_value = {"uuid": "ss1"}
        return db, step_id

    def test_extraction_field_metadata_is_resolved(self):
        """The resume copy of this builder dropped field_metadata entirely, so
        enum/optional constraints were silently lost after an approval gate."""
        from app.tasks.workflow_tasks import _build_steps_data

        db, step_id = self._db_with_extraction_step()
        wf = _make_workflow_doc(step_ids=[step_id])

        steps_data, _ = _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": []})

        task_data = steps_data[1]["tasks"][0]["data"]
        assert task_data["keys"] == ["amount", "status"]
        assert task_data["field_metadata"] == [
            {"key": "amount", "is_optional": True, "enum_values": []},
            {"key": "status", "is_optional": False, "enum_values": ["open", "closed"]},
        ]

    def test_fixed_documents_are_merged(self):
        """Also missing from the resume copy: fixed inputs vanished on resume."""
        from app.tasks.workflow_tasks import _build_steps_data

        db, step_id = self._db_with_extraction_step()
        db.smart_document.find_one.side_effect = lambda q, *a, **k: {
            "uuid": q.get("uuid"), "raw_text": f"text-{q.get('uuid')}",
        }
        wf = _make_workflow_doc(step_ids=[step_id])
        wf["input_config"] = {"fixed_documents": [{"uuid": "fixed1"}]}

        steps_data, _ = _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": ["u1"]})

        assert steps_data[1]["tasks"][0]["data"]["doc_texts"] == ["text-u1", "text-fixed1"]

    def test_no_input_mode_excludes_fixed_documents(self):
        from app.tasks.workflow_tasks import _build_steps_data

        db, step_id = self._db_with_extraction_step()
        db.smart_document.find_one.side_effect = lambda q, *a, **k: {
            "uuid": q.get("uuid"), "raw_text": "text",
        }
        wf = _make_workflow_doc(step_ids=[step_id])
        wf["input_config"] = {
            "trigger_type": "no_input", "fixed_documents": [{"uuid": "fixed1"}],
        }

        steps_data, _ = _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": []})

        assert "doc_texts" not in steps_data[1]["tasks"][0]["data"]

    def test_output_step_names_are_collected(self):
        from app.tasks.workflow_tasks import _build_steps_data

        step_a, step_b = _fake_oid(), _fake_oid()
        db = _mock_db(step_docs=[
            {"_id": step_a, "name": "First Step", "tasks": []},
            {"_id": step_b, "name": "Final Step", "tasks": [], "is_output": True},
        ])
        wf = _make_workflow_doc(step_ids=[step_a, step_b])

        _, output_step_names = _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": []})

        assert output_step_names == ["Final_Step"]


# ---------------------------------------------------------------------------
# _resolve_saved_prompt_formatter — saved Prompt/Formatter link resolution
# ---------------------------------------------------------------------------

class TestResolveSavedPromptFormatter:
    def _db(self, search_set=None, item=None):
        db = MagicMock()
        db.search_set.find_one.return_value = search_set
        db.search_set_item.find_one.return_value = item
        return db

    def test_prompt_body_from_item_searchphrase(self):
        from app.tasks.workflow_tasks import _resolve_saved_prompt_formatter

        db = self._db(
            search_set={"uuid": "p1", "extraction_config": {"content": "stale"}},
            item={"searchphrase": "Summarize the grant."},
        )
        data = {"saved_prompt_uuid": "p1"}
        _resolve_saved_prompt_formatter(db, "Prompt", data)
        # The materialized item wins over the create-time config snapshot.
        assert data["prompt"] == "Summarize the grant."

    def test_prompt_body_falls_back_to_config_content(self):
        from app.tasks.workflow_tasks import _resolve_saved_prompt_formatter

        db = self._db(
            search_set={"uuid": "p1", "extraction_config": {"content": "Summarize."}},
            item=None,
        )
        data = {"saved_prompt_uuid": "p1"}
        _resolve_saved_prompt_formatter(db, "Prompt", data)
        assert data["prompt"] == "Summarize."

    def test_formatter_sets_format_template(self):
        from app.tasks.workflow_tasks import _resolve_saved_prompt_formatter

        db = self._db(
            search_set={"uuid": "f1", "extraction_config": {}},
            item={"searchphrase": "Render as a table."},
        )
        data = {"saved_formatter_uuid": "f1"}
        _resolve_saved_prompt_formatter(db, "Formatter", data)
        assert data["format_template"] == "Render as a table."

    def test_missing_set_leaves_data_untouched(self):
        from app.tasks.workflow_tasks import _resolve_saved_prompt_formatter

        db = self._db(search_set=None)
        data = {"saved_prompt_uuid": "gone", "prompt": "inline"}
        _resolve_saved_prompt_formatter(db, "Prompt", data)
        # Silent fallback: a deleted set must not wipe the existing inline body.
        assert data["prompt"] == "inline"

    def test_no_link_is_noop(self):
        from app.tasks.workflow_tasks import _resolve_saved_prompt_formatter

        db = self._db()
        data = {"prompt": "inline"}
        _resolve_saved_prompt_formatter(db, "Prompt", data)
        assert data == {"prompt": "inline"}
        db.search_set.find_one.assert_not_called()

    def test_other_task_type_is_noop(self):
        from app.tasks.workflow_tasks import _resolve_saved_prompt_formatter

        db = self._db(search_set={"uuid": "x"}, item={"searchphrase": "x"})
        data = {"saved_prompt_uuid": "p1"}
        _resolve_saved_prompt_formatter(db, "Extraction", data)
        assert "prompt" not in data
        db.search_set.find_one.assert_not_called()


# ---------------------------------------------------------------------------
# Pre-flight input-readiness gate
# ---------------------------------------------------------------------------

class TestClassifyInputDocuments:
    def test_ready_processing_failed_and_missing(self):
        from app.tasks.workflow_tasks import _classify_input_documents

        wf_id = _fake_oid()
        db = _mock_db(smart_docs=[
            {"uuid": "ready", "raw_text": "text"},
            {"uuid": "proc", "raw_text": "", "processing": True, "title": "Proc.pdf"},
            {"uuid": "failed", "raw_text": "", "processing": False, "title": "Bad.pdf"},
        ])
        ready, processing, failed = _classify_input_documents(
            db, {"_id": wf_id}, ["ready", "proc", "failed", "gone"],
        )
        assert ready == 1
        assert processing == ["Proc.pdf"]
        # A finished-but-empty doc and a missing uuid both count as failed.
        assert failed == ["Bad.pdf", "gone"]

    def test_own_origin_documents_are_ignored(self):
        from app.tasks.workflow_tasks import _classify_input_documents

        wf_id = _fake_oid()
        db = _mock_db(smart_docs=[
            {"uuid": "self", "raw_text": "", "origin_workflow_id": str(wf_id)},
        ])
        ready, processing, failed = _classify_input_documents(
            db, {"_id": wf_id}, ["self"],
        )
        assert (ready, processing, failed) == (0, [], [])


class TestInputReadinessGate:
    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_all_processing_retries(self, mock_build, mock_get_db):
        from celery.exceptions import Retry
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            smart_docs=[{"uuid": "uuid1", "raw_text": "", "processing": True}],
        )
        mock_get_db.return_value = db

        # A still-extracting input should defer the run, not execute it.
        with pytest.raises(Retry):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )
        mock_build.assert_not_called()

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_all_failed_marks_error_without_running(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            smart_docs=[{"uuid": "uuid1", "raw_text": "", "processing": False,
                         "title": "Bad.pdf"}],
        )
        mock_get_db.return_value = db

        with patch("app.tasks.workflow_tasks.logger") as mock_logger:
            result = execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )

        assert result is None
        mock_build.assert_not_called()
        set_op = db.workflow_result.update_one.call_args[0][1]["$set"]
        assert set_op["status"] == "error"
        assert "Bad.pdf" in set_op["error"]
        assert set_op["error_payload"]["code"] == "input_documents_unready"
        # A handled, user-actionable abort must not page Sentry as a fault
        # (VANDALIZER-BACKEND-1T) — same level as the oversize pre-flight.
        mock_logger.error.assert_not_called()
        assert any(
            "aborted pre-flight" in str(c.args[0]) for c in mock_logger.warning.call_args_list
        )

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_partial_readiness_proceeds(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id, step_id, task_id = (
            _fake_oid(), _fake_oid(), _fake_oid(), _fake_oid(),
        )
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "S", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "t"}}],
            smart_docs=[
                {"uuid": "ready", "raw_text": "text"},
                {"uuid": "proc", "raw_text": "", "processing": True},
            ],
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("out", [{"name": "Doc", "output": ["x"]}])
        mock_engine.usage = MagicMock(tokens_in=1, tokens_out=1)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            result = execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["ready", "proc"]},
                model="gpt-4o",
            )

        # One ready document is enough — the gate must not block the run.
        assert result["status"] == "completed"
        mock_build.assert_called_once()


# ---------------------------------------------------------------------------
# Pre-flight context grouping
# ---------------------------------------------------------------------------

def test_context_groups_bundle_the_document_trigger_package():
    from app.tasks.workflow_tasks import _document_context_groups

    steps = [
        {"name": "Document", "data": {"doc_uuids": ["a", "b", "c", "d"]}},
        {"name": "Assess", "tasks": [{"name": "Prompt", "data": {}}]},
    ]
    assert _document_context_groups(steps) == [{"a", "b", "c", "d"}]


def test_context_groups_do_not_sum_docs_from_unrelated_steps():
    from app.tasks.workflow_tasks import _document_context_groups

    # Step One reads doc a, Step Two reads doc b. They never share a prompt, so
    # they must be scored separately — summing them would refuse a valid run.
    steps = [
        {"name": "One", "tasks": [{"name": "Prompt", "data": {"selected_document_uuid": "a"}}]},
        {"name": "Two", "tasks": [{"name": "Prompt", "data": {"selected_document_uuid": "b"}}]},
    ]
    assert _document_context_groups(steps) == [{"a"}, {"b"}]


def test_context_groups_add_trigger_docs_to_each_step():
    from app.tasks.workflow_tasks import _document_context_groups

    # The trigger package flows into every step, so a step's own attachment is
    # read alongside it.
    steps = [
        {"name": "Document", "data": {"doc_uuids": ["trigger"]}},
        {"name": "One", "tasks": [{"name": "Prompt", "data": {"selected_document_uuid": "a"}}]},
    ]
    assert _document_context_groups(steps) == [{"trigger"}, {"trigger", "a"}]


def test_context_groups_empty_when_nothing_attached():
    from app.tasks.workflow_tasks import _document_context_groups

    assert _document_context_groups([{"name": "One", "tasks": []}]) == []


def test_document_token_counts_maps_by_uuid():
    from app.tasks.workflow_tasks import _document_token_counts

    db = MagicMock()
    db.smart_document.find.return_value = [
        {"uuid": "a", "title": "A.pdf", "token_count": 12_000},
        {"uuid": "b", "token_count": None},  # missing title/count
    ]
    counts = _document_token_counts(db, {"a", "b"})
    assert counts["a"] == {"uuid": "a", "title": "A.pdf", "token_count": 12_000}
    assert counts["b"] == {"uuid": "b", "title": "b", "token_count": 0}


def test_document_token_counts_skips_query_when_empty():
    from app.tasks.workflow_tasks import _document_token_counts

    db = MagicMock()
    assert _document_token_counts(db, set()) == {}
    db.smart_document.find.assert_not_called()


class TestPreflightContextOverflow:
    """A package that only overflows once concatenated is refused before the run."""

    def _nasa_db(self, wf_id, result_id, step_id, task_id):
        return _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            # Margin pinned to 1.0 so this fixture measures the pre-flight
            # wiring rather than the stored-count divergence allowance, which
            # is covered directly in test_context_budget.py.
            sys_config={"available_models": [
                {"name": "qwen3", "context_window": 65_536, "token_safety_margin": 1.0},
            ]},
            step_docs=[{"_id": step_id, "name": "Assess", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "assess"}}],
            smart_docs=[
                {"uuid": "a", "title": "ECIPES.pdf", "token_count": 12_000, "raw_text": "x"},
                {"uuid": "b", "title": "Overview.pdf", "token_count": 15_000, "raw_text": "x"},
                {"uuid": "c", "title": "Solicitation.pdf", "token_count": 25_000, "raw_text": "x"},
                {"uuid": "d", "title": "ProposersGuide.pdf", "token_count": 40_119, "raw_text": "x"},
            ],
        )

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_combined_overflow_fails_before_the_engine_runs(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id, step_id, task_id = (_fake_oid() for _ in range(4))
        db = self._nasa_db(wf_id, result_id, step_id, task_id)
        mock_get_db.return_value = db
        mock_engine = MagicMock()
        mock_build.return_value = mock_engine

        execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": ["a", "b", "c", "d"]},
            model="qwen3",
        )

        mock_engine.execute.assert_not_called()
        payload = next(
            c[0][1]["$set"]["error_payload"]
            for c in db.workflow_result.update_one.call_args_list
            if "error_payload" in (c[0][1].get("$set") or {})
        )
        assert payload["overflow_kind"] == "combined"
        assert payload["total_tokens"] == 92_119
        assert payload["suggested_action"] == "convert_to_kb"
        assert {d["uuid"] for d in payload["oversize_documents"]} == {"a", "b", "c", "d"}

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_same_package_runs_on_a_wider_model(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id, step_id, task_id = (_fake_oid() for _ in range(4))
        db = self._nasa_db(wf_id, result_id, step_id, task_id)
        db.system_config.find_one.return_value = {
            "available_models": [{"name": "qwen3", "context_window": 262_144}],
        }
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Report", [{"name": "Assess", "output": "Report"}])
        mock_engine.usage = MagicMock(tokens_in=90_000, tokens_out=5_000)
        mock_build.return_value = mock_engine

        with patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            result = execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["a", "b", "c", "d"]},
                model="qwen3",
            )

        assert result["status"] == "completed"
        mock_engine.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Pre-flight: a fixed document deleted from Files fails the run by name
# ---------------------------------------------------------------------------

class TestMissingFixedDocuments:
    def test_lists_deleted_and_soft_deleted_by_saved_title(self):
        from app.tasks.workflow_tasks import _missing_fixed_documents

        db = _mock_db(smart_docs=[
            {"uuid": "ok", "title": "Present.pdf", "raw_text": "x"},
            {"uuid": "soft", "title": "Retired.pdf", "raw_text": "x", "soft_deleted": True},
        ])
        wf = {"input_config": {"fixed_documents": [
            {"uuid": "ok", "title": "Present.pdf"},
            {"uuid": "gone", "title": "Award Terms.pdf"},
            {"uuid": "soft", "title": "Retired.pdf"},
            "bare-uuid-gone",
        ]}}
        assert _missing_fixed_documents(db, wf) == ["Award Terms.pdf", "Retired.pdf", "bare-uuid-gone"]

    def test_no_input_mode_ignores_fixed_documents(self):
        from app.tasks.workflow_tasks import _missing_fixed_documents

        wf = {"input_config": {"trigger_type": "no_input", "fixed_documents": [{"uuid": "gone", "title": "x"}]}}
        assert _missing_fixed_documents(_mock_db(), wf) == []

    def test_message_wording(self):
        from app.tasks.workflow_tasks import fixed_documents_missing_message

        one = fixed_documents_missing_message(["Award Terms.pdf"])
        assert one.startswith("1 fixed document configured on this workflow's Input tab no longer exists: Award Terms.pdf.")
        assert "It was deleted from Files. Remove it from the Input tab" in one
        two = fixed_documents_missing_message(["a", "b"])
        assert two.startswith("2 fixed documents") and "They were deleted" in two

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_run_fails_before_building_when_a_fixed_document_is_gone(self, mock_build, mock_get_db):
        """Before: the missing document was logged and skipped, the run covered
        only the selected document and reported Completed."""
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        wf = _make_workflow_doc(wf_id=wf_id)
        wf["input_config"] = {"fixed_documents": [{"uuid": "fixed-gone", "title": "Award Terms.pdf"}]}
        db = _mock_db(
            workflow_doc=wf,
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            smart_docs=[{"uuid": "sel", "raw_text": "selected doc text", "processing": False, "title": "Selected.pdf"}],
        )
        mock_get_db.return_value = db

        with patch("app.tasks.workflow_tasks.logger") as mock_logger:
            result = execute_workflow_task(
                workflow_result_id=str(result_id), workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["sel"]}, model="gpt-4o",
            )

        assert result is None
        mock_build.assert_not_called()
        set_op = db.workflow_result.update_one.call_args[0][1]["$set"]
        assert set_op["status"] == "error"
        assert "Award Terms.pdf" in set_op["error"]
        assert set_op["error_payload"] == {
            "code": "fixed_documents_missing", "missing_documents": ["Award Terms.pdf"],
        }
        mock_logger.error.assert_not_called()

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_run_proceeds_when_fixed_documents_exist(self, mock_build, mock_get_db):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id, result_id = _fake_oid(), _fake_oid()
        wf = _make_workflow_doc(wf_id=wf_id)
        wf["input_config"] = {"fixed_documents": [{"uuid": "fixed", "title": "Award Terms.pdf"}]}
        db = _mock_db(
            workflow_doc=wf,
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            smart_docs=[
                {"uuid": "sel", "raw_text": "selected", "processing": False, "title": "Selected.pdf"},
                {"uuid": "fixed", "raw_text": "fixed", "processing": False, "title": "Award Terms.pdf"},
            ],
        )
        mock_get_db.return_value = db
        mock_build.return_value.execute.return_value = ("out", [])
        execute_workflow_task(
            workflow_result_id=str(result_id), workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": ["sel"]}, model="gpt-4o",
        )
        mock_build.assert_called_once()


class TestBuildStepsDataFormFiller:
    """Form Filler tasks carry document metadata (for per-field sources) and
    their fillable-PDF template; other tasks are untouched."""

    def _db(self, task_name, task_data):
        step_id, task_id = _fake_oid(), _fake_oid()
        db = _mock_db(
            step_docs=[{"_id": step_id, "name": "Fill", "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": task_name, "data": task_data}],
        )
        db.smart_document.find_one.side_effect = lambda q, *a, **k: {
            "uuid": q.get("uuid"), "title": f"{q.get('uuid')}.pdf", "raw_text": f"text-{q.get('uuid')}",
            "text_markers": [{"char_offset": 0, "kind": "page", "value": 1}],
            "extension": "pdf", "path": f"u/{q.get('uuid')}.pdf",
        }
        return db, step_id

    def test_form_filler_gets_doc_metas_aligned_with_doc_texts(self):
        from app.tasks.workflow_tasks import _build_steps_data

        db, step_id = self._db("FormFiller", {"template": "{{a}}", "input_sources": ["workflow_documents", "select_document"], "selected_document_uuid": "S"})
        wf = _make_workflow_doc(step_ids=[step_id])
        steps_data, _ = _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": ["u1", "u2"]})

        data = steps_data[1]["tasks"][0]["data"]
        assert data["doc_texts"] == ["text-u1", "text-u2"]
        assert [m["uuid"] for m in data["doc_metas"]] == ["u1", "u2"]
        assert data["doc_metas"][0]["title"] == "u1.pdf"
        assert data["doc_metas"][0]["text_markers"] == [{"char_offset": 0, "kind": "page", "value": 1}]
        assert data["selected_doc_meta"]["uuid"] == "S"
        assert "template_pdf_b64" not in data  # text mode

    def test_other_tasks_do_not_get_metas(self):
        from app.tasks.workflow_tasks import _build_steps_data

        db, step_id = self._db("Prompt", {"prompt": "x"})
        wf = _make_workflow_doc(step_ids=[step_id])
        steps_data, _ = _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": ["u1"]})
        data = steps_data[1]["tasks"][0]["data"]
        assert data["doc_texts"] == ["text-u1"]
        assert "doc_metas" not in data

    @patch("app.tasks.workflow_tasks._preload_form_filler_template")
    def test_pdf_template_preload_is_called_for_form_filler(self, mock_preload):
        from app.tasks.workflow_tasks import _build_steps_data

        db, step_id = self._db("FormFiller", {"template_source": "pdf", "template_document_uuid": "T"})
        wf = _make_workflow_doc(step_ids=[step_id])
        _build_steps_data(db, wf, str(wf["_id"]), {"doc_uuids": []})
        mock_preload.assert_called_once()
        assert mock_preload.call_args.args[1]["template_document_uuid"] == "T"


class TestBuildRefusalFailsTheRun:
    """The builder now raises WorkflowStepError for definitions it cannot
    honor (unknown task type, Code Execution for a non-admin) instead of
    silently skipping the step. The build sits outside the main try, so the
    task must catch the refusal and mark the run failed — otherwise the row
    strands at "running" for the reaper (#805).
    """

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_execute_marks_run_failed_with_the_builders_message(
        self, mock_build, mock_get_db,
    ):
        from app.services.workflow_engine import WorkflowStepError
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "MysteryTask", "data": {}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_get_db.return_value = db
        mock_build.side_effect = WorkflowStepError(
            "Step1", "Step 'Step1' contains an unknown task type 'MysteryTask'.",
        )

        result = execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": ["uuid1"]},
            model="gpt-4o",
        )

        assert result["status"] == "error"
        error_writes = [
            c[0][1]["$set"] for c in db.workflow_result.update_one.call_args_list
            if c[0][1].get("$set", {}).get("status") == "error"
        ]
        assert error_writes, "run was not marked failed"
        assert "MysteryTask" in error_writes[0]["error"]


class TestLibrarySaveDeliveryFailure:
    """#810: the finalize block swallowed a failed library write with a log
    line — the run reported completed with its configured deliverable never
    written. It must record the failure on the run and bell the launcher."""

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_completed_run_records_and_bells_the_undelivered_output(
        self, mock_build, mock_get_db,
    ):
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()

        workflow_doc = _make_workflow_doc(wf_id=wf_id, step_ids=[step_id])
        workflow_doc["output_config"] = {
            "storage": {"enabled": True, "destination_folder": "f-1"},
        }
        db = _mock_db(
            workflow_doc=workflow_doc,
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "test"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Final output", [{"name": "Doc", "output": ["uuid1"]}])
        mock_engine.usage = MagicMock(tokens_in=10, tokens_out=5)
        mock_build.return_value = mock_engine

        db.activity_event.find_one.return_value = {"user_id": "launcher-1"}
        activity_id = str(_fake_oid())

        with patch(
            "app.services.output_handlers.save_results_to_folder",
            side_effect=RuntimeError("destination folder deleted"),
        ), patch(
            "app.services.failure_notifications.notify_delivery_failed"
        ) as notify, patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            result = execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
                activity_id=activity_id,
            )

        # The run still completes — results exist and are viewable...
        assert result["status"] == "completed"
        # ...but the failure is recorded on the run...
        pushes = [
            c for c in db.workflow_result.update_one.call_args_list
            if "$push" in c[0][1] and "delivery_failures" in c[0][1]["$push"]
        ]
        assert pushes, "delivery failure was not recorded on the run"
        assert "destination folder deleted" in pushes[0][0][1]["$push"]["delivery_failures"]
        # ...and the bell goes to the LAUNCHER resolved from the activity
        # rail, not just the workflow owner.
        notify.assert_called_once()
        assert "could not be saved" in notify.call_args.kwargs["detail"]
        assert notify.call_args.kwargs["user_id"] == "launcher-1"


class TestMidRunBudgetStop:
    """#808: a TrialSpendBlockedError raised by the between-steps gate must
    mark the run failed with the budget_exhausted payload — a clean stop, not
    a retried crash."""

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_budget_stop_marks_run_error_with_payload(self, mock_build, mock_get_db):
        from app.exceptions import TrialBudgetExceededError
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()

        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "test"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_get_db.return_value = db

        mock_engine = MagicMock()
        mock_engine.execute.side_effect = TrialBudgetExceededError(
            "Your trial's token budget is exhausted.",
        )
        mock_engine.usage = MagicMock(tokens_in=10, tokens_out=5)
        mock_build.return_value = mock_engine

        result = execute_workflow_task(
            workflow_result_id=str(result_id),
            workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": ["uuid1"]},
            model="gpt-4o",
        )

        # Clean stop, no re-raise (no Celery retry of a budget error).
        assert result["status"] == "error"
        error_writes = [
            c[0][1]["$set"] for c in db.workflow_result.update_one.call_args_list
            if c[0][1].get("$set", {}).get("status") == "error"
        ]
        assert error_writes
        assert error_writes[0].get("error_payload", {}).get("code") == "budget_exhausted"
        assert "budget" in error_writes[0]["error"]

    def test_engine_receives_the_budget_hook(self):
        """The wiring itself: execute() must be handed check_budget."""
        from unittest.mock import MagicMock, patch

        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "test"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("out", [{"name": "Doc", "output": ["uuid1"]}])
        mock_engine.usage = MagicMock(tokens_in=1, tokens_out=1)

        with patch("app.tasks.workflow_tasks._get_db", return_value=db), \
             patch("app.services.workflow_engine.build_workflow_engine", return_value=mock_engine), \
             patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             patch("app.tasks.activity_tasks.generate_activity_description_task"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )
        assert mock_engine.execute.call_args.kwargs.get("check_budget") is not None


class TestBudgetHookPassesInFlightSpend:
    """The hook the task hands the engine must report the live scope's
    not-yet-flushed tokens; without that the ledger read is stale and the
    gate never trips (the #808 bug, one layer down)."""

    @patch("app.tasks.workflow_tasks._get_db")
    @patch("app.services.workflow_engine.build_workflow_engine")
    def test_hook_reports_live_scope_tokens(self, mock_build, mock_get_db):
        from unittest.mock import MagicMock, patch as _patch

        from app.tasks.workflow_tasks import execute_workflow_task

        wf_id = _fake_oid()
        result_id = _fake_oid()
        step_id = _fake_oid()
        task_id = _fake_oid()
        db = _mock_db(
            workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
            result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
            step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
            task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "t"}}],
            smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
        )
        mock_get_db.return_value = db

        captured = {}

        def fake_execute(**kwargs):
            # Simulate mid-run spend, then invoke the hook the way the engine
            # does at a step boundary.
            from app.services.metering import current_scope

            scope = current_scope()
            scope.tokens_in += 700
            scope.tokens_out += 200
            kwargs["check_budget"]()
            return ("out", [{"name": "Doc", "output": ["uuid1"]}])

        mock_engine = MagicMock()
        mock_engine.execute.side_effect = fake_execute
        mock_engine.usage = MagicMock(tokens_in=700, tokens_out=200)
        mock_build.return_value = mock_engine

        def fake_check_sync(user_id, *, extra_used=0):
            captured["user_id"] = user_id
            captured["extra_used"] = extra_used

        with _patch("app.services.trial_budget.check_sync", side_effect=fake_check_sync), \
             _patch("app.tasks.quality_tasks.auto_validate_workflow"), \
             _patch("app.tasks.activity_tasks.generate_activity_description_task"):
            execute_workflow_task(
                workflow_result_id=str(result_id),
                workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": ["uuid1"]},
                model="gpt-4o",
            )

        assert captured["extra_used"] == 900, "hook did not report in-flight spend"

    def test_unverified_account_gets_its_own_code(self):
        """budget_exhausted was hardcoded for the whole TrialSpendBlockedError
        family, offering a top-up for a problem a confirmation link solves."""
        from app.exceptions import TrialBudgetExceededError, TrialUnverifiedError
        from app.tasks.workflow_tasks import _spend_block_code

        assert _spend_block_code(TrialUnverifiedError("confirm")) == "email_unverified"
        assert _spend_block_code(TrialBudgetExceededError("spent")) == "budget_exhausted"
