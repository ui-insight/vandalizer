"""Saved pilot plans and separate approve/hold choices; no execution claims."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_batch_inputs as inputs
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabExecution, CertificationLabInput
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.batch_approval import BatchScopeRepository
from app.services.certification_versions.batch_preparation import BatchPreparation
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

repo = inputs.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await inputs.fixture(repo)
    f.snapshot = await inputs.capture(repo, f)
    f.plan_body = {'request_id': uuid4().hex, 'input_snapshot_id': f.snapshot['uuid'], 'input_snapshot_sha256': encode(f.snapshot)[1],
                   'case_sha256': f.case.digest, 'phase': 'pilot', 'consent': 'prepare_bounded_batch_action'}
    return f


async def prepare(repo, f, actor=None, config=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_batch_action') as progress:
        return await BatchPreparation().prepare(CourseOperation(f.learner.user_id, f.package, progress, True), f.plan_body,
            LAB_RUNTIME if config is None else config, actor_user_id=actor or f.learner.user_id)


async def scope(repo, f, run, *, choice='approve', body=None):
    body = body or {'request_id': uuid4().hex, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'case_sha256': f.case.digest, 'choice': choice, 'reason': 'I inspected both pilot sources, all five fields and this resolved model. The shared layout limits generalization.',
        'consent': 'save_bounded_batch_scope_decision'}
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='approve_batch_action') as progress:
        return await BatchScopeRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True), body,
                                                  actor_user_id=f.learner.user_id)


async def test_owned_pilot_plan_and_original_choice_survive_workspace_deletion(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as provider:
        run = await prepare(repo, f)
        assert run['state'] == 'prepared' and run['plan']['source_ids'] == ['proposal_1', 'proposal_3']
        approved = await scope(repo, f, run)
        assert approved['prompt']['batch_phase'] == 'pilot' and approved['prompt']['case_question_id'] == 'pilot_choice'
        await CertificationLabInput.get_motor_collection().delete_many({})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        replay = await prepare(repo, f, config={})
        assert replay['plan'] == run['plan'] and replay['scope_decision_id'] == approved['uuid']
        assert await scope(repo, f, run, body=approved['submission']) == approved
        provider.assert_not_called()
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_old_approval_replay_does_not_replace_a_new_hold(repo):
    f = await fixture(repo)
    run = await prepare(repo, f)
    approved = await scope(repo, f, run)
    held = await scope(repo, f, run, choice='hold')
    assert await scope(repo, f, run, body=approved['submission']) == approved
    current = await BatchPreparation().get(f.learner.user_id, run['run_id'])
    assert current['scope_decision_id'] == held['uuid']
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='check_batch_scope') as progress:
        with pytest.raises(EnrollmentConflict):
            await BatchScopeRepository().authorize(CourseOperation(f.learner.user_id, f.package, progress, True), current)


@pytest.mark.parametrize('change', ['actor', 'foreign_capture', 'missing_capture', 'digest', 'case', 'phase', 'parent_without_hash', 'reused_identity'])
async def test_wrong_owned_input_or_incomplete_lineage_cannot_prepare(repo, change):
    f = await fixture(repo)
    if change == 'foreign_capture':
        await CertificationLabInput.get_motor_collection().update_one({'uuid': f.snapshot['uuid']}, {'$set': {'user_id': 'foreign'}})
    elif change == 'missing_capture':
        f.plan_body['input_snapshot_id'] = uuid4().hex
    elif change == 'digest':
        f.plan_body['input_snapshot_sha256'] = '0' * 64
    elif change == 'case':
        f.plan_body['case_sha256'] = '0' * 64
    elif change == 'phase':
        f.plan_body['phase'] = 'batch'
    elif change == 'parent_without_hash':
        f.plan_body['parent_run_id'] = uuid4().hex
    elif change == 'reused_identity':
        await prepare(repo, f)
        f.plan_body['case_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        await prepare(repo, f, actor='foreign' if change == 'actor' else None)
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == (1 if change == 'reused_identity' else 0)


@pytest.mark.parametrize('change', ['case_plan', 'approval_phase', 'scope_expansion', 'source', 'credit', 'parent', 'claimed_without_executor'])
async def test_rehashed_plan_cannot_change_original_scope_or_invent_execution(repo, change):
    f = await fixture(repo)
    run = await prepare(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    plan = deepcopy(run['plan'])
    if change == 'case_plan':
        plan['item_plans'][0]['doc_texts'] = ['Unassigned text']
    elif change == 'approval_phase':
        plan['approval_requirement']['question']['batch_phase'] = 'batch'
    elif change == 'scope_expansion':
        plan['source_ids'].insert(1, 'proposal_2')
    elif change == 'source':
        plan['input_snapshot']['documents'][0]['pages'] = ['Changed source']
    elif change == 'credit':
        plan['credit_awarded'] = True
    elif change == 'parent':
        plan['parent_run_id'] = uuid4().hex
    else:
        raw['state'] = 'executing'
    raw['plan_json'], raw['plan_sha256'] = encode(plan)
    with pytest.raises(CourseCatalogError):
        BatchPreparation.decode(raw)
