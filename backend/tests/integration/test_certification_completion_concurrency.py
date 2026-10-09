"""Two HTTP clients cannot duplicate base credit or a legacy star upgrade."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationProgress
from app.routers.certification import router
from app.services import certification_service as service
from app.services.certification_versions import runtime
from app.services.certification_versions.attempts import AttemptRepository
from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.enrollments import EnrollmentRepository
from tests.integration import test_certification_enrollments as base
from tests.integration.test_certification_outcome_completion import setup

repo = base.repo
pytestmark = base.pytestmark


@pytest.mark.parametrize('same_request', [True, False])
@pytest.mark.parametrize('kind', ['competency', 'legacy_first', 'legacy_upgrade', 'legacy_unknown_date'])
async def test_simultaneous_completion_preserves_one_award_and_original_receipts(repo, monkeypatch, same_request, kind):
    original_date = None if kind == 'legacy_unknown_date' else '2025-04-02T12:00:00+00:00'
    upgrade = kind in ('legacy_upgrade', 'legacy_unknown_date')
    if kind == 'competency':
        f, client, app, body, _, judge = await setup(repo, monkeypatch)
        learner, module_id = f.learner, 'validation_qa'
    else:
        user_id, module_id = 'parallel-legacy', 'ai_literacy'
        package = repo.catalog.load(base.VERSION)
        base_xp = next(m.base_xp for m in package.manifest.modules if m.id == module_id)
        answers = {'experience': 'Some', 'comfort': 'Some', 'concern': 'Some'}
        credit = {'self_assessment': answers}
        if upgrade:
            credit.update(completed=True, stars=1, completed_at=original_date,
                          xp_earned=base_xp + package.manifest.star_bonus_xp, attempts=1)
        await CertificationProgress(user_id=user_id, modules={module_id: credit},
            total_xp=credit.get('xp_earned', 0)).insert()
        learner = await repo.ensure_initial(user_id)
        monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
        monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
        app = FastAPI()
        app.include_router(router, prefix='/certification')
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=user_id)
        client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
        body, judge = None, None
    package = repo.catalog.load(learner.course_version)
    before = await repo.read_progress(learner.user_id, learner.uuid)
    expected_total = next(m.base_xp for m in package.manifest.modules if m.id == module_id)
    expected_total += package.manifest.maximum_stars * package.manifest.star_bonus_xp
    first_id = uuid4().hex
    second_id = first_id if same_request else uuid4().hex
    params = {'enrollment_id': learner.uuid, 'request_id': first_id}
    path = f'/certification/modules/{module_id}/complete'
    entered, release = asyncio.Event(), asyncio.Event()
    validate = service.validate_module
    calls = 0

    async def pause_first(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.wait_for(release.wait(), 15)
        return await validate(*args, **kwargs)

    monkeypatch.setattr(service, 'validate_module', pause_first)
    async with client, AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as other:
        first = asyncio.create_task(client.post(path, params=params, json=body))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            concurrent = await other.post(path, params={**params, 'request_id': second_id}, json=body)
            assert concurrent.status_code == 409, concurrent.text
            in_flight = await repo.read_progress(learner.user_id, learner.uuid)
            assert in_flight.total_xp == before.total_xp
        finally:
            release.set()
            applied = await asyncio.wait_for(first, 20)
        assert applied.status_code == 200, applied.text
        assert applied.json()['xp_earned'] == expected_total - before.total_xp
        earned = await repo.read_progress(learner.user_id, learner.uuid)
        earned_date = earned.modules[module_id]['completed_at']
        if upgrade:
            assert earned_date == original_date
        else:
            assert earned_date
        # New repository/catalog objects replay the persisted original receipt.
        restarted = EnrollmentRepository(CourseCatalog(repo.catalog.root))
        monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: restarted)
        retried = await other.post(path, params={**params, 'request_id': second_id}, json=body)
        assert retried.status_code == 200, retried.text
        if same_request:
            assert retried.json() == applied.json()
        else:
            assert retried.json()['xp_earned'] == 0
        late_first = await client.post(path, params=params, json=body)
        assert late_first.json() == applied.json()
        saved = await restarted.read_progress(learner.user_id, learner.uuid)
        assert saved.total_xp == expected_total
        assert saved.modules[module_id]['xp_earned'] == expected_total
        assert saved.modules[module_id]['completed_at'] == earned_date
        assert saved.modules[module_id]['stars'] == package.manifest.maximum_stars
        records = await AttemptRepository().records.find({}).to_list(None)
        assert len(records) == (1 if same_request else 2)
        assert all(record['state'] == 'applied' for record in records)
        original = next(record for record in records if record['uuid'] == first_id)
        assert AttemptRepository.payload(original, 'result') == applied.json()
        if upgrade:
            old = AttemptRepository.payload(original, 'progress')['modules'][module_id]
            assert old['stars'] == 1 and old['completed_at'] == original_date
    assert calls == (1 if same_request else 2)
    if judge:
        judge.assert_awaited_once()
