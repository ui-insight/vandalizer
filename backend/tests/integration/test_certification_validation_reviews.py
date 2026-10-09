"""Automatic source-bound suite review cannot reward fabricated or incomplete repair."""
from copy import deepcopy
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_validation_preparation as prep
from tests.integration import test_certification_validation_execution as execution
from tests.integration import test_certification_validation_inputs as inputs
from tests.integration import test_certification_validation_suites as suites
from tests.integration import test_certification_enrollments as enrollment_fixtures
from app.models.certification import CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.validation_reviews import ValidationReviewRepository

repo = inputs.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, *, wrong_expected=False, corrected_wrong=False, incomplete=False):
    f = await prep.fixture(repo)
    if wrong_expected:
        body = suites.request(f, f.snapshot)
        body['expectations'][1]['expected_value'] = '177000'
        f.suite = await suites.submit(repo, f, body)
        f.plan_body.update(suite_id=f.suite['uuid'], suite_record_sha256=encode(f.suite)[1])
    run = await prep.prepare(repo, f)
    approved = await prep.scope(repo, f, run)
    f.execution_body = {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'scope_decision_id': approved['uuid'], 'scope_decision_sha256': encode(approved)[1],
        'consent': 'execute_approved_complete_validation_suite'}
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution.provider(f, wrong=True)):
        f.original = await execution.execute(repo, f)
    f.fields[1].searchphrase = 'Extract the full multi-year project budget, never an annual amount, as a plain USD number.'
    await f.fields[1].save()
    f.body['request_id'] = uuid4().hex
    corrected = await inputs.capture(repo, f)
    f.plan_body.update(request_id=uuid4().hex, input_snapshot_id=corrected['uuid'], input_snapshot_sha256=encode(corrected)[1],
        original_run_id=f.original['run_id'], original_run_sha256=encode(f.original)[1])
    run = await prep.prepare(repo, f)
    approved = await prep.scope(repo, f, run)
    f.execution_body.update(run_id=run['run_id'], plan_sha256=run['plan_sha256'],
        scope_decision_id=approved['uuid'], scope_decision_sha256=encode(approved)[1])
    callback = (lambda **kwargs: []) if incomplete else execution.provider(f, wrong=corrected_wrong)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=callback):
        f.corrected = await execution.execute(repo, f)
    f.review_body = {'request_id': uuid4().hex, 'run_id': f.corrected['run_id'], 'result_sha256': encode(f.corrected['result'])[1],
        'case_sha256': f.case.digest, 'answers': {'repair_review': 'The original NSF result returned USD 177000 instead of the full USD 485000. I corrected the same budget field and reran both complete cases with unchanged source-checked expectations. The NIH budget and absent Co-PI also remain checked; two proposals do not guarantee all future extraction.'},
        'consent': 'save_validation_repair_interpretation'}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_validation_review') as progress:
        return await ValidationReviewRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.review_body, actor_user_id=actor or f.learner.user_id)


async def prepare(repo, f, submission_id, request_id=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_validation_review') as progress:
        return await ReviewAttemptRepository().prepare_from_validation_review(CourseOperation(f.learner.user_id, f.package, progress, True),
            submission_id, request_id or uuid4().hex, actor_user_id=f.learner.user_id,
            model_name='synthetic-reviewer', system_config=enrollment_fixtures.REVIEW_CONFIG)


async def test_full_review_and_linked_revision_survive_live_run_deletion(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    await CertificationLabExecution.get_motor_collection().delete_many({})
    assert await submit(repo, f) == saved
    f.review_body.update(request_id=uuid4().hex, previous_submission_id=saved['uuid'])
    f.review_body['answers']['repair_review'] += ' This revision preserves the earlier answer and all original receipts.'
    revised = await submit(repo, f)
    assert revised['execution'] == saved['execution']
    assert await ValidationReviewRepository().get(f.learner.user_id, saved['uuid']) == saved
    assert await ValidationReviewRepository().get('foreign', saved['uuid']) is None
    prepared = await prepare(repo, f, saved['uuid'])
    evidence = encode(prepared['record']['evidence'])[0]
    assert 'source_pdf_base64' not in evidence and 'authored_case' not in evidence and 'review_guidance' not in evidence
    assert '177000' in evidence and '485000' in evidence and '1250000' in evidence
    assert {e['kind'] for e in prepared['record']['evidence']} == {'source_reference', 'test_case_snapshot', 'artifact_revision', 'validation_receipt', 'learner_decision'}
    await CertificationLearnerDecision.get_motor_collection().delete_many({})
    assert await prepare(repo, f, saved['uuid'], prepared['attempt_id']) == prepared
    judge = AsyncMock(side_effect=enrollment_fixtures.supported_review)
    assessed = await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge)
    assert assessed['result']['assessment']['status'] == 'requirements_supported'
    public = await ReviewDelivery(repo).get(f.learner.user_id, f.learner.uuid, prepared['attempt_id'])
    assert public['assessment_kind'] == 'validation_suite_review_draft' and public['validation_review_submission_id'] == saved['uuid']
    assert public['staff_review_required'] is public['credit_awarded'] is False
    listed = await ReviewDelivery(repo).list(f.learner.user_id, f.learner.uuid, 'validation_qa')
    assert listed['attempts'][0]['validation_review_submission_id'] == saved['uuid']
    assert await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge) == assessed
    assert judge.await_count == 1


