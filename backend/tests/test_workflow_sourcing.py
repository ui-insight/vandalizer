"""Sourcing must never change what a workflow produces.

It runs after a run is saved as completed, reads the saved output, and
writes only ``workflow_result.sourcing``. These tests pin that down: the
same model replies give byte-identical outputs with sourcing on and off,
tracing does not touch what it reads, the task writes nothing but its own
field, and a failure anywhere in it leaves the run exactly as it was."""

import json
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from tests.test_output_sourcing import EXPENSE, Judge

EXPENSE_TEXT = EXPENSE["raw_text"]


def _replies(model, prompt, data=None, **kw):
    if "vendor" in prompt:
        return '{"vendor": "Forestry Suppliers Inc."}'
    return '{"amount": 1240.0}'


def _format(model, instruction, text, **kw):
    return instruction, "**Vendor:** Forestry Suppliers Inc.\n**Amount:** $1,240.00\n"


def _run_engine():
    """One run of a three-step workflow on fixed model replies: what the run
    view, the steps' "Last run output" and the deliverable are built from."""
    from app.services.workflow_engine import build_workflow_engine

    steps = [
        {"name": "Document", "data": {"doc_uuids": ["exp"]}, "tasks": []},
        {"name": "Read", "data": {"input_sources": ["workflow_documents"]}, "tasks": [
            {"name": "Prompt", "data": {"prompt": "Extract the vendor", "doc_texts": [EXPENSE_TEXT]}},
            {"name": "Prompt", "data": {"prompt": "Extract the amount", "doc_texts": [EXPENSE_TEXT]}},
        ]},
        {"name": "Write up", "data": {"input_sources": ["step_input"]}, "tasks": [
            {"name": "Formatter", "data": {"format_template": "Write it up"}},
        ]},
    ]
    engine = build_workflow_engine(steps, model="m")
    steps_output: dict = {}

    def updater(update):
        for k, v in update.items():
            if k.startswith("steps_output."):
                steps_output[k[len("steps_output."):]] = v

    with patch("app.services.workflow_engine.llm_chat_model", side_effect=_replies), \
         patch("app.services.workflow_engine.format_model", side_effect=_format):
        final, data = engine.execute(workflow_result_updater=updater)
    return {"steps_output": steps_output, "final_output": {"output": final, "data": data}}


def _bytes(run):
    return json.dumps(run, sort_keys=True, default=str)


def test_the_same_replies_give_byte_identical_outputs_with_sourcing_on_and_off():
    from app.services.output_sourcing import trace_sources
    from app.tasks.sourcing_tasks import run_targets

    off = _run_engine()
    on = _run_engine()
    judge = Judge(("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."),
                  ("1,240", "Amount:", "Amount: $1,240.00"), ("1240", "Amount:", "Amount: $1,240.00"))
    before = _bytes(on)
    targets, passages = run_targets(on)
    sourcing = trace_sources(targets, [EXPENSE], passages, ask=judge, workers=1)

    assert _bytes(on) == before == _bytes(off)
    # The trace did find sources — the outputs are identical, not untested.
    traced = sum(t["summary"]["traced"] for t in sourcing["targets"].values())
    assert traced >= 3, sourcing
    assert set(sourcing["targets"]) == {"step:Read", "step:Write_up", "final"}


def test_the_engine_does_not_know_about_sourcing():
    """Nothing the steps read is affected: no prompt, setting or context
    the engine builds mentions it."""
    import ast
    import inspect

    from app.services import workflow_engine

    tree = ast.parse(inspect.getsource(workflow_engine))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not {m for m in imported if "sourcing" in m}, imported


# ---------------------------------------------------------------------------
# The run task: completion first, sourcing beside it
# ---------------------------------------------------------------------------

