"""Actual engine dispatch, durable cases and same-suite repair in disposable MongoDB."""
import asyncio
from copy import deepcopy
import os
import threading
from unittest.mock import patch

import pytest

from tests.integration import test_certification_governance_preparation as preparation_fixtures
from tests.integration import test_certification_governance_inputs as input_fixtures
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.governance_execution import GovernanceExecution
from app.services.certification_versions.governance_preparation import GovernancePreparation

repo = input_fixtures.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await preparation_fixtures.fixture(repo)
    f.run = await preparation_fixtures.prepare(repo, f)
    f.approval = await preparation_fixtures.scope(repo, f, f.run)
    f.execution_body = {'run_id': f.run['run_id'], 'plan_sha256': f.run['plan_sha256'],
        'scope_decision_id': f.approval['uuid'], 'scope_decision_sha256': encode(f.approval)[1],
        'consent': 'execute_approved_bounded_capstone_extraction'}
    return f


def provider(f, *, wrong=False):
    def extract(**kwargs):
        assert len(kwargs['doc_texts']) == 1 and kwargs['capture_sources'] is True
        for source in f.snapshot['documents']:
            assert all(page in kwargs['doc_texts'][0] for page in source['pages'])
        assert kwargs['model'] == 'synthetic-model' and len(kwargs['field_metadata']) == 6
        values = {e.field: e.expected_value for e in f.case.expectations}
        if wrong:
            values['Funds Obligated to Date'] = '600000'
        return [{key: values[field.title] for key, field in zip(kwargs['extract_keys'], f.case.fields)}]
    return extract


async def execute(repo, f, *, runner=None, config=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='execute_governance_suite') as progress:
        return await (runner or GovernanceExecution()).execute(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.execution_body, LAB_RUNTIME if config is None else config, actor_user_id=actor or f.learner.user_id)


async def test_actual_unsupported_result_is_preserved_without_repeating_or_awarding_credit(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=provider(f, wrong=True)) as engine:
        original = await execute(repo, f)
        assert engine.call_count == 1
        assert original['state'] == 'completed' and len(original['extraction_events']) == 2
        assert original['result']['checks']['observed_semantic_failure'] is True
        assert original['result']['checks']['source_supported'] is False
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({})
        for document in f.documents:
            await document.delete()
        await f.artifact.delete()
        assert await execute(repo, f, config={}) == original
        assert engine.call_count == 1
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
        monkeypatch.setattr('app.services.certification_versions.governance_plan.implementation_digest', lambda: '0' * 64)
    elif change == 'consent':
        f.execution_body['consent'] = 'repeat_everything'
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        with pytest.raises(ValueError):
            await execute(repo, f, config=config, actor='foreign' if change == 'actor' else None)
        engine.assert_not_called()
    saved = await GovernancePreparation().get(f.learner.user_id, f.run['run_id'])
    assert saved['state'] == 'prepared' and saved['extraction_events'] == []


@pytest.mark.parametrize('failing_case', [0])
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
        assert result['state'] == 'failed' and len(result['extraction_events']) == 2 * (failing_case + 1)
        assert result['extraction_events'][-1]['receipt']['result']['reason'] == 'extraction_unavailable'
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
            saved = await GovernancePreparation().get(f.learner.user_id, f.run['run_id'])
            assert saved['state'] == 'uncertain' and len(saved['extraction_events']) == 1
            release.set()
            await asyncio.sleep(.1)
            assert await GovernancePreparation().get(f.learner.user_id, f.run['run_id']) == saved
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
        result['extraction']['source_sha256s'][0] = '0' * 64
    elif change == 'result_values':
        result['extraction']['entities'][0] = {'invented': 'output'}
    elif change == 'checks':
        result['checks']['source_supported'] = False
    elif change == 'authority':
        result['credit_awarded'] = True
    else:
        result['extraction_events_sha256'] = '0' * 64
    raw['result_json'], raw['result_sha256'] = encode(result)
    with pytest.raises(CourseCatalogError):
        GovernancePreparation.decode(raw)


async def test_real_extraction_engine_consumes_joint_complete_sources_and_six_fields(repo):
    f = await fixture(repo)
    seen = []
    def dispatch(content, keys, model, config, meta_map, capture_sources):
        seen.append({'content': content, 'keys': keys, 'model': model, 'config': config,
            'metadata': meta_map, 'capture_sources': capture_sources})
        expected = {e.field: e.expected_value for e in f.case.expectations}
        return [{key: expected[field.title] for key, field in zip(keys, f.case.fields)}]
    with patch('app.services.extraction_engine.ExtractionEngine._dispatch_extraction', side_effect=dispatch):
        result = await execute(repo, f)
    assert result['state'] == 'completed' and result['result']['checks']['source_supported'] is True
    assert len(seen) == 1
    consumed, planned = seen[0], f.run['plan']['extraction_input']
    assert consumed['content'] == planned['doc_texts'][0]
    assert consumed['keys'] == planned['field_keys']
    assert consumed['metadata'] == {m['key']: m for m in planned['field_metadata']}
    assert consumed['config'] == f.run['plan']['effective_extraction_config']
    assert consumed['capture_sources'] is True and consumed['model'] == 'synthetic-model'


@pytest.mark.parametrize('response', [[], [{}], [{'unexpected': 'value'}], None])
async def test_unavailable_fields_never_invent_a_semantic_failure(repo, response):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', return_value=response):
        result = await execute(repo, f)
    assert result['state'] == 'completed'
    assert result['result']['checks']['complete'] is False
    assert result['result']['checks']['observed_semantic_failure'] is False
