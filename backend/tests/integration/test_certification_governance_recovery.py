"""Lost terminal writes recover from durable cases, never another model run."""
from copy import deepcopy
import os
from unittest.mock import patch

import pytest

from tests.integration import test_certification_governance_execution as execution_fixtures
from app.models.certification import CertificationLabExecution
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.governance_execution import GovernanceExecution
from app.services.certification_versions.governance_preparation import GovernancePreparation
from app.services.certification_versions.governance_recovery import GovernanceRecovery

repo = execution_fixtures.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


class LostTerminal(GovernanceExecution):
    async def _finish(self, *args, **kwargs):
        raise OSError('Synthetic unavailable terminal write')


def body(run):
    return {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
        'authorization_sha256': encode(run['authorization'])[1], 'extraction_events_sha256': encode(run['extraction_events'])[1],
        'consent': 'finalize_saved_governance_results_without_reexecution'}


async def finalize(repo, f, request, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='finalize_governance_results') as progress:
        return await GovernanceRecovery().finalize(CourseOperation(f.learner.user_id, f.package, progress, True),
            request, actor_user_id=actor or f.learner.user_id)


async def lost(repo, f):
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution_fixtures.provider(f)) as engine:
        with pytest.raises(OSError):
            await execution_fixtures.execute(repo, f, runner=LostTerminal())
        assert engine.call_count == 1
    run = await GovernancePreparation().get(f.learner.user_id, f.run['run_id'])
    assert run['state'] == 'executing' and len(run['extraction_events']) == 2
    return run


async def test_complete_saved_suite_finalizes_once_without_dispatch_or_fabricated_finish_time(repo):
    f = await execution_fixtures.fixture(repo)
    run = await lost(repo, f)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        assert await execution_fixtures.execute(repo, f) == run
        final = await finalize(repo, f, body(run))
        assert final['state'] == 'completed' and final['extraction_events'] == run['extraction_events']
        assert final['result']['checks']['source_supported'] is True
        assert final['result']['completion_mode'] == 'finalized_from_saved_extraction_receipts'
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
        request[{'plan': 'plan_sha256', 'authorization': 'authorization_sha256', 'events': 'extraction_events_sha256'}[change]] = '0' * 64
    elif change == 'consent':
        request['consent'] = 'rerun_validation'
    elif change == 'missing_case':
        events = run['extraction_events'][:1]
        serialized, digest = encode(events)
        await CertificationLabExecution.get_motor_collection().update_one({'uuid': run['run_id']},
            {'$set': {'extraction_events_json': serialized, 'extraction_events_sha256': digest, 'extraction_event_count': 1}})
        request['extraction_events_sha256'] = digest
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        with pytest.raises(ValueError):
            await finalize(repo, f, request, actor='foreign' if change == 'actor' else None)
        engine.assert_not_called()
    assert (await GovernancePreparation().get(f.learner.user_id, run['run_id']))['state'] == 'executing'


async def test_existing_failed_terminal_cannot_be_replaced_by_recovery(repo):
    f = await execution_fixtures.fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=RuntimeError('synthetic provider failure')):
        run = await execution_fixtures.execute(repo, f)
    with pytest.raises(EnrollmentConflict):
        await finalize(repo, f, body(run))
    assert await GovernancePreparation().get(f.learner.user_id, run['run_id']) == run


@pytest.mark.parametrize('change', ['actor', 'request', 'time'])
async def test_rehashed_finalization_metadata_cannot_change_original_receipt(repo, change):
    f = await execution_fixtures.fixture(repo)
    run = await lost(repo, f)
    final = await finalize(repo, f, body(run))
    result = deepcopy(final['result'])
    if change == 'actor':
        result['finalization_actor_user_id'] = 'foreign'
    elif change == 'request':
        result['finalization_request']['extraction_events_sha256'] = '0' * 64
    else:
        result['finished_at'] = result['receipt_finalized_at']
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        GovernancePreparation.decode(raw)
