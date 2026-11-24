"""validation_drift: a score goes out of date when its model or graded cases
change, not only when the item's own config does (#1013 §5)."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.quality_service import item_validation_drift, validation_drift

RUN_AT = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)
BEFORE = RUN_AT - datetime.timedelta(days=1)
AFTER = RUN_AT + datetime.timedelta(days=1)


def _run(model="qwen3.8", case_uuids=("a", "b")):
    return {
        "model": model,
        "created_at": RUN_AT.isoformat(),
        "result_snapshot": {"test_cases": [{"test_case_uuid": u} for u in case_uuids]},
    }


def test_no_run_reports_nothing():
    out = validation_drift(None, current_model="m", configured_models={"m"})
    assert out["model_changed"] is False
    assert out["drift_reasons"] == []


def test_same_model_and_cases_is_not_drift():
    out = validation_drift(
        _run(), current_model="qwen3.8", configured_models={"qwen3.8"},
        test_cases=[("a", BEFORE), ("b", BEFORE)],
    )
    assert out["model_changed"] is False
    assert out["test_cases_changed"] is False
    assert out["drift_reasons"] == []


def test_model_no_longer_configured():
    # The 2026-09 rename: the measured model's name disappeared from config.
    out = validation_drift(_run(model="qwen3.6"), current_model="qwen3.8", configured_models={"qwen3.8"})
    assert out["model_changed"] is True
    assert out["validated_model"] == "qwen3.6"
    assert out["drift_reasons"] == ["measured on qwen3.6, which is no longer configured"]


def test_new_runs_resolve_to_a_different_model():
    out = validation_drift(
        _run(model="qwen3.8"), current_model="gpt-oss-120b",
        configured_models={"qwen3.8", "gpt-oss-120b"},
    )
    assert out["model_changed"] is True
    assert out["drift_reasons"] == ["measured on qwen3.8; new runs use gpt-oss-120b"]


def test_run_without_a_single_model_reports_no_model_drift():
    # Workflow runs graded across several models record model=None.
    out = validation_drift(_run(model=None), current_model="x", configured_models={"x"})
    assert out["model_changed"] is False


def test_case_added_after_the_run():
    out = validation_drift(
        _run(), current_model="qwen3.8", configured_models={"qwen3.8"},
        test_cases=[("a", BEFORE), ("b", BEFORE), ("c", AFTER)],
    )
    assert out["test_cases_changed"] is True
    assert out["drift_reasons"] == ["test cases changed since the run (1 added)"]


def test_case_left_out_of_a_subset_run_is_not_drift():
    # "c" existed before the run and wasn't selected; that is not a change.
    out = validation_drift(
        _run(case_uuids=("a",)), current_model="qwen3.8", configured_models={"qwen3.8"},
        test_cases=[("a", BEFORE), ("c", BEFORE)],
    )
    assert out["test_cases_changed"] is False


def test_graded_case_deleted():
    out = validation_drift(
        _run(), current_model="qwen3.8", configured_models={"qwen3.8"},
        test_cases=[("a", BEFORE)],
    )
    assert out["test_cases_changed"] is True
    assert out["drift_reasons"] == ["test cases changed since the run (1 deleted)"]


def test_naive_created_at_from_mongo_compares():
    naive_after = AFTER.replace(tzinfo=None)
    out = validation_drift(
        _run(), current_model="qwen3.8", configured_models={"qwen3.8"},
        test_cases=[("a", BEFORE), ("b", BEFORE), ("c", naive_after)],
    )
    assert out["test_cases_changed"] is True


# ── item_validation_drift: the lookups behind the quality cards ──

def _sys_cfg(*names):
    cfg = MagicMock()
    cfg.model_dump.return_value = {"available_models": [{"name": n} for n in names]}
    return cfg


@pytest.mark.asyncio
async def test_workflow_drift_uses_the_viewers_run_model():
    with (
        patch("app.services.quality_service.SystemConfig.get_config", AsyncMock(return_value=_sys_cfg("a", "b"))),
        patch("app.services.workflow_service.resolve_run_model", AsyncMock(return_value="b")) as resolve,
    ):
        out = await item_validation_drift(
            "workflow", _run(model="a"), user_id="u1",
            item=SimpleNamespace(input_config={"default_model": "b"}),
        )
    resolve.assert_awaited_once_with({"default_model": "b"}, "u1")
    assert out["drift_reasons"] == ["measured on a; new runs use b"]


@pytest.mark.asyncio
async def test_drift_lookup_failure_reports_no_drift():
    with patch(
        "app.services.quality_service.SystemConfig.get_config",
        AsyncMock(side_effect=RuntimeError("db down")),
    ):
        out = await item_validation_drift("workflow", _run(), user_id="u1", item=SimpleNamespace(input_config={}))
    assert out["drift_reasons"] == []
    assert out["model_changed"] is False


@pytest.mark.asyncio
async def test_quality_status_route_returns_drift():
    from app.routers import workflows as workflows_router

    latest = {"score": 80.0, "created_at": RUN_AT.isoformat(), "extraction_config": {}}
    drift = {
        "model_changed": True, "validated_model": "a", "current_model": "b",
        "test_cases_changed": False, "drift_reasons": ["measured on a; new runs use b"],
    }
    verified = MagicMock()
    verified.find_one = AsyncMock(return_value=None)
    with (
        patch("app.models.verification.VerifiedItemMetadata", verified),
        patch("app.services.quality_service.get_latest_validation", AsyncMock(return_value=latest)),
        patch("app.services.quality_service.item_validation_drift", AsyncMock(return_value=drift)),
        patch("app.models.system_config.SystemConfig.get_config", AsyncMock(
            return_value=SimpleNamespace(get_quality_config=lambda: {}))),
        patch.object(workflows_router, "get_authorized_workflow",
                     AsyncMock(return_value=SimpleNamespace(validation_plan=[], steps=[], input_config={}))),
    ):
        result = await workflows_router.get_workflow_quality_status("wf-1", user=MagicMock())
    assert result["model_changed"] is True
    assert result["drift_reasons"] == ["measured on a; new runs use b"]
