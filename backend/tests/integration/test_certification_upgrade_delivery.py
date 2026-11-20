"""Public optional choices remain separate from publication and earned credit."""
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies import get_current_user
from app.routers.certification import router
from app.routers import certification_upgrades
from app.services.certification_versions import upgrade_delivery
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.upgrade_delivery import UpgradeDelivery
from app.services.certification_versions.writes import save_progress
from tests.integration import test_certification_upgrade_decisions as choices
from tests.integration.test_certification_saved_course_selection import histories

repo = choices.repo
pytestmark = choices.pytestmark


async def fixture(repo, *, verified=True):
    source, target, _, _ = await choices.setup(repo, verified=verified)
    return source, target, UpgradeDelivery(repo)


async def test_read_only_review_records_a_separate_choice_then_explicitly_selects_once(repo):
    source, target, service = await fixture(repo)
    before = await histories(repo, source.user_id)
    preview = await service.preview(source.user_id, source.uuid, target)
    assert preview == await service.preview(source.user_id, source.uuid, target)
    equivalence = preview['comparison']['equivalence_plan']
    assert equivalence['source_enrollment_id'] == source.uuid
    assert equivalence['target_version'] == target
    assert equivalence['required_outcome_count'] == 33
    assert equivalence['eligible_outcome_count'] == 0
    assert equivalence['credit_transferred'] is equivalence['can_apply'] is False
    assert equivalence['xp_awarded'] == 0
    assert preview['choice']['available'] and not preview['choice']['recorded']
    assert await service.decisions.records.count_documents({}) == 0
    assert await histories(repo, source.user_id) == before
    choice = await service.accept(source.user_id, preview['choice']['request'])
    assert choice['credit_transferred'] is False and choice['requires_fresh_activation_check'] is True
    assert await histories(repo, source.user_id) == before
    assert await service.decision(source.user_id, choice['decision_id']) == choice
    assert (await service.preview(source.user_id, source.uuid, target))['choice']['recorded']
    result = await service.activate(source.user_id, choice['activation_request'])
    assert result['receipt']['histories_preserved'] and result['receipt']['credit_transferred'] is False
    assert result['receipt']['target_manifest_sha256'] == choice['target_manifest_sha256']
    assert result['current_enrollment_id'] == result['receipt']['target_enrollment_id']
    assert not result['confirmation_pending']
    assert (await service.activation(source.user_id, choice['activation_request']['request_id']))['read_only']
    assert await service.activate(source.user_id, choice['activation_request']) == result
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2
    assert (await repo.read_progress(source.user_id, result['current_enrollment_id'])).total_xp == 0


async def test_lost_choice_response_and_guard_rotation_keep_original_choice_and_activation_request(repo, monkeypatch):
    source, target, service = await fixture(repo)
    preview = await service.preview(source.user_id, source.uuid, target)
    request = preview['choice']['request']
    insert = service.decisions.records.insert_one
    async def lost_response(value):
        await insert(value)
        raise RuntimeError('Lost choice reply')
    with monkeypatch.context() as patch:
        patch.setattr(service.decisions.records, 'insert_one', lost_response)
        with pytest.raises(RuntimeError):
            await service.accept(source.user_id, request)
    choice = await UpgradeDelivery(repo).decision(source.user_id, request['request_id'])
    async with repo.write_boundary(source.user_id, source.uuid):
        pass
    refreshed = await UpgradeDelivery(repo).preview(source.user_id, source.uuid, target)
    assert refreshed['choice']['request'] == request
    assert refreshed['choice']['decision'] == choice
    assert refreshed['comparison']['preview_sha256'] != request['preview_sha256']
    assert await service.accept(source.user_id, request) == choice
    assert await service.decisions.records.count_documents({}) == 1


async def test_another_device_reuses_original_prepared_activation_after_interruption(repo, monkeypatch):
    source, target, service = await fixture(repo)
    request = (await service.preview(source.user_id, source.uuid, target))['choice']['request']
    choice = await service.accept(source.user_id, request)
    async def fail(*args):
        raise RuntimeError('Paused before switch')
    with monkeypatch.context() as patch:
        patch.setattr(service.activations, 'commit', fail)
        with pytest.raises(RuntimeError):
            await service.activate(source.user_id, choice['activation_request'])
    state = await service.activation(source.user_id, choice['activation_request']['request_id'])
    assert state['state'] == 'prepared' and state['receipt'] is None and state['read_only']
    other = UpgradeDelivery(repo)
    fresh = await other.preview(source.user_id, source.uuid, target)
    assert fresh['choice']['decision']['activation_request'] == choice['activation_request']
    await other.activate(source.user_id, choice['activation_request'])
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2


