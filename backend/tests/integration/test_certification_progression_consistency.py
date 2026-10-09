"""Legacy study order is not an assessed prerequisite, with or without pinning."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationProgress
from app.routers.certification import router
from app.services import certification_service as service, chat_tools
from app.services.certification_versions import runtime
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


@pytest.mark.parametrize('versioned', [False, True])
async def test_later_legacy_module_is_accessible_but_still_requires_its_original_assessment(repo, monkeypatch, versioned):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    learner = 'any-order-learner'
    if versioned:
        enrollment = await repo.ensure_initial(learner)
        identity = {'enrollment_id': enrollment.uuid}
        assert all(not module.prerequisites for module in repo.catalog.load(enrollment.course_version).manifest.modules)
    else:
        await CertificationProgress(user_id=learner).insert()
        identity = {}
    context = SimpleNamespace(deps=SimpleNamespace(user_id=learner))
    async def saved_progress():
        return await repo.read_progress(learner, identity['enrollment_id']) if versioned else await service.get_progress(learner)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=learner)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        check = await chat_tools.check_certification_module(context, 'process_mapping', **identity)
        assert check['passed'] is False
        assert all(item['name'] != 'prerequisite' for item in check['checks'])
        denied = await client.post('/certification/modules/process_mapping/complete', params={**identity, 'request_id': uuid4().hex})
        assert denied.status_code == 400
        assert (await saved_progress()).total_xp == 0
        answers = {key: 'My original process decision and explanation.' for key in service.ASSESSMENT_KEYS['process_mapping']}
        saved = await chat_tools.submit_certification_assessment(context, 'process_mapping', answers, **identity)
        assert saved['stored'] is True
        allowed = await client.post('/certification/modules/process_mapping/validate', params=identity)
        assert allowed.status_code == 200 and allowed.json()['passed'] is True
        completed = await chat_tools.complete_certification_module(context, 'process_mapping', request_id=uuid4().hex, **identity)
        assert completed['xp_earned'] > 0
        progress = await saved_progress()
        assert progress.modules['process_mapping']['completed'] is True
        assert not progress.modules.get('foundations', {}).get('completed')
        assert not progress.modules.get('ai_literacy', {}).get('completed')
        assert progress.unlocked is False and progress.certified is False
