"""A transient failure retries the workflow instead of failing it.

Both workflow tasks skip a run that is already terminal when a delivery
starts, and both used to mark the run "error" *before* re-raising for
Celery's retry — so every retry found a failed run and did nothing. And an
LLM connection error never qualified anyway: the extraction engine wraps
pydantic-ai's ``ModelAPIError`` in ``ExtractionError``, which is not a
transient type. A two-second MindRouter blip failed the run outright
(Sentry 7610990045: "Extraction failed: Connection error.").
"""

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from app.services.extraction_engine import ExtractionError
from app.tasks import is_transient_llm_error, llm_retry_countdown
from tests.test_workflow_tasks import (
    _fake_oid,
    _make_result_doc,
    _make_workflow_doc,
    _mock_db,
)


def _wrapped(cause: BaseException) -> ExtractionError:
    """What the engine raises: ``raise ExtractionError(...) from e``."""
    try:
        raise cause
    except BaseException as e:
        try:
            raise ExtractionError(f"Extraction failed: {e}") from e
        except ExtractionError as wrapped:
            return wrapped


class TestIsTransientLlmError:
    def test_a_wrapped_connection_error_is_transient(self):
        exc = _wrapped(ModelAPIError(model_name="m", message="Connection error."))
        assert is_transient_llm_error(exc)

    @pytest.mark.parametrize("status", [429, 502, 503, 504])
    def test_rate_limits_and_gateway_errors_are_transient(self, status):
        assert is_transient_llm_error(
            _wrapped(ModelHTTPError(status_code=status, model_name="m")),
        )

    @pytest.mark.parametrize("status", [400, 401, 404])
    def test_a_client_error_is_not(self, status):
        """A bad request or a renamed model fails the same way every time."""
        assert not is_transient_llm_error(
            _wrapped(ModelHTTPError(status_code=status, model_name="m")),
        )

    def test_an_unrelated_error_is_not(self):
        assert not is_transient_llm_error(ExtractionError("Model returned unparseable output"))
        assert not is_transient_llm_error(ValueError("bad config"))


def test_llm_retries_wait_longer_than_the_provider_client_did():
    assert [llm_retry_countdown(n) for n in range(3)] == [30, 60, 120]


def _run_execute(db, engine_error, retries=0):
    from app.tasks.workflow_tasks import execute_workflow_task

    engine = MagicMock()
    engine.execute.side_effect = engine_error
    wf_id, result_id = db.ids
    with patch("app.tasks.workflow_tasks._get_db", return_value=db), \
         patch("app.services.workflow_engine.build_workflow_engine", return_value=engine), \
         patch.object(execute_workflow_task, "retry", side_effect=Retry()) as retry, \
         patch.object(execute_workflow_task.request, "retries", retries, create=True):
        try:
            execute_workflow_task(
                workflow_result_id=str(result_id), workflow_id=str(wf_id),
                trigger_step_data={"doc_uuids": []}, model="gpt-4o",
            )
        except Retry:
            return retry, "retried"
        except type(engine_error):
            return retry, "raised"
    return retry, "returned"


def _db():
    wf_id, result_id = _fake_oid(), _fake_oid()
    db = _mock_db(
        workflow_doc=_make_workflow_doc(wf_id=wf_id),
        result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
    )
    db.ids = (wf_id, result_id)
    return db


def _error_writes(db):
    return [
        c for c in db.workflow_result.update_one.call_args_list
        if c[0][1].get("$set", {}).get("status") == "error"
    ]


class TestExecuteWorkflowRetriesTransientFailures:
    def test_an_llm_connection_error_retries_without_failing_the_run(self):
        db = _db()
        retry, outcome = _run_execute(
            db, _wrapped(ModelAPIError(model_name="m", message="Connection error.")),
        )
        assert outcome == "retried"
        assert retry.call_args.kwargs["countdown"] == 30
        # The retry's terminal-status guard would skip a run marked failed.
        assert _error_writes(db) == []

    def test_a_network_error_retries_without_failing_the_run(self):
        db = _db()
        retry, outcome = _run_execute(db, ConnectionError("reset by peer"))
        assert outcome == "retried"
        assert _error_writes(db) == []

    def test_the_last_attempt_fails_the_run(self):
        db = _db()
        retry, outcome = _run_execute(
            db, _wrapped(ModelAPIError(model_name="m", message="Connection error.")),
            retries=3,
        )
        assert outcome == "raised"
        retry.assert_not_called()
        assert len(_error_writes(db)) == 1

    def test_a_permanent_error_fails_the_run_at_once(self):
        db = _db()
        retry, outcome = _run_execute(
            db, _wrapped(ModelHTTPError(status_code=404, model_name="gone")),
        )
        assert outcome == "raised"
        retry.assert_not_called()
        assert len(_error_writes(db)) == 1


