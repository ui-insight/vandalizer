"""Tests for the no-workflow baseline measurement (Phase 2A).

The baseline runs a single-shot LLM call as a counterfactual to a multi-step
workflow, then scores the single-shot output against the same validation
plan. The score tells the user whether the workflow is earning its complexity.

These tests mock the LLM and the check evaluator; we verify the orchestration:
when the helper runs vs. skips, how it computes the score, what it returns.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_service
from app.services.workflow_service import (
    _build_baseline_instructions,
    _extract_source_text_from_steps,
    _measure_no_workflow_baseline,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_build_baseline_instructions_combines_name_description_steps():
    out = _build_baseline_instructions({
        "name": "Grant intake",
        "description": "Process incoming grant applications.",
        "steps": [
            {"name": "Classify", "description": "Categorize the grant type."},
            {"name": "Extract", "description": "Pull key fields."},
        ],
    })
    assert "Task: Grant intake" in out
    assert "Process incoming grant applications." in out
    assert "Classify" in out
    assert "Extract" in out


def test_build_baseline_instructions_returns_empty_when_wf_data_is_none():
    assert _build_baseline_instructions(None) == ""


def test_build_baseline_instructions_handles_steps_without_descriptions():
    """Step name alone is enough; missing description shouldn't blank the bullet."""
    out = _build_baseline_instructions({
        "name": "Test",
        "steps": [{"name": "Step1"}, {"name": "Step2", "description": "Do something"}],
    })
    assert "Step1" in out
    assert "Step2" in out


def test_extract_source_text_returns_empty_for_no_document_step():
    """When the workflow doesn't start with a Document/AddDocument step, we
    can't reuse the input — return empty so the caller falls back to skipping."""
    assert _extract_source_text_from_steps({"OtherStep": "some output"}) == ""
    assert _extract_source_text_from_steps(None) == ""
    assert _extract_source_text_from_steps({}) == ""


def test_extract_source_text_finds_document_step_by_name():
    out = _extract_source_text_from_steps({
        "Document": {"step_name": "Document", "output": "The document text here."},
    })
    assert out == "The document text here."


def test_extract_source_text_handles_string_step_data():
    """Some steps store output as a bare string; the extractor should handle that."""
    out = _extract_source_text_from_steps({"document": "Plain string content."})
    assert out == "Plain string content."


# ---------------------------------------------------------------------------
# _measure_no_workflow_baseline
# ---------------------------------------------------------------------------


def _make_wf_data(plan=None) -> dict:
    return {
        "name": "Process invoice",
        "description": "Extract the total and vendor from an invoice.",
        "validation_plan": plan or [
            {"id": "c1", "name": "Has total", "description": "Output contains a total amount.", "category": "content"},
        ],
        "steps": [],
    }


def _make_last_result(source_text: str = "Invoice text here.") -> MagicMock:
    """WorkflowResult mock with the source text in steps_output."""
    wr = MagicMock()
    wr.steps_output = {
        "Document": {"step_name": "Document", "output": source_text},
    }
    return wr


@pytest.mark.asyncio
async def test_measure_baseline_returns_none_without_validation_plan():
    """No plan = nothing to score against = skip."""
    out = await _measure_no_workflow_baseline(
        wf_data={"name": "x", "description": "y", "validation_plan": []},
        last_result=_make_last_result(),
    )
    assert out is None


@pytest.mark.asyncio
async def test_measure_baseline_returns_none_without_source_text():
    """No document text in steps_output = no input to feed = skip."""
    wr = MagicMock(); wr.steps_output = {"OtherStep": "irrelevant"}
    out = await _measure_no_workflow_baseline(
        wf_data=_make_wf_data(),
        last_result=wr,
    )
    assert out is None


@pytest.mark.asyncio
async def test_measure_baseline_returns_none_without_instructions():
    """Empty workflow name + description + no steps = no instructions = skip."""
    out = await _measure_no_workflow_baseline(
        wf_data={"name": "", "description": "", "validation_plan": [{"id": "c1", "name": "x"}], "steps": []},
        last_result=_make_last_result(),
    )
    assert out is None


