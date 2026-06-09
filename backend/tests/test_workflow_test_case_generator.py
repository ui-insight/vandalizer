"""Tests for the workflow test-case generator (Phase A).

The generator proposes past WorkflowResults as candidate expected_outputs so
the optimizer doesn't hard-error with 'No test inputs available' for any
workflow whose user hasn't manually saved one. These tests cover:

- the filtering pipeline (empty / error-shaped / too-short / already-saved)
- LLM scoring vs. deterministic fallback
- JSON extraction tolerance for markdown fences
- accept_proposals persistence semantics
- synthesize_seed_input happy + sad paths
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_test_case_generator as tcg
from app.services.workflow_test_case_generator import (
    _extract_json,
    _fallback_proposal,
    _parse_proposals,
    accept_proposals,
    propose_from_history,
    synthesize_seed_input,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_extract_json_parses_clean_json():
    out = _extract_json('{"proposals": [{"session_id": "abc"}]}')
    assert out == {"proposals": [{"session_id": "abc"}]}


def test_extract_json_strips_markdown_fence():
    out = _extract_json('```json\n{"label": "hi"}\n```')
    assert out == {"label": "hi"}


def test_extract_json_strips_bare_fence():
    out = _extract_json('```\n{"x": 1}\n```')
    assert out == {"x": 1}


def test_extract_json_locates_object_in_surrounding_text():
    out = _extract_json('Here is the JSON: {"y": 2} done')
    assert out == {"y": 2}


def test_extract_json_returns_none_on_failure():
    assert _extract_json("not json at all") is None
    assert _extract_json("") is None


def test_fallback_proposal_uses_deterministic_label():
    cand = {
        "session_id": "abcdef1234567890",
        "output_preview": "Some output",
        "output_length": 11,
        "created_at": None,
    }
    p = _fallback_proposal(cand)
    assert p["session_id"] == "abcdef1234567890"
    assert "abcdef12" in p["suggested_label"]
    assert p["confidence"] == 0.5
    assert "fallback" in p["why"].lower() or "deterministic" in p["why"].lower()


def test_parse_proposals_drops_hallucinated_session_ids():
    """LLM that invents a session_id for a candidate we didn't supply should be filtered."""
    candidates = [{"session_id": "real1", "output_preview": "x", "output_length": 1}]
    parsed = {
        "proposals": [
            {"session_id": "real1", "label": "Good", "confidence": 0.9, "why": "ok"},
            {"session_id": "hallucinated", "label": "Fake", "confidence": 0.8, "why": "x"},
        ]
    }
    out = _parse_proposals(parsed, candidates)
    assert len(out) == 1
    assert out[0]["session_id"] == "real1"
    assert out[0]["suggested_label"] == "Good"
    assert out[0]["confidence"] == 0.9


def test_parse_proposals_clamps_confidence():
    candidates = [{"session_id": "s1", "output_preview": "x", "output_length": 1}]
    parsed = {"proposals": [{"session_id": "s1", "label": "L", "confidence": 5.0, "why": ""}]}
    out = _parse_proposals(parsed, candidates)
    assert out[0]["confidence"] == 1.0


def test_parse_proposals_handles_string_confidence():
    """LLMs sometimes return numbers as strings — coerce, don't crash."""
    candidates = [{"session_id": "s1", "output_preview": "x", "output_length": 1}]
    parsed = {"proposals": [{"session_id": "s1", "label": "L", "confidence": "0.7", "why": ""}]}
    out = _parse_proposals(parsed, candidates)
    assert out[0]["confidence"] == 0.7


def test_parse_proposals_fills_in_unscored_candidates_with_fallback():
    """If the LLM only scores 1 of 3 candidates, the other 2 still appear with fallback metadata."""
    candidates = [
        {"session_id": "s1", "output_preview": "a", "output_length": 1},
        {"session_id": "s2", "output_preview": "b", "output_length": 1},
        {"session_id": "s3", "output_preview": "c", "output_length": 1},
    ]
    parsed = {"proposals": [{"session_id": "s2", "label": "Only one scored", "confidence": 0.9, "why": "x"}]}
    out = _parse_proposals(parsed, candidates)
    assert len(out) == 3
    by_session = {p["session_id"]: p for p in out}
    assert by_session["s2"]["confidence"] == 0.9
    assert by_session["s1"]["confidence"] == 0.5
    assert by_session["s3"]["confidence"] == 0.5


# ---------------------------------------------------------------------------
# propose_from_history filtering
# ---------------------------------------------------------------------------


def _make_workflow(session_ids_saved: list[str] | None = None) -> MagicMock:
    wf = MagicMock()
    wf.id = "wfid"
    wf.name = "Test workflow"
    wf.description = "Do something useful."
    wf.validation_inputs = [
        {"type": "expected_output", "session_id": sid, "id": f"e_{sid}"}
        for sid in (session_ids_saved or [])
    ]
    return wf


def _make_result(session_id: str, output: str | None = "Real output 12345" * 5):
    wr = MagicMock()
    wr.session_id = session_id
    wr.start_time = None
    wr.final_output = {"output": output} if output is not None else None
    wr.steps_output = {}
    return wr


@pytest.mark.asyncio
async def test_propose_skips_already_saved():
    wf = _make_workflow(session_ids_saved=["s1"])
    user = MagicMock(); user.user_id = "u"

    # Build the find().sort().limit().to_list() chain
    chain = MagicMock()
    chain.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[_make_result("s1"), _make_result("s2")]
    )

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find", return_value=chain),
        patch("app.services.workflow_test_case_generator._score_candidates_with_llm",
              new=AsyncMock(return_value=[])),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await propose_from_history("wfid", user)

    assert result["skipped"]["duplicates"] == 1
    assert result["synthesized"] is False


