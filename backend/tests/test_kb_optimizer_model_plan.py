"""KB tuning: who judges, who answers today, who competes, and who won.

The runner's chat model used to be all three (judge, current answerer, and
the family-exclusion pivot), so switching the chat picker flipped the
"Best configuration" on the same KB. These pin the separation.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_optimizer
from app.services.kb_optimizer import (
    DEFAULT_TRIAL_TOKEN_ESTIMATE,
    KBOptimizer,
    ModelPlanError,
    resolve_model_plan,
)
from app.services.kb_validation_service import RAGConfig

MODELS = ["gpt-oss-120b", "glm-4.5", "claude-3-haiku", "claude-3-opus"]


def _plan_patches(stack, *, user_model, grader="claude-3-opus", override_model=None):
    sys_cfg = MagicMock()
    sys_cfg.available_models = [{"name": m} for m in MODELS]
    stack.enter_context(patch.object(
        kb_optimizer.SystemConfig, "get_config", new=AsyncMock(return_value=sys_cfg),
    ))
    stack.enter_context(patch(
        "app.services.config_service.get_validation_judge_model",
        new=AsyncMock(return_value=(grader, None)),
    ))
    stack.enter_context(patch(
        "app.services.config_service.get_user_model_name",
        new=AsyncMock(return_value=user_model),
    ))

    async def by_name(name):
        return {"name": name} if name in MODELS else None

    stack.enter_context(patch(
        "app.services.config_service.get_llm_model_by_name", new=by_name,
    ))
    stack.enter_context(patch.object(
        kb_optimizer.kb_validation_service, "_resolve_rag_config",
        new=AsyncMock(return_value=RAGConfig(model=override_model)),
    ))


@pytest.mark.asyncio
async def test_default_plan_judges_with_the_grader_not_the_chat_model():
    plans = []
    for chat_model in ("gpt-oss-120b", "glm-4.5"):
        with ExitStack() as stack:
            _plan_patches(stack, user_model=chat_model)
            plans.append(await resolve_model_plan("kb-1", "u1"))

    for plan, chat_model in zip(plans, ("gpt-oss-120b", "glm-4.5")):
        assert plan["judge_model"] == "claude-3-opus"
        assert plan["judge_source"] == "validation_grader"
        assert plan["current_model"] == chat_model
        # Switching the chat model changes who answers today, never who
        # judges or who competes.
        assert plan["challenger_models"] == ["gpt-oss-120b", "glm-4.5"]

    by_name = {m["name"]: m for m in plans[0]["models"]}
    assert by_name["claude-3-opus"]["ineligible_reason"] == "It is the judge."
    assert not by_name["claude-3-haiku"]["eligible"]
    assert "Same family as the judge (claude)" in by_name["claude-3-haiku"]["ineligible_reason"]
    assert by_name["gpt-oss-120b"]["is_current"] is True


@pytest.mark.asyncio
async def test_current_model_is_the_applied_override_when_there_is_one():
    with ExitStack() as stack:
        _plan_patches(stack, user_model="gpt-oss-120b", override_model="glm-4.5")
        plan = await resolve_model_plan("kb-1", "u1")
    assert plan["current_model"] == "glm-4.5"


@pytest.mark.asyncio
async def test_selected_judge_and_narrowed_challengers():
    with ExitStack() as stack:
        _plan_patches(stack, user_model="gpt-oss-120b")
        plan = await resolve_model_plan(
            "kb-1", "u1", judge_model="glm-4.5", challenger_models=["claude-3-haiku"],
        )
    assert plan["judge_model"] == "glm-4.5"
    assert plan["judge_source"] == "selected"
    assert plan["challenger_models"] == ["claude-3-haiku"]


@pytest.mark.asyncio
async def test_ineligible_challenger_is_rejected_with_its_reason():
    with ExitStack() as stack:
        _plan_patches(stack, user_model="gpt-oss-120b")
        with pytest.raises(ModelPlanError, match="Same family as the judge"):
            await resolve_model_plan(
                "kb-1", "u1", challenger_models=["gpt-oss-120b", "claude-3-haiku"],
            )


@pytest.mark.asyncio
async def test_unknown_judge_is_rejected():
    with ExitStack() as stack:
        _plan_patches(stack, user_model="gpt-oss-120b")
        with pytest.raises(ModelPlanError, match="isn't configured"):
            await resolve_model_plan("kb-1", "u1", judge_model="nope")


# ---------------------------------------------------------------------------
# run(): the plan is executed, and the winner is stated honestly
# ---------------------------------------------------------------------------


def _run_doc(options):
    rd = MagicMock()
    rd.uuid = "opt-1"
    rd.kb_uuid = "kb-1"
    rd.user_id = "u1"
    rd.status = "queued"
    rd.tokens_used = 0
    rd.cancel_requested = False
    rd.trials = []
    rd.options = options
    rd.save = AsyncMock()
    return rd


async def _run(default_score, trial_score, *, apply_on_finish=False):
    """One query, grader claude-3-opus, chat model glm-4.5, 2 trials."""
    run_doc = _run_doc({"apply_on_finish": apply_on_finish})
    fake_kb = MagicMock(uuid="kb-1", title="KB")
    tq = MagicMock(uuid="tq-1", query="Q?", expected_answer="A.")
    calls: list[dict] = []

    async def fake_judge(kb_uuid, queries, model, mode="judge", judge_model=None, **_kw):
        calls.append({"answer": model, "judge": judge_model})
        s = default_score if len(calls) == 1 else trial_score
        return {
            "details": [{"query_uuid": "tq-1", "judge": {"score": s, "verdict": "PASS"}, "actual_answer": "x"}],
            "avg_judge_score": s, "num_queries_judged": 1,
        }

    baselines_only = AsyncMock(return_value={
        "avg_baseline_score": 0.1, "num_baselines_judged": 1, "tokens_used": 0,
        "details": [{"query_uuid": "tq-1", "baseline_judge": {"score": 0.1, "verdict": "FAIL"}}],
    })
    judge_answer = AsyncMock(return_value={"score": 0.5})
    apply = AsyncMock()
    with ExitStack() as stack:
        _plan_patches(stack, user_model="glm-4.5")
        KBR = stack.enter_context(patch.object(kb_optimizer, "KBOptimizationRun"))
        KB = stack.enter_context(patch.object(kb_optimizer, "KnowledgeBase"))
        KBTQ = stack.enter_context(patch.object(kb_optimizer, "KBTestQuery"))
        svc = kb_optimizer.kb_validation_service
        stack.enter_context(patch.object(svc, "judge_baselines_only", new=baselines_only))
        stack.enter_context(patch.object(svc, "judge_test_queries", side_effect=fake_judge))
        stack.enter_context(patch.object(svc, "_judge_answer", new=judge_answer))
        stack.enter_context(patch.object(svc, "check_source_health",
                                         new=AsyncMock(return_value={"ratio": 1.0})))
        stack.enter_context(patch.object(svc, "check_chunk_coverage",
                                         new=AsyncMock(return_value={"ratio": 1.0})))
        stack.enter_context(patch.object(svc, "check_retrieval_precision",
                                         new=AsyncMock(return_value={"avg_precision": 1.0})))
        stack.enter_context(patch.object(KBOptimizer, "_apply_to_kb", new=apply))
        stack.enter_context(patch.object(KBOptimizer, "_notify_terminal", new=AsyncMock()))
        KBR.find_one = AsyncMock(return_value=run_doc)
        KB.find_one = AsyncMock(return_value=fake_kb)
        KBTQ.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[tq])))

        await KBOptimizer().run(
            kb_uuid="kb-1", user_id="u1", run_uuid="opt-1",
            token_budget=DEFAULT_TRIAL_TOKEN_ESTIMATE * 2, rng_seed=7,
        )
    return run_doc, calls, baselines_only, judge_answer, apply


@pytest.mark.asyncio
async def test_run_grades_everything_with_the_grader_and_answers_with_current():
    run_doc, calls, baselines_only, judge_answer, _ = await _run(0.5, 0.9)

    assert run_doc.status == "completed"
    assert run_doc.judge_model == "claude-3-opus"
    assert run_doc.current_model == "glm-4.5"
    assert run_doc.challenger_models == ["gpt-oss-120b", "glm-4.5"]
    # Every pass is graded by the grader except the last: the cross-judge
    # sanity check re-grades the winner with a second model on purpose.
    *graded, cross = calls
    assert {c["judge"] for c in graded} == {"claude-3-opus"}
    assert cross["judge"] != "claude-3-opus"
    # The default-KB baseline answers with the KB's current model.
    assert calls[0]["answer"] == "glm-4.5"
    assert baselines_only.await_args.kwargs["judge_model"] == "claude-3-opus"
    # The variance re-judge goes to the grader too.
    assert {c.kwargs["model_name"] for c in judge_answer.await_args_list} <= {"claude-3-opus"}
    assert run_doc.winner == "challenger"


@pytest.mark.asyncio
async def test_current_settings_win_when_every_trial_scores_below_them():
    run_doc, _, _, _, apply = await _run(0.9, 0.2, apply_on_finish=True)

    assert run_doc.status == "completed"
    assert run_doc.tied_with_baseline is False
    assert run_doc.winner == "current"
    # A clearly worse config must never be auto-applied.
    apply.assert_not_awaited()
