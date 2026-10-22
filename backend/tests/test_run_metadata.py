"""A workflow run records what it needs to be reproduced.

Request: an evaluation running workflows through the API has to log, per run,
the model actually used (its name, not a tag like "strong" or "fast") and every
Vandalizer setting needed to reproduce the result. The status endpoint returned
neither: ``WorkflowResult.model`` held only the run's default, which a step's
own model, an optimizer override or a fallback retry can each replace.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

from app.services import metering, run_metadata
from app.services.llm_service import MeteredModel


@pytest.fixture(autouse=True)
def _no_flush(monkeypatch):
    monkeypatch.setattr(metering, "flush_sync", lambda s: None)

    async def _afl(s):
        return None

    monkeypatch.setattr(metering, "flush_async", _afl)


SYS_CONFIG = {
    "llm_endpoint": "http://default-llm:8000/v1",
    "available_models": [
        {
            "name": "openai/gpt-oss-120b", "tag": "strong", "api_protocol": "vllm",
            "endpoint": "https://user:pw@llm.example.edu:8443/v1?key=abc",
            "api_key": "gAAAA-encrypted-secret", "temperature": 0.0,
            "context_window": 131072, "thinking": True,
            "request_timeout_seconds": 300,
        },
        {"name": "glm-5.3-flash", "tag": "fast"},
    ],
}


class TestEndpointHost:
    @pytest.mark.parametrize("url, expected", [
        ("https://user:pw@llm.example.edu:8443/v1?key=abc", "https://llm.example.edu:8443"),
        ("http://localhost:11434/v1", "http://localhost:11434"),
        ("", None),
        (None, None),
        ("not a url", None),
    ])
    def test_reduces_to_scheme_and_host(self, url, expected):
        assert run_metadata.endpoint_host(url) == expected


class TestModelConfigSnapshot:
    def test_copies_the_allow_list_and_never_the_key(self):
        snap = run_metadata.model_config_snapshot("openai/gpt-oss-120b", SYS_CONFIG)
        assert snap["tag"] == "strong"
        assert snap["temperature"] == 0.0
        assert snap["context_window"] == 131072
        assert snap["api_protocol"] == "vllm"
        assert snap["request_timeout_seconds"] == 300
        assert snap["endpoint"] == "https://llm.example.edu:8443"
        assert snap["configured"] is True
        assert "api_key" not in snap
        assert "gAAAA" not in repr(snap) and "pw" not in repr(snap)

    def test_falls_back_to_the_system_endpoint(self):
        snap = run_metadata.model_config_snapshot("glm-5.3-flash", SYS_CONFIG)
        assert snap["endpoint"] == "http://default-llm:8000"

    def test_an_unconfigured_name_says_so(self):
        assert run_metadata.model_config_snapshot("gone", SYS_CONFIG) == {
            "name": "gone", "configured": False,
        }


class _FakeModel:
    def __init__(self):
        self.base_url = "https://user:pw@llm.example.edu:8443/v1"

    @property
    def model_name(self):
        return "gpt-oss-120b"

    @property
    def system(self):
        return "openai"

    async def request(self, messages, model_settings, model_request_parameters):
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=10, output_tokens=2), parts=[],
            finish_reason="stop",
        )


def _metered():
    mm = MeteredModel.__new__(MeteredModel)
    mm.wrapped = _FakeModel()
    mm.configured_model = "openai/gpt-oss-120b"
    return mm


class TestRequestCapture:
    async def test_records_what_each_call_was_sent(self):
        settings = {
            "temperature": 0.0, "max_tokens": 4096, "thinking": True,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
            "timeout": 300.0,
        }
        params = SimpleNamespace(output_mode="native")
        with metering.metered("workflow") as scope:
            with metering.metered_step(1, "Extract"):
                await _metered().request([], settings, params)
                await _metered().request([], settings, params)
                # Pass 2 of a two-pass extraction: same model, thinking off.
                await _metered().request([], {**settings, "thinking": False}, params)

        [row] = metering.model_usage_rows(scope)
        assert row["model"] == "gpt-oss-120b"
        assert row["requests"] == 3
        assert len(row["settings"]) == 2  # identical calls fold together
        first = row["settings"][0]
        assert first == {
            "configured_model": "openai/gpt-oss-120b",
            "provider": "openai",
            "endpoint": "https://llm.example.edu:8443",
            "temperature": 0.0,
            "max_tokens": 4096,
            "thinking": True,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
            "output_mode": "native",
        }
        assert row["settings"][1]["thinking"] is False

    def test_rows_without_settings_keep_their_shape(self):
        with metering.metered("workflow") as scope:
            metering.record_usage("m", 1, 1)
        assert "settings" not in metering.model_usage_rows(scope)[0]

    def test_a_fingerprint_that_cannot_be_read_does_not_raise(self):
        broken = SimpleNamespace()  # no system, no wrapped model
        assert run_metadata.request_fingerprint(broken, None, None) == {}


def _steps(prompt="Summarize the award.", doc_text="Award text"):
    return [
        {"name": "Document", "data": {"doc_uuids": ["D1"]}, "tasks": []},
        {
            "name": "Summarize",
            "data": {},
            "tasks": [{
                "name": "Prompt",
                "data": {
                    "prompt": prompt, "model": "openai/gpt-oss-120b",
                    "_fallback_model": "glm-5.3-flash", "user_id": "u1",
                    "doc_texts": [doc_text], "template_bytes": b"%PDF-1.7",
                },
            }],
        },
    ]


def _db(raw_text="Award text"):
    db = MagicMock()
    db.smart_document.find_one.side_effect = lambda q, *a, **k: (
        {"uuid": q["uuid"], "title": "award.pdf", "extension": "pdf", "raw_text": raw_text}
        if q["uuid"] == "D1" else None
    )
    return db


def _config(steps=None, db=None, **overrides):
    kwargs = dict(
        workflow_doc={"_id": ObjectId(), "name": "Award intake", "version": 3,
                      "input_config": {"fixed_documents": [{"uuid": "F1"}]}},
        steps_data=steps or _steps(),
        trigger_step_data={"doc_uuids": ["D1"]},
        model="openai/gpt-oss-120b",
        sys_config=SYS_CONFIG,
        config_override={"step_overrides": {"Summarize": {"model": "glm-5.3-flash"}}},
    )
    kwargs.update(overrides)
    return run_metadata.build_run_config(db or _db(), **kwargs)


class TestRunConfig:
    def test_snapshots_version_workflow_models_and_documents(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.version_service.get_current_version", lambda: "v4.15.0",
        )
        cfg = _config()
        assert cfg["vandalizer_version"] == "v4.15.0"
        assert cfg["workflow"]["name"] == "Award intake"
        assert cfg["workflow"]["version"] == 3
        assert cfg["workflow"]["config_override"] == {
            "step_overrides": {"Summarize": {"model": "glm-5.3-flash"}},
        }
        assert cfg["default_model"] == "openai/gpt-oss-120b"
        assert cfg["steps"] == [{
            "index": 1, "name": "Summarize",
            "tasks": [{"type": "Prompt", "model": "openai/gpt-oss-120b",
                       "fallback_model": "glm-5.3-flash"}],
        }]
        assert isinstance(cfg["extraction_config"], dict) and cfg["extraction_config"]
        doc, fixed = cfg["documents"]
        assert doc["uuid"] == "D1" and doc["text_chars"] == len("Award text")
        assert len(doc["text_sha256"]) == 64
        assert fixed == {"uuid": "F1", "found": False}

    def test_definition_hash_tracks_configuration_not_document_text(self):
        base = _config()["workflow"]["definition_hash"]
        other_doc = _config(steps=_steps(doc_text="A different award"))
        assert other_doc["workflow"]["definition_hash"] == base
        other_prompt = _config(steps=_steps(prompt="List the deadlines."))
        assert other_prompt["workflow"]["definition_hash"] != base

    def test_document_hash_tracks_its_text(self):
        a = _config(db=_db("one"))["documents"][0]["text_sha256"]
        b = _config(db=_db("two"))["documents"][0]["text_sha256"]
        assert a != b

    def test_snapshot_is_written_once(self):
        db = _db()
        run_id = ObjectId()
        run_metadata.snapshot_run_config(
            db, str(run_id),
            workflow_doc={"_id": ObjectId(), "name": "W"}, steps_data=_steps(),
            trigger_step_data={"doc_uuids": ["D1"]}, model="m",
            sys_config=SYS_CONFIG, config_override=None,
        )
        query, update = db.workflow_result.update_one.call_args.args
        # Guarded on run_config being unset, so a resume keeps the first pass's.
        assert query == {"_id": run_id, "run_config": None}
        assert update["$set"]["run_config"]["default_model"] == "m"

    def test_a_failed_snapshot_does_not_fail_the_run(self, monkeypatch):
        db = MagicMock()
        db.workflow_result.update_one.side_effect = RuntimeError("mongo down")
        run_metadata.snapshot_run_config(
            db, str(ObjectId()),
            workflow_doc={}, steps_data=[], trigger_step_data={}, model=None,
            sys_config={}, config_override=None,
        )


class TestPassUsage:
    def test_appends_rows_and_the_configs_of_the_models_called(self):
        scope = metering.MeterScope(feature="workflow")
        token = metering._current_scope.set(scope)
        try:
            with metering.metered_step(1, "Summarize"):
                metering.record_usage(
                    "gpt-oss-120b", 10, 2,
                    settings={"configured_model": "openai/gpt-oss-120b", "temperature": 0.0},
                )
        finally:
            metering._current_scope.reset(token)

        db = MagicMock()
        run_id = ObjectId()
        run_metadata.record_pass_usage(db, str(run_id), scope, SYS_CONFIG)
        query, update = db.workflow_result.update_one.call_args.args
        assert query == {"_id": run_id}
        [row] = update["$push"]["model_usage"]["$each"]
        assert row["model"] == "gpt-oss-120b" and row["step"] == "Summarize"
        [cfg] = update["$push"]["model_configs"]["$each"]
        assert cfg["name"] == "openai/gpt-oss-120b" and cfg["tag"] == "strong"

    def test_a_pass_that_called_no_model_writes_nothing(self):
        db = MagicMock()
        run_metadata.record_pass_usage(
            db, str(ObjectId()), metering.MeterScope(feature="workflow"), SYS_CONFIG,
        )
        db.workflow_result.update_one.assert_not_called()


class TestDescribeRun:
    def test_runs_from_before_this_have_none(self):
        assert run_metadata.describe_run(SimpleNamespace(model="m")) is None
        # A MagicMock result (as other tests build) has nothing recorded either.
        assert run_metadata.describe_run(MagicMock()) is None

    def test_folds_passes_into_one_record(self):
        fp = {"configured_model": "openai/gpt-oss-120b", "temperature": 0.0}
        result = SimpleNamespace(
            model="openai/gpt-oss-120b",
            run_config={"vandalizer_version": "v4.15.0", "default_model": "openai/gpt-oss-120b"},
            model_usage=[
                # first pass, then the approval resume of the same run
                {"step_index": 1, "step": "Extract", "model": "gpt-oss-120b",
                 "tokens_input": 100, "tokens_output": 10, "requests": 1, "settings": [fp]},
                {"step_index": 3, "step": "Write", "model": "glm-5.3-flash",
                 "tokens_input": 5, "tokens_output": 1, "requests": 1},
                {"step_index": 1, "step": "Extract", "model": "gpt-oss-120b",
                 "tokens_input": 50, "tokens_output": 5, "requests": 1, "settings": [fp]},
            ],
            model_configs=[
                {"name": "openai/gpt-oss-120b", "tag": "strong"},
                {"name": "glm-5.3-flash", "tag": "fast"},
                {"name": "openai/gpt-oss-120b", "tag": "strong"},
            ],
        )
        meta = run_metadata.describe_run(result)
        assert meta["vandalizer_version"] == "v4.15.0"
        assert meta["models_used"] == ["gpt-oss-120b", "glm-5.3-flash"]
        extract, write = meta["model_usage"]
        assert (extract["requests"], extract["tokens_input"]) == (2, 150)
        assert extract["settings"] == [fp]
        assert write["settings"] == []
        assert [c["name"] for c in meta["model_configs"]] == [
            "openai/gpt-oss-120b", "glm-5.3-flash",
        ]


async def test_status_payload_carries_run_metadata(monkeypatch):
    from unittest.mock import AsyncMock, patch

    from app.schemas.workflows import WorkflowStatusResponse
    from app.services.workflow_service import get_workflow_status

    result = MagicMock()
    result.status = "completed"
    result.num_steps_completed = 1
    result.num_steps_total = 1
    result.current_step_name = result.current_step_detail = result.current_step_preview = None
    result.final_output = {"output": "done"}
    result.steps_output = {}
    result.output_step_names = []
    result.approval_request_id = None
    result.error = None
    result.error_payload = None
    result.delivery_failures = []
    result.retrieved_sources = []
    result.document_title = None
    result.model = "openai/gpt-oss-120b"
    result.run_config = {"vandalizer_version": "v4.15.0"}
    result.model_usage = [{"step_index": 1, "step": "S", "model": "gpt-oss-120b",
                           "tokens_input": 1, "tokens_output": 1, "requests": 1}]
    result.model_configs = []
    result.sourcing = None
    with patch("app.services.workflow_service.WorkflowResult") as wr, \
            patch("app.services.workflow_service.Workflow") as wf:
        wr.find_one = AsyncMock(return_value=result)
        wf.get = AsyncMock(return_value=None)
        status = await get_workflow_status("sess1")

    body = WorkflowStatusResponse(**status).model_dump()
    assert body["run_metadata"]["models_used"] == ["gpt-oss-120b"]
    assert body["run_metadata"]["default_model"] == "openai/gpt-oss-120b"
