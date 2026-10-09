"""Exact suite plans and explicit approve/hold choices without provider calls."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_validation_inputs as input_fixtures
from tests.integration.test_certification_validation_suites import request as suite_request, submit as submit_suite
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabInput, CertificationLearnerDecision, CertificationLabExecution
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.validation_approval import ValidationScopeRepository
from app.services.certification_versions.validation_plan import validation_plan
from app.services.certification_versions.validation_preparation import ValidationPreparation

repo = input_fixtures.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await input_fixtures.fixture(repo)
    f.snapshot = await input_fixtures.capture(repo, f)
    f.suite = await submit_suite(repo, f, suite_request(f, f.snapshot))
    f.plan_body = {'request_id': uuid4().hex, 'input_snapshot_id': f.snapshot['uuid'],
        'input_snapshot_sha256': encode(f.snapshot)[1], 'suite_id': f.suite['uuid'], 'suite_record_sha256': encode(f.suite)[1],
        'case_sha256': f.case.digest, 'consent': 'prepare_complete_validation_suite'}
    return f


async def prepare(repo, f, config=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_validation_suite') as progress:
        return await ValidationPreparation().prepare(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.plan_body, LAB_RUNTIME if config is None else config, actor_user_id=actor or f.learner.user_id)


async def scope(repo, f, run, *, choice='approve', body=None):
    body = body or {'request_id': uuid4().hex, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'case_sha256': f.case.digest, 'choice': choice, 'reason': 'I inspected both complete sources, all expectations and the exact fields and model before choosing this scope.',
        'consent': 'save_validation_suite_scope_decision'}
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='approve_validation_suite') as progress:
        return await ValidationScopeRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            body, actor_user_id=f.learner.user_id)


async def test_preparation_binds_both_full_sources_models_and_original_expectations(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as provider:
        run = await prepare(repo, f)
        plan = run['plan']
        assert run['state'] == 'prepared' and plan['phase'] == 'original'
        assert plan['model_names'] == ['synthetic-model']
        assert plan['suite_sha256'] == f.suite['suite_sha256']
        assert len(plan['case_plans']) == 2
        for stage, source in zip(plan['case_plans'], f.snapshot['documents']):
            assert stage['doc_texts'] == ['\n\n'.join(source['pages'])]
            assert len(stage['field_keys']) == len(stage['field_metadata']) == 3
        assert 'synthetic-secret' not in encode(plan)[0]
        decision = await scope(repo, f, run)
        assert decision['submission']['choice'] == 'approve'
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_one({'uuid': f.suite['uuid']})
        await f.artifact.delete()
        reread = await prepare(repo, f, config={})
        assert reread['plan'] == plan and reread['scope_decision_id'] == decision['uuid']
        provider.assert_not_called()
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_a_new_hold_is_not_replaced_by_old_approval_replay(repo):
    f = await fixture(repo)
    run = await prepare(repo, f)
    approved = await scope(repo, f, run)
    held = await scope(repo, f, run, choice='hold')
    assert await scope(repo, f, run, body=approved['submission']) == approved
    latest = await ValidationPreparation().get(f.learner.user_id, run['run_id'])
    assert latest['scope_decision_id'] == held['uuid']
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='inspect_approval') as progress:
        with pytest.raises(EnrollmentConflict):
            await ValidationScopeRepository().authorize(CourseOperation(f.learner.user_id, f.package, progress, True), latest)


@pytest.mark.parametrize('change', ['actor', 'capture', 'suite', 'capture_hash', 'suite_hash', 'case', 'retest_id_only',
    'retest_hash_only', 'missing_original', 'different_original_revision', 'unconfigured_model', 'image_mode', 'client_authority'])
async def test_invalid_plan_never_claims_or_executes_a_run(repo, change):
    f = await fixture(repo)
    config = deepcopy(LAB_RUNTIME)
    if change in ('capture', 'suite'):
        f.plan_body['input_snapshot_id' if change == 'capture' else 'suite_id'] = uuid4().hex
    elif change in ('capture_hash', 'suite_hash', 'case'):
        f.plan_body[{'capture_hash': 'input_snapshot_sha256', 'suite_hash': 'suite_record_sha256', 'case': 'case_sha256'}[change]] = '0' * 64
    elif change in ('retest_id_only', 'retest_hash_only', 'missing_original'):
        if change != 'retest_hash_only':
            f.plan_body['original_run_id'] = uuid4().hex
        if change != 'retest_id_only':
            f.plan_body['original_run_sha256'] = '0' * 64
    elif change == 'different_original_revision':
        f.fields[1].searchphrase += ' Changed before original run'
        await f.fields[1].save()
        f.body['request_id'] = uuid4().hex
        other = await input_fixtures.capture(repo, f)
        f.plan_body.update(input_snapshot_id=other['uuid'], input_snapshot_sha256=encode(other)[1])
    elif change == 'unconfigured_model':
        config['available_models'] = []
    elif change == 'image_mode':
        f.artifact.extraction_config = {'use_images': True}
        await f.artifact.save()
        f.body['request_id'] = uuid4().hex
        f.snapshot = await input_fixtures.capture(repo, f)
        f.suite = await submit_suite(repo, f, suite_request(f, f.snapshot))
        f.plan_body.update(input_snapshot_id=f.snapshot['uuid'], input_snapshot_sha256=encode(f.snapshot)[1],
                           suite_id=f.suite['uuid'], suite_record_sha256=encode(f.suite)[1])
    elif change == 'client_authority':
        f.plan_body['approved'] = True
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as provider:
        with pytest.raises(ValueError):
            await prepare(repo, f, config=config, actor='foreign' if change == 'actor' else None)
        provider.assert_not_called()
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == 0


@pytest.mark.parametrize('change', ['capture', 'suite', 'scope', 'authority', 'phase'])
async def test_rehashed_nested_plan_changes_do_not_create_valid_originals(repo, change):
    f = await fixture(repo)
    run = await prepare(repo, f)
    plan = deepcopy(run['plan'])
    if change == 'capture':
        plan['input_snapshot']['artifact']['fields'][0]['searchphrase'] = 'Changed instruction'
    elif change == 'suite':
        plan['suite']['test_cases'][0]['expectations'][0]['expected_value'] = 'Changed name'
    elif change == 'scope':
        plan['approval_requirement']['question']['prompt'] = 'Approve all future actions'
    elif change == 'authority':
        plan['execution_authorized'] = True
    else:
        plan['phase'] = 'unsupported'
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    raw['plan_json'], raw['plan_sha256'] = encode(plan)
    with pytest.raises(CourseCatalogError):
        ValidationPreparation.decode(raw)


async def test_resolved_plan_rejects_retest_without_actual_semantic_failure(repo):
    f = await fixture(repo)
    original = await prepare(repo, f)
    f.fields[1].searchphrase += ' Repair the full-project instruction'
    await f.fields[1].save()
    f.body['request_id'] = uuid4().hex
    corrected = await input_fixtures.capture(repo, f)
    with pytest.raises(EnrollmentConflict, match='completed run'):
        validation_plan(corrected, f.suite, f.case, LAB_RUNTIME, original_run=original)