@pytest.mark.asyncio
async def test_measure_baseline_returns_score_from_check_verdicts():
    """Happy path: LLM returns text, checks evaluate to PASS, score is high."""
    plan = [
        {"id": "c1", "name": "Has total", "description": "x", "category": "content"},
        {"id": "c2", "name": "Has vendor", "description": "x", "category": "content"},
    ]
    wf = _make_wf_data(plan=plan)
    wr = _make_last_result()

    # Mock the LLM agent
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="Total: $1000, Vendor: Acme"))

    # Mock check evaluation: both PASS
    fake_checks = [
        {"check_id": "c1", "status": "PASS", "consistency": 1.0},
        {"check_id": "c2", "status": "PASS", "consistency": 1.0},
    ]

    with (
        patch.object(workflow_service, "_evaluate_checks_against_output", new=AsyncMock(return_value=fake_checks)),
        patch("app.services.workflow_validator._resolve_model_name", return_value="claude-haiku"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=wr)

    assert out is not None
    # Both checks PASS, equal weights → weighted_pass_rate = 1.0 → score = 100.0
    assert out["score"] == 100.0
    assert out["weighted_pass_rate"] == 1.0
    assert out["output"] == "Total: $1000, Vendor: Acme"
    assert len(out["checks"]) == 2


@pytest.mark.asyncio
async def test_measure_baseline_blends_partial_pass_and_fail():
    """PASS + FAIL on equal-weight checks → 50% weighted pass rate."""
    plan = [
        {"id": "c1", "name": "x", "category": "content"},
        {"id": "c2", "name": "y", "category": "content"},
    ]
    wf = _make_wf_data(plan=plan)

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="Some output"))

    fake_checks = [
        {"check_id": "c1", "status": "PASS"},
        {"check_id": "c2", "status": "FAIL"},
    ]

    with (
        patch.object(workflow_service, "_evaluate_checks_against_output", new=AsyncMock(return_value=fake_checks)),
        patch("app.services.workflow_validator._resolve_model_name", return_value="m"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=_make_last_result())

    assert out is not None
    assert out["weighted_pass_rate"] == 0.5
    assert out["score"] == 50.0


@pytest.mark.asyncio
async def test_measure_baseline_warn_status_counts_as_half():
    """WARN status → 0.5 in the weighted score; matches the workflow scorer."""
    plan = [{"id": "c1", "name": "x", "category": "content"}]
    wf = _make_wf_data(plan=plan)

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="meh"))

    with (
        patch.object(workflow_service, "_evaluate_checks_against_output", new=AsyncMock(return_value=[
            {"check_id": "c1", "status": "WARN"},
        ])),
        patch("app.services.workflow_validator._resolve_model_name", return_value="m"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=_make_last_result())

    assert out["weighted_pass_rate"] == 0.5
    assert out["score"] == 50.0


@pytest.mark.asyncio
async def test_measure_baseline_skip_status_excluded_from_score():
    """SKIP doesn't pull the weighted score down — it's just absent from the
    denominator (matches the workflow scorer's behavior)."""
    plan = [
        {"id": "c1", "name": "x", "category": "content"},
        {"id": "c2", "name": "y", "category": "content"},
    ]
    wf = _make_wf_data(plan=plan)

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="text"))

    with (
        patch.object(workflow_service, "_evaluate_checks_against_output", new=AsyncMock(return_value=[
            {"check_id": "c1", "status": "PASS"},
            {"check_id": "c2", "status": "SKIP"},
        ])),
        patch("app.services.workflow_validator._resolve_model_name", return_value="m"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=_make_last_result())

    # Only c1 (PASS) evaluated → 1.0 / 1.0 = 1.0
    assert out["weighted_pass_rate"] == 1.0


@pytest.mark.asyncio
async def test_measure_baseline_returns_none_when_llm_errors():
    """LLM call failure surfaces as None, not an exception — callers can fall
    through to a result without the baseline."""
    wf = _make_wf_data()

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("model down"))

    with (
        patch("app.services.workflow_validator._resolve_model_name", return_value="m"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=_make_last_result())

    assert out is None


@pytest.mark.asyncio
async def test_measure_baseline_returns_none_when_llm_returns_empty():
    """Empty LLM output = no signal to evaluate = skip."""
    wf = _make_wf_data()

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="   "))

    with (
        patch("app.services.workflow_validator._resolve_model_name", return_value="m"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=_make_last_result())

    assert out is None


@pytest.mark.asyncio
async def test_measure_baseline_truncates_long_output():
    """Long LLM responses are truncated at 5000 chars before persisting — the
    full text isn't needed downstream, and bloating the run doc hurts polling."""
    wf = _make_wf_data()
    long_text = "x" * 10_000

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output=long_text))

    with (
        patch.object(workflow_service, "_evaluate_checks_against_output", new=AsyncMock(return_value=[
            {"check_id": "c1", "status": "PASS"},
        ])),
        patch("app.services.workflow_validator._resolve_model_name", return_value="m"),
        patch("app.services.llm_service.get_agent_model", return_value=MagicMock()),
        patch("pydantic_ai.Agent", return_value=mock_agent),
    ):
        out = await _measure_no_workflow_baseline(wf_data=wf, last_result=_make_last_result())

    assert len(out["output"]) == 5000
