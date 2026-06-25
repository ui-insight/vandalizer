"""Tests for app.services.extraction_judge — semantic-equality field judge.

The LLM call itself is mocked; we verify the prompt assembly, JSON parsing,
verdict normalisation, and the batch judge_test_case_extraction helper.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import extraction_judge
from app.services.extraction_judge import (
    _parse_verdict,
    _extract_json,
    judge_field_value,
    judge_test_case_extraction,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_extract_json_handles_plain_json():
    assert _extract_json('{"score": 0.9, "verdict": "PASS"}') == {"score": 0.9, "verdict": "PASS"}


def test_extract_json_strips_markdown_fences():
    fenced = '```json\n{"score": 0.5}\n```'
    assert _extract_json(fenced) == {"score": 0.5}


def test_extract_json_finds_inline_object_in_prose():
    prose = 'Here is my judgement: {"score": 0.3, "verdict": "FAIL"} done.'
    assert _extract_json(prose) == {"score": 0.3, "verdict": "FAIL"}


def test_extract_json_returns_empty_dict_on_unparseable():
    assert _extract_json("not json at all") == {}


def test_parse_verdict_clamps_score_and_normalises_verdict():
    out = _parse_verdict({"score": 1.5, "verdict": "pass", "reasoning": "ok"})
    assert out["score"] == 1.0
    assert out["verdict"] == "PASS"
    assert out["reasoning"] == "ok"


def test_parse_verdict_derives_verdict_from_score_when_missing():
    assert _parse_verdict({"score": 0.9})["verdict"] == "PASS"
    assert _parse_verdict({"score": 0.5})["verdict"] == "PARTIAL"
    assert _parse_verdict({"score": 0.1})["verdict"] == "FAIL"


def test_parse_verdict_truncates_reasoning():
    long = "x" * 1000
    assert len(_parse_verdict({"reasoning": long})["reasoning"]) == 500


def test_get_agent_reuses_within_same_loop():
    """Same running loop + same model -> one agent, built once."""
    import asyncio

    extraction_judge._agent_cache.clear()
    sentinel = object()
    with patch.object(extraction_judge, "get_agent_model", return_value=MagicMock()), \
         patch.object(extraction_judge, "Agent", return_value=sentinel) as agent_ctor:
        async def _twice():
            return extraction_judge._get_agent("m"), extraction_judge._get_agent("m")

        a, b = asyncio.run(_twice())
    extraction_judge._agent_cache.clear()
    assert a is b is sentinel
    assert agent_ctor.call_count == 1


def test_get_agent_rebuilds_across_loops():
    """A cached agent from a prior, now-closed loop is NOT reused on a new loop.

    Regression for zero-token "Connection error": the agent's httpx pool is bound
    to the loop that built it, so reusing it on a later Celery task's loop fails
    with "bound to a different event loop".
    """
    import asyncio

    extraction_judge._agent_cache.clear()
    with patch.object(extraction_judge, "get_agent_model", return_value=MagicMock()), \
         patch.object(extraction_judge, "Agent", side_effect=lambda *a, **k: object()) as agent_ctor:
        async def _build():
            return extraction_judge._get_agent("m")

        first = asyncio.run(_build())
        second = asyncio.run(_build())
    extraction_judge._agent_cache.clear()
    assert first is not second
    assert agent_ctor.call_count == 2


def test_parse_verdict_handles_garbage_input():
    # Non-dict input → defaults to score=0.0, verdict=FAIL
    out = _parse_verdict("garbage")
    assert out["score"] == 0.0
    assert out["verdict"] == "FAIL"


def test_parse_verdict_handles_list_wrapper():
    """Some models wrap the response in a list."""
    out = _parse_verdict([{"score": 0.8, "verdict": "PASS"}])
    assert out["score"] == 0.8
    assert out["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# judge_field_value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_field_value_returns_parsed_verdict():
    """LLM-judge path: free-text equivalence case the deterministic router
    can't resolve (paraphrase). The judge should be called and its verdict
    returned."""
    mock_run_result = MagicMock()
    mock_run_result.output = '{"score": 0.95, "verdict": "PASS", "reasoning": "paraphrase, same fact"}'
    mock_run_result.usage = MagicMock(return_value=MagicMock(total_tokens=42))

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_run_result)

    with (
        patch.object(extraction_judge, "_ensure_system_config_loaded", new=AsyncMock(return_value=None)),
        patch.object(extraction_judge, "_get_agent", return_value=mock_agent),
    ):
        out = await judge_field_value(
            field_name="Summary",
            expected="Quarterly revenue grew 12%",
            actual="Revenue increased by twelve percent this quarter",
            model_name="claude-haiku-4-5",
        )

    assert out["score"] == 0.95
    assert out["verdict"] == "PASS"
    assert out["tokens_used"] == 42
    assert out["comparator"] == "llm"
    # Prompt assembly: field name + expected + actual all surface to the model
    call_args = mock_agent.run.call_args[0][0]
    assert "Summary" in call_args
    assert "Quarterly revenue grew 12%" in call_args
    assert "Revenue increased by twelve percent" in call_args


@pytest.mark.asyncio
async def test_judge_field_value_deterministic_router_short_circuits_dates():
    """Same date in two formats → deterministic comparator resolves; LLM
    isn't touched. Guards the optimization that motivated the router."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock()  # would raise if called via assert below

    with (
        patch.object(extraction_judge, "_ensure_system_config_loaded", new=AsyncMock(return_value=None)),
        patch.object(extraction_judge, "_get_agent", return_value=mock_agent),
    ):
        out = await judge_field_value(
            field_name="Award Date",
            expected="2026-01-05",
            actual="Jan 5, 2026",
            model_name="claude-haiku-4-5",
        )

    assert out["score"] == 1.0
    assert out["verdict"] == "PASS"
    assert out["comparator"] == "deterministic"
    mock_agent.run.assert_not_called()


