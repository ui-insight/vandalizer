"""Real durable batch orchestration with explicitly synthetic model responses."""
import asyncio
from copy import deepcopy
import os
import threading
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_batch_preparation as prep
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.batch_checks import check_recovery
from app.services.certification_versions.batch_execution import BatchExecution
from app.services.certification_versions.batch_preparation import BatchPreparation
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.runtime import CourseOperation

repo = prep.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def approve(repo, f):
    f.run = await prep.prepare(repo, f)
    f.approval = await prep.scope(repo, f, f.run)
    f.execution_body = {'run_id': f.run['run_id'], 'plan_sha256': f.run['plan_sha256'],
        'scope_decision_id': f.approval['uuid'], 'scope_decision_sha256': encode(f.approval)[1],
        'consent': 'execute_approved_bounded_batch_action'}
    return f.run


async def fixture(repo):
    f = await prep.fixture(repo)
    await approve(repo, f)
    return f


def values(f, text, keys, wrong=False):
    source_id = next(s['source_id'] for s in f.snapshot['documents'] if text == '\n\n'.join(s['pages']))
    expected = {e.field: e.expected_value for e in f.case.expectations if e.source_id == source_id}
    if wrong:
        expected['Total Budget'] = '1'
    return [{key: expected[field.title] for key, field in zip(keys, f.case.fields)}]


def provider(f, wrong=False):
    def extract(**kwargs):
        assert len(kwargs['doc_texts']) == 1 and kwargs['capture_sources'] is True
        assert kwargs['model'] == 'synthetic-model' and len(kwargs['field_metadata']) == 5
        return values(f, kwargs['doc_texts'][0], kwargs['extract_keys'], wrong)
    return extract


async def execute(repo, f, *, runner=None, config=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='execute_batch_action') as progress:
        return await (runner or BatchExecution()).execute(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.execution_body, LAB_RUNTIME if config is None else config, actor_user_id=actor or f.learner.user_id)


async def next_plan(repo, f, phase, parent, previous=None, source='proposal_2'):
    f.plan_body.update(request_id=uuid4().hex, phase=phase, parent_run_id=parent['run_id'], parent_run_sha256=encode(parent)[1],
        failed_source_id=source if phase == 'retry' else None,
        previous_retry_id=previous['run_id'] if previous else None, previous_retry_sha256=encode(previous)[1] if previous else None)
    return await approve(repo, f)


async def original_batch(repo, f):
    pilot = await execute(repo, f)
    await next_plan(repo, f, 'batch', pilot)
    return await execute(repo, f)


