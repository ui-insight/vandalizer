"""A ValidationRun must be labeled with the model that actually executed.

Two lies these tests pin against:
  1. A model pinned in system/per-set extraction config silently wins over the
     caller's ``model`` argument, while the run was persisted under the
     requested model — a score labeled with a model that never ran.
  2. A caller explicitly requesting a model (regression suite, mgmt API) got
     the config-pinned model instead, so "validate under model X" measured
     something else entirely.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extraction_engine import ExtractionEngine
from app.services.extraction_validation_service import (
    _effective_model_info,
    _force_model_config,
)


def _sys_cfg(extraction_model: str | None = None) -> dict:
    cfg: dict = {
        "available_models": [
            {"name": "cfg-model", "temperature": 0.1},
            {"name": "user-model", "temperature": 0.7},
            {"name": "req-model", "temperature": 0.3},
        ],
    }
    if extraction_model is not None:
        cfg["extraction_config"] = {"model": extraction_model}
    return cfg


# ---------------------------------------------------------------------------
# ExtractionEngine.effective_model_info
# ---------------------------------------------------------------------------


class TestEffectiveModelInfo:
    def test_config_pinned_model_wins_over_fallback(self):
        engine = ExtractionEngine(system_config_doc=_sys_cfg("cfg-model"))
        info = engine.effective_model_info(None, "user-model")
        assert info["model"] == "cfg-model"
        assert info["source"] == "config"
        assert info["temperature"] == 0.1

    def test_fallback_model_used_when_nothing_pinned(self):
        engine = ExtractionEngine(system_config_doc=_sys_cfg())
        info = engine.effective_model_info(None, "user-model")
        assert info["model"] == "user-model"
        assert info["source"] == "caller_default"
        assert info["temperature"] == 0.7

    def test_system_default_when_no_fallback(self):
        engine = ExtractionEngine(system_config_doc=_sys_cfg())
        info = engine.effective_model_info(None, None)
        assert info["model"] == "cfg-model"
        assert info["source"] == "system_default"

    def test_per_pass_pins_are_reported(self):
        engine = ExtractionEngine(system_config_doc=_sys_cfg())
        override = {"two_pass": {"pass_2": {"model": "req-model"}}}
        info = engine.effective_model_info(override, "user-model")
        assert info["pass_models"] == {
            "pass_1": "user-model",
            "pass_2": "req-model",
        }


# ---------------------------------------------------------------------------
# _force_model_config — the explicit-override channel
# ---------------------------------------------------------------------------


class TestForceModelConfig:
    def test_forces_model_and_both_pass_models(self):
        merged = _force_model_config(
            {"two_pass": {"pass_1": {"model": "other", "thinking": True}}},
            "req-model",
        )
        assert merged["model"] == "req-model"
        assert merged["two_pass"]["pass_1"]["model"] == "req-model"
        assert merged["two_pass"]["pass_2"]["model"] == "req-model"
        # Unrelated keys survive the overlay
        assert merged["two_pass"]["pass_1"]["thinking"] is True

    def test_does_not_mutate_the_original_override(self):
        original = {"two_pass": {"pass_1": {"model": "other"}}}
        _force_model_config(original, "req-model")
        assert original["two_pass"]["pass_1"]["model"] == "other"

    def test_forced_model_beats_a_system_config_pin(self):
        # The composition the validation service relies on: even with a model
        # pinned in system config, the forced override is what resolves.
        engine = ExtractionEngine(system_config_doc=_sys_cfg("cfg-model"))
        merged = _force_model_config(None, "req-model")
        info = engine.effective_model_info(merged, "user-model")
        assert info["model"] == "req-model"
        assert info["pass_models"] == {"pass_1": "req-model", "pass_2": "req-model"}

    def test_effective_model_info_relabels_requested(self):
        info = _effective_model_info(
            _sys_cfg("cfg-model"),
            _force_model_config(None, "req-model"),
            "user-model",
            "req-model",
        )
        assert info["model"] == "req-model"
        assert info["source"] == "requested"
        assert info["requested_model"] == "req-model"
        assert info["temperature"] == 0.3


# ---------------------------------------------------------------------------
# run_validation wiring — the persisted label matches what ran
# ---------------------------------------------------------------------------


def _tc_result() -> dict:
    return {
        "test_case_uuid": "tc-1",
        "label": "Case 1",
        "fields": [],
        "overall_accuracy": 1.0,
        "overall_consistency": 1.0,
        "per_run_correct": [],
    }


async def _run_validation_with(requested_model, sys_cfg_doc):
    ss = MagicMock()
    ss.title = "Set"
    ss.cross_field_rules = None

    sys_config = MagicMock()
    sys_config.model_dump.return_value = sys_cfg_doc
    sys_config.get_quality_config.return_value = {}

    vr = MagicMock(score=90.0, score_breakdown={})

    with (
        patch(
            "app.services.extraction_validation_service.get_extraction_keys",
            new_callable=AsyncMock, return_value=["A"],
        ),
        patch(
            "app.services.extraction_validation_service.list_test_cases",
            new_callable=AsyncMock, return_value=[MagicMock()],
        ),
        patch(
            "app.services.extraction_validation_service.get_user_model_name",
            new_callable=AsyncMock, return_value="user-model",
        ),
        patch(
            "app.services.extraction_validation_service.get_search_set",
            new_callable=AsyncMock, return_value=ss,
        ),
        patch(
            "app.services.extraction_validation_service.effective_extraction_config",
            return_value=None,
        ),
        patch(
            "app.services.extraction_validation_service.SystemConfig"
        ) as mock_sc,
        patch(
            "app.services.extraction_validation_service.get_extraction_field_metadata",
            new_callable=AsyncMock, return_value=[],
        ),
        patch(
            "app.services.extraction_validation_service._validate_test_case",
            new_callable=AsyncMock, return_value=_tc_result(),
        ) as mock_vtc,
        patch(
            "app.services.extraction_validation_service._compute_executive_summary",
            return_value={},
        ),
        patch(
            "app.services.quality_service.persist_validation_run",
            new_callable=AsyncMock, return_value=vr,
        ) as mock_persist,
        patch(
            "app.services.quality_service.compute_quality_tier",
            return_value="gold",
        ),
    ):
        mock_sc.get_config = AsyncMock(return_value=sys_config)
        from app.services.extraction_validation_service import run_validation

        await run_validation("ss-1", "user-1", model=requested_model)
        return mock_persist.call_args.kwargs, mock_vtc.call_args.args


@pytest.mark.asyncio
async def test_config_pinned_model_is_what_gets_persisted():
    # System config pins cfg-model; the caller passed no model. The engine
    # runs cfg-model, so the run must be labeled cfg-model — not the user's
    # default, which never executed.
    persist_kwargs, _ = await _run_validation_with(None, _sys_cfg("cfg-model"))
    assert persist_kwargs["model"] == "cfg-model"
    assert persist_kwargs["model_settings"]["source"] == "config"
    assert persist_kwargs["model_settings"]["requested_model"] is None


@pytest.mark.asyncio
async def test_requested_model_actually_runs_and_is_persisted():
    # The caller explicitly requested req-model while system config pins
    # cfg-model. The request must win — both in the persisted label and in
    # the config handed to the engine.
    persist_kwargs, vtc_args = await _run_validation_with(
        "req-model", _sys_cfg("cfg-model")
    )
    assert persist_kwargs["model"] == "req-model"
    assert persist_kwargs["model_settings"]["source"] == "requested"
    assert persist_kwargs["model_settings"]["requested_model"] == "req-model"
    # arg 4 of _validate_test_case is extraction_config_override — the forced
    # model must be inside it, or the engine would still run cfg-model.
    override = vtc_args[4]
    assert override["model"] == "req-model"
    assert override["two_pass"]["pass_1"]["model"] == "req-model"
    assert override["two_pass"]["pass_2"]["model"] == "req-model"


@pytest.mark.asyncio
async def test_no_pin_no_request_persists_user_default():
    persist_kwargs, _ = await _run_validation_with(None, _sys_cfg())
    assert persist_kwargs["model"] == "user-model"
    assert persist_kwargs["model_settings"]["source"] == "caller_default"
