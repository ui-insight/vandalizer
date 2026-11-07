"""Actual engine dispatch, durable cases and same-suite repair in disposable MongoDB."""
import asyncio
from copy import deepcopy
import os
import threading
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_validation_preparation as preparation_fixtures
from tests.integration import test_certification_validation_inputs as input_fixtures
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.validation_execution import ValidationExecution
from app.services.certification_versions.validation_preparation import ValidationPreparation

repo = input_fixtures.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await preparation_fixtures.fixture(repo)
    f.run = await preparation_fixtures.prepare(repo, f)
    f.approval = await preparation_fixtures.scope(repo, f, f.run)
    f.execution_body = {'run_id': f.run['run_id'], 'plan_sha256': f.run['plan_sha256'],
        'scope_decision_id': f.approval['uuid'], 'scope_decision_sha256': encode(f.approval)[1],
        'consent': 'execute_approved_complete_validation_suite'}
    return f


def provider(f, *, wrong=False):
    def extract(**kwargs):
        text = kwargs['doc_texts'][0]
        source_id = 'nsf' if 'NSF Grant Proposal' in text else 'nih'
        assert len(kwargs['doc_texts']) == 1
        assert kwargs['capture_sources'] is True and kwargs['model'] == 'synthetic-model'
        assert len(kwargs['field_metadata']) == 3
        values = {e.field: e.expected_value for e in f.case.expectations if e.source_id == source_id}
        if wrong and source_id == 'nsf':
            values['Total Project Budget'] = '177000'
        return [{key: values[field.title] for key, field in zip(kwargs['extract_keys'], f.case.fields)}]
    return extract


async def execute(repo, f, *, runner=None, config=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='execute_validation_suite') as progress:
        return await (runner or ValidationExecution()).execute(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.execution_body, LAB_RUNTIME if config is None else config, actor_user_id=actor or f.learner.user_id)


async def test_original_failure_and_complete_changed_revision_retest_preserve_actual_engine_results(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f, wrong=True)) as engine:
        original = await execute(repo, f)
        assert engine.call_count == 2
        assert original['state'] == 'completed' and len(original['case_events']) == 4
        assert original['result']['checks']['observed_semantic_failure'] is True
        assert original['result']['checks']['source_supported'] is False
        assert await execute(repo, f, config={}) == original
        assert engine.call_count == 2
    f.fields[1].searchphrase = 'Return the complete project budget across all years in USD; never return a single annual budget.'
    await f.fields[1].save()
    f.body['request_id'] = uuid4().hex
    corrected = await input_fixtures.capture(repo, f)
    f.plan_body.update(request_id=uuid4().hex, input_snapshot_id=corrected['uuid'], input_snapshot_sha256=encode(corrected)[1],
                       original_run_id=original['run_id'], original_run_sha256=encode(original)[1])
    retest = await preparation_fixtures.prepare(repo, f)
    approval = await preparation_fixtures.scope(repo, f, retest)
    f.execution_body.update(run_id=retest['run_id'], plan_sha256=retest['plan_sha256'],
                            scope_decision_id=approval['uuid'], scope_decision_sha256=encode(approval)[1])
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)) as engine:
        result = await execute(repo, f)
        assert engine.call_count == 2
        assert result['result']['repair_checks']['repair_requirements_supported'] is True
        assert result['result']['checks']['source_supported'] is True
        assert result['plan']['suite']['suite_sha256'] == original['plan']['suite']['suite_sha256']
        assert result['result']['credit_awarded'] is False
        await CertificationLabExecution.get_motor_collection().delete_one({'uuid': original['run_id']})
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        assert await execute(repo, f, config={}) == result
        assert engine.call_count == 2
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'new_hold', 'plan_digest', 'approval_digest', 'runtime', 'implementation', 'consent'])
async def test_execution_rejects_changed_authorization_before_provider_dispatch(repo, monkeypatch, change):
    f = await fixture(repo)
    config = deepcopy(LAB_RUNTIME)
    if change == 'new_hold':
        await preparation_fixtures.scope(repo, f, f.run, choice='hold')
    elif change == 'plan_digest':
        f.execution_body['plan_sha256'] = '0' * 64
    elif change == 'approval_digest':
        f.execution_body['scope_decision_sha256'] = '0' * 64
    elif change == 'runtime':
        config['available_models'][0]['endpoint'] = 'https://example.invalid/changed'
    elif change == 'implementation':
        monkeypatch.setattr('app.services.certification_versions.validation_plan.implementation_digest', lambda: '0' * 64)
    elif change == 'consent':
        f.execution_body['consent'] = 'repeat_everything'
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        with pytest.raises(ValueError):
            await execute(repo, f, config=config, actor='foreign' if change == 'actor' else None)
        engine.assert_not_called()
    saved = await ValidationPreparation().get(f.learner.user_id, f.run['run_id'])
    assert saved['state'] == 'prepared' and saved['case_events'] == []