@pytest.mark.parametrize('change', ['actor', 'case', 'result', 'missing_run', 'original_only', 'unknown_parent', 'blank', 'extra_evidence', 'reuse'])
async def test_foreign_or_changed_review_cannot_claim_actual_repair(repo, change):
    f = await fixture(repo)
    if change in ('case', 'result'):
        f.review_body[change + '_sha256'] = '0' * 64
    elif change == 'missing_run':
        f.review_body['run_id'] = uuid4().hex
    elif change == 'original_only':
        f.review_body.update(run_id=f.original['run_id'], result_sha256=encode(f.original['result'])[1])
    elif change == 'unknown_parent':
        f.review_body['previous_submission_id'] = uuid4().hex
    elif change == 'blank':
        f.review_body['answers']['repair_review'] = '   '
    elif change == 'extra_evidence':
        f.review_body['passed'] = True
    elif change == 'reuse':
        await submit(repo, f)
        f.review_body['answers']['repair_review'] = 'Changed answer cannot replace the original submission.'
    with pytest.raises(ValueError):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('wrong_expected,corrected_wrong', [(True, False), (False, True)])
async def test_source_checks_veto_a_scripted_favorable_model_verdict(repo, wrong_expected, corrected_wrong):
    f = await fixture(repo, wrong_expected=wrong_expected, corrected_wrong=corrected_wrong)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    judge = AsyncMock(side_effect=enrollment_fixtures.supported_review)
    assessed = await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge)
    result = assessed['result']['assessment']
    assert result['status'] == 'revision_required' and result['passed'] is False
    assert any(o['verdict'] == 'contradicted' for o in result['outcomes'])
    assert all(o['verdict'] == 'supported' for o in result['model_outcomes'])
    assert result['credit_awarded'] is result['staff_review_required'] is False


async def test_unavailable_output_is_not_graded_as_a_learner_failure(repo):
    f = await fixture(repo, incomplete=True)
    saved = await submit(repo, f)
    with pytest.raises(EvidenceAssemblyUnavailable):
        await prepare(repo, f, saved['uuid'])


async def test_technical_judge_retry_preserves_packet_and_never_reexecutes_extraction(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    prepared = await prepare(repo, f, saved['uuid'])
    failed = await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], AsyncMock(side_effect=RuntimeError('synthetic')))
    assert failed['state'] == 'unavailable'
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='retry_validation_judge') as progress:
        retry = await ReviewAttemptRepository().prepare_retry(CourseOperation(f.learner.user_id, f.package, progress, True),
            failed['attempt_id'], uuid4().hex, actor_user_id=f.learner.user_id, system_config=enrollment_fixtures.REVIEW_CONFIG)
    assert retry['record']['evidence'] == prepared['record']['evidence']
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        result = await enrollment_fixtures.evaluate_review(repo, f.learner, f.package, retry['attempt_id'], AsyncMock(side_effect=enrollment_fixtures.supported_review))
        assert result['state'] == 'evaluated'
        engine.assert_not_called()


@pytest.mark.parametrize('change', ['execution', 'answer_hash', 'authority'])
async def test_rehashed_review_cannot_change_its_original_evidence(repo, change):
    f = await fixture(repo)
    saved = deepcopy(await submit(repo, f))
    if change == 'execution':
        saved['execution']['plan_sha256'] = '0' * 64
    elif change == 'answer_hash':
        saved['request_sha256'] = '0' * 64
    else:
        saved['credit_awarded'] = True
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw['record_json'], raw['record_sha256'] = encode(saved)
    with pytest.raises(CourseCatalogError):
        ValidationReviewRepository.decode(raw)