async def test_saved_pair_return_resume_and_no_second_started_enrollment_for_same_version(repo):
    source, target, service = await fixture(repo)
    choice = await service.accept(source.user_id, (await service.preview(source.user_id, source.uuid, target))['choice']['request'])
    upgrade = await service.activate(source.user_id, choice['activation_request'])
    target_id = upgrade['current_enrollment_id']
    async with repo.write_boundary(source.user_id, target_id) as progress:
        progress.position_revision = 8
        await save_progress(progress)
    both = await histories(repo, source.user_id)
    options = await service.saved_options(source.user_id)
    assert options['read_only'] and options['current_enrollment_id'] == target_id
    assert options['courses'][0]['action'] == 'return_to_original_course'
    item = options['courses'][0]
    preview = await service.saved_preview(source.user_id, item['activation_id'], item['action'])
    assert preview == await service.saved_preview(source.user_id, item['activation_id'], item['action'])
    await service.select_saved(source.user_id, preview['request'])
    assert await histories(repo, source.user_id) == both
    duplicate = await service.preview(source.user_id, source.uuid, target)
    assert duplicate['choice']['available'] is False and duplicate['choice']['reason'] == 'resume_saved_course'
    with pytest.raises(EnrollmentConflict, match='saved course'):
        await service.accept(source.user_id, duplicate['choice']['request'])
    # Bypassing the public accept path cannot bypass the activation safeguard.
    internal = await service.decisions.accept(source.user_id, duplicate['choice']['request'])
    with pytest.raises(EnrollmentConflict, match='existing saved course'):
        await service.activate(source.user_id, (await service.decision_view(internal))['activation_request'])
    options = await service.saved_options(source.user_id)
    assert options['courses'][0]['action'] == 'resume_upgraded_course'
    item = options['courses'][0]
    resumed = await service.select_saved(source.user_id, (await service.saved_preview(source.user_id, item['activation_id'], item['action']))['request'])
    assert resumed['current_enrollment_id'] == target_id
    assert await histories(repo, source.user_id) == both
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 2
    # Old return replay is a historical receipt, not another return.
    replay = await service.select_saved(source.user_id, preview['request'])
    assert replay['receipt']['target_enrollment_id'] == source.uuid and replay['current_enrollment_id'] == target_id
    read = await service.saved_selection(source.user_id, preview['request']['request_id'])
    assert read['receipt'] == replay['receipt'] and read['current_enrollment_id'] == target_id
    assert read['read_only'] and read['state'] == 'applied' and not read['confirmation_pending']
    assert read['source_enrollment_id'] == target_id and read['request'] == preview['request']
    assert await histories(repo, source.user_id) == both


@pytest.mark.parametrize('change', ['work', 'withdrawn_offer', 'unverified_target'])
async def test_unavailable_or_changed_choices_cannot_switch(repo, change):
    source, target, service = await fixture(repo, verified=change != 'unverified_target')
    preview = await service.preview(source.user_id, source.uuid, target)
    if change == 'unverified_target':
        assert preview['choice']['reason'] == 'assessment_unavailable' and not preview['choice']['available']
        with pytest.raises(choices.UpgradeUnavailable):
            await service.accept(source.user_id, preview['choice']['request'])
        return
    choice = await service.accept(source.user_id, preview['choice']['request'])
    if change == 'work':
        async with repo.write_boundary(source.user_id, source.uuid) as progress:
            progress.position_revision += 1
            await save_progress(progress)
    else:
        choices.fixtures.set_upgrade_offer(repo, source.course_version, target, enabled=False)
    with pytest.raises((EnrollmentConflict, choices.UpgradeUnavailable)):
        await service.activate(source.user_id, choice['activation_request'])
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert await service.decision(source.user_id, choice['decision_id']) == choice