class TestApprovalResumeRetriesTransientFailures:
    """The approved-run resume has the same shape: its retry refuses a run
    that is not pending_approval/running, so marking it "error" first turned
    a blip into "the reviewer approved it and it failed"."""

    def _run(self, engine_error):
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
        engine = MagicMock()
        engine.execute.side_effect = engine_error
        with patch("app.tasks.workflow_tasks._get_db", return_value=db), \
             patch("app.services.workflow_engine.build_workflow_engine", return_value=engine), \
             patch.object(resume_workflow_after_approval, "retry", side_effect=Retry()) as retry:
            with pytest.raises((Retry, type(engine_error))) as raised:
                resume_workflow_after_approval("a1")
        return db, retry, raised.type

    def test_an_llm_connection_error_retries_without_failing_the_run(self):
        db, retry, raised = self._run(
            _wrapped(ModelAPIError(model_name="m", message="Connection error.")),
        )
        assert raised is Retry
        assert retry.call_args.kwargs["countdown"] == 30
        assert _error_writes(db) == []

    def test_a_permanent_error_fails_the_run(self):
        db, retry, raised = self._run(ValueError("bad step config"))
        assert raised is ValueError
        retry.assert_not_called()
        assert len(_error_writes(db)) == 1


# ---------------------------------------------------------------------------
# Review of #979: a retry resumes at the failed step and re-runs ALL of it.
# A multi-task step runs its tasks concurrently, so an API POST could finish
# before a sibling Extraction hit a connection error — and the retry would
# send it again. Steps that act outside the run are not retried.
# ---------------------------------------------------------------------------


class _Failing:
    def __init__(self, side_effects):
        self._side_effects = side_effects
        self.name = "step"

    def has_side_effects(self):
        return self._side_effects

    def process(self, _inputs):
        raise _wrapped(ModelAPIError(model_name="m", message="Connection error."))


def test_a_failure_in_a_step_with_side_effects_is_tagged():
    from app.services.workflow_engine import STEP_SIDE_EFFECTS_ATTR, _process_tagged

    with pytest.raises(ExtractionError) as raised:
        _process_tagged(_Failing(True), {})
    assert getattr(raised.value, STEP_SIDE_EFFECTS_ATTR, False) is True

    with pytest.raises(ExtractionError) as raised:
        _process_tagged(_Failing(False), {})
    assert not getattr(raised.value, STEP_SIDE_EFFECTS_ATTR, False)


def test_a_multi_task_step_has_side_effects_if_any_task_does():
    from app.services.workflow_engine import APICallNode, MultiTaskNode, PromptNode

    step = MultiTaskNode("Step")
    step.tasks = [APICallNode({"method": "POST"}), PromptNode.__new__(PromptNode)]
    assert step.has_side_effects() is True
    step.tasks = [APICallNode({"method": "GET"}), PromptNode.__new__(PromptNode)]
    assert step.has_side_effects() is False


def test_a_tagged_transient_failure_is_not_retried():
    from app.services.workflow_engine import STEP_SIDE_EFFECTS_ATTR

    exc = _wrapped(ModelAPIError(model_name="m", message="Connection error."))
    setattr(exc, STEP_SIDE_EFFECTS_ATTR, True)
    db = _db()
    retry, outcome = _run_execute(db, exc)
    assert outcome == "raised"
    retry.assert_not_called()
    assert len(_error_writes(db)) == 1


def test_an_error_raised_from_none_is_not_made_transient_by_its_context():
    try:
        try:
            raise ModelAPIError(model_name="m", message="Connection error.")
        except ModelAPIError:
            raise ValueError("bad payload") from None
    except ValueError as e:
        assert not is_transient_llm_error(e)