@pytest.mark.parametrize('failing_case', [0, 1])
async def test_provider_failure_preserves_exact_prefix_without_secret_or_successor_replay(repo, failing_case):
    f = await fixture(repo)
    calls = 0
    actual = provider(f)
    def flaky(**kwargs):
        nonlocal calls
        index = calls
        calls += 1
        if index == failing_case:
            raise RuntimeError('synthetic private secret should never be persisted')
        return actual(**kwargs)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=flaky):
        result = await execute(repo, f)
        assert result['state'] == 'failed' and len(result['case_events']) == 2 * (failing_case + 1)
        assert result['case_events'][-1]['receipt']['result']['reason'] == 'extraction_unavailable'
        assert 'private secret' not in encode(result)[0]
        assert await execute(repo, f) == result
        assert calls == failing_case + 1


async def test_cancellation_fences_late_provider_result_and_never_starts_next_case(repo):
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
            saved = await ValidationPreparation().get(f.learner.user_id, f.run['run_id'])
            assert saved['state'] == 'uncertain' and len(saved['case_events']) == 1
            release.set()
            await asyncio.sleep(.1)
            assert await ValidationPreparation().get(f.learner.user_id, f.run['run_id']) == saved
            assert engine.call_count == 1
    finally:
        release.set()


@pytest.mark.parametrize('change', ['case_source', 'result_values', 'checks', 'authority', 'event_hash'])
async def test_rehashed_terminal_changes_cannot_replace_original_case_evidence(repo, change):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f)):
        run = await execute(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': run['run_id']})
    result = deepcopy(run['result'])
    if change == 'case_source':
        result['case_results'][0]['source_sha256'] = '0' * 64
    elif change == 'result_values':
        result['case_results'][0]['entities'][0] = {'invented': 'output'}
    elif change == 'checks':
        result['checks']['source_supported'] = False
    elif change == 'authority':
        result['credit_awarded'] = True
    else:
        result['case_events_sha256'] = '0' * 64
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        ValidationPreparation.decode(raw)


async def test_real_extraction_engine_consumes_exact_case_text_and_field_metadata(repo):
    f = await fixture(repo)
    seen = []
    def dispatch(content, keys, model, config, meta_map, capture_sources):
        source_id = 'nsf' if 'NSF Grant Proposal' in content else 'nih'
        seen.append({'source_id': source_id, 'content': content, 'keys': keys, 'model': model,
                     'config': config, 'metadata': meta_map, 'capture_sources': capture_sources})
        expected = {e.field: e.expected_value for e in f.case.expectations if e.source_id == source_id}
        return [{key: expected[field.title] for key, field in zip(keys, f.case.fields)}]
    # Only model dispatch is substituted. The real engine resolves configuration,
    # field chunks, document iteration, entity assembly and source processing.
    with patch('app.services.extraction_engine.ExtractionEngine._dispatch_extraction', side_effect=dispatch):
        result = await execute(repo, f)
    assert result['state'] == 'completed' and result['result']['checks']['source_supported'] is True
    assert [r['source_id'] for r in seen] == ['nsf', 'nih']
    for consumed, planned in zip(seen, f.run['plan']['case_plans']):
        assert consumed['content'] == planned['doc_texts'][0]
        assert consumed['keys'] == planned['field_keys']
        assert consumed['metadata'] == {m['key']: m for m in planned['field_metadata']}
        assert consumed['config'] == f.run['plan']['effective_extraction_config']
        assert consumed['capture_sources'] is True and consumed['model'] == 'synthetic-model'