def _execute(monkeypatch, sourcing, delay_error=None):
    from tests.test_workflow_tasks import _fake_oid, _make_result_doc, _make_workflow_doc, _mock_db
    from app.tasks.workflow_tasks import execute_workflow_task

    monkeypatch.setenv("WORKFLOW_SOURCING", "on" if sourcing else "off")
    wf_id, result_id, step_id, task_id = _fake_oid(), _fake_oid(), _fake_oid(), _fake_oid()
    db = _mock_db(
        workflow_doc=_make_workflow_doc(wf_id=wf_id, step_ids=[step_id]),
        result_doc=_make_result_doc(result_id=result_id, workflow_id=wf_id),
        step_docs=[{"_id": step_id, "name": "Step1", "data": {}, "tasks": [task_id]}],
        task_docs=[{"_id": task_id, "name": "Prompt", "data": {"prompt": "test"}}],
        smart_docs=[{"uuid": "uuid1", "raw_text": "document text"}],
    )
    engine = MagicMock()
    engine.execute.return_value = ("**Vendor:** Forestry Suppliers Inc.", [{"name": "Step1", "output": "x"}])
    engine.usage = MagicMock(tokens_in=1, tokens_out=1)
    delay = MagicMock(side_effect=delay_error)
    with patch("app.tasks.workflow_tasks._get_db", return_value=db), \
         patch("app.services.workflow_engine.build_workflow_engine", return_value=engine), \
         patch("app.tasks.sourcing_tasks.trace_run_sources.delay", delay), \
         patch("app.tasks.quality_tasks.auto_validate_workflow"), \
         patch("app.tasks.activity_tasks.generate_activity_description_task"):
        out = execute_workflow_task(
            workflow_result_id=str(result_id), workflow_id=str(wf_id),
            trigger_step_data={"doc_uuids": ["uuid1"]}, model="gpt-4o",
        )
    writes = [c[0] for c in db.workflow_result.update_one.call_args_list]
    return out, writes, delay


def _completion(writes):
    return [w for w in writes if w[1].get("$set", {}).get("status") == "completed"]


def test_the_completed_result_is_written_identically_with_sourcing_on_and_off(monkeypatch):
    out_on, writes_on, delay_on = _execute(monkeypatch, sourcing=True)
    out_off, writes_off, delay_off = _execute(monkeypatch, sourcing=False)
    assert out_on["status"] == out_off["status"] == "completed"
    on, off = _completion(writes_on), _completion(writes_off)
    assert len(on) == len(off) == 1
    assert _bytes(on[0][1]) == _bytes(off[0][1])
    # Sourcing is queued only after the result is saved, and writes its own field.
    sourcing_writes = [i for i, w in enumerate(writes_on) if "sourcing" in w[1].get("$set", {})]
    assert sourcing_writes and sourcing_writes[0] > writes_on.index(on[0])
    assert set(writes_on[sourcing_writes[0]][1]["$set"]) == {"sourcing"}
    delay_on.assert_called_once()
    delay_off.assert_not_called()
    assert not any("sourcing" in w[1].get("$set", {}) for w in writes_off)


def test_sourcing_is_queued_for_a_run_whose_record_holds_a_null_sourcing(monkeypatch):
    """The API creates a run through Beanie, which writes `sourcing: null`.
    The queue's once-only guard must match that, not just a missing field
    (a `$exists: False` guard queued nothing on the first real run)."""
    _, writes, delay = _execute(monkeypatch, sourcing=True)
    [queued] = [w for w in writes if "sourcing" in w[1].get("$set", {})]
    assert queued[0]["sourcing"] is None
    assert queued[0]["status"] == "completed"
    delay.assert_called_once()


def test_a_sourcing_queue_failure_leaves_the_run_completed(monkeypatch):
    out, writes, _ = _execute(monkeypatch, sourcing=True, delay_error=ConnectionError("broker down"))
    assert out["status"] == "completed"
    assert len(_completion(writes)) == 1
    failed = [w for w in writes if w[1].get("$set", {}).get("sourcing", {}).get("status") == "failed"]
    assert failed


# ---------------------------------------------------------------------------
# The sourcing task writes only its own field
# ---------------------------------------------------------------------------

def _saved_run():
    oid = ObjectId()
    return oid, {
        "_id": oid, "status": "completed", "workflow": ObjectId(), "model": "m",
        "input_context": {"doc_uuids": ["exp"]},
        "steps_output": {
            "Document": {"step_name": "Document", "output": ["exp"]},
            "Read": {"step_name": "Read", "output": {"vendor": "Forestry Suppliers Inc."}},
        },
        "final_output": {"output": "**Vendor:** Forestry Suppliers Inc.", "data": []},
        "sourcing": {"version": 1, "status": "pending"},
    }