async def test_request_binding_foreign_references_and_index_metadata_fail_closed(repo):
    source, target, service = await fixture(repo)
    preview = await service.preview(source.user_id, source.uuid, target)
    with pytest.raises(EnrollmentConflict, match='original request'):
        await service.accept(source.user_id, {**preview['choice']['request'], 'request_id': uuid4().hex})
    choice = await service.accept(source.user_id, preview['choice']['request'])
    for method, args in [('decision', (choice['decision_id'],)), ('activate', (choice['activation_request'],))]:
        with pytest.raises(choices.UpgradeUnavailable):
            await getattr(service, method)('foreign', *args)
    await service.decisions.records.update_one({'uuid': choice['decision_id']}, {'$set': {'target_version': 'contradictory-course'}})
    with pytest.raises(CourseCatalogError):
        await service.decision(source.user_id, choice['decision_id'])
    assert (await repo.current(source.user_id)).uuid == source.uuid


async def test_http_choices_are_authenticated_and_disabled_writes_do_not_hide_original_receipts(repo, monkeypatch):
    source, target, service = await fixture(repo)
    monkeypatch.setattr(upgrade_delivery, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(certification_upgrades, 'versioning_enabled', lambda: True)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        params = {'enrollment_id': source.uuid, 'target_version': target}
        preview = await client.get('/certification/upgrade-choice-preview', params=params)
        assert preview.status_code == 200, preview.text
        assert 'record_json' not in preview.text and 'self_assessment' not in preview.text
        request = preview.json()['choice']['request']
        for invalid in ({**request, 'consent': 'switch'}, {**request, 'transfer_xp': True}):
            assert (await client.post('/certification/upgrade-choices', json=invalid)).status_code == 422
        choice_response = await client.post('/certification/upgrade-choices', json=request)
        assert choice_response.status_code == 200
        choice = choice_response.json()
        assert (await repo.current(source.user_id)).uuid == source.uuid
        activation = await client.post('/certification/upgrade-activations', json=choice['activation_request'])
        assert activation.status_code == 200, activation.text
        options = await client.get('/certification/saved-course-options')
        item = options.json()['courses'][0]
        returning = await client.get('/certification/saved-course-preview', params={key: item[key] for key in ('activation_id', 'action')})
        assert returning.status_code == 200
        returned = await client.post('/certification/saved-course-selections', json=returning.json()['request'])
        assert returned.status_code == 200 and returned.json()['current_enrollment_id'] == source.uuid
        assert (await client.get('/certification/saved-course-options', params={'cursor': 'invalid'})).status_code == 422
        monkeypatch.setattr(certification_upgrades, 'versioning_enabled', lambda: False)
        assert (await client.get('/certification/upgrade-choice-preview', params=params)).status_code == 404
        assert (await client.post('/certification/upgrade-activations', json=choice['activation_request'])).status_code == 404
        assert (await client.post('/certification/saved-course-selections', json=returning.json()['request'])).status_code == 404
        assert (await client.get('/certification/upgrade-choices/' + choice['decision_id'])).status_code == 200
        assert (await client.get('/certification/upgrade-activations/' + choice['activation_request']['request_id'])).status_code == 200
        assert (await client.get('/certification/saved-course-options')).status_code == 200
        saved_path = '/certification/saved-course-selections/' + returning.json()['request']['request_id']
        assert (await client.get(saved_path)).json()['receipt'] == returned.json()['receipt']
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
        assert (await client.get('/certification/upgrade-choices/' + choice['decision_id'])).status_code == 404
        assert (await client.get('/certification/upgrade-activations/' + choice['activation_request']['request_id'])).status_code == 404
        assert (await client.get('/certification/saved-course-options')).json()['courses'] == []
        assert (await client.get(saved_path)).status_code == 404
        app.dependency_overrides.clear()
        assert (await client.get('/certification/saved-course-options')).status_code == 401
        assert (await client.get('/certification/upgrade-choices/' + choice['decision_id'])).status_code == 401
        assert (await client.get(saved_path)).status_code == 401


async def test_older_indexless_choice_keeps_original_consent_without_rewriting_on_read(repo):
    source, target, service = await fixture(repo)
    preview = await service.preview(source.user_id, source.uuid, target)
    choice = await service.accept(source.user_id, preview['choice']['request'])
    await service.decisions.records.update_one({'uuid': choice['decision_id']}, {'$unset': {'target_version': '', 'decision_basis_sha256': ''}})
    original = await service.decisions.records.find_one({'uuid': choice['decision_id']})
    async with repo.write_boundary(source.user_id, source.uuid):
        pass
    reviewed = await service.preview(source.user_id, source.uuid, target)
    assert reviewed['choice']['recorded'] and reviewed['choice']['decision'] == choice
    assert reviewed['choice']['request'] == preview['choice']['request']
    assert await service.decisions.records.find_one({'uuid': choice['decision_id']}) == original
