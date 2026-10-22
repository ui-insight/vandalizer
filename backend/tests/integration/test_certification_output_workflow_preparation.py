"""Output preparation and explicit scope decisions preserve the original work."""
from copy import deepcopy
import os
from uuid import uuid4

import pytest

from tests.integration import test_certification_output_workflow_plan as planning_fixtures
from app.models.certification import CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision
from app.services.certification_versions.output_workflow_preparation import OutputWorkflowPreparation
from app.services.certification_versions.output_workflow_approval import OutputScopeRepository
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_workflow_approval import ConnectedScopeRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = planning_fixtures.repo


async def fixture(repo):
    f = await planning_fixtures.fixture(repo)
    f.plan_body = {'request_id': uuid4().hex, 'input_snapshot_id': f.saved['uuid'],
        'input_snapshot_sha256': encode(f.saved)[1], 'case_sha256': f.case.digest,
        'consent': 'prepare_output_workflow_plan'}
    return f


async def prepare(repo, f, config=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='prepare_output_workflow') as progress:
        return await OutputWorkflowPreparation().prepare(
            CourseOperation(f.learner.user_id, f.package, progress, True), f.plan_body,
            planning_fixtures.RUNTIME if config is None else config,
            actor_user_id=f.learner.user_id, default_model='report-model')


def scope_body(f, run, choice='approve'):
    return {'request_id': uuid4().hex, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'case_sha256': f.case.digest, 'choice': choice, 'reason': 'I inspected the saved source, source and internal-only PDF/CSV generation.',
        'consent': 'save_output_workflow_scope_decision'}


async def decide(repo, f, body):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='decide_output_workflow_scope') as progress:
        return await OutputScopeRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            body, actor_user_id=f.learner.user_id)


async def test_plan_history_survives_source_capture_deletion_and_unavailable_runtime(repo):
    f = await fixture(repo)
    run = await prepare(repo, f)
    assert run['state'] == 'prepared' and run['authorization'] is None
    await CertificationLabInput.get_motor_collection().delete_many({})
    await f.workflow.delete()
    await f.document.delete()
    assert await prepare(repo, f, config={}) == run
    assert await OutputWorkflowPreparation().get('foreign', run['run_id']) is None
    decision = await decide(repo, f, scope_body(f, run))
    current = await OutputWorkflowPreparation().get(f.learner.user_id, run['run_id'])
    assert current['scope_decision_id'] == decision['uuid']
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='check_output_authorization') as progress:
        operation = CourseOperation(f.learner.user_id, f.package, progress, True)
        authorization = await OutputScopeRepository().authorize(operation, current)
        assert authorization['decision'] == decision
        with pytest.raises(EnrollmentConflict, match='generation executor'):
            await OutputWorkflowPreparation().execute(operation, current)
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


async def test_new_hold_cannot_be_replaced_by_old_approval_replay(repo):
    f = await fixture(repo)
    run = await prepare(repo, f)
    approved_body = scope_body(f, run)
    approved = await decide(repo, f, approved_body)
    held = await decide(repo, f, scope_body(f, run, 'hold'))
    assert held['previous_scope_decision_id'] == approved['uuid']
    assert await decide(repo, f, approved_body) == approved
    current = await OutputWorkflowPreparation().get(f.learner.user_id, run['run_id'])
    assert current['scope_decision_id'] == held['uuid']
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='check_hold') as progress:
        with pytest.raises(EnrollmentConflict, match='latest scope'):
            await OutputScopeRepository().authorize(CourseOperation(f.learner.user_id, f.package, progress, True), current)


@pytest.mark.parametrize('change', ['missing_capture', 'capture_hash', 'case', 'reused_request', 'oversize'])
async def test_plan_requires_exact_owned_capture_and_bounded_immutable_request(repo, monkeypatch, change):
    from app.services.certification_versions import output_workflow_preparation
    f = await fixture(repo)
    existing = None
    if change == 'missing_capture':
        f.plan_body['input_snapshot_id'] = uuid4().hex
    elif change == 'capture_hash':
        f.plan_body['input_snapshot_sha256'] = 'a' * 64
    elif change == 'case':
        f.plan_body['case_sha256'] = 'a' * 64
    elif change == 'reused_request':
        existing = await prepare(repo, f)
        f.plan_body['input_snapshot_id'] = uuid4().hex
    else:
        monkeypatch.setattr(output_workflow_preparation, 'MAX_PLAN_BYTES', 100)
    with pytest.raises(EnrollmentConflict):
        await prepare(repo, f)
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == (1 if existing else 0)


@pytest.mark.parametrize('change', ['plan', 'case', 'actor', 'wrong_scope_protocol'])
async def test_scope_cannot_approve_other_work_or_use_connected_protocol(repo, change):
    f = await fixture(repo)
    run = await prepare(repo, f)
    body = scope_body(f, run)
    if change == 'plan':
        body['plan_sha256'] = 'a' * 64
    elif change == 'case':
        body['case_sha256'] = 'a' * 64
    if change == 'wrong_scope_protocol':
        body['consent'] = 'save_connected_workflow_scope_decision'
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='check_output_scope') as progress:
        service = ConnectedScopeRepository() if change == 'wrong_scope_protocol' else OutputScopeRepository()
        with pytest.raises((EnrollmentConflict, CourseCatalogError)):
            await service.submit(CourseOperation(f.learner.user_id, f.package, progress, True), body,
                actor_user_id='foreign' if change == 'actor' else f.learner.user_id)
    assert await CertificationLearnerDecision.get_motor_collection().count_documents({}) == 0


@pytest.mark.parametrize('change', ['source_pdf', 'scope_question', 'credit', 'snapshot_link'])
async def test_plan_rejects_rehashed_inner_evidence_or_authority_corruption(repo, change):
    f = await fixture(repo)
    run = await prepare(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    plan = deepcopy(run['plan'])
    if change == 'source_pdf':
        plan['input_snapshot']['documents'][0]['source_sha256'] = 'a' * 64
    elif change == 'scope_question':
        plan['approval_requirement']['question']['prompt'] = 'Approve external delivery'
    elif change == 'credit':
        plan['credit_awarded'] = True
    else:
        plan['input_snapshot_sha256'] = 'a' * 64
    raw['plan_json'], raw['plan_sha256'] = encode(plan)
    with pytest.raises(CourseCatalogError):
        OutputWorkflowPreparation.decode(raw)
