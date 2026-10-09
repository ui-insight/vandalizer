"""Lost terminal writes recover from durable cases, never another model run."""
from copy import deepcopy
import os
from unittest.mock import patch

import pytest

from tests.integration import test_certification_batch_execution as execution_fixtures
from app.models.certification import CertificationLabExecution
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.batch_execution import BatchExecution
from app.services.certification_versions.batch_preparation import BatchPreparation
from app.services.certification_versions.batch_recovery import BatchRecovery

repo = execution_fixtures.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


class LostTerminal(BatchExecution):
    async def _finish(self, *args, **kwargs):
        raise OSError('Synthetic unavailable terminal write')


def body(run):
    return {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'authorization_sha256': encode(run['authorization'])[1], 'item_events_sha256': encode(run['item_events'])[1],
        'consent': 'finalize_saved_batch_results_without_reexecution'}


async def finalize(repo, f, request, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='finalize_batch_results') as progress:
        return await BatchRecovery().finalize(CourseOperation(f.learner.user_id, f.package, progress, True),
            request, actor_user_id=actor or f.learner.user_id)


async def lost(repo, f):
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution_fixtures.provider(f)) as engine:
        with pytest.raises(OSError):
            await execution_fixtures.execute(repo, f, runner=LostTerminal())
        assert engine.call_count == 2
    run = await BatchPreparation().get(f.learner.user_id, f.run['run_id'])
    assert run['state'] == 'executing' and len(run['item_events']) == 4
    return run


async def test_complete_saved_inventory_finalizes_once_without_dispatch_or_fabricated_finish_time(repo):
    f = await execution_fixtures.fixture(repo)
    run = await lost(repo, f)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        assert await execution_fixtures.execute(repo, f) == run
        final = await finalize(repo, f, body(run))
        assert final['state'] == 'completed' and final['item_events'] == run['item_events']
        assert final['result']['checks']['all_values_source_supported'] is True
        assert final['result']['completion_mode'] == 'finalized_from_saved_item_receipts'
        assert final['result']['started_at'] is final['result']['finished_at'] is None
        assert final['result']['receipt_finalized_at']
        assert final['result']['credit_awarded'] is False
        assert await finalize(repo, f, body(run)) == final
        engine.assert_not_called()


@pytest.mark.parametrize('change', ['actor', 'plan', 'authorization', 'events', 'consent', 'missing_case'])
async def test_recovery_rejects_changed_or_incomplete_saved_evidence(repo, change):
    f = await execution_fixtures.fixture(repo)
    run = await lost(repo, f)
    request = body(run)
    if change in ('plan', 'authorization', 'events'):
        request[{'plan': 'plan_sha256', 'authorization': 'authorization_sha256', 'events': 'item_events_sha256'}[change]] = '0' * 64
    elif change == 'consent':
        request['consent'] = 'rerun_batch'
    elif change == 'missing_case':
        events = run['item_events'][:2]
        serialized, digest = encode(events)
        await CertificationLabExecution.get_motor_collection().update_one({'uuid': run['run_id']},
            {'$set': {'item_events_json': serialized, 'item_events_sha256': digest, 'item_event_count': 2}})
        request['item_events_sha256'] = digest
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        with pytest.raises(ValueError):
            await finalize(repo, f, request, actor='foreign' if change == 'actor' else None)
        engine.assert_not_called()
    assert (await BatchPreparation().get(f.learner.user_id, run['run_id']))['state'] == 'executing'


async def test_existing_failed_terminal_cannot_be_replaced_by_recovery(repo):
    f = await execution_fixtures.fixture(repo)
    with patch('app.services.certification_versions.batch_execution.execute_approved_batch', side_effect=RuntimeError('synthetic executor failure')):
        run = await execution_fixtures.execute(repo, f)
    with pytest.raises(EnrollmentConflict):
        await finalize(repo, f, body(run))
    assert await BatchPreparation().get(f.learner.user_id, run['run_id']) == run


@pytest.mark.parametrize('change', ['actor', 'request', 'time'])
async def test_rehashed_finalization_metadata_cannot_change_original_receipt(repo, change):
    f = await execution_fixtures.fixture(repo)
    run = await lost(repo, f)
    final = await finalize(repo, f, body(run))
    result = deepcopy(final['result'])
    if change == 'actor':
        result['finalization_actor_user_id'] = 'foreign'
    elif change == 'request':
        result['finalization_request']['item_events_sha256'] = '0' * 64
    else:
        result['finished_at'] = result['receipt_finalized_at']
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        BatchPreparation.decode(raw)


async def test_mixed_full_batch_can_finalize_without_retrying_failed_item(repo):
    f = await execution_fixtures.fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution_fixtures.provider(f)):
        pilot = await execution_fixtures.execute(repo, f)
        await execution_fixtures.next_plan(repo, f, 'batch', pilot)
        with pytest.raises(OSError):
            await execution_fixtures.execute(repo, f, runner=LostTerminal())
    run = await BatchPreparation().get(f.learner.user_id, f.run['run_id'])
    assert len(run['item_events']) == 6 and run['state'] == 'executing'
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        final = await finalize(repo, f, body(run))
        assert final['state'] == 'completed'
        assert final['result']['checks']['terminal_coverage_complete'] is True
        assert final['result']['checks']['all_items_completed'] is False
        assert [r['status'] for r in final['result']['item_results']] == ['completed', 'failed', 'completed']
        assert final['item_events'] == run['item_events']
        engine.assert_not_called()
