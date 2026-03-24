"""Tests for the workflow service layer — async CRUD, execution dispatching,
batch operations, validation plan, and expected outputs.

Uses mocked Beanie models and Celery to avoid DB/broker dependencies.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from beanie import PydanticObjectId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_oid():
    return PydanticObjectId()


def _make_workflow(name="Test WF", user_id="user1", team_id=None, space=None, steps=None):
    wf = MagicMock()
    wf.id = _fake_oid()
    wf.name = name
    wf.user_id = user_id
    wf.team_id = team_id
    wf.space = space
    wf.steps = steps or []
    wf.attachments = []
    wf.description = "test desc"
    wf.num_executions = 0
    wf.input_config = {}
    wf.validation_plan = []
    wf.validation_inputs = []
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    wf.save = AsyncMock()
    wf.insert = AsyncMock()
    wf.delete = AsyncMock()
    return wf


def _make_step(name="Step1", tasks=None, data=None, is_output=False):
    step = MagicMock()
    step.id = _fake_oid()
    step.name = name
    step.tasks = tasks or []
    step.data = data or {}
    step.is_output = is_output
    step.save = AsyncMock()
    step.insert = AsyncMock()
    step.delete = AsyncMock()
    return step


def _make_task(name="Prompt", data=None):
    task = MagicMock()
    task.id = _fake_oid()
    task.name = name
    task.data = data or {}
    task.save = AsyncMock()
    task.insert = AsyncMock()
    task.delete = AsyncMock()
    return task


def _make_user(user_id="user1", current_team=None):
    user = MagicMock()
    user.user_id = user_id
    user.current_team = current_team
    return user


def _make_result(session_id="abc123", status="completed", final_output=None, workflow_id=None):
    result = MagicMock()
    result.id = _fake_oid()
    result.session_id = session_id
    result.status = status
    result.workflow = workflow_id or _fake_oid()
    result.num_steps_completed = 3
    result.num_steps_total = 3
    result.current_step_name = None
    result.current_step_detail = None
    result.current_step_preview = None
    result.final_output = final_output or {"output": "done"}
    result.steps_output = {}
    result.batch_id = None
    result.document_title = None
    result.insert = AsyncMock()
    return result


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

class TestCreateWorkflow:
    @patch("app.services.workflow_service.Workflow")
    async def test_creates_workflow(self, mock_wf_cls):
        from app.services.workflow_service import create_workflow

        mock_wf = MagicMock()
        mock_wf.insert = AsyncMock()
        mock_wf_cls.return_value = mock_wf

        result = await create_workflow(
            name="My Workflow",
            user_id="user1",
            description="A test workflow",
            team_id="team1",
        )
        assert result is mock_wf
        mock_wf.insert.assert_awaited_once()


class TestGetWorkflowStatus:
    @patch("app.services.workflow_service.WorkflowResult")
    async def test_returns_status_dict(self, mock_wr_cls):
        from app.services.workflow_service import get_workflow_status

        wr = _make_result(session_id="sess1", status="completed")
        mock_wr_cls.find_one = AsyncMock(return_value=wr)

        result = await get_workflow_status("sess1")
        assert result["status"] == "completed"
        assert result["num_steps_completed"] == 3
        assert result["final_output"] == {"output": "done"}

    @patch("app.services.workflow_service.WorkflowResult")
    async def test_returns_none_for_missing(self, mock_wr_cls):
        from app.services.workflow_service import get_workflow_status

        mock_wr_cls.find_one = AsyncMock(return_value=None)
        result = await get_workflow_status("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Batch status
# ---------------------------------------------------------------------------

class TestGetBatchStatus:
    @patch("app.services.workflow_service.Workflow")
    @patch("app.services.workflow_service.WorkflowResult")
    async def test_aggregates_batch(self, mock_wr_cls, mock_wf_cls):
        from app.services.workflow_service import get_batch_status

        wf_id = _fake_oid()
        results = [
            _make_result("s1", "completed", workflow_id=wf_id),
            _make_result("s2", "completed", workflow_id=wf_id),
            _make_result("s3", "error", workflow_id=wf_id),
        ]
        results[2].document_title = "doc3.pdf"

        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=results)
        mock_wr_cls.find.return_value = mock_find

        result = await get_batch_status("batch1")
        assert result is not None
        assert result["total"] == 3
        assert result["completed"] == 2
        assert result["failed"] == 1
        assert result["status"] == "completed"  # completed+failed == total
        assert len(result["items"]) == 3

    @patch("app.services.workflow_service.WorkflowResult")
    async def test_empty_batch(self, mock_wr_cls):
        from app.services.workflow_service import get_batch_status

        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[])
        mock_wr_cls.find.return_value = mock_find

        result = await get_batch_status("nonexistent")
        assert result is None

    @patch("app.services.workflow_service.Workflow")
    @patch("app.services.workflow_service.WorkflowResult")
    async def test_all_running(self, mock_wr_cls, mock_wf_cls):
        from app.services.workflow_service import get_batch_status

        wf_id = _fake_oid()
        results = [
            _make_result("s1", "running", workflow_id=wf_id),
            _make_result("s2", "queued", workflow_id=wf_id),
        ]
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=results)
        mock_wr_cls.find.return_value = mock_find

        result = await get_batch_status("batch2")
        assert result["status"] == "running"

    @patch("app.services.workflow_service.Workflow")
    @patch("app.services.workflow_service.WorkflowResult")
    async def test_all_failed(self, mock_wr_cls, mock_wf_cls):
        from app.services.workflow_service import get_batch_status

        wf_id = _fake_oid()
        results = [
            _make_result("s1", "error", workflow_id=wf_id),
            _make_result("s2", "failed", workflow_id=wf_id),
        ]
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=results)
        mock_wr_cls.find.return_value = mock_find

        result = await get_batch_status("batch3")
        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Step reordering
# ---------------------------------------------------------------------------

class TestReorderSteps:
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_valid_reorder(self, mock_auth):
        from app.services.workflow_service import reorder_steps

        s1, s2, s3 = _fake_oid(), _fake_oid(), _fake_oid()
        wf = _make_workflow(steps=[s1, s2, s3])
        mock_auth.return_value = wf

        user = _make_user()
        result = await reorder_steps(str(wf.id), [str(s3), str(s1), str(s2)], user)
        assert result is True
        assert wf.steps == [s3, s1, s2]
        wf.save.assert_awaited_once()

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_invalid_step_ids(self, mock_auth):
        from app.services.workflow_service import reorder_steps

        s1, s2 = _fake_oid(), _fake_oid()
        wf = _make_workflow(steps=[s1, s2])
        mock_auth.return_value = wf

        user = _make_user()
        result = await reorder_steps(str(wf.id), [str(s1), str(_fake_oid())], user)
        assert result is False

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_unauthorized(self, mock_auth):
        from app.services.workflow_service import reorder_steps

        mock_auth.return_value = None
        user = _make_user()
        result = await reorder_steps("wf-id", ["s1"], user)
        assert result is False


# ---------------------------------------------------------------------------
# Validation plan
# ---------------------------------------------------------------------------

class TestValidationPlan:
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_get_plan(self, mock_auth):
        from app.services.workflow_service import get_validation_plan

        wf = _make_workflow()
        wf.validation_plan = [{"id": "c1", "name": "Check 1", "category": "completeness"}]
        mock_auth.return_value = wf

        result = await get_validation_plan(str(wf.id), _make_user())
        assert len(result) == 1
        assert result[0]["name"] == "Check 1"

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_update_plan(self, mock_auth):
        from app.services.workflow_service import update_validation_plan

        wf = _make_workflow()
        mock_auth.return_value = wf

        new_checks = [{"id": "c1", "name": "New Check", "category": "accuracy"}]
        result = await update_validation_plan(str(wf.id), new_checks, _make_user())
        assert wf.validation_plan == new_checks
        wf.save.assert_awaited_once()

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_get_plan_unauthorized(self, mock_auth):
        from app.services.workflow_service import get_validation_plan

        mock_auth.return_value = None
        with pytest.raises(ValueError):
            await get_validation_plan("wf-id", _make_user())


# ---------------------------------------------------------------------------
# Validation inputs
# ---------------------------------------------------------------------------

class TestValidationInputs:
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_get_inputs(self, mock_auth):
        from app.services.workflow_service import get_validation_inputs

        wf = _make_workflow()
        wf.validation_inputs = [{"id": "i1", "type": "document", "document_uuid": "d1"}]
        mock_auth.return_value = wf

        result = await get_validation_inputs(str(wf.id), _make_user())
        assert len(result) == 1

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_update_inputs(self, mock_auth):
        from app.services.workflow_service import update_validation_inputs

        wf = _make_workflow()
        mock_auth.return_value = wf

        new_inputs = [{"id": "i1", "type": "text", "text": "sample"}]
        result = await update_validation_inputs(str(wf.id), new_inputs, _make_user())
        assert wf.validation_inputs == new_inputs
        wf.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# Expected outputs
# ---------------------------------------------------------------------------

class TestExpectedOutputs:
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_get_expected_outputs(self, mock_auth):
        from app.services.workflow_service import get_expected_outputs

        wf = _make_workflow()
        wf.validation_inputs = [
            {"id": "i1", "type": "text", "text": "sample"},
            {"id": "e1", "type": "expected_output", "session_id": "s1", "output_text": "expected"},
        ]
        mock_auth.return_value = wf

        result = await get_expected_outputs(str(wf.id), _make_user())
        assert len(result) == 1
        assert result[0]["type"] == "expected_output"

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_delete_expected_output(self, mock_auth):
        from app.services.workflow_service import delete_expected_output

        wf = _make_workflow()
        wf.validation_inputs = [
            {"id": "e1", "type": "expected_output"},
            {"id": "e2", "type": "expected_output"},
        ]
        mock_auth.return_value = wf

        result = await delete_expected_output(str(wf.id), "e1", _make_user())
        assert result is True
        assert len(wf.validation_inputs) == 1
        assert wf.validation_inputs[0]["id"] == "e2"

    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_delete_nonexistent_expected_output(self, mock_auth):
        from app.services.workflow_service import delete_expected_output

        wf = _make_workflow()
        wf.validation_inputs = [{"id": "e1", "type": "expected_output"}]
        mock_auth.return_value = wf

        result = await delete_expected_output(str(wf.id), "nonexistent", _make_user())
        assert result is False


# ---------------------------------------------------------------------------
# _merge_multi_run_checks
# ---------------------------------------------------------------------------

class TestMergeMultiRunChecks:
    def test_single_run(self):
        from app.services.workflow_service import _merge_multi_run_checks

        plan = [{"id": "c1", "name": "Check 1"}]
        checks = [[{"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok"}]]
        result = _merge_multi_run_checks(plan, checks)
        assert len(result) == 1
        assert result[0]["status"] == "PASS"
        assert result[0]["consistency"] == 1.0

    def test_consistent_multi_run(self):
        from app.services.workflow_service import _merge_multi_run_checks

        plan = [{"id": "c1", "name": "Check 1"}]
        checks = [
            [{"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok"}],
            [{"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "good"}],
            [{"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "fine"}],
        ]
        result = _merge_multi_run_checks(plan, checks)
        assert result[0]["consistency"] == 1.0
        assert result[0]["status"] == "PASS"
        assert len(result[0]["run_statuses"]) == 3

    def test_inconsistent_multi_run(self):
        from app.services.workflow_service import _merge_multi_run_checks

        plan = [{"id": "c1", "name": "Check 1"}]
        checks = [
            [{"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok"}],
            [{"check_id": "c1", "name": "Check 1", "status": "FAIL", "detail": "bad"}],
            [{"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok"}],
        ]
        result = _merge_multi_run_checks(plan, checks)
        assert result[0]["status"] == "PASS"  # majority
        assert result[0]["consistency"] == pytest.approx(2 / 3)
        assert "Inconsistent" in result[0]["detail"]

    def test_empty_runs(self):
        from app.services.workflow_service import _merge_multi_run_checks
        result = _merge_multi_run_checks([], [])
        assert result == []


# ---------------------------------------------------------------------------
# _compare_outputs
# ---------------------------------------------------------------------------

class TestCompareOutputs:
    def test_dict_comparison(self):
        from app.services.workflow_service import _compare_outputs

        results = [_make_result(final_output={"Name": "Alice", "Age": "30"})]
        expected = [{"output_snapshot": {"Name": "Alice", "Age": "30"}, "label": "test"}]

        with patch("app.services.extraction_validation_service._values_match", return_value=True), \
             patch("app.services.extraction_validation_service._is_not_found", return_value=False):
            comparison = _compare_outputs(results, expected)

        assert comparison["has_expected"] is True
        assert comparison["output_accuracy"] > 0

    def test_text_comparison_exact_match(self):
        from app.services.workflow_service import _compare_outputs

        results = [_make_result(final_output="hello world")]
        expected = [{"output_snapshot": "Hello World", "label": "test"}]
        comparison = _compare_outputs(results, expected)
        assert comparison["has_expected"] is True
        assert comparison["output_accuracy"] == 1.0

    def test_text_comparison_mismatch(self):
        from app.services.workflow_service import _compare_outputs

        results = [_make_result(final_output="hello")]
        expected = [{"output_snapshot": "goodbye", "label": "test"}]
        comparison = _compare_outputs(results, expected)
        assert comparison["output_accuracy"] == 0.0

    def test_no_expected(self):
        from app.services.workflow_service import _compare_outputs

        results = [_make_result()]
        comparison = _compare_outputs(results, [])
        assert comparison["has_expected"] is False

    def test_list_comparison(self):
        from app.services.workflow_service import _compare_outputs

        results = [_make_result(final_output=["a", "b", "c"])]
        expected = [{"output_snapshot": ["a", "b", "d"], "label": "test"}]
        comparison = _compare_outputs(results, expected)
        assert comparison["has_expected"] is True
        assert 0 < comparison["output_accuracy"] < 1  # 2/3 match


# ---------------------------------------------------------------------------
# _build_result (score computation)
# ---------------------------------------------------------------------------

class TestBuildResult:
    @patch("app.services.quality_service.persist_validation_run", new_callable=AsyncMock)
    async def test_all_pass(self, mock_persist):
        from app.services.workflow_service import _build_result

        checks = [
            {"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok", "consistency": 1.0},
            {"check_id": "c2", "name": "Check 2", "status": "PASS", "detail": "ok", "consistency": 1.0},
        ]
        result = await _build_result(checks, "wf-id", {"name": "Test", "user_id": "u1"})
        assert result["grade"] == "A"
        assert result["score"] == 100.0
        assert result["check_pass_rate"] == 1.0

    @patch("app.services.quality_service.persist_validation_run", new_callable=AsyncMock)
    async def test_all_fail(self, mock_persist):
        from app.services.workflow_service import _build_result

        checks = [
            {"check_id": "c1", "name": "Check 1", "status": "FAIL", "detail": "bad", "consistency": 1.0},
        ]
        result = await _build_result(checks, "wf-id", {"name": "Test", "user_id": "u1"})
        assert result["grade"] in ("D", "F")
        assert result["check_pass_rate"] == 0.0

    @patch("app.services.quality_service.persist_validation_run", new_callable=AsyncMock)
    async def test_mixed_results(self, mock_persist):
        from app.services.workflow_service import _build_result

        checks = [
            {"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok", "consistency": 1.0},
            {"check_id": "c2", "name": "Check 2", "status": "WARN", "detail": "eh", "consistency": 1.0},
            {"check_id": "c3", "name": "Check 3", "status": "FAIL", "detail": "bad", "consistency": 1.0},
        ]
        result = await _build_result(checks, "wf-id", {"name": "Test", "user_id": "u1"})
        assert 0 < result["score"] < 100
        assert result["check_pass_rate"] == pytest.approx(0.5)  # (1.0 + 0.5 + 0.0) / 3

    @patch("app.services.quality_service.persist_validation_run", new_callable=AsyncMock)
    async def test_with_output_accuracy(self, mock_persist):
        from app.services.workflow_service import _build_result

        checks = [
            {"check_id": "c1", "name": "Check 1", "status": "PASS", "detail": "ok", "consistency": 1.0},
        ]
        output_comparison = {"has_expected": True, "output_accuracy": 0.8}
        result = await _build_result(
            checks, "wf-id", {"name": "Test", "user_id": "u1"},
            output_comparison=output_comparison,
        )
        # Score should be blended: 40% check + 30% consistency + 30% output accuracy
        assert result["score"] > 0

    @patch("app.services.quality_service.persist_validation_run", new_callable=AsyncMock)
    async def test_all_skip(self, mock_persist):
        from app.services.workflow_service import _build_result

        checks = [
            {"check_id": "c1", "name": "Check 1", "status": "SKIP", "detail": "skipped"},
        ]
        result = await _build_result(checks, "wf-id", {"name": "Test", "user_id": "u1"})
        assert result["grade"] == "F"
        assert result["check_pass_rate"] == 0.0


# ---------------------------------------------------------------------------
# _parse_json_array
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# run_workflow
# ---------------------------------------------------------------------------

class TestRunWorkflow:
    @patch("app.services.workflow_service.celery_app")
    @patch("app.services.workflow_service.WorkflowResult")
    @patch("app.services.workflow_service.get_user_model_name", new_callable=AsyncMock, return_value="gpt-4o")
    @patch("app.services.workflow_service.Workflow")
    async def test_run_workflow_creates_result_and_sends_task(self, mock_wf_cls, mock_model, mock_wr_cls, mock_celery):
        from app.services.workflow_service import run_workflow

        wf = _make_workflow(steps=[_fake_oid(), _fake_oid()])
        mock_wf_cls.get = AsyncMock(return_value=wf)

        mock_result = MagicMock()
        mock_result.id = _fake_oid()
        mock_result.insert = AsyncMock()
        mock_wr_cls.return_value = mock_result

        session_id = await run_workflow(
            str(wf.id), ["doc-uuid-1"], "user1",
        )

        assert isinstance(session_id, str)
        assert len(session_id) == 8
        mock_result.insert.assert_awaited_once()
        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args[1]
        assert call_kwargs["queue"] == "workflows"
        assert call_kwargs["kwargs"]["model"] == "gpt-4o"

    @patch("app.services.workflow_service.Workflow")
    async def test_run_workflow_not_found(self, mock_wf_cls):
        from app.services.workflow_service import run_workflow

        mock_wf_cls.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await run_workflow(str(_fake_oid()), ["doc1"], "user1")


# ---------------------------------------------------------------------------
# run_workflow_batch
# ---------------------------------------------------------------------------

class TestRunWorkflowBatch:
    @patch("app.services.workflow_service.celery_app")
    @patch("app.services.workflow_service.WorkflowResult")
    @patch("app.services.workflow_service.get_user_model_name", new_callable=AsyncMock, return_value="gpt-4o")
    @patch("app.services.workflow_service.Workflow")
    async def test_batch_creates_one_result_per_doc(self, mock_wf_cls, mock_model, mock_wr_cls, mock_celery):
        from app.services.workflow_service import run_workflow_batch

        wf = _make_workflow(steps=[_fake_oid()])
        mock_wf_cls.get = AsyncMock(return_value=wf)

        mock_result = MagicMock()
        mock_result.id = _fake_oid()
        mock_result.insert = AsyncMock()
        mock_wr_cls.return_value = mock_result

        # SmartDocument is imported inside the function body
        mock_doc = MagicMock()
        mock_doc.title = "Test Doc"
        with patch("app.services.workflow_service.SmartDocument") as mock_doc_cls:
            mock_doc_cls.find_one = AsyncMock(return_value=mock_doc)
            batch_id = await run_workflow_batch(
                str(wf.id), ["doc1", "doc2", "doc3"], "user1",
            )

        assert isinstance(batch_id, str)
        assert len(batch_id) == 8
        # One Celery task per document
        assert mock_celery.send_task.call_count == 3
        # One WorkflowResult inserted per document
        assert mock_result.insert.await_count == 3


# ---------------------------------------------------------------------------
# test_step
# ---------------------------------------------------------------------------

class TestTestStep:
    @patch("app.services.workflow_service.celery_app")
    @patch("app.services.workflow_service.get_user_model_name", new_callable=AsyncMock, return_value="gpt-4o")
    async def test_returns_celery_task_id(self, mock_model, mock_celery):
        from app.services.workflow_service import test_step

        mock_celery_result = MagicMock()
        mock_celery_result.id = "celery-task-123"
        mock_celery.send_task.return_value = mock_celery_result

        task_id = await test_step(
            task_name="Prompt",
            task_data={"prompt": "Summarize"},
            document_uuids=["doc1"],
            user_id="user1",
        )

        assert task_id == "celery-task-123"
        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args[1]
        assert call_kwargs["kwargs"]["task_name"] == "Prompt"

    @patch("app.services.workflow_service.SearchSetItem")
    @patch("app.services.workflow_service.celery_app")
    @patch("app.services.workflow_service.get_user_model_name", new_callable=AsyncMock, return_value="gpt-4o")
    async def test_extraction_resolves_search_set(self, mock_model, mock_celery, mock_ssi_cls):
        from app.services.workflow_service import test_step

        mock_item1 = MagicMock()
        mock_item1.searchphrase = "Name"
        mock_item2 = MagicMock()
        mock_item2.searchphrase = "Date"

        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[mock_item1, mock_item2])
        mock_ssi_cls.find.return_value = mock_find

        mock_celery_result = MagicMock()
        mock_celery_result.id = "task-id"
        mock_celery.send_task.return_value = mock_celery_result

        task_id = await test_step(
            task_name="Extraction",
            task_data={"search_set_uuid": "ss-123"},
            document_uuids=["doc1"],
            user_id="user1",
        )

        assert task_id == "task-id"
        call_kwargs = mock_celery.send_task.call_args[1]["kwargs"]
        assert set(call_kwargs["task_data"]["keys"]) == {"Name", "Date"}


# ---------------------------------------------------------------------------
# get_test_status
# ---------------------------------------------------------------------------

class TestGetTestStatus:
    @patch("app.services.workflow_service.AsyncResult")
    def test_completed(self, mock_async_result_cls):
        from app.services.workflow_service import get_test_status

        mock_result = MagicMock()
        mock_result.ready.return_value = True
        mock_result.result = {"output": "test result"}
        mock_async_result_cls.return_value = mock_result

        status = get_test_status("task-123")
        assert status["status"] == "completed"
        assert status["result"]["output"] == "test result"

    @patch("app.services.workflow_service.AsyncResult")
    def test_pending(self, mock_async_result_cls):
        from app.services.workflow_service import get_test_status

        mock_result = MagicMock()
        mock_result.ready.return_value = False
        mock_result.state = "PENDING"
        mock_async_result_cls.return_value = mock_result

        status = get_test_status("task-123")
        assert status["status"] == "PENDING"


# ---------------------------------------------------------------------------
# save_expected_output
# ---------------------------------------------------------------------------

class TestSaveExpectedOutput:
    @patch("app.services.workflow_service.WorkflowResult")
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_saves_expected_output(self, mock_auth, mock_wr_cls):
        from app.services.workflow_service import save_expected_output

        wf = _make_workflow()
        wf.validation_inputs = []
        mock_auth.return_value = wf

        mock_wr = MagicMock()
        mock_wr.final_output = {"output": "expected result"}
        mock_wr.steps_output = {"step1": {"output": "step data"}}
        mock_wr_cls.find_one = AsyncMock(return_value=mock_wr)

        result = await save_expected_output(str(wf.id), "sess1", _make_user(), label="test")

        assert result["type"] == "expected_output"
        assert result["session_id"] == "sess1"
        assert result["label"] == "test"
        assert len(wf.validation_inputs) == 1
        wf.save.assert_awaited_once()

    @patch("app.services.workflow_service.WorkflowResult")
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_replaces_existing_for_same_session(self, mock_auth, mock_wr_cls):
        from app.services.workflow_service import save_expected_output

        wf = _make_workflow()
        wf.validation_inputs = [
            {"id": "old", "type": "expected_output", "session_id": "sess1"},
            {"id": "keep", "type": "text", "text": "sample"},
        ]
        mock_auth.return_value = wf

        mock_wr = MagicMock()
        mock_wr.final_output = "new output"
        mock_wr.steps_output = {}
        mock_wr_cls.find_one = AsyncMock(return_value=mock_wr)

        await save_expected_output(str(wf.id), "sess1", _make_user())

        # Old expected_output for sess1 replaced, text input kept
        assert len(wf.validation_inputs) == 2
        types = [i["type"] for i in wf.validation_inputs]
        assert "text" in types
        assert "expected_output" in types

    @patch("app.services.workflow_service.WorkflowResult")
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_not_found_raises(self, mock_auth, mock_wr_cls):
        from app.services.workflow_service import save_expected_output

        wf = _make_workflow()
        mock_auth.return_value = wf
        mock_wr_cls.find_one = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await save_expected_output(str(wf.id), "nonexistent", _make_user())


# ---------------------------------------------------------------------------
# _parse_json_array
# ---------------------------------------------------------------------------

class TestParseJsonArray:
    def test_plain_array(self):
        from app.services.workflow_service import _parse_json_array
        result = _parse_json_array('[{"name": "check1"}]')
        assert result == [{"name": "check1"}]

    def test_code_block(self):
        from app.services.workflow_service import _parse_json_array
        result = _parse_json_array('```json\n[{"name": "check1"}]\n```')
        assert result == [{"name": "check1"}]

    def test_embedded_in_text(self):
        from app.services.workflow_service import _parse_json_array
        result = _parse_json_array('Here are the checks:\n[{"name": "check1"}]\nDone.')
        assert result == [{"name": "check1"}]

    def test_invalid_json(self):
        from app.services.workflow_service import _parse_json_array
        result = _parse_json_array("not json")
        assert result is None

    def test_object_not_array(self):
        from app.services.workflow_service import _parse_json_array
        result = _parse_json_array('{"name": "not an array"}')
        assert result is None

    def test_empty_array(self):
        from app.services.workflow_service import _parse_json_array
        result = _parse_json_array("[]")
        assert result == []
