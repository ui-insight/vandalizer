"""Preserve exact owned budget workflow/calculation evidence in disposable MongoDB."""
from copy import deepcopy
import os
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.integration import test_certification_advanced_calculation_records as calculation_fixtures
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.services.certification_versions.advanced_workflow_inputs import AdvancedWorkflowInputRepository
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.lab_execution import execution_plan
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = calculation_fixtures.repo


async def fixture(repo):
    f = await calculation_fixtures.fixture(repo)
    # Incorrect work is valid evidence. Capture must not replace or bless it.
    f.body['records'][0]['result'] = '45001.00'
    f.calculation = await calculation_fixtures.submit(repo, f)
    f.task = await WorkflowStepTask(name='Prompt', data={'prompt': 'Draft an internal exception memo from the assigned budget.'}).insert()
    f.step = await WorkflowStep(name='Budget review', tasks=[f.task.id]).insert()
    f.workflow = await Workflow(name='Owned budget review', user_id=f.learner.user_id, steps=[f.step.id], share_token='private-share-token').insert()
    f.capture_body = {'request_id': uuid4().hex, 'workflow_id': str(f.workflow.id),
        'calculation_snapshot_id': f.calculation['uuid'], 'calculation_snapshot_sha256': encode(f.calculation)[1],
        'case_sha256': f.case.digest, 'consent': 'capture_budget_workflow_and_method',
        'method_choice': 'Use the available Prompt for interpretation and explicit learner addition for arithmetic. Preserve conflicts in an internal memo without requiring Code access.'}
    return f


async def capture(repo, f, inputs=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='capture_budget_workflow') as progress:
        return await (inputs or AdvancedWorkflowInputRepository()).capture(
            CourseOperation(f.learner.user_id, f.package, progress, True), f.capture_body,
            actor_user_id=actor or f.learner.user_id)


async def test_preserves_workflow_method_and_wrong_calculation_after_live_and_original_deletion(repo):
    f = await fixture(repo)
    saved = await capture(repo, f)
    assert saved['calculation_snapshot'] == f.calculation
    assert saved['calculation_snapshot']['checks']['all_arithmetic_supported'] is False
    assert saved['request']['method_choice'] == f.capture_body['method_choice']
    assert 'share_token' not in saved['artifact']['workflow']
    await f.document.delete()
    await f.workflow.delete()
    await f.step.delete()
    await f.task.delete()
    await CertificationLabInput.get_motor_collection().delete_one({'uuid': f.calculation['uuid']})
    assert await capture(repo, f) == saved
    assert await AdvancedWorkflowInputRepository().get(f.learner.user_id, saved['uuid']) == saved
    assert await AdvancedWorkflowInputRepository().get('foreign', saved['uuid']) is None
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == 0
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0
    with pytest.raises(EnrollmentConflict, match='not executable'):
        execution_plan(saved, {})


@pytest.mark.parametrize('change', ['actor', 'case', 'missing_calculation', 'calculation_hash', 'foreign_calculation',
                                  'foreign_workflow', 'changed_workflow', 'blank_method', 'client_evidence', 'consent'])
async def test_capture_rejects_unbound_or_fabricated_evidence(repo, monkeypatch, change):
    f = await fixture(repo)
    inputs = AdvancedWorkflowInputRepository()
    if change == 'case':
        f.capture_body['case_sha256'] = 'a' * 64
    elif change == 'missing_calculation':
        f.capture_body['calculation_snapshot_id'] = uuid4().hex
    elif change == 'calculation_hash':
        f.capture_body['calculation_snapshot_sha256'] = 'a' * 64
    elif change == 'foreign_calculation':
        await CertificationLabInput.get_motor_collection().update_one({'uuid': f.calculation['uuid']}, {'$set': {'user_id': 'foreign'}})
    elif change == 'foreign_workflow':
        f.workflow.user_id = 'foreign'
        await f.workflow.save()
    elif change == 'changed_workflow':
        original = inputs._read_artifact
        calls = 0

        async def racing_read(*args):
            nonlocal calls
            artifact = await original(*args)
            calls += 1
            if calls == 1:
                f.task.data['prompt'] = 'Changed instructions after inspection'
                await f.task.save()
            return artifact

        monkeypatch.setattr(inputs, '_read_artifact', racing_read)
    elif change == 'blank_method':
        f.capture_body['method_choice'] = ' ' * 50
    elif change == 'client_evidence':
        f.capture_body['artifact'] = {'workflow': 'fabricated'}
    elif change == 'consent':
        f.capture_body['consent'] = 'execute_workflow'
    with pytest.raises((EnrollmentConflict, ValidationError)):
        await capture(repo, f, inputs, actor='foreign' if change == 'actor' else None)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 1


@pytest.mark.parametrize('change', ['calculation', 'method', 'workflow', 'authority', 'case'])
async def test_rehashed_nested_corruption_is_rejected(repo, change):
    f = await fixture(repo)
    saved = await capture(repo, f)
    raw = await CertificationLabInput.get_motor_collection().find_one({'uuid': saved['uuid']})
    altered = deepcopy(saved)
    if change == 'calculation':
        altered['calculation_snapshot']['checks']['all_arithmetic_supported'] = True
        altered['request']['calculation_snapshot_sha256'] = encode(altered['calculation_snapshot'])[1]
        altered['request_sha256'] = encode(altered['request'])[1]
    elif change == 'method':
        altered['request']['method_choice'] = 'I claim every result is correct without checking its sources.'
    elif change == 'workflow':
        altered['artifact']['workflow']['user_id'] = 'foreign'
        altered['artifact_sha256'] = encode(altered['artifact'])[1]
    elif change == 'authority':
        altered['execution_authorized'] = True
    else:
        altered['case']['notice'] += ' Changed case.'
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        AdvancedWorkflowInputRepository.decode(raw)


async def test_capture_request_cannot_replace_original_method_or_calculations(repo):
    f = await fixture(repo)
    saved = await capture(repo, f)
    f.capture_body['method_choice'] += ' Revised answer.'
    with pytest.raises(EnrollmentConflict):
        await capture(repo, f)
    assert await AdvancedWorkflowInputRepository().get(f.learner.user_id, saved['uuid']) == saved


@pytest.mark.parametrize('change', ['oversize', 'revoked_lease'])
async def test_capture_never_truncates_evidence_or_saves_after_revocation(repo, monkeypatch, change):
    from app.services.certification_versions import advanced_workflow_inputs
    f = await fixture(repo)
    inputs = AdvancedWorkflowInputRepository()
    if change == 'oversize':
        monkeypatch.setattr(advanced_workflow_inputs, 'MAX_SNAPSHOT_BYTES', 100)
    else:
        original = inputs._check_lease
        calls = 0

        async def revoked(lease):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise EnrollmentConflict('Revoked test lease')
            await original(lease)

        monkeypatch.setattr(inputs, '_check_lease', revoked)
    with pytest.raises(EnrollmentConflict):
        await capture(repo, f, inputs)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 1
