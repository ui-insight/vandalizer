"""Runs record which model their LLM calls used, per workflow step.

Support ticket: History showed status, time, duration and tokens but not the
model, so a user could not confirm a model choice was applied, compare two
runs, or tell which runs a misbehaving model affected — and a workflow with
per-step model overrides gave no way to see which step used which model. The
metering scope only kept the first model it saw.
"""

import contextvars
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from app.services import metering
from app.services.workflow_engine import MultiTaskNode, Node, WorkflowEngine


_real_flush_sync = metering.flush_sync


@pytest.fixture(autouse=True)
def _no_flush(monkeypatch):
    monkeypatch.setattr(metering, "flush_sync", lambda s: None)


class TestScope:
    def test_every_model_is_kept_per_step(self):
        with metering.metered("workflow") as scope:
            metering.record_usage("glm-5.3-flash", 100, 10)  # outside any step
            with metering.metered_step(0, "Extract"):
                metering.record_usage("gpt-oss-120b", 50, 5)
                metering.record_usage("gpt-oss-120b", 50, 5)
            with metering.metered_step(1, "Summarize"):
                metering.record_usage("glm-5.3-flash", 10, 1)
                metering.record_usage(None, 1, 1)
        rows = {(r["step_index"], r["model"]): r for r in metering.model_usage_rows(scope)}
        assert rows[(None, "glm-5.3-flash")]["tokens_input"] == 100
        assert rows[(0, "gpt-oss-120b")] == {
            "step_index": 0, "step": "Extract", "model": "gpt-oss-120b",
            "tokens_input": 100, "tokens_output": 10, "requests": 2,
        }
        assert rows[(1, metering.UNKNOWN_MODEL)]["requests"] == 1
        # The ledger's single model and the totals are what they were.
        assert scope.model == "glm-5.3-flash"
        assert (scope.tokens_in, scope.tokens_out, scope.requests) == (211, 22, 5)

    def test_a_steps_worker_threads_are_attributed_to_it(self):
        def call(model):
            metering.record_usage(model, 1, 1)

        with metering.metered("workflow") as scope:
            with metering.metered_step(2, "Tasks"):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [
                        pool.submit(contextvars.copy_context().run, call, m)
                        for m in ["a", "b"] * 200
                    ]
                    [f.result() for f in futures]
        assert metering.step_models(scope, 2) == ["a", "b"]
        assert sum(r["requests"] for r in metering.model_usage_rows(scope)) == 400


class TestSummary:
    def test_folds_passes_and_orders_by_tokens(self):
        rows = [
            # first pass, then an approval resume of the same run
            {"step_index": 0, "step": "Extract", "model": "a", "tokens_input": 10, "tokens_output": 0},
            {"step_index": 0, "step": "Extract", "model": "b", "tokens_input": 50, "tokens_output": 0},
            {"step_index": 2, "step": "Write", "model": "a", "tokens_input": 100, "tokens_output": 0},
            {"step_index": None, "step": None, "model": "c", "tokens_input": 1, "tokens_output": 0},
        ]
        assert metering.summarize_model_usage(rows) == {
            "models": ["a", "b", "c"],
            "steps": [
                {"index": 0, "name": "Extract", "models": ["b", "a"]},
                {"index": 2, "name": "Write", "models": ["a"]},
            ],
        }

    def test_runs_from_before_models_were_recorded(self):
        assert metering.run_model_fields(None) == {"models": [], "step_models": []}


def test_flush_appends_usage_to_the_activity(monkeypatch):
    from bson import ObjectId

    db = MagicMock()
    monkeypatch.setattr("app.tasks.get_sync_db", lambda: db)
    scope = metering.MeterScope(feature="workflow", activity_id=str(ObjectId()))
    with metering.metered_step(0, "Extract"):
        token = metering._current_scope.set(scope)
        metering.record_usage("gpt-oss-120b", 5, 1)
        metering._current_scope.reset(token)

    _real_flush_sync(scope)

    update = db.activity_event.update_one.call_args.args[1]
    # Pushed, not set: a resumed or retried run flushes once per pass.
    assert update["$push"]["model_usage"]["$each"] == [{
        "step_index": 0, "step": "Extract", "model": "gpt-oss-120b",
        "tokens_input": 5, "tokens_output": 1, "requests": 1,
    }]


