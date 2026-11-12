"""An accepted choice stays exact while the current enrollment is write-locked."""
from uuid import uuid4

from bson import ObjectId
import pytest

from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.transition_preview import TransitionPreview
from app.services.certification_versions.upgrade_comparison import UpgradeUnavailable
from app.services.certification_versions.writes import require_lease
from tests.integration import test_certification_upgrade_decisions as choices
from tests.integration import test_certification_enrollments as fixtures

repo = choices.repo
pytestmark = choices.pytestmark


async def test_exact_choice_revalidates_under_lock_and_repeated_clean_guards_do_not_expire_consent(repo):
    source, target, body, decisions = await choices.setup(repo)
    accepted = await decisions.accept(source.user_id, body)
    original = accepted.model_dump_json()
    for _ in range(2):
        async with decisions.hold_reviewed_choice(source.user_id, body['request_id']) as (record, progress, package):
            assert record.model_dump_json() == original
            assert progress.enrollment_id == source.uuid and package.manifest.release_id == target
            assert require_lease(source.user_id, source.uuid)
            assert (await repo.selections.find_one({'user_id': source.user_id}))['in_flight_writes'] == 1
            with pytest.raises(EnrollmentConflict, match='in flight'):
                async with repo.write_boundary(source.user_id, source.uuid):
                    pytest.fail('A competing certification write entered the held boundary')
        assert (await repo.selections.find_one({'user_id': source.user_id}))['in_flight_writes'] == 0
    after = await repo.read_progress(source.user_id, source.uuid)
    assert after.total_xp == 0 and not after.certified
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert (await decisions.get(source.user_id, body['request_id'])).model_dump_json() == original


@pytest.mark.parametrize('change', ['xp', 'saved_place', 'new_prepared_run', 'selection_revision'])
async def test_post_consent_work_changes_require_a_new_choice(repo, change):
    source, _, body, decisions = await choices.setup(repo)
    original = await decisions.accept(source.user_id, body)
    if change == 'xp':
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'total_xp': 50}})
    elif change == 'saved_place':
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'position_revision': 1}})
    elif change == 'new_prepared_run':
        await fixtures.insert_execution_summary(source.user_id, source.uuid, 'prepared')
    else:
        await repo.selections.update_one({'user_id': source.user_id}, {'$inc': {'revision': 1}})
    with pytest.raises(EnrollmentConflict, match='changed after the choice'):
        async with decisions.hold_reviewed_choice(source.user_id, body['request_id']):
            pytest.fail('Stale consent was renewed')
    assert await decisions.get(source.user_id, body['request_id']) == original
    assert (await repo.selections.find_one({'user_id': source.user_id}))['in_flight_writes'] == 0


async def test_withdrawn_target_is_rejected_without_selecting_a_different_course(repo):
    source, target, body, decisions = await choices.setup(repo)
    await decisions.accept(source.user_id, body)
    fixtures.set_upgrade_offer(repo, source.course_version, target, enabled=False)
    with pytest.raises(UpgradeUnavailable):
        async with decisions.hold_reviewed_choice(source.user_id, body['request_id']):
            pytest.fail('Withdrawn target was offered')
    assert (await repo.current(source.user_id)).uuid == source.uuid


async def test_revoked_guard_cannot_hide_itself_from_the_preview(repo, monkeypatch):
    source, _, body, decisions = await choices.setup(repo)
    await decisions.accept(source.user_id, body)
    original = TransitionPreview.inspect
    async def revoked(preview, *args, **kwargs):
        lease = require_lease(source.user_id, source.uuid)
        await repo.progress.update_one(lease.progress_filter(), {'$set': {'_certification_write_fence': uuid4().hex}})
        return await original(preview, *args, **kwargs)
    monkeypatch.setattr(TransitionPreview, 'inspect', revoked)
    with pytest.raises(EnrollmentConflict, match='no longer owns'):
        async with decisions.hold_reviewed_choice(source.user_id, body['request_id']):
            pytest.fail('Revoked ownership was accepted')


async def test_owned_guard_normalization_requires_an_actual_matching_write_boundary(repo):
    source, target, _, _ = await choices.setup(repo)
    with pytest.raises(EnrollmentConflict, match='does not hold'):
        await TransitionPreview(repo).inspect(source.user_id, source.uuid, target, _held_write=True)


async def test_foreign_decision_is_unavailable_before_acquiring_a_source_guard(repo):
    source, _, body, decisions = await choices.setup(repo)
    await decisions.accept(source.user_id, body)
    with pytest.raises(EnrollmentConflict, match='unavailable'):
        async with decisions.hold_reviewed_choice('foreign', body['request_id']):
            pytest.fail('Foreign consent was accepted')
    assert (await repo.selections.find_one({'user_id': source.user_id}))['in_flight_writes'] == 0


async def test_withdrawal_during_revalidation_is_rechecked_before_yield(repo, monkeypatch):
    source, target, body, decisions = await choices.setup(repo)
    await decisions.accept(source.user_id, body)
    original = TransitionPreview.inspect
    async def withdrawn(preview, *args, **kwargs):
        result = await original(preview, *args, **kwargs)
        fixtures.set_upgrade_offer(repo, source.course_version, target, enabled=False)
        return result
    monkeypatch.setattr(TransitionPreview, 'inspect', withdrawn)
    with pytest.raises(UpgradeUnavailable):
        async with decisions.hold_reviewed_choice(source.user_id, body['request_id']):
            pytest.fail('The offer was withdrawn during review')
