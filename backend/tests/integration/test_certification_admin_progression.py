"""A staff prerequisite toggle cannot change the explicit flexible-order policy."""
import json
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.routers import admin, certification
from app.services import chat_tools
from app.services.certification_versions.progression_policy import public_progression_policy
from app.services.certification_versions import enrollments, readers, runtime
from app.services.certification_versions.catalog import CourseCatalog
from tests.integration import test_certification_enrollments as base
from tests.test_certification_outcome_rubric import candidate, VERSION

repo = base.repo
pytestmark = base.pytestmark


async def test_admin_and_learner_read_the_same_policy_and_no_override_write_occurs(repo, monkeypatch, tmp_path):
    # These review/release flags are synthetic test metadata, never evidence
    # of actual policy acceptance, live grading or publication readiness.
    fixture = candidate.__wrapped__(tmp_path)
    path = fixture.folder.parent / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][VERSION].update(state='published', supported_for_existing=True)
    registry['new_enrollment_default'] = VERSION
    path.write_text(json.dumps(registry))
    repo.catalog = CourseCatalog(fixture.folder.parent)
    enrollment = await repo.ensure_initial('policy-learner')
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(enrollments, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    audit = AsyncMock()
    monkeypatch.setattr(admin, '_audit', audit)
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.include_router(certification.router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='operator', is_admin=True, is_staff=True)
    before = [await collection.find({}).to_list(None) for collection in (repo.progress, repo.enrollments, repo.selections)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        listing = await client.get('/admin/certifications')
        assert listing.status_code == 200, listing.text
        row = listing.json()['items'][0]
        assert row['progression_policy_id'] == 'required-outcomes-flexible-order.1'
        assert row['learning_order'] == 'any_order' and row['can_unlock'] is False
        assert row['modules_total'] == 11 and row['modules_completed'] == 0
        assert 'required outcome' in row['unlock_unavailable_reason']
        detail = await client.get('/admin/certifications/policy-learner', params={'enrollment_id': enrollment.uuid})
        assert detail.status_code == 200, detail.text
        assert detail.json()['progression_policy_id'] == row['progression_policy_id']
        for unlocked in (True, False):
            result = await client.put('/admin/certifications/policy-learner/unlock', params={'enrollment_id': enrollment.uuid}, json={'unlocked': unlocked, 'request_id': uuid4().hex, 'reason': 'Test that assessed requirements remain enforced'})
            assert result.status_code == 409 and 'cannot waive' in result.json()['detail']
        audit.assert_not_awaited()
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=enrollment.user_id, is_admin=False, is_staff=False)
        forbidden = await client.put('/admin/certifications/policy-learner/unlock', params={'enrollment_id': enrollment.uuid}, json={'unlocked': True, 'request_id': uuid4().hex, 'reason': 'Test administrator authorization'})
        assert forbidden.status_code == 403
        course = await client.get('/certification/course', params={'enrollment_id': enrollment.uuid})
        assert course.status_code == 200, course.text
        policy = course.json()['progression_policy']
        assert policy['policy_id'] == row['progression_policy_id']
        assert policy['required_modules'] == row['modules_total'] and policy['required_outcomes'] == 33
        assert all(not values for values in course.json()['prerequisites'].values())
        chat = await chat_tools.get_certification_progress(SimpleNamespace(deps=SimpleNamespace(user_id=enrollment.user_id)))
        assert 'error' not in chat, chat
        assert chat['progression_policy'] == policy == public_progression_policy(repo.catalog.load(enrollment.course_version))
        assert chat['maximum_stars'] == 1 and chat['credit_basis'] == 'required_outcomes'
        assert any('without approval or a grade penalty' in rule for rule in policy['rules'])
        assert any('staff grading are not course requirements' in rule for rule in policy['rules'])
    assert before == [await collection.find({}).to_list(None) for collection in (repo.progress, repo.enrollments, repo.selections)]
