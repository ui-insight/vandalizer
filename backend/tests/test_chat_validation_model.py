"""Chat validation tools and the model question.

Pins three things: an explicitly requested model is resolved against the
configured list before any LLM spend and forwarded to the service; the chat
session's model is NOT smuggled in as a forced override when the user didn't
ask for one; and get_quality_info exposes a per-model comparison with the
onboarding demo's fabricated run excluded.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_tools


def _ctx(**overrides):
    ctx = MagicMock()
    deps = MagicMock()
    deps.user_id = "user1"
    deps.team_id = "team1"
    deps.model_name = "chat-session-model"
    for k, v in overrides.items():
        setattr(deps, k, v)
    ctx.deps = deps
    return ctx


def _search_set():
    ss = MagicMock()
    ss.uuid = "ss-1"
    ss.title = "Grant Fields"
    ss.verified = True
    ss.user_id = "user1"
    ss.team_id = "team1"
    return ss


def _sys_cfg_with_models():
    cfg = MagicMock()
    cfg.available_models = [
        {"name": "gpt-x-large", "tag": "smart"},
        {"name": "local-llama", "tag": "local"},
    ]
    return cfg


def _tc_count(n):
    chain = MagicMock()
    chain.count = AsyncMock(return_value=n)
    return MagicMock(return_value=chain)


def _latest_run_chain(run):
    find_chain = MagicMock()
    find_chain.sort.return_value.first_or_none = AsyncMock(return_value=run)
    return find_chain


class TestRunValidationModel:
    @pytest.mark.asyncio
    async def test_unknown_model_is_rejected_before_any_llm_spend(self):
        with (
            patch.object(chat_tools, "SearchSet") as MockSS,
            patch.object(chat_tools, "ExtractionTestCase") as MockTC,
            patch("app.models.system_config.SystemConfig") as MockCfg,
            patch.object(chat_tools, "_confirm_gate", new_callable=AsyncMock, return_value=None),
            patch(
                "app.services.extraction_validation_service.run_validation",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            MockSS.find_one = AsyncMock(return_value=_search_set())
            MockTC.find = _tc_count(2)
            MockCfg.get_config = AsyncMock(return_value=_sys_cfg_with_models())

            result = await chat_tools.run_validation(
                _ctx(), "ss-1", model="gpt-typo", confirmed=True,
            )

        assert "error" in result
        assert "gpt-typo" in result["error"]
        assert "gpt-x-large" in result.get("hint", "")
        mock_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_model_resolves_tag_and_is_forwarded(self):
        run = MagicMock(score=88.0, score_breakdown={}, model="local-llama")
        with (
            patch.object(chat_tools, "SearchSet") as MockSS,
            patch.object(chat_tools, "ExtractionTestCase") as MockTC,
            patch.object(chat_tools, "ValidationRun") as MockVR,
            patch("app.models.system_config.SystemConfig") as MockCfg,
            patch.object(chat_tools, "_confirm_gate", new_callable=AsyncMock, return_value=None),
            patch(
                "app.services.extraction_validation_service.run_validation",
                new_callable=AsyncMock, return_value={"aggregate_accuracy": 0.9,
                                                      "aggregate_consistency": 0.9},
            ) as mock_run,
        ):
            MockSS.find_one = AsyncMock(return_value=_search_set())
            MockTC.find = _tc_count(2)
            MockVR.find.return_value = _latest_run_chain(run)
            MockCfg.get_config = AsyncMock(return_value=_sys_cfg_with_models())

            result = await chat_tools.run_validation(
                _ctx(), "ss-1", model="local", confirmed=True,
            )

        assert mock_run.await_args.kwargs["model"] == "local-llama"
        assert result["model_requested"] == "local-llama"
        assert result["model"] == "local-llama"

    @pytest.mark.asyncio
    async def test_chat_session_model_is_not_a_forced_override(self):
        # No explicit request: the service must receive model=None so the
        # template's own configuration decides — the chat session's model
        # would otherwise silently override an optimizer-applied config.
        run = MagicMock(score=88.0, score_breakdown={}, model="cfg-model")
        with (
            patch.object(chat_tools, "SearchSet") as MockSS,
            patch.object(chat_tools, "ExtractionTestCase") as MockTC,
            patch.object(chat_tools, "ValidationRun") as MockVR,
            patch.object(chat_tools, "_confirm_gate", new_callable=AsyncMock, return_value=None),
            patch(
                "app.services.extraction_validation_service.run_validation",
                new_callable=AsyncMock, return_value={"aggregate_accuracy": 0.9,
                                                      "aggregate_consistency": 0.9},
            ) as mock_run,
        ):
            MockSS.find_one = AsyncMock(return_value=_search_set())
            MockTC.find = _tc_count(2)
            MockVR.find.return_value = _latest_run_chain(run)

            result = await chat_tools.run_validation(_ctx(), "ss-1", confirmed=True)

        assert mock_run.await_args.kwargs["model"] is None
        assert result["model_requested"] is None
        # The label still reports what actually ran.
        assert result["model"] == "cfg-model"


class TestQualityInfoModelComparison:
    @pytest.mark.asyncio
    async def test_groups_by_model_and_excludes_demo_seed(self):
        def _run(model, score, source=None):
            return SimpleNamespace(model=model, score=score, source=source)

        latest = MagicMock()
        latest.score = 90.0
        latest.accuracy = 0.9
        latest.consistency = 0.9
        latest.grade = None
        latest.num_test_cases = 3
        latest.num_runs = 3
        latest.model = "gpt-x-large"
        latest.created_at = None
        latest.score_breakdown = None

        all_runs = [
            _run("gpt-x-large", 90.0),
            _run("gpt-x-large", 80.0),
            _run("local-llama", 70.0),
            _run(None, 60.0),
            _run(None, 92.0, source="demo_seed"),  # fabricated demo — excluded
        ]

        find_chain = MagicMock()
        find_chain.sort.return_value.first_or_none = AsyncMock(return_value=latest)
        find_chain.to_list = AsyncMock(return_value=all_runs)

        alert_chain = MagicMock()
        alert_chain.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        with (
            patch.object(chat_tools, "ValidationRun") as MockVR,
            patch.object(chat_tools, "QualityAlert") as MockQA,
            patch(
                "app.services.optimization_summary.latest_optimization_summary",
                new_callable=AsyncMock, return_value=None,
            ),
        ):
            MockVR.find.return_value = find_chain
            MockQA.find.return_value = alert_chain

            result = await chat_tools.get_quality_info(_ctx(), "knowledge_base", "kb-1")

        comparison = result["model_comparison"]
        assert [c["model"] for c in comparison] == ["gpt-x-large", "local-llama", "(unattributed)"]
        assert comparison[0]["avg_score"] == 85.0
        assert comparison[0]["run_count"] == 2
        # The demo run's 92 is nowhere: unattributed avg is the real 60.
        assert comparison[2]["avg_score"] == 60.0
        assert comparison[2]["run_count"] == 1
