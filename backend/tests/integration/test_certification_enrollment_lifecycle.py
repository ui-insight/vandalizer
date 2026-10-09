"""Lifecycle metadata cannot reopen closed records during credential recovery."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.certification import CertificationCredential
from app.models.user import User
from app.services import certification_service, chat_tools
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


@pytest.mark.parametrize('state', ['prepared', 'transferred', 'abandoned'])
@pytest.mark.parametrize('phase', ['before_issuance', 'after_issuance'])
async def test_completion_never_reopens_an_incompatible_enrollment(versioned_runtime, monkeypatch, state, phase):
    repository = versioned_runtime
    monkeypatch.setattr(certification_service, '_fire_certification_complete_hooks', AsyncMock())
    user_id = 'lifecycle-graduate'
    await User(user_id=user_id, name='Original learner', email='learner@example.test').insert()
    enrollment = await repository.ensure_initial(user_id)
    progress = await repository.read_progress(user_id, enrollment.uuid)
    progress.modules = {module.id: {'completed': True, 'stars': 3, 'xp_earned': module.base_xp + 75,
        'completed_at': '2026-10-01'} for module in repository.catalog.load(base.VERSION).manifest.modules}
    progress.modules['ai_literacy']['self_assessment'] = {'experience': 'Some', 'comfort': 'Some', 'concern': 'Some'}
    progress.total_xp = 2675
    await progress.save()
    original_finish, original_persist = certification_service._finish_pending_credential, CredentialRepository.persist

    async def change_state():
        await repository.enrollments.update_one({'uuid': enrollment.uuid}, {'$set': {'state': state}})

    async def changed_before(progress):
        await change_state()
        return await original_finish(progress)

    async def changed_after(self, record):
        preserved = await original_persist(self, record)
        await change_state()
        return preserved

    if phase == 'before_issuance':
        monkeypatch.setattr(certification_service, '_finish_pending_credential', changed_before)
    else:
        monkeypatch.setattr(CredentialRepository, 'persist', changed_after)
    context = SimpleNamespace(deps=SimpleNamespace(user_id=user_id))
    result = await chat_tools.complete_certification_module(context, 'ai_literacy', enrollment_id=enrollment.uuid)
    assert 'enrollment changed' in result['error']
    assert (await repository.current(user_id)).state == state
    pending = await repository.read_progress(user_id, enrollment.uuid)
    assert pending.pending_credential is not None and pending.total_xp == 2675
    assert await CertificationCredential.count() == (1 if phase == 'after_issuance' else 0)
    if phase == 'after_issuance':
        credential = await CredentialRepository().for_enrollment(user_id, enrollment.uuid)
        assert credential.model_dump(mode='json') == pending.pending_credential
    with pytest.raises(EnrollmentConflict, match='read-only'):
        async with repository.write_boundary(user_id, enrollment.uuid):
            pytest.fail('Completion must never reopen the changed enrollment')


@pytest.mark.parametrize('field,value', [('manifest_sha256', 'f' * 64), ('progress_id', '0' * 24)])
async def test_pending_completion_rejects_rebound_enrollment_identity(versioned_runtime, monkeypatch, field, value):
    repository = versioned_runtime
    monkeypatch.setattr(certification_service, '_fire_certification_complete_hooks', AsyncMock())
    enrollment = await repository.ensure_initial('rebound-graduate')
    progress = await repository.read_progress(enrollment.user_id, enrollment.uuid)
    package = repository.catalog.load(base.VERSION)
    progress.certified = True
    progress.certified_at = base.datetime.datetime(2026, 10, 1, tzinfo=base.datetime.timezone.utc)
    progress.modules = {module.id: {'completed': True, 'stars': 1, 'completed_at': '2026-10-01'} for module in package.manifest.modules}
    progress.pending_credential = CredentialRepository.prepare(progress, package, 'Original learner').model_dump(mode='json')
    await progress.save()
    original_finish = certification_service._finish_pending_credential

    async def rebound(progress):
        await repository.enrollments.update_one({'uuid': enrollment.uuid}, {'$set': {field: value}})
        return await original_finish(progress)

    monkeypatch.setattr(certification_service, '_finish_pending_credential', rebound)
    with pytest.raises(EnrollmentConflict, match='enrollment changed'):
        await certification_service.complete_module(enrollment.user_id, 'ai_literacy', enrollment_id=enrollment.uuid)
    assert await CertificationCredential.count() == 0
    raw = await repository.enrollments.find_one({'uuid': enrollment.uuid})
    assert raw[field] == value and raw['state'] == 'active'