async def test_real_engine_pilot_mixed_batch_and_exact_retry_preserve_all_originals(repo):
    f = await fixture(repo)
    seen = []
    def dispatch(content, keys, model, config, meta_map, capture_sources):
        seen.append({'text': content, 'keys': keys, 'model': model, 'config': config, 'metadata': meta_map, 'sources': capture_sources})
        return values(f, content, keys)
    with patch('app.services.extraction_engine.ExtractionEngine._dispatch_extraction', side_effect=dispatch):
        original = await original_batch(repo, f)
        assert len(seen) == 4
        assert original['state'] == 'completed' and len(original['item_events']) == 6
        assert original['result']['checks']['terminal_coverage_complete'] is True
        assert original['result']['checks']['all_items_completed'] is False
        rejected = original['result']['item_results'][1]
        assert rejected['reason'] == 'controlled_training_rejection_before_dispatch' and rejected['extraction_started'] is False
        await next_plan(repo, f, 'retry', original)
        retry = await execute(repo, f)
        assert len(seen) == 5 and len(retry['item_events']) == 2
        reconciled = check_recovery(f.case, f.snapshot, original['result']['item_results'], retry['result']['item_results'], batch_id=original['run_id'])
        assert reconciled['targeted_recovery_supported'] is True
        assert len(reconciled['original_successes_preserved']) == 2
        assert await BatchPreparation().get(f.learner.user_id, original['run_id']) == original
        assert await execute(repo, f, config={}) == retry and len(seen) == 5
        for actual in seen:
            assert actual['sources'] is True and actual['model'] == 'synthetic-model'
            assert actual['keys'] == f.run['plan']['item_plans'][0]['field_keys']
            assert actual['metadata'] == {m['key']: m for m in f.run['plan']['item_plans'][0]['field_metadata']}
            assert actual['config'] == f.run['plan']['effective_extraction_config']
        await CertificationLabExecution.get_motor_collection().delete_many({'uuid': {'$ne': retry['run_id']}})
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        assert await execute(repo, f, config={}) == retry and len(seen) == 5
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'new_hold', 'plan_digest', 'approval_digest', 'runtime', 'implementation', 'consent'])
async def test_changed_authorization_cannot_dispatch(repo, monkeypatch, change):
    f = await fixture(repo)
    config = deepcopy(LAB_RUNTIME)
    if change == 'new_hold':
        await prep.scope(repo, f, f.run, choice='hold')
    elif change in ('plan_digest', 'approval_digest'):
        f.execution_body['plan_sha256' if change == 'plan_digest' else 'scope_decision_sha256'] = '0' * 64
    elif change == 'runtime':
        config['available_models'][0]['endpoint'] = 'https://example.invalid/changed'
    elif change == 'implementation':
        monkeypatch.setattr('app.services.certification_versions.batch_plan.implementation_digest', lambda: '0' * 64)
    elif change == 'consent':
        f.execution_body['consent'] = 'repeat_everything'
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        with pytest.raises(ValueError):
            await execute(repo, f, config=config, actor='foreign' if change == 'actor' else None)
        engine.assert_not_called()
    assert (await BatchPreparation().get(f.learner.user_id, f.run['run_id']))['state'] == 'prepared'


async def test_incorrect_pilot_blocks_scaling_without_dispatch(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f, wrong=True)) as engine:
        pilot = await execute(repo, f)
        assert pilot['result']['checks']['all_values_source_supported'] is False
        with pytest.raises(ValueError):
            await next_plan(repo, f, 'batch', pilot)
        assert engine.call_count == 2


async def test_failed_item_does_not_erase_inventory_or_leak_provider_error(repo):
    f = await fixture(repo)
    actual, count = provider(f), 0
    def flaky(**kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError('synthetic private provider secret')
        return actual(**kwargs)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=flaky):
        run = await execute(repo, f)
        assert run['state'] == 'completed' and len(run['item_events']) == 4
        assert [r['status'] for r in run['result']['item_results']] == ['failed', 'completed']
        assert run['result']['checks']['terminal_coverage_complete'] is True
        assert 'private provider secret' not in encode(run)[0]
        assert await execute(repo, f) == run and count == 2


async def test_retry_reservation_replays_same_identity_and_blocks_competing_plan(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)) as engine:
        original = await original_batch(repo, f)
        first = await next_plan(repo, f, 'retry', original)
        first_body = deepcopy(f.execution_body)
        await next_plan(repo, f, 'retry', original)
        second_body = deepcopy(f.execution_body)
        async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='reserve_retry') as progress:
            operation = CourseOperation(f.learner.user_id, f.package, progress, True)
            # Simulate a lost response after the original-item reservation, before own run claim.
            await BatchExecution().reserve_retry(operation, first)
        with pytest.raises(EnrollmentConflict):
            await execute(repo, f)
        assert engine.call_count == 4
        f.execution_body = first_body
        successful = await execute(repo, f)
        assert successful['result']['checks']['all_items_completed'] is True and engine.call_count == 5
        f.execution_body = second_body
        with pytest.raises(EnrollmentConflict):
            await execute(repo, f)
        assert engine.call_count == 5
        with pytest.raises(ValueError):
            await next_plan(repo, f, 'retry', original, successful)
        with pytest.raises(ValueError):
            await next_plan(repo, f, 'retry', original, source='proposal_1')


