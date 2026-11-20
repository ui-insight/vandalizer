"""Acceptance cohorts for optional migration; all records are disposable."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.certification import CertificationProgress
from app.services.certification_versions.attempts import AttemptRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.saved_course_selection import SavedCourseSelectionRepository
from app.services.certification_versions.writes import save_progress
from tests.integration import test_certification_upgrade_activation as activation
from tests.integration.test_certification_saved_course_selection import histories

repo = activation.repo
pytestmark = activation.pytestmark


async def partial(repo):
    await CertificationProgress(user_id='upgrade-choice-learner', total_xp=125, modules={
        'foundations': {'completed': True, 'stars': 2, 'xp_earned': 125, 'completed_at': '2025-02-03'},
        'ai_literacy': {'completed': False, 'attempts': 2, 'self_assessment': {'reflection': 'Original unfinished answer'},
                        'provisioned_docs': ['original-partial-lab']},
    }, learning_position={'module_id': 'ai_literacy', 'lesson_id': 'original-partial-lesson'},
        position_revision=7, lab_folder_id='original-partial-folder').insert()
    return await activation.setup(repo, preserve_existing=True)


async def test_partial_modules_answers_places_and_labs_survive_upgrade_return_and_resume(repo):
    source, request, upgrades, _ = await partial(repo)
    original = await histories(repo, source.user_id)
    selected = await upgrades.activate(source.user_id, request)
    target_id = selected['target_enrollment_id']
    async with repo.write_boundary(source.user_id, target_id) as progress:
        progress.modules = {'ai_literacy': {'completed': False, 'self_assessment': {'reflection': 'New unfinished answer'},
                                          'provisioned_docs': ['new-partial-lab']}}
        progress.lab_folder_id = 'new-partial-folder'
        progress.learning_position = {'module_id': 'ai_literacy', 'lesson_id': 'new-partial-lesson'}
        progress.position_revision = 4
        await save_progress(progress)
    both = await histories(repo, source.user_id)
    assert original['progress'][0] in both['progress']
    assert source.provenance == 'legacy_version_unknown'
    switches = SavedCourseSelectionRepository(repo)
    for action, destination in [('return_to_original_course', source.uuid), ('resume_upgraded_course', target_id)]:
        preview = await switches.preview(source.user_id, request['request_id'], action)
        result = await switches.select(source.user_id, {'request_id': uuid4().hex, 'activation_id': request['request_id'],
            'action': action, 'preview_sha256': preview['preview_sha256'],
            'consent': 'select_saved_course_preserving_both_histories_and_credit'})
        assert result['target_enrollment_id'] == destination and result['credit_transferred'] is False
        assert await histories(repo, source.user_id) == both
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 125
    assert (await repo.read_progress(source.user_id, target_id)).total_xp == 0


async def test_mid_assessment_original_snapshot_blocks_switch_without_losing_partial_work(repo):
    source, request, upgrades, _ = await partial(repo)
    attempts = AttemptRepository()
    async with repo.write_boundary(source.user_id, source.uuid, operation='complete_module') as progress:
        record, created = await attempts.begin(CourseOperation(source.user_id, repo.catalog.load(source.course_version), progress, True),
            'ai_literacy', uuid4().hex)
        assert created and record['state'] == 'evaluating'
        while_running = await histories(repo, source.user_id)
        with pytest.raises(EnrollmentConflict):
            await upgrades.activate(source.user_id, request)
        assert await histories(repo, source.user_id) == while_running
    saved_attempt = deepcopy(await attempts.records.find_one({'uuid': record['uuid']}))
    before = await histories(repo, source.user_id)
    with pytest.raises(EnrollmentConflict):
        await upgrades.activate(source.user_id, request)
    assert await attempts.records.find_one({'uuid': record['uuid']}) == saved_attempt
    assert await histories(repo, source.user_id) == before
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 1
    snapshot = AttemptRepository.payload(saved_attempt, 'progress')
    assert snapshot['modules']['ai_literacy']['self_assessment']['reflection'] == 'Original unfinished answer'


async def test_duplicate_legacy_cohort_is_not_silently_merged_selected_or_reset(repo):
    for xp, answer in [(100, 'First original answer'), (200, 'Second original answer')]:
        await CertificationProgress(user_id='duplicate-cohort', total_xp=xp,
            modules={'ai_literacy': {'self_assessment': {'reflection': answer}}}).insert()
    before = await repo.progress.find({'user_id': 'duplicate-cohort'}).sort('_id', 1).to_list(None)
    for _ in range(2):
        with pytest.raises(EnrollmentConflict, match='Multiple legacy'):
            await repo.ensure_initial('duplicate-cohort')
    assert await repo.progress.find({'user_id': 'duplicate-cohort'}).sort('_id', 1).to_list(None) == before
    assert await repo.enrollments.count_documents({'user_id': 'duplicate-cohort'}) == 0
    assert await repo.selections.count_documents({'user_id': 'duplicate-cohort'}) == 0
