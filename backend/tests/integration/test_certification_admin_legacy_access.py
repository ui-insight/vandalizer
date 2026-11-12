"""Legacy prerequisite access must not replace concurrently earned work."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.certification import CertificationProgress
from app.services.certification_versions import readers, runtime
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def configure(repo, monkeypatch):
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)


async def test_legacy_access_change_preserves_concurrent_credit_answers_and_reading_position(repo, monkeypatch):
    await configure(repo, monkeypatch)
    progress = CertificationProgress(user_id='legacy-access')
    await progress.insert()
    original_read = readers.existing_active_progress
    concurrent = {'modules': {'ai_literacy': {'completed': True, 'stars': 3, 'xp_earned': 150, 'reflections': ['Original answer']}},
                  'total_xp': 150, 'level': 'apprentice', 'certified': True, 'certified_at': '2026-10-08T10:00:00+00:00',
                  'learning_position': {'module_id': 'foundations', 'lesson_id': 'stable-lesson'},
                  'completion_receipt': {'attempt_id': 'a' * 32}, 'pending_credential': {'original_identity': 'private-test'}}
    async def concurrent_read(user_id):
        stale = await original_read(user_id)
        await repo.progress.update_one({'_id': progress.id}, {'$set': deepcopy(concurrent)})
        return stale
    monkeypatch.setattr(readers, 'existing_active_progress', concurrent_read)
    result = await readers.set_support_unlock(progress.user_id, True, None, actor_user_id='support-admin', reason='Restore learning access', request_id=uuid4().hex)
    saved = await repo.progress.find_one({'_id': progress.id})
    assert saved['unlocked'] is True
    assert {key: saved[key] for key in concurrent} == concurrent
    assert result.total_xp == 150 and result.modules == concurrent['modules']
    assert await repo.enrollments.count_documents({}) == 0


async def test_access_change_does_not_create_progress_for_a_missing_learner(repo, monkeypatch):
    await configure(repo, monkeypatch)
    with pytest.raises(EnrollmentConflict, match='existing progress'):
        await readers.set_support_unlock('missing-learner', True, None, actor_user_id='support-admin', reason='Restore learning access', request_id=uuid4().hex)
    assert await repo.progress.count_documents({}) == 0
    assert await repo.enrollments.count_documents({}) == 0


@pytest.mark.parametrize('changes', [{'unlocked': True}, {'enrollment_id': 'a' * 32, 'course_version': 'different-course'}])
async def test_stale_access_change_cannot_replace_new_access_or_binding(repo, monkeypatch, changes):
    await configure(repo, monkeypatch)
    progress = CertificationProgress(user_id='legacy-stale')
    await progress.insert()
    original_read = readers.existing_active_progress
    async def stale_read(user_id):
        stale = await original_read(user_id)
        await repo.progress.update_one({'_id': progress.id}, {'$set': changes})
        return stale
    monkeypatch.setattr(readers, 'existing_active_progress', stale_read)
    with pytest.raises(EnrollmentConflict, match='changed'):
        await readers.set_support_unlock(progress.user_id, True, None, actor_user_id='support-admin', reason='Restore learning access', request_id=uuid4().hex)
    saved = await repo.progress.find_one({'_id': progress.id})
    assert all(saved[key] == value for key, value in changes.items())


async def test_historical_missing_access_flag_uses_false_without_replacing_other_fields(repo, monkeypatch):
    await configure(repo, monkeypatch)
    progress = CertificationProgress(user_id='old-record', total_xp=75)
    await progress.insert()
    await repo.progress.update_one({'_id': progress.id}, {'$unset': {'unlocked': ''}, '$set': {'unknown_historical_field': 'preserve'}})
    saved = await readers.set_support_unlock(progress.user_id, True, None, actor_user_id='support-admin', reason='Restore learning access', request_id=uuid4().hex)
    assert saved.unlocked is True and saved.total_xp == 75
    assert (await repo.progress.find_one({'_id': progress.id}))['unknown_historical_field'] == 'preserve'


async def test_unselected_record_with_a_versioned_write_fence_requires_reconciliation(repo, monkeypatch):
    await configure(repo, monkeypatch)
    progress = CertificationProgress(user_id='fenced-legacy', total_xp=75)
    await progress.insert()
    await repo.progress.update_one({'_id': progress.id}, {'$set': {'_certification_write_fence': 'original-fence'}})
    before = await repo.progress.find_one({'_id': progress.id})
    with pytest.raises(EnrollmentConflict, match='binding changed'):
        await readers.set_support_unlock(progress.user_id, True, None, actor_user_id='support-admin', reason='Restore learning access', request_id=uuid4().hex)
    assert await repo.progress.find_one({'_id': progress.id}) == before
