"""Actual legacy field-count policy, through both supported validation paths."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import certification_service
from app.services.certification_versions import grading
from app.services.certification_versions.catalog import CourseCatalog


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('field_count,passed,stars', [(14, False, 0), (15, True, 1), (20, True, 2), (25, True, 3)])
async def test_missing_expected_fields_are_advice_under_original_count_policy(monkeypatch, versioned, field_count, passed, stars):
    package = CourseCatalog().load('legacy-2026-10-02.1', preview=True)
    service = grading.load_rubric(package) if versioned else certification_service
    progress = SimpleNamespace(user_id='learner', course_version=package.manifest.release_id, modules={})
    query = MagicMock()
    query.to_list = AsyncMock(return_value=[])
    workflow = MagicMock()
    workflow.find.return_value = query
    monkeypatch.setattr(service, 'Workflow', workflow)
    monkeypatch.setattr(service, 'get_progress', AsyncMock(return_value=progress))
    monkeypatch.setattr(service, '_collect_extraction_fields', AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(service, '_collect_searchset_fields', AsyncMock(return_value=[f'Unique test field {i}' for i in range(field_count)]))
    if versioned:
        result = await grading.grade(package, progress, 'extraction_engine', preview=True)
    else:
        monkeypatch.setattr(certification_service, 'current_operation', lambda: None)
        result = await certification_service.validate_module.__wrapped__('learner', 'extraction_engine')
    required, advice = result['checks']
    assert required['name'] == '15+ extraction fields' and required['role'] == 'required'
    assert required['passed'] is passed
    assert advice['name'] == 'Missing expected fields' and advice['role'] == 'advisory'
    assert advice['passed'] is False
    assert result['passed'] is all(c['passed'] for c in result['checks'] if c['role'] == 'required') is passed
    assert result['stars'] == stars


async def test_other_legacy_checks_remain_required(monkeypatch):
    package = CourseCatalog().load('legacy-2026-10-02.1', preview=True)
    rubric = grading.load_rubric(package)
    progress = SimpleNamespace(user_id='learner', course_version=package.manifest.release_id, modules={})
    monkeypatch.setattr(rubric, 'get_progress', AsyncMock(return_value=progress))
    result = await grading.grade(package, progress, 'ai_literacy', preview=True)
    assert result['passed'] is False
    assert result['checks'] and all(c['role'] == 'required' for c in result['checks'])
