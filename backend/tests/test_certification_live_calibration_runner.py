"""Bounded live-runner orchestration, with all provider calls replaced in tests."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

spec = importlib.util.spec_from_file_location('certification_live_calibration',
    Path(__file__).resolve().parents[2] / 'scripts/run_certification_review_calibration.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
CONTRACT, SUITES = runner.load_suites(['foundations'])
CONFIG = {'available_models': [{'name': 'synthetic-judge', 'api_key': 'private-test-key'}]}


async def supported(name, config, payload):
    data = json.loads(payload)
    evidence = {e['kind']: e for e in data['evidence']}
    runner.metering.record_usage(name, 100, 20)
    return {'outcomes': [{'outcome_id': o['id'], 'verdict': 'supported',
        'explanation': 'Injected runner control; no real judgment was performed.', 'revision_instruction': '',
        'citations': [{'evidence_id': evidence[k]['id'], 'quote': evidence[k]['text'][:2000]} for k in o['evidence']]}
        for o in data['requirements']]}


@pytest.fixture(autouse=True)
def prevent_live_calls_and_application_writes(monkeypatch):
    from app.services.certification_versions import automatic_review
    async def no_provider(*args, **kwargs):
        pytest.fail('Runner tests must not call a live provider')
    def no_write(*args, **kwargs):
        pytest.fail('Calibration must not flush usage into the application database')
    monkeypatch.setattr(automatic_review, '_call_model', no_provider)
    monkeypatch.setattr(runner.metering, 'flush_sync', no_write)
    monkeypatch.setattr(runner.metering, 'flush_async', no_write)


async def run(path, **kwargs):
    return await runner.run_batch(CONTRACT, SUITES, model_name='synthetic-judge', config=CONFIG,
                                  output=path, **kwargs)


def test_plan_covers_all_cases_without_loading_config_or_calling_provider(capsys):
    assert runner.main(['--config', '/nonexistent/private-config.json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['case_count'] == 60
    assert len(report['suites']) == 10
    assert report['release_ready'] is report['credit_awarded'] is False


async def test_one_case_budget_resumes_without_repeating_and_keeps_usage_local(tmp_path):
    path = tmp_path / 'report.json'
    call = AsyncMock(side_effect=supported)
    first = await run(path, call_model=call)
    assert call.await_count == 1
    assert first['summary']['pending_cases'] == 6
    assert first['summary']['all_cases_matched'] is False
    assert first['attempts'][0]['matches'] is True
    assert first['attempts'][0]['usage']['tokens_in'] == 100
    assert first['attempts'][0]['usage']['tokens_out'] == 20
    assert runner.metering.current_scope() is None
    second = await run(path, call_model=call, resume=True, max_cases=2)
    assert call.await_count == 3
    assert second['attempts'][0] == first['attempts'][0]
    assert len({r['case_id'] for r in second['attempts']}) == 3
    assert second['execution_kind'] == 'injected_test_control'
    assert 'private-test-key' not in path.read_text()
    assert second['release_ready'] is second['credit_awarded'] is False


async def test_provider_outage_stops_and_explicit_retry_preserves_original_attempt(tmp_path):
    path = tmp_path / 'report.json'
    unavailable = AsyncMock(side_effect=RuntimeError('secret error: private-test-key'))
    first = await run(path, call_model=unavailable, max_cases=6)
    assert unavailable.await_count == 1
    assert first['stop_reason'] == 'provider_unavailable'
    assert first['summary']['unavailable_cases'] == 1
    assert first['summary']['false_rejection_count'] == 0
    assert 'private-test-key' not in path.read_text()
    call = AsyncMock(side_effect=supported)
    second = await run(path, call_model=call, resume=True, retry_unavailable=True)
    assert call.await_count == 1
    assert second['attempts'][0] == first['attempts'][0]
    assert second['attempts'][1]['case_id'] == first['attempts'][0]['case_id']
    assert second['summary']['recorded_cases'] == 1
    assert second['summary']['unavailable_cases'] == 0
    assert second['summary']['pending_cases'] == 6


@pytest.mark.parametrize('change', ['routing', 'suite', 'tamper'])
async def test_resume_rejects_changed_inputs_or_corrupt_results_before_calling(tmp_path, change):
    path = tmp_path / 'report.json'
    await run(path, call_model=supported)
    config, suites = deepcopy(CONFIG), list(SUITES)
    if change == 'routing':
        config['llm_endpoint'] = 'https://changed.example.invalid/v1'
    elif change == 'suite':
        suites[0] = suites[0].model_copy(update={'suite_id': 'different-suite'})
    else:
        data = json.loads(path.read_text())
        data['attempts'][0]['matches'] = False
        path.write_text(json.dumps(data))
    before = path.read_bytes()
    call = AsyncMock(side_effect=supported)
    with pytest.raises(ValueError):
        await runner.run_batch(CONTRACT, suites, model_name='synthetic-judge', config=config,
                               output=path, resume=True, call_model=call)
    call.assert_not_awaited()
    assert path.read_bytes() == before
    assert not path.with_name('report.json.lock').exists()


async def test_cancellation_keeps_completed_cases_and_releases_output_lock(tmp_path):
    path = tmp_path / 'report.json'
    count = 0
    async def interrupted(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise asyncio.CancelledError()
        return await supported(*args)
    with pytest.raises(asyncio.CancelledError):
        await run(path, call_model=interrupted, max_cases=6)
    report = json.loads(path.read_text())
    assert len(report['attempts']) == 1
    assert report['summary']['pending_cases'] == 6
    assert not path.with_name('report.json.lock').exists()
    assert runner.metering.current_scope() is None


async def test_existing_report_or_active_lock_never_starts_another_call(tmp_path):
    path = tmp_path / 'report.json'
    await run(path, call_model=supported)
    before = path.read_bytes()
    call = AsyncMock(side_effect=supported)
    with pytest.raises(ValueError):
        await run(path, call_model=call)
    lock = path.with_name('report.json.lock')
    lock.touch()
    with pytest.raises(FileExistsError):
        await run(path, call_model=call, resume=True)
    assert lock.exists()
    assert path.read_bytes() == before
    call.assert_not_awaited()


async def test_unavailable_is_not_retried_without_explicit_flag(tmp_path):
    path = tmp_path / 'report.json'
    first = await run(path, call_model=AsyncMock(side_effect=RuntimeError('outage')))
    second = await run(path, call_model=supported, resume=True)
    assert second['attempts'][1]['case_id'] != first['attempts'][0]['case_id']
    assert second['summary']['unavailable_cases'] == 1
    assert second['summary']['all_cases_matched'] is False


async def test_missing_model_and_invalid_budget_fail_before_creating_evidence(tmp_path):
    path = tmp_path / 'report.json'
    with pytest.raises(ValueError):
        await run(path, call_model=supported, max_cases=0)
    with pytest.raises(ValueError):
        await runner.run_batch(CONTRACT, SUITES, model_name='absent', config=CONFIG,
                               output=path, call_model=supported)
    assert not path.exists()


async def test_complete_oracle_run_still_cannot_claim_release_or_credit(tmp_path):
    expected = {json.dumps([e.model_dump(mode='json') for e in c.evidence], sort_keys=True): c.expected
                for c in SUITES[0].cases}
    async def oracle(name, config, payload):
        response = await supported(name, config, payload)
        labels = expected[json.dumps(json.loads(payload)['evidence'], sort_keys=True)]
        for result in response['outcomes']:
            result['verdict'] = labels[result['outcome_id']]
            if result['verdict'] != 'supported':
                result['revision_instruction'] = 'Inspect the cited saved decision and correct its unsupported source or approval before reassessment.'
        return response
    report = await run(tmp_path / 'report.json', call_model=oracle, max_cases=len(SUITES[0].cases))
    assert report['stop_reason'] == 'completed'
    assert report['summary']['all_cases_matched'] is True
    assert report['summary']['pending_cases'] == report['summary']['unavailable_cases'] == 0
    assert report['summary']['release_ready'] is report['summary']['credit_awarded'] is False


async def test_live_resume_cannot_relabel_injected_controls_as_provider_evidence(tmp_path):
    path = tmp_path / 'report.json'
    await run(path, call_model=supported)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='Resume inputs changed'):
        await run(path, resume=True)
    assert path.read_bytes() == before
