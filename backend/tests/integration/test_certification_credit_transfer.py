"""Synthetic published equivalence, real disposable persistence, no live grading."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.certification import CertificationEnrollment, CertificationProgress
from app.services.certification_versions import runtime
from app.services.certification_versions.attempts import AttemptRepository
from app.services.certification_versions.credit_transfer import CreditTransfer
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.outcome_credit import verified_credit_snapshot
from tests import test_certification_credit_equivalence as fixtures
from tests.integration import test_certification_enrollments as persisted

repo = persisted.repo
candidate = fixtures.candidate
pytestmark = persisted.pytestmark


async def setup(repo, candidate, monkeypatch, *, activate=False):
    candidate.progress.enrollment_id = uuid4().hex
    candidate.progress.user_id = 'transfer-learner'
    source_package, fake = fixtures.complete_fixture(candidate)
    policy = fixtures.mapping(source_package)
    target_package = fixtures.changed(source_package, version=policy['target_version'], assets={'credit-equivalence.json': policy})
    registry_path = repo.catalog.root / 'registry.json'
    registry = json.loads(registry_path.read_text())
    for package in (source_package, target_package):
        folder = repo.catalog.root / package.manifest.release_id
        folder.mkdir()
        (folder / 'manifest.json').write_bytes(package.manifest_bytes)
        for name, data in package.artifact_bytes:
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        registry['releases'][package.manifest.release_id] = {
            'state': 'published', 'supported_for_existing': True, 'manifest_sha256': package.manifest_sha256}
    registry_path.write_text(json.dumps(registry))
    source_package = repo.catalog.load(source_package.manifest.release_id)
    source_progress = CertificationProgress(user_id=fake.user_id, enrollment_id=fake.enrollment_id,
        course_version=source_package.manifest.release_id, modules=deepcopy(fake.modules),
        total_xp=sum(item.base_xp for item in source_package.manifest.modules), certified=True,
        certified_at=fake.certified_at, level='architect')
    await source_progress.insert()
    source = CertificationEnrollment(uuid=fake.enrollment_id, user_id=fake.user_id,
        course_version=source_package.manifest.release_id, manifest_sha256=source_package.manifest_sha256,
        progress_id=str(source_progress.id), provenance='new_enrollment', state='completed')
    await source.insert()
    credential = await CredentialRepository().persist(CredentialRepository.prepare(source_progress, source_package, 'Original learner'))
    activation_id = None
    if activate:
        from app.services.certification_versions.transition_preview import TransitionPreview
        from app.services.certification_versions.upgrade_decisions import UpgradeDecisionRepository
        from app.services.certification_versions.upgrade_activation import UpgradeActivationRepository
        persisted.set_upgrade_offer(repo, source.course_version, target_package.manifest.release_id)
        await repo.selections.insert_one({'user_id': fake.user_id, 'active_enrollment_id': source.uuid,
            'revision': 0, 'in_flight_writes': 0})
        preview = await TransitionPreview(repo).inspect(fake.user_id, source.uuid, target_package.manifest.release_id)
        decision_id, activation_id = uuid4().hex, uuid4().hex
        await UpgradeDecisionRepository(repo).accept(fake.user_id, {'request_id': decision_id,
            'source_enrollment_id': source.uuid, 'target_version': target_package.manifest.release_id,
            'preview_sha256': preview['preview_sha256'], 'consent': 'preserve_original_work_and_require_all_new_outcomes'})
        result = await UpgradeActivationRepository(repo).activate(fake.user_id, {'request_id': activation_id,
            'decision_id': decision_id, 'consent': 'activate_optional_upgrade_preserving_original_work_without_credit_transfer'})
        target = await repo._enrollment(fake.user_id, result['target_enrollment_id'])
    else:
        target_id = uuid4().hex
        target_progress = CertificationProgress(user_id=fake.user_id, enrollment_id=target_id,
            course_version=target_package.manifest.release_id)
        await target_progress.insert()
        target = CertificationEnrollment(uuid=target_id, user_id=fake.user_id, course_version=target_package.manifest.release_id,
            manifest_sha256=target_package.manifest_sha256, progress_id=str(target_progress.id),
            provenance='explicit_upgrade', source_enrollment_id=source.uuid)
        await target.insert()
        await repo.selections.insert_one({'user_id': fake.user_id, 'active_enrollment_id': target.uuid,
            'revision': 1, 'in_flight_writes': 0})
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    monkeypatch.setattr('app.services.certification_service._fire_certification_complete_hooks', AsyncMock())
    grader = AsyncMock(side_effect=AssertionError('Transfer must not run a model or regrade the original work'))
    monkeypatch.setattr('app.services.certification_service.validate_module', grader)
    return SimpleNamespace(user=fake.user_id, source=source, target=target, service=CreditTransfer(repo),
        source_package=source_package, package=repo.catalog.load(target.course_version), credential=credential,
        grader=grader, activation_id=activation_id)


async def request_for(f, module='ai_literacy'):
    preview = await f.service.preview(f.user, f.target.uuid)
    return next(row['request'] for row in preview['modules'] if row['module_id'] == module)


async def test_transfer_preserves_original_credit_and_carries_xp_without_another_reward(repo, candidate, monkeypatch):
    f = await setup(repo, candidate, monkeypatch)
    before = (await repo.read_progress(f.user, f.source.uuid)).model_dump(mode='json')
    request = await request_for(f)
    assert (await repo.read_progress(f.user, f.target.uuid)).total_xp == 0
    result = await f.service.apply(f.user, request)
    base = f.package.manifest.modules[0].base_xp
    assert result['credit_origin'] == 'transferred' and result['xp_earned'] == 0 and result['xp_carried'] == base
    progress = await repo.read_progress(f.user, f.target.uuid)
    credit = progress.modules['ai_literacy']
    assert progress.total_xp == base and credit['attempts'] == 0 and credit['xp_earned'] == 0
    snapshot = verified_credit_snapshot(f.package, progress, 'ai_literacy', credit['outcome_credit'], expected_attempt_id=request['request_id'])
    assert snapshot['source_enrollment_id'] == f.source.uuid
    assert len(snapshot['outcomes']) == 3
    assert await f.service.apply(f.user, request) == result
    assert (await repo.read_progress(f.user, f.target.uuid)).total_xp == base
    assert (await repo.read_progress(f.user, f.source.uuid)).model_dump(mode='json') == before
    assert await CredentialRepository().get(f.user, f.credential.credential_id) == f.credential
    assert await f.service.journal.records.count_documents({}) == 1
    f.grader.assert_not_awaited()


@pytest.mark.parametrize('point', ['progress_reply', 'journal_reply'])
async def test_interrupted_transfer_replays_original_receipt_without_duplicate_credit(repo, candidate, monkeypatch, point):
    f = await setup(repo, candidate, monkeypatch)
    request = await request_for(f)
    import app.services.certification_service as service
    original_save, original_finish = service.save_progress, AttemptRepository.finish
    interrupted = False
    async def save(progress):
        nonlocal interrupted
        value = await original_save(progress)
        if not interrupted:
            interrupted = True
            raise RuntimeError('Lost saved progress reply')
        return value
    async def finish(journal, record, result, **kwargs):
        nonlocal interrupted
        value = await original_finish(journal, record, result, **kwargs)
        if not interrupted:
            interrupted = True
            raise RuntimeError('Lost journal reply')
        return value
    with monkeypatch.context() as patch:
        if point == 'progress_reply':
            patch.setattr(service, 'save_progress', save)
        else:
            patch.setattr(AttemptRepository, 'finish', finish)
        with pytest.raises(RuntimeError, match='Lost'):
            await f.service.apply(f.user, request)
    result = await f.service.apply(f.user, request)
    assert result['xp_earned'] == 0
    assert (await repo.read_progress(f.user, f.target.uuid)).total_xp == result['xp_carried']
    assert await f.service.journal.records.count_documents({'state': 'applied'}) == 1


async def test_two_tabs_cannot_duplicate_carried_xp(repo, candidate, monkeypatch):
    f = await setup(repo, candidate, monkeypatch)
    request = await request_for(f)
    results = await asyncio.gather(*(f.service.apply(f.user, request) for _ in range(3)), return_exceptions=True)
    assert any(isinstance(result, dict) for result in results)
    assert all(isinstance(result, (dict, EnrollmentConflict)) for result in results)
    saved = await repo.read_progress(f.user, f.target.uuid)
    assert saved.total_xp == f.package.manifest.modules[0].base_xp
    assert await f.service.journal.records.count_documents({}) == 1


@pytest.mark.parametrize('change', ['owner', 'source', 'module', 'preview', 'request', 'target_work'])
async def test_changed_or_unowned_transfer_is_rejected_before_credit(repo, candidate, monkeypatch, change):
    f = await setup(repo, candidate, monkeypatch)
    request = await request_for(f)
    user = f.user
    if change == 'owner':
        user = 'someone-else'
    elif change == 'source':
        request['source_enrollment_id'] = uuid4().hex
    elif change == 'module':
        request['module_id'] = 'foundations'
    elif change == 'preview':
        request['preview_sha256'] = '0' * 64
    elif change == 'request':
        request['request_id'] = uuid4().hex
    else:
        await repo.progress.update_one({'enrollment_id': f.target.uuid}, {'$set': {'modules.ai_literacy.self_assessment': {'answer': 'New work'}}})
    with pytest.raises(EnrollmentConflict):
        await f.service.apply(user, request)
    assert (await repo.read_progress(f.user, f.target.uuid)).total_xp == 0
    assert await f.service.journal.records.count_documents({}) == 0


async def test_all_transferred_modules_issue_one_new_credential_with_original_provenance(repo, candidate, monkeypatch):
    f = await setup(repo, candidate, monkeypatch)
    final_request = None
    for module in f.package.manifest.modules:
        final_request = await request_for(f, module.id)
        result = await f.service.apply(f.user, final_request)
        assert result['xp_earned'] == 0
    target = await repo.read_progress(f.user, f.target.uuid)
    assert target.certified and target.pending_credential is None
    assert target.total_xp == sum(module.base_xp for module in f.package.manifest.modules)
    credential = await CredentialRepository().for_enrollment(f.user, f.target.uuid)
    assert credential.credential_id != f.credential.credential_id
    assert all(row['basis'] == 'transferred_required_outcomes' and row['xp_earned'] == 0 for row in credential.evidence)
    assert all(row['assessment_snapshot']['source_enrollment_id'] == f.source.uuid for row in credential.evidence)
    assert len(credential.outcomes) == 33
    assert await f.service.apply(f.user, final_request) == result
    assert await CredentialRepository().records.count_documents({'user_id': f.user}) == 2
    assert await CredentialRepository().get(f.user, f.credential.credential_id) == f.credential
    f.grader.assert_not_awaited()


async def test_revoked_worker_cannot_save_late_and_original_transfer_can_resume(repo, candidate, monkeypatch):
    from app.services.certification_versions.recovery import CompletionRecovery
    import app.services.certification_service as service
    f = await setup(repo, candidate, monkeypatch)
    request = await request_for(f)
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.save_progress
    async def pause(progress):
        entered.set()
        await release.wait()
        return await original(progress)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'save_progress', pause)
        worker = asyncio.create_task(f.service.apply(f.user, request))
        try:
            await asyncio.wait_for(entered.wait(), timeout=20)
            selected = await repo.selections.find_one({'user_id': f.user})
            recovered = await CompletionRecovery(repo).recover_worker(f.user, f.target.uuid,
                expected_write_id=selected['active_write']['id'], expected_revision=selected['revision'],
                reason='Synthetic interrupted transfer worker')
            assert recovered['status'] == 'retry_saved_grade'
        finally:
            release.set()
            result = await asyncio.wait_for(asyncio.gather(worker, return_exceptions=True), timeout=20)
        assert isinstance(result[0], EnrollmentConflict)
    result = await f.service.apply(f.user, request)
    assert result['xp_earned'] == 0
    assert (await repo.read_progress(f.user, f.target.uuid)).total_xp == result['xp_carried']


async def test_public_transfer_requires_explicit_consent_and_read_only_receipt_is_owned(repo, candidate, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.dependencies import get_current_user
    from app.routers import certification_upgrades as routes
    f = await setup(repo, candidate, monkeypatch)
    monkeypatch.setattr(routes, 'versioning_enabled', lambda: True)
    monkeypatch.setattr(routes, 'CreditTransfer', lambda: f.service)
    app = FastAPI()
    app.include_router(routes.router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=f.user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        preview = await client.get('/certification/credit-transfer-preview', params={'enrollment_id': f.target.uuid})
        assert preview.status_code == 200
        request = preview.json()['modules'][0]['request']
        bad = await client.post('/certification/credit-transfers', json={**request, 'consent': 'switch_course'})
        assert bad.status_code == 422
        result = await client.post('/certification/credit-transfers', json=request)
        assert result.status_code == 200, result.text
        before = (await repo.read_progress(f.user, f.target.uuid)).model_dump(mode='json')
        monkeypatch.setattr(routes, 'versioning_enabled', lambda: False)
        saved = await client.get('/certification/credit-transfers/' + request['request_id'])
        assert saved.status_code == 200 and saved.json()['read_only']
        assert saved.json()['result'] == result.json()
        assert (await repo.read_progress(f.user, f.target.uuid)).model_dump(mode='json') == before
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='another-user')
        assert (await client.get('/certification/credit-transfers/' + request['request_id'])).status_code == 404


async def test_unavailable_target_rubric_cannot_grant_partial_credit(repo, candidate, monkeypatch):
    from app.services.certification_versions.catalog import CourseCatalogError
    f = await setup(repo, candidate, monkeypatch)
    request = await request_for(f)
    def unavailable(package):
        raise CourseCatalogError('Installed target grading is unavailable')
    monkeypatch.setattr('app.services.certification_versions.grading.load_rubric', unavailable)
    with pytest.raises(CourseCatalogError, match='unavailable'):
        await f.service.apply(f.user, request)
    assert await f.service.journal.records.count_documents({}) == 0
    assert (await repo.read_progress(f.user, f.target.uuid)).total_xp == 0


async def test_transfer_then_return_and_resume_preserves_both_histories(repo, candidate, monkeypatch):
    from app.services.certification_versions.delivery import CourseDelivery
    from app.services.certification_versions.saved_course_selection import SavedCourseSelectionRepository
    from tests.integration.test_certification_saved_course_selection import histories
    f = await setup(repo, candidate, monkeypatch, activate=True)
    before_course = await CourseDelivery(repo).course(f.user, f.target.uuid)
    preview = await f.service.preview(f.user, f.target.uuid)
    request = next(row['request'] for row in preview['modules'] if row['eligible'])
    result = await f.service.apply(f.user, request)
    receipt = await f.service.saved(f.user, request['request_id'])
    after_course = await CourseDelivery(repo).course(f.user, f.target.uuid)
    before = await histories(repo, f.user)
    service = SavedCourseSelectionRepository(repo)
    for action, expected in [('return_to_original_course', f.source.uuid), ('resume_upgraded_course', f.target.uuid)]:
        choice = await service.preview(f.user, f.activation_id, action)
        await service.select(f.user, {'request_id': uuid4().hex, 'activation_id': f.activation_id,
            'action': action, 'preview_sha256': choice['preview_sha256'],
            'consent': 'select_saved_course_preserving_both_histories_and_credit'})
        assert (await repo.current(f.user)).uuid == expected
        assert await histories(repo, f.user) == before
    assert await f.service.apply(f.user, request) == result
    f.grader.assert_not_awaited()
    destination = os.environ.get('CERTIFICATION_TRANSFER_FIXTURE')
    if destination:
        options = {'current_enrollment_id': f.target.uuid, 'read_only': True, 'next_cursor': None,
            'courses': [{'activation_id': f.activation_id, 'action': 'return_to_original_course',
                'enrollment_id': f.source.uuid, 'course_version': f.source.course_version,
                'course_title': f.source_package.manifest.title, 'definition_available': True}]}
        Path(destination).write_text(json.dumps({'before_course': before_course, 'after_course': after_course,
            'preview': preview, 'request': request, 'result': result, 'receipt': receipt, 'options': options}, indent=2) + '\n')
