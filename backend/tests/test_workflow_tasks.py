"""Tests for Celery workflow tasks — execute_workflow_task,
execute_task_step_test, and resume_workflow_after_approval.

Mocks pymongo (_get_db) and build_workflow_engine to test orchestration
logic without MongoDB or real LLM calls.

Note: Celery tasks with bind=True receive `self` automatically. We call
the underlying function directly via .__wrapped__ or the task object.
"""

from unittest.mock import MagicMock, patch
from bson import ObjectId

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    db.system_config.find_one.return_value = sys_config or {}
    db.approval_request.find_one.return_value = approval_doc

    _steps = {s["_id"]: s for s in (step_docs or [])}
    _tasks = {t["_id"]: t for t in (task_docs or [])}
    _docs = {d["uuid"]: d for d in (smart_docs or [])}

    db.workflow_step.find_one.side_effect = lambda q: _steps.get(q.get("_id"))
    db.workflow_step_task.find_one.side_effect = lambda q: _tasks.get(q.get("_id"))
    db.smart_document.find_one.side_effect = lambda q: _docs.get(q.get("uuid"))
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
        assert activity_completed[0][0][1]["$set"]["tokens_input"] == 200

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
