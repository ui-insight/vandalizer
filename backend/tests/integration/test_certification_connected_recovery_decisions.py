"""Recovery choices bind actual owned failures and preserve every revision."""
from copy import deepcopy
import os
from uuid import uuid4

import pytest

from tests.integration import test_certification_connected_failure_practice as practice
from tests.integration import test_certification_enrollments as f
from tests.test_certification_connected_workflow_runtime import providers
from app.models.certification import CertificationLabExecution
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_recovery_decisions import ConnectedRecoveryDecisionRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

repo = f.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, monkeypatch):
    data, _, execution = await practice.fixture(repo)
    mocks = providers(monkeypatch)
    run = await f.dispatch_connected(repo, data, execution)
    body = {'request_id': uuid4().hex, 'run_id': run['run_id'], 'result_sha256': encode(run['result'])[1],
            'stage_events_sha256': encode(run['stage_events'])[1], 'case_sha256': run['plan']['case_sha256'],
            'failed_stage': 'reason', 'preserve': 'keep_original_run_and_completed_outputs',
            'next_action': 'prepare_separate_bounded_run',
            'explanation': 'I inspected the actual extraction and the saved reasoning input and rejection. Preserve this run and separately approve only another internal computation; never replay external writes.',
            'consent': 'save_my_actual_stopped_run_recovery_choices'}
    return data, run, mocks, body


async def submit(repo, data, body, *, actor=None):
    source, package = data[:2]
    async with repo.write_boundary(source.user_id, source.uuid, operation='save_stopped_run_recovery_choices') as progress:
        return await ConnectedRecoveryDecisionRepository().submit(CourseOperation(source.user_id, package, progress, True),
            body, actor_user_id=actor or source.user_id)


async def test_wrong_choices_revise_against_same_original_work_after_deletion_without_dispatch(repo, monkeypatch):
    data, run, (extract, reason, formatter), body = await fixture(repo, monkeypatch)
    wrong = {**body, 'failed_stage': 'format', 'preserve': 'partial_is_complete', 'next_action': 'restart_all_writes'}
    first = await submit(repo, data, wrong)
    assert first['checks']['choices_supported'] is False
    assert all(not check['supported'] for check in first['checks']['checks'])
    assert first['checks']['explanation_quality_assessed'] is False
    await CertificationLabExecution.get_motor_collection().delete_many({})
    await f.Workflow.get_motor_collection().delete_many({})
    await f.SmartDocument.get_motor_collection().delete_many({})
    assert await submit(repo, data, wrong) == first
    second = await submit(repo, data, {**body, 'request_id': uuid4().hex, 'previous_submission_id': first['uuid']})
    assert second['checks']['choices_supported'] is True
    assert second['stopped_execution'] == first['stopped_execution']
    assert second['checks']['successful_extraction_receipt_sha256'] == run['stage_events'][1]['receipt_sha256']
    store = ConnectedRecoveryDecisionRepository()
    assert await store.get(data[0].user_id, first['uuid']) == first
    assert await store.get('foreign', first['uuid']) is None
    assert extract.call_count == 1 and reason.call_count == formatter.call_count == 0
    assert second['credit_awarded'] is second['module_completion_eligible'] is False
    assert (await repo.read_progress(data[0].user_id, data[0].uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'case', 'run', 'result', 'events', 'previous'])
async def test_foreign_or_changed_evidence_never_saves_a_recovery_choice(repo, monkeypatch, change):
    data, _, _, body = await fixture(repo, monkeypatch)
    actor = None
    if change == 'actor':
        actor = 'foreign'
    elif change == 'case':
        body['case_sha256'] = 'f' * 64
    elif change == 'run':
        body['run_id'] = 'f' * 32
    elif change == 'result':
        body['result_sha256'] = 'f' * 64
    elif change == 'events':
        body['stage_events_sha256'] = 'f' * 64
    else:
        body['previous_submission_id'] = 'f' * 32
    with pytest.raises(EnrollmentConflict):
        await submit(repo, data, body, actor=actor)
    assert await ConnectedRecoveryDecisionRepository().records.count_documents({'prompt_id': 'own_stopped_run_recovery'}) == 0


@pytest.mark.parametrize('change', ['feedback', 'actor_channel', 'credit', 'question', 'inner_result'])
async def test_rehashed_outer_record_cannot_change_original_decision_or_actual_work(repo, monkeypatch, change):
    data, _, _, body = await fixture(repo, monkeypatch)
    record = await submit(repo, data, body)
    store = ConnectedRecoveryDecisionRepository()
    raw = await store.records.find_one({'uuid': record['uuid']})
    altered = deepcopy(record)
    if change == 'feedback':
        altered['checks']['explanation_quality_assessed'] = True
    elif change == 'actor_channel':
        altered['submission_channel'] = 'agent_assertion'
    elif change == 'credit':
        altered['credit_awarded'] = True
    elif change == 'question':
        altered['question'] = 'A different assignment'
    else:
        altered['stopped_execution']['result_sha256'] = 'f' * 64
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        store.decode(raw)
    with pytest.raises(EnrollmentConflict, match='different work or answers'):
        await submit(repo, data, {**body, 'failed_stage': 'unknown'})
