"""Explicit original receipts, never a best historical score or a credit write."""
import json
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.certification import CertificationCredential, CertificationReviewAttempt
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.module_readiness import ModuleReadiness
from app.services.certification_versions.review_delivery import SavedReviewUnavailable
from app.services.certification_versions.scenario_submissions import module_bank
from tests.integration import test_certification_enrollments as existing
from tests.integration import test_certification_validation_reviews as validation

repo = existing.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


def assert_draft(result):
    assert result['read_only'] is True
    assert result['credit_awarded'] is result['module_completion_eligible'] is result['staff_review_required'] is False


async def test_scenario_selection_preserves_the_chosen_failure_despite_later_pass(repo):
    source, package, bank, answers = await existing.scenario_fixture(repo)
    failed, passed = uuid4().hex, uuid4().hex
    await existing.submit_scenario(repo, source, package, bank, {}, failed)
    await existing.submit_scenario(repo, source, package, bank, answers, passed)
    before = await repo.progress.find_one({'user_id': source.user_id})
    reader = ModuleReadiness(repo)
    empty = await reader.preview(source.user_id, source.uuid, bank.module_id)
    assert empty['status'] == 'selection_required' and empty['selected_receipts'] == []
    old = await reader.preview(source.user_id, source.uuid, bank.module_id, scenario_attempt_id=failed)
    assert old['status'] == 'revision_required' and not old['all_required_outcomes_supported']
    assert {item['attempt_id'] for item in old['outcomes']} == {failed}
    current = await reader.preview(source.user_id, source.uuid, bank.module_id, scenario_attempt_id=passed)
    assert current['status'] == 'requirements_supported' and current['all_required_outcomes_supported']
    assert {item['state'] for item in current['outcomes']} == {'supported'}
    assert len(current['outcomes']) == 3
    for result in (empty, old, current):
        assert_draft(result)
    assert await repo.progress.find_one({'user_id': source.user_id}) == before
    assert await CertificationCredential.get_motor_collection().count_documents({}) == 0


@pytest.mark.parametrize('state', ['prepared', 'supported', 'revision', 'unavailable', 'corrupt'])
async def test_practical_receipt_states_and_integrity_are_preserved(repo, state):
    source, package, _, _, run, _ = await existing.trusted_review_fixture(repo)
    prepared = await existing.prepare_trusted_review(repo, source, package, run['run_id'])
    async def response(name, config, payload):
        result = await existing.supported_review(name, config, payload)
        if state == 'revision':
            result['outcomes'][0].update(verdict='unclear', revision_instruction='Compare the saved source with the assigned agency before approving it.')
        return result
    judge = AsyncMock(side_effect=RuntimeError('Synthetic provider failure') if state == 'unavailable' else response)
    if state != 'prepared':
        await existing.evaluate_review(repo, source, package, prepared['attempt_id'], judge)
    records = CertificationReviewAttempt.get_motor_collection()
    if state == 'corrupt':
        raw = await records.find_one({'uuid': prepared['attempt_id']})
        result = json.loads(raw['result_json'])
        result['assessment']['deterministic_outcomes'] = []
        serialized, digest = encode(result)
        await records.update_one({'uuid': prepared['attempt_id']}, {'$set': {'result_json': serialized, 'result_sha256': digest}})
    before = await repo.progress.find_one({'user_id': source.user_id})
    receipt = await records.find_one({'uuid': prepared['attempt_id']})
    read = ModuleReadiness(repo).preview(source.user_id, source.uuid, 'foundations', review_attempt_id=prepared['attempt_id'])
    if state == 'corrupt':
        with pytest.raises(CourseCatalogError, match='reconciliation'):
            await read
    else:
        result = await read
        assert result['status'] == {'prepared': 'assessment_pending', 'supported': 'requirements_supported', 'revision': 'revision_required', 'unavailable': 'grading_unavailable'}[state]
        assert result['all_required_outcomes_supported'] is (state == 'supported')
        assert len(result['outcomes']) == 3
        assert_draft(result)
        assert result['selected_receipts'][0]['record_sha256'] == prepared['record_sha256']
    assert judge.await_count == (0 if state == 'prepared' else 1)
    assert await repo.progress.find_one({'user_id': source.user_id}) == before
    assert await records.find_one({'uuid': prepared['attempt_id']}) == receipt
    with pytest.raises(EnrollmentConflict, match='another module'):
        await ModuleReadiness(repo).preview(source.user_id, source.uuid, 'extraction_engine', review_attempt_id=prepared['attempt_id'])


