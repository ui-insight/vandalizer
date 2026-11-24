"""Pin requested evidence before grading; retries cannot select different work."""
import json
import os
from uuid import uuid4

import pytest

from app.services.certification_versions.attempts import AttemptRepository
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.recovery import CompletionRecovery
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    source, package, bank, answers = await base.scenario_fixture(repo)
    scenario_id = uuid4().hex
    await base.submit_scenario(repo, source, package, bank, answers, scenario_id)
    return source, package, {'scenario_attempt_id': scenario_id}


async def begin(repo, source, package, request_id, selection=None, module_id='ai_literacy'):
    async with repo.write_boundary(source.user_id, source.uuid, operation='complete_module') as progress:
        operation = CourseOperation(source.user_id, package, progress, True)
        return await AttemptRepository().begin(operation, module_id, request_id, assessment_selection=selection)


async def test_exact_selection_survives_restart_and_is_in_the_recovery_seed(repo):
    source, package, selected = await fixture(repo)
    request_id = uuid4().hex
    async with repo.write_boundary(source.user_id, source.uuid, operation='complete_module') as progress:
        operation = CourseOperation(source.user_id, package, progress, True)
        original, started = await AttemptRepository().begin(operation, 'ai_literacy', request_id, assessment_selection=selected)
        assert started
        marker = await repo.selections.find_one({'user_id': source.user_id})
        seed = marker['active_write']['attempt_seed']
        assert AttemptRepository.assessment_selection(seed) == selected
    serialized = original['assessment_selection_json']
    selected['scenario_attempt_id'] = uuid4().hex
    replay, started = await begin(repo, source, package, request_id)
    assert not started
    assert replay['assessment_selection_json'] == serialized
    assert AttemptRepository.assessment_selection(replay) == json.loads(serialized)
    assert await AttemptRepository().records.count_documents({}) == 1
    saved = await repo.read_progress(source.user_id, source.uuid)
    assert saved.total_xp == 0 and not saved.certified
    assert not saved.modules['ai_literacy'].get('completed')


@pytest.mark.parametrize('state', ['evaluating', 'graded', 'applied', 'rejected', 'failed'])
async def test_same_request_cannot_be_rebound_to_other_evidence_in_any_state(repo, state):
    source, package, selected = await fixture(repo)
    request_id = uuid4().hex
    journal = AttemptRepository()
    async with repo.write_boundary(source.user_id, source.uuid, operation='complete_module') as progress:
        record, _ = await journal.begin(CourseOperation(source.user_id, package, progress, True),
            'ai_literacy', request_id, assessment_selection=selected)
        if state == 'failed':
            await journal.finish(record, {'error': 'Synthetic unavailable evaluation'}, failed=True)
        elif state != 'evaluating':
            record = await journal.graded(record, {'passed': state == 'applied', 'test_fixture': True})
            if state in ('applied', 'rejected'):
                await journal.finish(record, {'module_id': 'ai_literacy'} if state == 'applied' else {'error': 'Synthetic rejected evaluation'})
    before = await journal.records.find_one({'uuid': request_id})
    with pytest.raises(EnrollmentConflict, match='different saved assessment selection'):
        await begin(repo, source, package, request_id, {'scenario_attempt_id': uuid4().hex})
    assert await journal.records.find_one({'uuid': request_id}) == before
    replay, started = await begin(repo, source, package, request_id, selected)
    assert not started and replay['state'] == state
    assert journal.assessment_selection(replay) == selected


@pytest.mark.parametrize('selection', [{}, [], 'latest', {'scenario_attempt_id': ''}, {'review_attempt_id': None},
    {'scenario_attempt_id': 'A' * 32}, {'best_attempt_id': 'a' * 32}, {'scenario_attempt_id': 'a' * 32, 'passed': True}])
async def test_invalid_or_inferred_selection_is_rejected_before_journal_creation(repo, selection):
    source, package, _ = await fixture(repo)
    with pytest.raises(EnrollmentConflict, match='exact references'):
        await begin(repo, source, package, uuid4().hex, selection)
    assert await AttemptRepository().records.count_documents({}) == 0


async def test_saved_selection_integrity_and_request_ownership_are_checked_on_replay(repo):
    source, package, selected = await fixture(repo)
    request_id = uuid4().hex
    await begin(repo, source, package, request_id, selected)
    journal = AttemptRepository()
    with pytest.raises(EnrollmentConflict, match='another learner, module or course'):
        await begin(repo, source, package, request_id, selected, module_id='foundations')
    other = await repo.ensure_initial('other-learner')
    with pytest.raises(EnrollmentConflict, match='another learner, module or course'):
        await begin(repo, other, package, request_id, selected)
    await journal.records.update_one({'uuid': request_id}, {'$set': {'assessment_selection_json': json.dumps({'scenario_attempt_id': uuid4().hex})}})
    with pytest.raises(CourseCatalogError, match='integrity'):
        await begin(repo, source, package, request_id)


async def test_legacy_requests_without_selection_remain_replayable_and_reject_new_outcome_inputs(repo):
    source = await repo.ensure_initial('legacy-reader')
    package = repo.catalog.load(source.course_version)
    request_id = uuid4().hex
    original, _ = await begin(repo, source, package, request_id)
    assert AttemptRepository.assessment_selection(original) is None
    await AttemptRepository().records.update_one({'uuid': request_id}, {'$unset': {'assessment_selection_json': '', 'assessment_selection_sha256': ''}})
    replay, started = await begin(repo, source, package, request_id)
    assert not started and AttemptRepository.assessment_selection(replay) is None
    with pytest.raises(EnrollmentConflict, match='preserved legacy rubric'):
        await begin(repo, source, package, request_id, {'scenario_attempt_id': uuid4().hex})


@pytest.mark.parametrize('corrupt', [False, True])
async def test_explicit_recovery_preserves_or_rejects_the_original_selection(repo, corrupt):
    source, package, selected = await fixture(repo)
    request_id = uuid4().hex
    original, _ = await begin(repo, source, package, request_id, selected)
    journal = AttemptRepository()
    if corrupt:
        await journal.records.update_one({'uuid': request_id}, {'$set': {'assessment_selection_sha256': '0' * 64}})
    recovery = CompletionRecovery(repo)
    pending = recovery.reconcile_attempt(source.user_id, source.uuid, attempt_id=request_id, reason='Synthetic interrupted selected assessment')
    if corrupt:
        with pytest.raises(CourseCatalogError, match='integrity'):
            await pending
        assert (await journal.records.find_one({'uuid': request_id}))['state'] == 'evaluating'
    else:
        result = await pending
        assert result['status'] == 'interrupted_before_grade'
        saved = await journal.records.find_one({'uuid': request_id})
        assert saved['state'] == 'failed'
        assert saved['assessment_selection_json'] == original['assessment_selection_json']
        assert journal.assessment_selection(saved) == selected
