"""Blank staged courses cannot masquerade as started enrollments."""
import datetime

import pytest

from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.course_history import CourseHistory
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.selection_delivery import SelectionDelivery
from app.services.certification_versions.selection_journal import SelectionJournal
from app.services.certification_versions.upgrade_targets import target_identity
from tests.integration import test_certification_upgrade_activation as activation
from tests.integration import test_certification_selection_delivery as delivery_tests
from tests.integration.test_certification_saved_course_selection import histories

repo = activation.repo
pytestmark = activation.pytestmark


async def test_staged_course_is_readable_preparation_and_cannot_accept_writes(repo):
    source, body, upgrades, _ = await activation.setup(repo)
    target = await upgrades.targets.prepare(source.user_id, body['decision_id'])
    history = CourseHistory(repo)
    before = await histories(repo, source.user_id)
    courses = (await history.courses(source.user_id))['courses']
    assert next(item for item in courses if item['enrollment_id'] == source.uuid)['selection_status'] == 'current'
    prepared = next(item for item in courses if item['enrollment_id'] == target['target_enrollment_id'])
    assert prepared['enrollment_state'] == prepared['selection_status'] == 'prepared'
    view = await history.course(source.user_id, prepared['enrollment_id'])
    assert view['read_only'] and view['selection_status'] == 'prepared'
    with pytest.raises(EnrollmentConflict, match='read-only'):
        async with repo.write_boundary(source.user_id, prepared['enrollment_id']):
            pytest.fail('Preparation cannot accept course work')
    assert await histories(repo, source.user_id) == before


@pytest.mark.parametrize('phase', ['before_selection', 'before_promotion', 'after_promotion'])
async def test_interrupted_activation_labels_and_retries_promote_only_the_same_target(repo, monkeypatch, phase):
    source, body, upgrades, _ = await activation.setup(repo, certified=True)
    target_id, _ = target_identity(body['decision_id'])
    async def fail(*args, **kwargs):
        raise RuntimeError('Synthetic lifecycle interruption')
    with monkeypatch.context() as patch:
        if phase == 'before_selection':
            patch.setattr(upgrades, 'commit', fail)
        elif phase == 'before_promotion':
            patch.setattr(upgrades, 'clear_pending', fail)
        else:
            patch.setattr(SelectionJournal, 'clear_pending', fail)
        with pytest.raises(RuntimeError, match='lifecycle interruption'):
            await upgrades.activate(source.user_id, body)
    history = CourseHistory(repo)
    before = await histories(repo, source.user_id)
    view = await history.course(source.user_id, target_id)
    assert view['selection_status'] == ('prepared' if phase == 'before_selection' else 'confirmation_pending')
    assert view['enrollment_state'] == ('active' if phase == 'after_promotion' else 'prepared')
    if phase != 'before_selection':
        with pytest.raises(EnrollmentConflict):
            async with repo.write_boundary(source.user_id, target_id):
                pytest.fail('Even a promoted course must retain its pending-confirmation guard')
        status = await SelectionDelivery(repo).status(source.user_id)
        await SelectionDelivery(repo).confirm(source.user_id, delivery_tests.confirmation(status))
    else:
        await upgrades.activate(source.user_id, body)
    after = await histories(repo, source.user_id)
    for enrollment in before['enrollments']:
        if enrollment['uuid'] == target_id:
            enrollment['state'] = 'active'
    assert after == before
    assert (await history.course(source.user_id, target_id))['selection_status'] == 'current'
    assert (await history.course(source.user_id, source.uuid))['selection_status'] == 'retained'
    before_replay = await histories(repo, source.user_id)
    await upgrades.activate(source.user_id, body)
    assert await histories(repo, source.user_id) == before_replay


@pytest.mark.parametrize('damage', ['state', 'identity'])
async def test_changed_prepared_enrollment_cannot_be_promoted_or_unlocked(repo, monkeypatch, damage):
    source, body, upgrades, _ = await activation.setup(repo)
    original = upgrades.clear_pending
    async def changed(raw, result):
        update = {'state': 'abandoned'} if damage == 'state' else {'created_at': datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)}
        await repo.enrollments.update_one({'uuid': result['target_enrollment_id']}, {'$set': update})
        return await original(raw, result)
    monkeypatch.setattr(upgrades, 'clear_pending', changed)
    with pytest.raises((EnrollmentConflict, CourseCatalogError)):
        await upgrades.activate(source.user_id, body)
    selected = await repo.selections.find_one({'user_id': source.user_id})
    assert selected['pending_transition_id'] == body['request_id']
    with pytest.raises(EnrollmentConflict):
        async with repo.write_boundary(source.user_id, selected['active_enrollment_id']):
            pytest.fail('Changed target identity must not unlock course work')


@pytest.mark.parametrize('view', ['courses', 'course'])
async def test_history_does_not_label_a_selection_that_changed_while_loading(repo, monkeypatch, view):
    source, _, _, _ = await activation.setup(repo)
    history = CourseHistory(repo)
    original = history.selection
    calls = 0
    async def changed(user):
        nonlocal calls
        calls += 1
        result = await original(user)
        return {**result, 'revision': result['revision'] + 1} if calls > 1 else result
    monkeypatch.setattr(history, 'selection', changed)
    before = await histories(repo, source.user_id)
    with pytest.raises(EnrollmentConflict, match='changed while history'):
        if view == 'courses':
            await history.courses(source.user_id)
        else:
            await history.course(source.user_id, source.uuid)
    assert await histories(repo, source.user_id) == before
