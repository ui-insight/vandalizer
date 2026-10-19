"""The KB judge scores against the expected answer, and flags conflicts apart.

Support ticket (NSF PAPPG 24-1 validation, 2026-10-14): when a generated
answer contradicted the expected answer but agreed with a retrieved excerpt,
the judge was told to return WARN and label it an "expected-answer conflict".
It gave such answers 0.6, so "Yes" against an expected "No" (Q007) and "No"
against an expected "Yes" (Q004) counted as partly correct in the reported
accuracy. A conflict is now a review flag that carries no credit, and the
run reports how many there are and what the accuracy is without them.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_validation_service as svc

# The shape the judge returned for Q004 in the reporter's export, plus the
# fields the new prompt asks for.
Q004_CONFLICT = {
    "score": 0.6,
    "verdict": "WARN",
    "confidence": 0.9,
    "reasoning": "expected-answer conflict: the answer says 9-point captions are not allowed, "
                 "which the retrieved font-size requirements support.",
    "missing_facts": [],
    "hallucinated_facts": [],
    "contradicted_facts": ["A proposer may not use 9-point text for a figure caption"],
    "expected_conflict": True,
    "conflict_evidence": "must be 10 points or larger ... all uploaded sections of a proposal",
}


def test_prompt_no_longer_trades_a_contradiction_for_partial_credit():
    prompt = svc.KB_JUDGE_SYSTEM_PROMPT
    assert "Return WARN" not in prompt
    assert "The expected answer is the answer key" in prompt
    assert "Retrieved support never earns credit" in prompt
    assert '"expected_conflict"' in prompt and '"contradicted_facts"' in prompt
    # Q001: the expected answers end with grading instructions, which the
    # judge listed as "missing facts".
    assert "never list them in missing_facts" in prompt
    # Q014: a right headline hid a wrong detail.
    assert "Grade the complete answer" in prompt


def test_a_conflict_scores_what_the_rubric_gives_a_contradiction():
    v = svc._parse_kb_verdict(dict(Q004_CONFLICT), rubric="factoid")

    assert v["expected_conflict"] is True
    assert (v["score"], v["verdict"]) == (0.0, "FAIL")
    assert v["contradicted_facts"] == Q004_CONFLICT["contradicted_facts"]
    assert v["conflict_evidence"].startswith("must be 10 points")


def test_a_summary_with_one_conflicting_point_keeps_at_most_half_credit():
    raw = {**Q004_CONFLICT, "score": 0.8, "verdict": "PASS"}
    v = svc._parse_kb_verdict(raw, rubric="summarization")

    assert (v["score"], v["verdict"]) == (0.5, "WARN")
    assert v["expected_conflict"] is True


def test_a_multi_hop_answer_with_one_conflicting_step_keeps_half_credit():
    """The multi-hop rubric gives 0.5 when the final answer is right and one
    intermediate fact is wrong; a conflict on that step must not zero it."""
    raw = {**Q004_CONFLICT, "score": 0.5, "verdict": "WARN"}
    v = svc._parse_kb_verdict(raw, rubric="multi_hop")

    assert (v["score"], v["verdict"]) == (0.5, "WARN")
    assert v["expected_conflict"] is True


def test_a_lower_score_than_the_ceiling_is_left_alone():
    raw = {**Q004_CONFLICT, "score": 0.2, "verdict": "FAIL"}
    assert svc._parse_kb_verdict(raw, rubric="summarization")["score"] == 0.2


@pytest.mark.parametrize("raw, context_given", [
    # The no-KB baseline has no retrieved context, so nothing can support it.
    (Q004_CONFLICT, False),
    # A conflict with nothing named as contradicted is not one.
    ({**Q004_CONFLICT, "contradicted_facts": []}, True),
    # Only an explicit true counts.
    ({**Q004_CONFLICT, "expected_conflict": "yes"}, True),
])
def test_conflict_needs_context_a_contradicted_fact_and_an_explicit_flag(raw, context_given):
    v = svc._parse_kb_verdict(dict(raw), rubric="factoid", context_given=context_given)

    assert v["expected_conflict"] is False
    assert v["conflict_evidence"] == ""
    # Not a conflict, so the parser does not touch the judge's score.
    assert v["score"] == raw["score"]


def test_a_plain_contradiction_is_reported_without_a_conflict_flag():
    raw = {
        "score": 0.5, "verdict": "WARN", "confidence": 0.9, "reasoning": "...",
        "missing_facts": ["Maximum length: one extension of up to 12 months"],
        "contradicted_facts": ["The policy does not specify a maximum length"],
        "expected_conflict": False,
    }
    v = svc._parse_kb_verdict(raw, rubric="summarization")

    assert v["contradicted_facts"] == ["The policy does not specify a maximum length"]
    assert v["expected_conflict"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("context, expected", [("Font: 10 points or larger.", True), (None, False)])
async def test_judge_answer_flags_conflicts_only_when_it_saw_context(context, expected):
    agent = MagicMock()
    agent.run = AsyncMock(return_value=SimpleNamespace(output=json.dumps(Q004_CONFLICT), usage=lambda: None))
    with patch.object(svc, "_get_or_build_agent", return_value=agent), \
         patch.object(svc, "_usage_tokens", return_value=0):
        v = await svc._judge_answer(
            query="May a proposer use 9-point text for a figure caption?",
            expected_answer="Yes. Figure captions are an exception.",
            actual_answer="No.",
            model_name="judge",
            retrieved_context=context,
            category="factual",
        )

    assert v["expected_conflict"] is expected
    assert v["score"] == (0.0 if expected else 0.6)


def _tq(uuid: str):
    tq = MagicMock()
    tq.uuid = uuid
    tq.query = f"question {uuid}"
    tq.expected_answer = "expected"
    tq.category = "factual"
    tq.save = AsyncMock()
    return tq


@pytest.mark.asyncio
async def test_run_reports_conflicts_and_the_accuracy_without_them():
    verdicts = {
        "question q1": {"score": 1.0, "verdict": "PASS"},
        "question q2": {"score": 0.5, "verdict": "WARN"},
        "question q3": {"score": 0.0, "verdict": "FAIL", "expected_conflict": True},
        "question q4": {"score": 0.0, "verdict": "FAIL", "expected_conflict": True},
    }

    async def fake_kb_answer(kb_uuid, query, model_name, k=8, config=None):
        return ("answer", [{"content": "excerpt", "metadata": {"source_name": "Doc"}}])

    async def fake_judge(*, query, **_):
        base = {"confidence": 0.9, "reasoning": "", "evidence": "",
                "missing_facts": [], "hallucinated_facts": []}
        return {**base, **verdicts[query]}

    with patch.object(svc, "_generate_kb_answer", side_effect=fake_kb_answer), \
         patch.object(svc, "_judge_answer", side_effect=fake_judge):
        out = await svc.judge_test_queries(
            "kb-1", [_tq("q1"), _tq("q2"), _tq("q3"), _tq("q4")], "model", mode="judge",
        )

    # Conflicts stay in the accuracy at their score …
    assert out["avg_judge_score"] == 0.375
    # … and the run says how many there are and what leaving them out gives.
    assert out["num_expected_conflicts"] == 2
    assert out["avg_judge_score_excluding_conflicts"] == 0.75


@pytest.mark.asyncio
async def test_a_run_with_no_conflicts_reports_the_same_accuracy_both_ways():
    async def fake_kb_answer(kb_uuid, query, model_name, k=8, config=None):
        return ("answer", [])

    async def fake_judge(**_):
        return {"score": 0.8, "verdict": "PASS", "confidence": 0.9, "reasoning": "",
                "evidence": "", "missing_facts": [], "hallucinated_facts": []}

    with patch.object(svc, "_generate_kb_answer", side_effect=fake_kb_answer), \
         patch.object(svc, "_judge_answer", side_effect=fake_judge):
        out = await svc.judge_test_queries("kb-1", [_tq("q1")], "model", mode="judge")

    assert out["num_expected_conflicts"] == 0
    assert out["avg_judge_score_excluding_conflicts"] == out["avg_judge_score"] == 0.8