@pytest.mark.asyncio
async def test_propose_filters_empty_and_error_outputs():
    wf = _make_workflow()
    user = MagicMock(); user.user_id = "u"

    chain = MagicMock()
    chain.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[
            _make_result("s1", output=""),
            _make_result("s2", output="Error: rate limit exceeded"),
            _make_result("s3", output="This is a long, real output that should pass filtering" * 3),
        ]
    )

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find", return_value=chain),
        patch("app.services.workflow_test_case_generator._score_candidates_with_llm",
              new=AsyncMock(return_value=[
                  {"session_id": "s3", "suggested_label": "L", "output_preview": "p",
                   "output_length": 30, "confidence": 0.8, "why": "", "already_saved": False,
                   "created_at": None},
              ])),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await propose_from_history("wfid", user)

    assert result["skipped"]["empty_or_error"] == 2
    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["session_id"] == "s3"


@pytest.mark.asyncio
async def test_propose_filters_too_short_outputs():
    wf = _make_workflow()
    user = MagicMock(); user.user_id = "u"

    chain = MagicMock()
    chain.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[_make_result("s1", output="short")]
    )

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find", return_value=chain),
        patch("app.services.workflow_test_case_generator._score_candidates_with_llm",
              new=AsyncMock(return_value=[])),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await propose_from_history("wfid", user)

    assert result["skipped"]["too_short"] == 1
    assert len(result["proposals"]) == 0


@pytest.mark.asyncio
async def test_propose_returns_note_when_no_usable_candidates():
    wf = _make_workflow()
    user = MagicMock(); user.user_id = "u"

    chain = MagicMock()
    chain.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find", return_value=chain),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await propose_from_history("wfid", user)

    assert result["proposals"] == []
    assert "note" in result


@pytest.mark.asyncio
async def test_propose_falls_back_when_llm_fails():
    """LLM error doesn't abort the whole proposal — fall back to deterministic labels."""
    wf = _make_workflow()
    user = MagicMock(); user.user_id = "u"

    long_output = "Real output text " * 10
    chain = MagicMock()
    chain.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[_make_result("session1234abc", output=long_output)]
    )

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find", return_value=chain),
        patch("app.services.workflow_test_case_generator._run_llm",
              new=AsyncMock(side_effect=RuntimeError("model down"))),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await propose_from_history("wfid", user)

    assert len(result["proposals"]) == 1
    # Fallback labels include the session prefix
    assert "session1" in result["proposals"][0]["suggested_label"]
    assert result["proposals"][0]["confidence"] == 0.5


@pytest.mark.asyncio
async def test_propose_raises_when_workflow_not_found():
    user = MagicMock(); user.user_id = "u"
    with patch("app.services.workflow_service.get_authorized_workflow",
               new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="not found"):
            await propose_from_history("missing", user)


# ---------------------------------------------------------------------------
# accept_proposals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_persists_each_session():
    wf = _make_workflow()
    wf.save = AsyncMock()
    user = MagicMock(); user.user_id = "u"

    long_output = "Real output text " * 10

    async def fake_find_one(*args, **kwargs):
        return _make_result("s1", output=long_output)

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find_one",
              new=AsyncMock(side_effect=lambda *a, **k: _make_result("s1", output=long_output))),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await accept_proposals("wfid", user, ["s1"], label_overrides={"s1": "My label"})

    assert len(result["accepted"]) == 1
    assert result["accepted"][0]["label"] == "My label"
    assert result["accepted"][0]["type"] == "expected_output"
    assert result["accepted"][0]["source"] == "test_case_generator"
    wf.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_accept_skips_already_saved():
    wf = _make_workflow(session_ids_saved=["s1"])
    wf.save = AsyncMock()
    user = MagicMock(); user.user_id = "u"

    with patch("app.services.workflow_service.get_authorized_workflow",
               new=AsyncMock(return_value=wf)):
        result = await accept_proposals("wfid", user, ["s1"])

    assert len(result["accepted"]) == 0
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["reason"] == "already saved"
    wf.save.assert_not_called()


@pytest.mark.asyncio
async def test_accept_skips_missing_result():
    wf = _make_workflow()
    wf.save = AsyncMock()
    user = MagicMock(); user.user_id = "u"

    with (
        patch("app.services.workflow_test_case_generator.WorkflowResult.find_one",
              new=AsyncMock(return_value=None)),
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
    ):
        result = await accept_proposals("wfid", user, ["missing"])

    assert len(result["accepted"]) == 0
    assert result["skipped"][0]["reason"] == "result not found"


# ---------------------------------------------------------------------------
# synthesize_seed_input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_returns_label_and_text():
    user = MagicMock(); user.user_id = "u"

    with (
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=_make_workflow())),
        patch("app.services.workflow_service.get_workflow",
              new=AsyncMock(return_value={"name": "X", "description": "Y", "steps": []})),
        patch("app.services.workflow_test_case_generator._run_llm",
              new=AsyncMock(return_value='{"label": "Sample", "text": "Some doc text"}')),
    ):
        out = await synthesize_seed_input("wfid", user)

    assert out["label"] == "Sample"
    assert out["text"] == "Some doc text"
    assert out["synthesized"] is True


@pytest.mark.asyncio
async def test_synthesize_raises_when_no_text():
    user = MagicMock(); user.user_id = "u"

    with (
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=_make_workflow())),
        patch("app.services.workflow_service.get_workflow",
              new=AsyncMock(return_value={"name": "X", "description": "Y", "steps": []})),
        patch("app.services.workflow_test_case_generator._run_llm",
              new=AsyncMock(return_value='{"label": "X", "text": ""}')),
    ):
        with pytest.raises(ValueError, match="no content"):
            await synthesize_seed_input("wfid", user)
