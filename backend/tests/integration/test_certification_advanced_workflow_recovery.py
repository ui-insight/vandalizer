"""Explicit finalization reads durable tasks and never dispatches providers."""
import os

import pytest

from tests.integration import test_certification_advanced_workflow_execution as execution_fixtures
from app.models.certification import CertificationLabExecution
from app.services.certification_versions.advanced_workflow_execution import AdvancedWorkflowExecution
from app.services.certification_versions.advanced_workflow_recovery import AdvancedWorkflowRecovery
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = execution_fixtures.repo


async def fixture(repo, monkeypatch, *, partial=False):
    f = await execution_fixtures.fixture(repo, monkeypatch)
    service = AdvancedWorkflowExecution()

    async def interrupted(*args):
        raise OSError('Synthetic terminal write interrupted')

    monkeypatch.setattr(service, '_finish_budget', interrupted)
    if partial:
        from app.services import workflow_engine

        def provider(**kwargs):
            f.calls.append(kwargs['prompt'])
            if kwargs['prompt'] == 'Review source conflicts':
                raise RuntimeError('Synthetic branch failure')
            return 'Source review only'

        monkeypatch.setattr(workflow_engine, 'llm_chat_model', provider)
    with pytest.raises(OSError):
        await execution_fixtures.execute(repo, f, service)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': f.execution_body['run_id']})
    f.finalize_body = {key: raw[key] for key in ('plan_sha256', 'authorization_sha256', 'task_events_sha256')}
    f.finalize_body.update(run_id=raw['uuid'], consent='finalize_saved_budget_results_without_reexecution')
    return f


async def finalize(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='finalize_budget_results') as progress:
        return await AdvancedWorkflowRecovery().finalize(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.finalize_body, actor_user_id=actor or f.learner.user_id)


async def test_all_saved_results_finalize_once_with_no_provider_repeat(repo, monkeypatch):
    f = await fixture(repo, monkeypatch)
    original_calls = list(f.calls)
    completed = await finalize(repo, f)
    assert completed['state'] == 'completed'
    assert completed['result']['completion_mode'] == 'finalized_from_saved_task_receipts'
    assert completed['result']['execution_finished_at'] is None
    assert completed['result']['credit_awarded'] is False
    assert await finalize(repo, f) == completed
    assert await execution_fixtures.execute(repo, f, config={}) == completed
    assert f.calls == original_calls
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': completed['run_id']})
    assert raw['checkpoint_closed'] is True


@pytest.mark.parametrize('change', ['partial', 'plan_sha256', 'authorization_sha256', 'task_events_sha256', 'actor', 'terminal'])
async def test_finalization_cannot_invent_missing_results_or_replace_existing_work(repo, monkeypatch, change):
    f = await fixture(repo, monkeypatch, partial=change in ('partial', 'terminal'))
    original_calls = list(f.calls)
    if change.endswith('sha256'):
        f.finalize_body[change] = 'a' * 64
    if change == 'terminal':
        # A valid failed receipt is already authoritative and must stay so.
        service = AdvancedWorkflowExecution()
        async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='terminal_test_fixture') as progress:
            operation = CourseOperation(f.learner.user_id, f.package, progress, True)
            run = await service.get(f.learner.user_id, f.execution_body['run_id'])
            lease = service.check_operation(operation, run['plan'])
            await service.records.update_one({'uuid': run['run_id']}, {'$set': {'worker_id': lease.write_id}})
            await service._finish_budget(run, lease, {'status': 'failed', 'reason': 'execution_error', 'credit_awarded': False},
                                         '2026-10-06T00:00:00+00:00')
    before = await AdvancedWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id'])
    with pytest.raises(EnrollmentConflict):
        await finalize(repo, f, actor='foreign' if change == 'actor' else None)
    assert await AdvancedWorkflowExecution().get(f.learner.user_id, f.execution_body['run_id']) == before
    assert f.calls == original_calls
