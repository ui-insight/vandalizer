from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from app.services.optimization_actions import apply_workflow_optimization, OptimizationActionError


def state():
    workflow=SimpleNamespace(id='workflow',name='Review',config_override=None,save=AsyncMock())
    run=SimpleNamespace(uuid='candidate',status='completed',best_config={'step_overrides':{'A':{'model':'a'},'B':{'model':'b'}}},tied_with_baseline=False,previous_override=None,optimized_score=.8,judge_model=None,judge_variance=None,save=AsyncMock())
    return workflow,run

@pytest.mark.asyncio
async def test_repeated_apply_preserves_baseline_and_avoids_duplicate_timeline():
    workflow,run=state()
    with patch('app.services.quality_service.record_optimizer_apply',new=AsyncMock()) as history:
        await apply_workflow_optimization(workflow,run,'owner')
        await apply_workflow_optimization(workflow,run,'owner')
        assert run.previous_override is None
        run.save.assert_awaited_once()
        workflow.save.assert_awaited_once()
        history.assert_awaited_once()

@pytest.mark.asyncio
async def test_partial_apply_keeps_original_snapshot_and_rejects_invalid_selection_before_writes():
    workflow,run=state()
    baseline={'step_overrides':{'Original':{'model':'original'}},'from_run_uuid':'previous'}
    workflow.config_override=baseline
    with patch('app.services.quality_service.record_optimizer_apply',new=AsyncMock()):
        with pytest.raises(OptimizationActionError,match='Unknown step_ids'):
            await apply_workflow_optimization(workflow,run,'owner',step_ids=['missing'])
        run.save.assert_not_awaited();workflow.save.assert_not_awaited()
        await apply_workflow_optimization(workflow,run,'owner',step_ids=['A'])
        await apply_workflow_optimization(workflow,run,'owner',step_ids=['B'])
    assert run.previous_override==baseline
    assert set(workflow.config_override['step_overrides'])=={'Original','A','B'}
    run.save.assert_awaited_once()