@pytest.mark.parametrize('wrong_execution', [False, True])
async def test_mixed_module_requires_both_selected_receipts_and_retains_scenario_failure(repo, wrong_execution):
    f = await validation.fixture(repo, corrected_wrong=wrong_execution)
    submission = await validation.submit(repo, f)
    prepared = await validation.prepare(repo, f, submission['uuid'])
    judge = AsyncMock(side_effect=existing.supported_review)
    await existing.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge)
    bank = module_bank(f.package, 'validation_qa')
    failed, passed = uuid4().hex, uuid4().hex
    await existing.submit_scenario(repo, f.learner, f.package, bank, {}, failed)
    await existing.submit_scenario(repo, f.learner, f.package, bank, {q.id: q.correct_choice_id for q in bank.questions}, passed)
    reader = ModuleReadiness(repo)
    before = await repo.progress.find_one({'user_id': f.learner.user_id})
    async def preview(**selected):
        result = await reader.preview(f.learner.user_id, f.learner.uuid, 'validation_qa', **selected)
        assert_draft(result)
        return result
    only_review = await preview(review_attempt_id=prepared['attempt_id'])
    assert only_review['status'] == ('revision_required' if wrong_execution else 'selection_required')
    if not wrong_execution:
        assert [item['state'] for item in only_review['outcomes']].count('supported') == 2
    only_scenario = await preview(scenario_attempt_id=passed)
    assert only_scenario['status'] == 'selection_required'
    assert [item['state'] for item in only_scenario['outcomes']].count('supported') == 1
    older_failure = await preview(review_attempt_id=prepared['attempt_id'], scenario_attempt_id=failed)
    assert older_failure['status'] == 'revision_required'
    complete = await preview(review_attempt_id=prepared['attempt_id'], scenario_attempt_id=passed)
    assert complete['all_required_outcomes_supported'] is (not wrong_execution)
    assert complete['status'] == ('revision_required' if wrong_execution else 'requirements_supported')
    assert len(complete['selected_receipts']) == 2
    assert await repo.progress.find_one({'user_id': f.learner.user_id}) == before
    judge.assert_awaited_once()


async def test_cross_owner_cross_module_and_inapplicable_selections_are_rejected(repo):
    source, package, bank, answers = await existing.scenario_fixture(repo)
    request_id = uuid4().hex
    await existing.submit_scenario(repo, source, package, bank, answers, request_id)
    reader = ModuleReadiness(repo)
    for module_id, selected in [('ai_literacy', {'review_attempt_id': request_id}),
                                ('foundations', {'scenario_attempt_id': request_id}),
                                ('missing_module', {}), ('ai_literacy', {'scenario_attempt_id': ''})]:
        with pytest.raises(EnrollmentConflict):
            await reader.preview(source.user_id, source.uuid, module_id, **selected)
    with pytest.raises(EnrollmentConflict):
        await reader.preview('foreign', source.uuid, 'ai_literacy', scenario_attempt_id=request_id)
    other = await repo.ensure_initial('another-learner')
    with pytest.raises(SavedReviewUnavailable):
        await reader.preview(other.user_id, other.uuid, 'ai_literacy', scenario_attempt_id=request_id)
    with pytest.raises(SavedReviewUnavailable):
        await reader.preview(source.user_id, source.uuid, 'validation_qa', scenario_attempt_id=request_id)
    with pytest.raises(SavedReviewUnavailable):
        await reader.preview(source.user_id, source.uuid, 'foundations', review_attempt_id=uuid4().hex)


async def test_legacy_participation_is_not_competency_evidence(repo):
    source = await repo.ensure_initial('legacy-reader')
    with pytest.raises(EnrollmentConflict, match='no competency outcomes'):
        await ModuleReadiness(repo).preview(source.user_id, source.uuid, 'foundations')
