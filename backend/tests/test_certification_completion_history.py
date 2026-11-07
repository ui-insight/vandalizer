"""Completion retries preserve earned-credit history without changing the rubric."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import certification_service as service


@pytest.mark.parametrize('original_date', ['2025-04-02T12:00:00+00:00', None])
async def test_star_upgrade_and_repeat_keep_original_completion_date(original_date):
    progress = SimpleNamespace(
        user_id='learner',
        modules={'foundations': {'completed': True, 'stars': 1, 'xp_earned': 125, 'attempts': 1, 'completed_at': original_date}},
        total_xp=125, level='apprentice', certified=False, last_activity_date=None,
        save=AsyncMock(),
    )
    with patch.object(service, 'save_progress', AsyncMock()), patch.object(service, 'get_progress', AsyncMock(return_value=progress)), patch.object(
        service, 'validate_module', AsyncMock(return_value={'passed': True, 'stars': 3, 'checks': []})
    ):
        upgraded = await service.complete_module('learner', 'foundations')
        repeated = await service.complete_module('learner', 'foundations')
    assert upgraded['xp_earned'] == 50
    assert repeated['xp_earned'] == 0
    assert progress.total_xp == 175
    assert progress.modules['foundations']['completed_at'] == original_date
    assert progress.modules['foundations']['stars'] == 3


async def test_reflection_save_preserves_module_completion_and_dates_its_own_answers():
    earned = '2025-04-02T12:00:00+00:00'
    progress = SimpleNamespace(
        modules={'ai_literacy': {'completed': True, 'completed_at': earned}},
        last_activity_date=None, save=AsyncMock(),
    )
    with patch.object(service, 'save_progress', AsyncMock()), patch.object(service, 'get_progress', AsyncMock(return_value=progress)):
        result = await service.store_assessment('learner', 'ai_literacy', {'experience': 'Some experience'})
    assert result['stored'] is True
    assert progress.modules['ai_literacy']['completed_at'] == earned
    assert progress.modules['ai_literacy']['self_assessment']['completed_at']
