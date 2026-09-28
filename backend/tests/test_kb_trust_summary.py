"""Trust summaries must retain score semantics and application provenance."""
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.knowledge import _latest_runs_by_kb

STAMP = datetime.datetime(2026, 9, 26, tzinfo=datetime.timezone.utc)


async def summarize(manual=(), optimized=()):
    vquery, oquery = MagicMock(), MagicMock()
    vquery.sort.return_value.to_list = AsyncMock(return_value=list(manual))
    oquery.sort.return_value.to_list = AsyncMock(return_value=list(optimized))
    with patch('app.routers.knowledge.ValidationRun.find', return_value=vquery) as vf, \
         patch('app.routers.knowledge.KBOptimizationRun.find', return_value=oquery) as of:
        result = await _latest_runs_by_kb(['kb-visible'])
    assert vf.call_args.args[0]['item_id'] == {'$in': ['kb-visible']}
    assert of.call_args.args[0]['kb_uuid'] == {'$in': ['kb-visible']}
    return result['kb-visible']


def optimization(**overrides):
    return SimpleNamespace(**dict(
        dict(kb_uuid='kb-visible', completed_at=STAMP, started_at=STAMP,
             optimized_score=0.8, baseline_default_score=0.65,
             baseline_no_kb_score=0.4, applied_at=None, reverted_at=None),
        **overrides,
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize('applied,reverted,state', [
    (None, None, 'proposed'), (STAMP, None, 'applied'), (STAMP, STAMP, 'reverted'),
])
async def test_composite_quality_never_invents_answer_accuracy_lift(applied, reverted, state):
    result = await summarize(optimized=[optimization(applied_at=applied, reverted_at=reverted)])
    assert result.score == 0.8
    assert result.metric == 'composite_quality'
    assert result.config_state == state
    assert result.baseline is None
    assert result.lift is None


@pytest.mark.asyncio
async def test_default_score_remains_a_test_of_default_settings():
    result = await summarize(optimized=[optimization(optimized_score=None)])
    assert result.score == 0.65
    assert result.config_state == 'default'


@pytest.mark.asyncio
async def test_newer_manual_validation_retains_comparable_accuracy():
    result = await summarize(manual=[SimpleNamespace(
        item_id='kb-visible', created_at=STAMP + datetime.timedelta(days=1),
        result_snapshot={'retrieval_precision': {
            'avg_judge_score': 0.9, 'avg_baseline_score': 0.4, 'avg_lift': 0.5,
        }},
    )], optimized=[optimization()])
    assert (result.score, result.baseline, result.lift) == (0.9, 0.4, 0.5)
    assert result.metric == 'answer_accuracy'
    assert result.config_state is None


@pytest.mark.asyncio
async def test_empty_list_does_not_query_runs():
    with patch('app.routers.knowledge.ValidationRun.find') as find:
        assert await _latest_runs_by_kb([]) == {}
    find.assert_not_called()