class _ModelNode(Node):
    def __init__(self, name, *models):
        super().__init__(name)
        self.models = models

    def process(self, inputs):
        for model in self.models:
            metering.record_usage(model, 10, 1)
        return {"output": self.name, "input": None, "step_name": self.name}


def test_engine_records_each_steps_models_on_its_output():
    engine = WorkflowEngine()
    first = _ModelNode("Extract", "gpt-oss-120b")
    second = MultiTaskNode("Summarize")
    second.add_tasks([_ModelNode("t1", "glm-5.3-flash"), _ModelNode("t2", "gpt-oss-120b")])
    third = _ModelNode("Format")  # no LLM call
    engine.add_node(first)
    engine.add_node(second)
    engine.add_node(third)
    engine.connect(first, second)
    engine.connect(second, third)

    persisted = {}
    with metering.metered("workflow") as scope:
        _, data = engine.execute(workflow_result_updater=lambda u: persisted.update(u))

    by_name = {entry["name"]: entry for entry in data}
    assert by_name["Extract"]["models"] == ["gpt-oss-120b"]
    assert set(by_name["Summarize"]["models"]) == {"glm-5.3-flash", "gpt-oss-120b"}
    assert "models" not in by_name["Format"]
    # Persisted with the step's output, which the run's export reads.
    assert persisted["steps_output.Extract"]["models"] == ["gpt-oss-120b"]
    steps = metering.run_model_fields(metering.model_usage_rows(scope))["step_models"]
    assert [(s["index"], s["name"]) for s in steps] == [(0, "Extract"), (1, "Summarize")]
    assert set(steps[1]["models"]) == {"glm-5.3-flash", "gpt-oss-120b"}


def _event(**kw):
    import datetime

    from types import SimpleNamespace

    base = dict(
        id="ev1", status="completed", started_at=datetime.datetime(2026, 10, 1), finished_at=None,
        duration_ms=10, error=None, tokens_input=1, tokens_output=1, documents_touched=1,
        steps_completed=2, steps_total=2, workflow_session_id="s1", result_snapshot={}, meta_summary={},
        model_usage=[
            {"step_index": 0, "step": "Extract", "model": "gpt-oss-120b", "tokens_input": 9, "tokens_output": 0},
            {"step_index": 1, "step": "Write", "model": "glm-5.3-flash", "tokens_input": 1, "tokens_output": 0},
        ],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _activity_cls(events):
    from unittest.mock import AsyncMock

    query = MagicMock()
    query.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=events)
    cls = MagicMock()
    cls.find.return_value = query
    return cls


@pytest.mark.asyncio
async def test_workflow_history_names_the_models_per_step():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.routers import workflows

    with patch.object(workflows, "get_authorized_workflow", AsyncMock(return_value=SimpleNamespace(id="wf"))), \
         patch("app.models.activity.ActivityEvent", _activity_cls([_event(), _event(model_usage=[])])):
        out = await workflows.get_workflow_history("wf", user=SimpleNamespace(user_id="u"))
    run, old = out["runs"]
    assert run["models"] == ["gpt-oss-120b", "glm-5.3-flash"]
    assert run["step_models"] == [
        {"index": 0, "name": "Extract", "models": ["gpt-oss-120b"]},
        {"index": 1, "name": "Write", "models": ["glm-5.3-flash"]},
    ]
    assert old["models"] == [] and old["step_models"] == []


@pytest.mark.asyncio
async def test_extraction_history_names_the_model():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.routers import extractions

    usage = [{"step_index": None, "step": None, "model": "glm-5.3-flash", "tokens_input": 5, "tokens_output": 1}]
    with patch.object(extractions, "_get_search_set_or_404", AsyncMock()), \
         patch("app.models.activity.ActivityEvent", _activity_cls([_event(model_usage=usage)])):
        out = await extractions.get_extraction_history("ss", user=SimpleNamespace(user_id="u"))
    assert out["runs"][0]["models"] == ["glm-5.3-flash"]
    assert out["runs"][0]["step_models"] == []
