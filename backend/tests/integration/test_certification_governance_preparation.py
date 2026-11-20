"""Exact capstone preparation follows a real saved learner scope correction."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_scope as scope_fixture
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.governance_approval import GovernanceApprovalRepository
from app.services.certification_versions.governance_preparation import GovernancePreparation
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

repo = scope_fixture.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await scope_fixture.fixture(repo)
    f.correction = await scope_fixture.submit(repo, f)
    f.plan_body = {'request_id': uuid4().hex, 'input_snapshot_id': f.snapshot['uuid'], 'input_snapshot_sha256': encode(f.snapshot)[1],
        'scope_correction_id': f.correction['uuid'], 'scope_correction_sha256': encode(f.correction)[1],
        'case_sha256': f.case.digest, 'consent': 'prepare_original_bounded_capstone_extraction'}
    return f


async def prepare(repo, f, actor=None, config=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_capstone') as progress:
        return await GovernancePreparation().prepare(CourseOperation(f.learner.user_id, f.package, progress, True), f.plan_body,
            LAB_RUNTIME if config is None else config, actor_user_id=actor or f.learner.user_id)


async def scope(repo, f, run, *, choice='approve', body=None):
    body = body or {'request_id': uuid4().hex, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'case_sha256': f.case.digest, 'choice': choice,
        'reason': 'I inspected both complete assigned records, the six-field revision, the flawed original instruction and resolved model. This is only an internal diagnostic run.',
        'consent': 'save_bounded_governance_execution_decision'}
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='approve_capstone') as progress:
        return await GovernanceApprovalRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True), body,
            actor_user_id=f.learner.user_id)


async def test_original_joint_input_and_approval_survive_workspace_deletion_without_dispatch(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        run = await prepare(repo, f)
        stage = run['plan']['extraction_input']
        assert len(stage['doc_texts']) == 1 and len(stage['field_keys']) == 6
        for source in f.snapshot['documents']:
            assert all(page in stage['doc_texts'][0] for page in source['pages'])
        approved = await scope(repo, f, run)
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_one({'uuid': f.correction['uuid']})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        replay = await prepare(repo, f, config={})
        assert replay['plan'] == run['plan'] and replay['scope_decision_id'] == approved['uuid']
        assert await scope(repo, f, run, body=approved['submission']) == approved
        assert await GovernancePreparation().get('foreign', run['run_id']) is None
        engine.assert_not_called()
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_old_approval_cannot_replace_later_hold(repo):
    f = await fixture(repo)
    run = await prepare(repo, f)
    approved = await scope(repo, f, run)
    held = await scope(repo, f, run, choice='hold')
    assert await scope(repo, f, run, body=approved['submission']) == approved
    current = await GovernancePreparation().get(f.learner.user_id, run['run_id'])
    assert current['scope_decision_id'] == held['uuid']
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='check_scope') as progress:
        with pytest.raises(EnrollmentConflict):
            await GovernanceApprovalRepository().authorize(CourseOperation(f.learner.user_id, f.package, progress, True), current)


@pytest.mark.parametrize('change', ['actor', 'capture', 'hash', 'case', 'correction', 'correction_hash', 'phase', 'reuse'])
async def test_original_requires_exact_owned_corrected_scope(repo, change):
    f = await fixture(repo)
    if change == 'capture':
        f.plan_body['input_snapshot_id'] = uuid4().hex
    elif change in ('hash', 'case', 'correction_hash'):
        f.plan_body[{'hash': 'input_snapshot_sha256', 'case': 'case_sha256', 'correction_hash': 'scope_correction_sha256'}[change]] = '0' * 64
    elif change == 'correction':
        f.plan_body['scope_correction_id'] = uuid4().hex
    elif change == 'phase':
        f.plan_body['phase'] = 'repair'
    elif change == 'reuse':
        await prepare(repo, f)
        f.plan_body['case_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        await prepare(repo, f, actor='foreign' if change == 'actor' else None)
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == (1 if change == 'reuse' else 0)


@pytest.mark.parametrize('change', ['input', 'phase', 'source', 'correction', 'authority', 'approval', 'claimed'])
async def test_rehashed_plan_cannot_invent_scope_or_execution(repo, change):
    f = await fixture(repo)
    run = await prepare(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    plan = deepcopy(run['plan'])
    if change == 'input':
        plan['extraction_input']['doc_texts'] = ['Different evidence']
    elif change == 'phase':
        plan['phase'] = 'repair'
    elif change == 'source':
        plan['input_snapshot']['documents'][0]['pages'] = ['Changed source']
    elif change == 'correction':
        plan['scope_correction']['submission']['ongoing_automation'] = 'enable'
    elif change == 'authority':
        plan['external_effects_authorized'] = True
    elif change == 'approval':
        plan['approval_requirement']['question']['phase'] = 'after_execution'
    else:
        raw['state'] = 'executing'
    raw['plan_json'], raw['plan_sha256'] = encode(plan)
    with pytest.raises(CourseCatalogError):
        GovernancePreparation.decode(raw)