def _task_db(run):
    db = MagicMock()
    db.workflow_result.find_one.return_value = run
    db.workflow_result.update_one.return_value = MagicMock(modified_count=1)
    db.workflow.find_one.return_value = {"user_id": "u1", "team_id": "t1"}
    db.smart_document.find_one.side_effect = lambda q, *a, **k: EXPENSE if q.get("uuid") == "exp" else None
    db.system_config.find_one.return_value = {}
    return db


def test_the_task_writes_only_the_sourcing_field():
    from app.tasks.sourcing_tasks import trace_run_sources

    oid, run = _saved_run()
    db = _task_db(run)
    judge = Judge(("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."))
    with patch("app.tasks.sourcing_tasks._get_db", return_value=db), \
         patch("app.services.workflow_engine._run_form_filler_model",
               side_effect=lambda model, i, p, **kw: judge(i, p)):
        trace_run_sources.run(str(oid), ["exp"])
    claim, final = [c[0] for c in db.workflow_result.update_one.call_args_list]
    assert claim[0] == {"_id": oid, "status": "completed", "sourcing.status": "pending"}
    assert set(final[1]["$set"]) == {"sourcing"}
    sourcing = final[1]["$set"]["sourcing"]
    assert sourcing["status"] == "done"
    assert set(sourcing["targets"]) == {"step:Read", "final"}       # never the Document trigger
    assert sourcing["targets"]["final"]["summary"] == {"statements": 1, "traced": 1}
    assert sourcing["sources"][0]["document_uuid"] == "exp"


def test_a_task_that_fails_records_the_failure_and_nothing_else():
    from app.tasks.sourcing_tasks import trace_run_sources

    oid, run = _saved_run()
    db = _task_db(run)
    with patch("app.tasks.sourcing_tasks._get_db", return_value=db), \
         patch("app.services.output_sourcing.trace_sources", side_effect=RuntimeError("boom")):
        trace_run_sources.run(str(oid), ["exp"])
    final = db.workflow_result.update_one.call_args_list[-1][0]
    assert set(final[1]["$set"]) == {"sourcing"}
    assert final[1]["$set"]["sourcing"]["status"] == "failed"


def test_a_run_already_claimed_is_not_traced_twice():
    from app.tasks.sourcing_tasks import trace_run_sources

    oid, run = _saved_run()
    db = _task_db(run)
    db.workflow_result.update_one.return_value = MagicMock(modified_count=0)
    with patch("app.tasks.sourcing_tasks._get_db", return_value=db), \
         patch("app.services.output_sourcing.trace_sources") as traced:
        assert trace_run_sources.run(str(oid), ["exp"]) == {"status": "skipped"}
    traced.assert_not_called()


def test_run_targets_reads_what_each_view_shows():
    from app.tasks.sourcing_tasks import run_targets

    run = {
        "retrieved_sources": [{"chunk_id": "a", "content": "Passage A"}],
        "steps_output": {
            "Document": {"step_name": "Document", "output": ["x"]},
            "Extract": {"step_name": "Extract", "output": [{"a": 1}], "formatted_output": "### Extract\na: 1",
                        "retrieved_sources": [{"chunk_id": "b", "content": "Passage B"}, {"chunk_id": "c"}]},
        },
        "final_output": {"output": "Done.", "data": []},
    }
    targets, passages = run_targets(run)
    assert targets == {"step:Extract": "### Extract\na: 1", "final": "Done."}
    assert [p["chunk_id"] for p in passages] == ["a", "b"]   # a passage without text cannot be checked


@pytest.mark.parametrize("value, enabled", [("off", False), ("0", False), ("on", True), ("", True)])
def test_sourcing_is_on_unless_turned_off(monkeypatch, value, enabled):
    from app.tasks.sourcing_tasks import sourcing_enabled

    monkeypatch.setenv("WORKFLOW_SOURCING", value)
    assert sourcing_enabled() is enabled
