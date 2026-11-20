"""Pure plan resolution on captured inputs; synthetic parents are not execution QA."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_batch_inputs as inputs
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.batch_plan import batch_plan
from app.services.certification_versions.enrollments import EnrollmentConflict

repo = inputs.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await inputs.fixture(repo)
    f.snapshot = await inputs.capture(repo, f)
    return f


def synthetic_parent(f, phase, *, parent=None, failed_source_id=None):
    """Only a unit boundary stand-in for a future decoded durable execution."""
    run_id = uuid4().hex
    plan = batch_plan(f.snapshot, f.case, LAB_RUNTIME, run_id=run_id, phase=phase, parent=parent, failed_source_id=failed_source_id)
    plan.update({key: f.snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')})
    plan['input_snapshot'] = deepcopy(f.snapshot)
    results = []
    for item in plan['item_plans']:
        values = {e.field: e.expected_value for e in f.case.expectations if e.source_id == item['source_id']}
        results.append({key: item[key] for key in ('item_id', 'batch_id', 'run_id', 'attempt_kind', 'source_id', 'document_id', 'source_sha256')} | {
            'artifact_sha256': f.snapshot['artifact_sha256'], 'status': 'completed', 'reason': None,
            'entities': [{field.meaning: values[field.title] for field in f.case.fields}], 'extraction_started': True,
            'started_at': '2026-10-07T10:00:00+00:00', 'finished_at': '2026-10-07T10:00:01+00:00',
            'elapsed_ms': 1000, 'usage': None, 'cost': None, 'external_effects': False})
    if phase == 'batch':
        results[1].update(status='failed', reason='controlled_training_rejection_before_dispatch', entities=None, extraction_started=False)
    return {'run_id': run_id, 'plan': plan, 'state': 'completed', 'result': {'status': 'completed', 'item_results': results}}


async def test_pilot_binds_exact_two_sources_five_fields_models_without_dispatch(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as provider:
        run_id = uuid4().hex
        plan = batch_plan(f.snapshot, f.case, LAB_RUNTIME, run_id=run_id, phase='pilot')
        assert plan['batch_id'] == run_id and plan['source_ids'] == ['proposal_1', 'proposal_3']
        assert plan['model_names'] == ['synthetic-model'] and plan['input_snapshot_sha256'] == encode(f.snapshot)[1]
        assert len(plan['item_plans']) == 2
        for item, source in zip(plan['item_plans'], [f.snapshot['documents'][0], f.snapshot['documents'][2]]):
            assert item['document_id'] == source['document_id'] and item['doc_texts'] == ['\n\n'.join(source['pages'])]
            assert len(item['field_keys']) == 5
        assert plan['execution_authorized'] is plan['credit_awarded'] is plan['external_effects_authorized'] is False
        assert 'synthetic-secret' not in encode(plan)[0]
        provider.assert_not_called()


async def test_checked_pilot_scales_same_revision_and_recovery_targets_only_original_failure(repo):
    f = await fixture(repo)
    pilot = synthetic_parent(f, 'pilot')
    batch = synthetic_parent(f, 'batch', parent=pilot)
    retry_id = uuid4().hex
    plan = batch_plan(f.snapshot, f.case, LAB_RUNTIME, run_id=retry_id, phase='retry', parent=batch, failed_source_id='proposal_2')
    assert plan['batch_id'] == batch['run_id'] and plan['source_ids'] == ['proposal_2']
    assert plan['parent_run_sha256'] == encode(batch)[1] and plan['parent_run_id'] == batch['run_id']
    assert plan['item_plans'][0]['item_id'] == batch['plan']['item_plans'][1]['item_id']
    assert plan['item_plans'][0]['run_id'] != batch['run_id']
    assert plan['execution_authorized'] is False


@pytest.mark.parametrize('change', ['no_pilot', 'inflight_pilot', 'wrong_phase', 'wrong_value', 'missing_output', 'different_revision',
    'different_learner', 'changed_model', 'changed_runtime', 'pilot_with_parent', 'batch_with_retry_scope', 'same_run_id'])
async def test_scale_requires_complete_source_supported_same_revision_pilot(repo, change):
    f = await fixture(repo)
    parent = synthetic_parent(f, 'pilot')
    phase, run_id, failed_source, config = 'batch', uuid4().hex, None, deepcopy(LAB_RUNTIME)
    if change == 'no_pilot':
        parent = None
    elif change == 'inflight_pilot':
        parent['state'] = 'executing'
    elif change == 'wrong_phase':
        parent['plan']['phase'] = 'batch'
    elif change == 'wrong_value':
        parent['result']['item_results'][0]['entities'][0][f.case.fields[2].meaning] = '32000'
    elif change == 'missing_output':
        parent['result']['item_results'][0]['entities'] = []
    elif change == 'different_revision':
        parent['plan']['input_snapshot']['artifact']['fields'][0]['searchphrase'] += ' changed'
    elif change == 'different_learner':
        parent['plan']['user_id'] = 'foreign'
    elif change == 'changed_model':
        config['available_models'].append({'name': 'another-model', 'api_key': 'synthetic'})
        config['extraction_config']['model'] = 'another-model'
    elif change == 'changed_runtime':
        config['extraction_config']['prompt_variant'] = 'strict'
    elif change == 'pilot_with_parent':
        phase = 'pilot'
    elif change == 'batch_with_retry_scope':
        failed_source = 'proposal_2'
    else:
        run_id = parent['run_id']
    with pytest.raises(EnrollmentConflict):
        batch_plan(f.snapshot, f.case, config, run_id=run_id, phase=phase, parent=parent, failed_source_id=failed_source)


@pytest.mark.parametrize('change', ['success', 'unknown_source', 'uncertain_batch', 'incomplete_batch', 'successful_retry', 'other_item_retry'])
async def test_targeted_retry_requires_exact_confirmed_failed_item_and_known_prior_state(repo, change):
    f = await fixture(repo)
    pilot = synthetic_parent(f, 'pilot')
    batch = synthetic_parent(f, 'batch', parent=pilot)
    source_id, previous = 'proposal_2', None
    if change == 'success':
        source_id = 'proposal_1'
    elif change == 'unknown_source':
        source_id = 'unassigned'
    elif change == 'uncertain_batch':
        batch['state'] = 'uncertain'
    elif change == 'incomplete_batch':
        batch['result']['item_results'].pop()
    else:
        previous = synthetic_parent(f, 'retry', parent=batch, failed_source_id='proposal_2')
        if change == 'other_item_retry':
            previous['plan']['source_ids'] = ['proposal_1']
    with pytest.raises(EnrollmentConflict):
        batch_plan(f.snapshot, f.case, LAB_RUNTIME, run_id=uuid4().hex, phase='retry', parent=batch,
                   failed_source_id=source_id, previous_retry=previous)


async def test_known_failed_retry_preserves_original_batch_and_previous_receipt(repo):
    f = await fixture(repo)
    pilot = synthetic_parent(f, 'pilot')
    batch = synthetic_parent(f, 'batch', parent=pilot)
    previous = synthetic_parent(f, 'retry', parent=batch, failed_source_id='proposal_2')
    previous['result']['item_results'][0].update(status='failed', reason='extraction_unavailable', entities=None)
    plan = batch_plan(f.snapshot, f.case, LAB_RUNTIME, run_id=uuid4().hex, phase='retry', parent=batch,
                      failed_source_id='proposal_2', previous_retry=previous)
    assert plan['previous_retry_sha256'] == encode(previous)[1] and plan['parent_run_id'] == batch['run_id']
    assert plan['source_ids'] == ['proposal_2']