@pytest.mark.asyncio
async def test_judge_field_value_deterministic_router_fails_missing_actual():
    """Expected has a value, actual is empty → deterministic FAIL (no LLM).
    The 'not found' sentinel detection lives in extraction_validation_service."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock()

    with (
        patch.object(extraction_judge, "_ensure_system_config_loaded", new=AsyncMock(return_value=None)),
        patch.object(extraction_judge, "_get_agent", return_value=mock_agent),
    ):
        out = await judge_field_value(
            field_name="PI Name",
            expected="Dr. Smith",
            actual="",
            model_name="claude-haiku-4-5",
        )

    assert out["score"] == 0.0
    assert out["verdict"] == "FAIL"
    assert out["comparator"] == "deterministic"
    mock_agent.run.assert_not_called()


@pytest.mark.asyncio
async def test_judge_field_value_swallows_exceptions_returns_fail():
    """Judge failure shouldn't crash the surrounding optimizer trial loop."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("network down"))

    with (
        patch.object(extraction_judge, "_ensure_system_config_loaded", new=AsyncMock(return_value=None)),
        patch.object(extraction_judge, "_get_agent", return_value=mock_agent),
    ):
        out = await judge_field_value(
            field_name="X", expected="y", actual="z", model_name="m",
        )

    assert out["verdict"] == "FAIL"
    assert out["score"] == 0.0
    assert "judge error" in out["reasoning"]


# ---------------------------------------------------------------------------
# judge_test_case_extraction (batch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_test_case_extraction_aggregates_per_field():
    """Batch helper judges each expected field and averages scores."""
    # Set up judge_field_value to return different scores per field
    field_scores = {
        "PI Name": 1.0,
        "Award Date": 0.5,
        "Amount": 0.0,
    }

    async def fake_judge(field_name, expected, actual, model_name, field_metadata=None):
        return {
            "score": field_scores[field_name],
            "verdict": "PASS" if field_scores[field_name] >= 0.7 else "FAIL",
            "reasoning": f"score for {field_name}",
            "tokens_used": 5,
        }

    with patch.object(extraction_judge, "judge_field_value", new=AsyncMock(side_effect=fake_judge)):
        out = await judge_test_case_extraction(
            keys=["PI Name", "Award Date", "Amount"],
            expected={"PI Name": "Smith", "Award Date": "2026-01-05", "Amount": "$1000"},
            actual={"PI Name": "Dr. Smith", "Award Date": "Jan 5", "Amount": "1500"},
            model_name="claude-haiku-4-5",
        )

    assert out["num_fields_judged"] == 3
    # avg = (1.0 + 0.5 + 0.0) / 3
    assert out["avg_score"] == pytest.approx(0.5, abs=1e-4)
    assert out["tokens_used"] == 15
    assert len(out["fields"]) == 3


@pytest.mark.asyncio
async def test_judge_test_case_extraction_skips_fields_without_expected():
    """Fields with no expected value aren't judged (can't compare to nothing)."""
    async def fake_judge(field_name, expected, actual, model_name, field_metadata=None):
        return {"score": 0.8, "verdict": "PASS", "reasoning": "", "tokens_used": 5}

    with patch.object(extraction_judge, "judge_field_value", new=AsyncMock(side_effect=fake_judge)):
        out = await judge_test_case_extraction(
            keys=["PI Name", "Optional Field"],
            expected={"PI Name": "Smith"},  # Optional Field has no expected value
            actual={"PI Name": "Smith", "Optional Field": "irrelevant"},
            model_name="m",
        )

    assert out["num_fields_judged"] == 1
    assert out["avg_score"] == 0.8
    # Skipped field is recorded so callers can see the skip
    skipped_fields = [f for f in out["fields"] if f.get("skipped")]
    assert len(skipped_fields) == 1
    assert skipped_fields[0]["field"] == "Optional Field"


@pytest.mark.asyncio
async def test_judge_test_case_extraction_empty_keys():
    """No keys = no judgement, no crash."""
    out = await judge_test_case_extraction(
        keys=[],
        expected={},
        actual={},
        model_name="m",
    )
    assert out["num_fields_judged"] == 0
    assert out["avg_score"] == 0.0
    assert out["fields"] == []