async def test_failed_retry_allows_only_exact_previous_terminal_head(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)):
        original = await original_batch(repo, f)
    await next_plan(repo, f, 'retry', original)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=RuntimeError('synthetic failure')):
        failed = await execute(repo, f)
    assert failed['state'] == 'completed' and failed['result']['item_results'][0]['status'] == 'failed'
    await next_plan(repo, f, 'retry', original, failed)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)) as engine:
        recovered = await execute(repo, f)
        assert recovered['result']['checks']['all_values_source_supported'] is True and engine.call_count == 1


async def test_cancellation_fences_late_result_and_successor(repo):
    f = await fixture(repo)
    entered, release = threading.Event(), threading.Event()
    actual = provider(f)
    def blocked(**kwargs):
        entered.set()
        release.wait(timeout=8)
        return actual(**kwargs)
    try:
        with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=blocked) as engine:
            task = asyncio.create_task(execute(repo, f))
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            saved = await BatchPreparation().get(f.learner.user_id, f.run['run_id'])
            assert saved['state'] == 'uncertain' and len(saved['item_events']) == 1
            release.set()
            await asyncio.sleep(.1)
            assert await execute(repo, f) == saved and engine.call_count == 1
    finally:
        release.set()


@pytest.mark.parametrize('change', ['source', 'values', 'checks', 'authority', 'event_hash'])
async def test_rehashed_terminal_cannot_replace_original_evidence(repo, change):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)):
        run = await execute(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    result = deepcopy(run['result'])
    if change == 'source':
        result['item_results'][0]['source_sha256'] = '0' * 64
    elif change == 'values':
        result['item_results'][0]['entities'] = [{'invented': 'answer'}]
    elif change == 'checks':
        result['checks']['all_values_source_supported'] = False
    elif change == 'authority':
        result['credit_awarded'] = True
    else:
        result['item_events_sha256'] = '0' * 64
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        BatchPreparation.decode(raw)


async def test_simultaneous_retry_reservations_have_one_owner(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)):
        original = await original_batch(repo, f)
    first = await next_plan(repo, f, 'retry', original)
    second = await next_plan(repo, f, 'retry', original)
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='race_retry_claims') as progress:
        operation = CourseOperation(f.learner.user_id, f.package, progress, True)
        results = await asyncio.gather(*(BatchExecution().reserve_retry(operation, run) for run in (first, second)), return_exceptions=True)
    claims = [r for r in results if isinstance(r, dict)]
    assert len(claims) == 1 and sum(isinstance(r, EnrollmentConflict) for r in results) == 1
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': original['run_id']})
    assert raw['retry_heads']['proposal_2'] == claims[0]['run_id']
    assert BatchPreparation.decode(raw) == original


@pytest.mark.parametrize('change', ['missing', 'source', 'original', 'run', 'previous'])
async def test_rehashed_retry_claim_cannot_change_exact_target(repo, change):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)):
        original = await original_batch(repo, f)
        await next_plan(repo, f, 'retry', original)
        run = await execute(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    authorization = deepcopy(run['authorization'])
    if change == 'missing':
        authorization.pop('retry_claim')
    else:
        authorization['retry_claim'][{'source': 'source_id', 'original': 'batch_id', 'run': 'run_id', 'previous': 'previous_retry_id'}[change]] = uuid4().hex
    # Strip terminal evidence so rejection specifically tests the authorization,
    # not stale event/result hashes after changing its claim.
    raw.update(state='executing', result_json=None, result_sha256=None, item_events_json=None, item_events_sha256=None, item_event_count=0)
    raw['authorization_json'], raw['authorization_sha256'] = encode(authorization)
    with pytest.raises(CourseCatalogError):
        BatchPreparation.decode(raw)
