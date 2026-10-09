"""Source and repair comparisons; synthetic result objects grant no execution claim."""
from copy import deepcopy
import os
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_inputs as inputs
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.governance_checks import canonical, check_result, compare_repair

repo = inputs.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


def result(case, snapshot, *, wrong=False, phase='original'):
    return {'run_id': uuid4().hex, 'phase': phase, 'artifact_sha256': snapshot['artifact_sha256'],
        'source_sha256s': [s['source_sha256'] for s in snapshot['documents']], 'status': 'completed', 'reason': None,
        'entities': [{f['searchphrase']: '600000' if wrong and e.field == 'Funds Obligated to Date' else e.expected_value for f, e in zip(snapshot['artifact']['fields'], case.expectations)}], 'credit_awarded': False}


async def test_exact_source_checks_distinguish_obligations_ceiling_and_amended_date(repo):
    f = await inputs.fixture(repo)
    snapshot = await inputs.capture(repo, f)
    actual = result(f.case, snapshot)
    correct = check_result(f.case, snapshot, actual, run_id=actual['run_id'], phase='original')
    assert correct['complete'] and correct['source_supported'] and not correct['observed_semantic_failure']
    wrong = result(f.case, snapshot, wrong=True)
    checked = check_result(f.case, snapshot, wrong, run_id=wrong['run_id'], phase='original')
    assert checked['complete'] and checked['observed_semantic_failure'] and not checked['source_supported']
    assert [field['field'] for field in checked['fields'] if not field['matches_source']] == ['Funds Obligated to Date']


@pytest.mark.parametrize('value,supported', [('2029-03-31', True), ('2028-09-30', False), ('2029-02-30', False), ('March 31, 2029', False), (None, False)])
async def test_actual_date_must_be_valid_normalized_latest_amendment(repo, value, supported):
    f = await inputs.fixture(repo)
    snapshot = await inputs.capture(repo, f)
    actual = result(f.case, snapshot)
    actual['entities'][0][snapshot['artifact']['fields'][5]['searchphrase']] = value
    checked = check_result(f.case, snapshot, actual, run_id=actual['run_id'], phase='original')
    assert checked['source_supported'] is supported
    if value in ('2029-02-30', 'March 31, 2029', None):
        assert not checked['complete'] and not checked['observed_semantic_failure']


@pytest.mark.parametrize('entities', [None, [], [{}, {}], {}, [{}]])
async def test_missing_or_malformed_output_is_unavailable_not_invented_semantic_failure(repo, entities):
    f = await inputs.fixture(repo)
    snapshot = await inputs.capture(repo, f)
    actual = result(f.case, snapshot)
    actual['entities'] = entities
    checked = check_result(f.case, snapshot, actual, run_id=actual['run_id'], phase='original')
    assert not checked['complete'] and not checked['observed_semantic_failure']


@pytest.mark.parametrize('change', ['source', 'revision', 'run', 'phase', 'credit', 'failed_values'])
async def test_wrong_execution_identity_or_authority_is_rejected(repo, change):
    f = await inputs.fixture(repo)
    snapshot = await inputs.capture(repo, f)
    actual = result(f.case, snapshot)
    run_id = actual['run_id']
    if change == 'source':
        actual['source_sha256s'].reverse()
    elif change == 'revision':
        actual['artifact_sha256'] = '0' * 64
    elif change == 'run':
        actual['run_id'] = uuid4().hex
    elif change == 'phase':
        actual['phase'] = 'repair'
    elif change == 'credit':
        actual['credit_awarded'] = True
    else:
        actual.update(status='failed', reason='extraction_unavailable')
    with pytest.raises(ValueError):
        check_result(f.case, snapshot, actual, run_id=run_id, phase='original')


@pytest.mark.parametrize('change', [None, 'unchanged', 'title_only', 'different_field', 'same_bad_value', 'no_original_failure'])
async def test_repair_requires_same_extraction_changed_fields_actual_failure_and_complete_source_correct_rerun(repo, change):
    f = await inputs.fixture(repo)
    original = await inputs.capture(repo, f)
    old_result = result(f.case, original, wrong=change != 'no_original_failure')
    f.fields[3].searchphrase = 'Return revised cumulative funds obligated to date from the latest issued amendment, never the maximum planned ceiling or increment alone.'
    await f.fields[3].save()
    f.body['request_id'] = uuid4().hex
    corrected = await inputs.capture(repo, f)
    if change == 'unchanged':
        corrected = deepcopy(original)
    elif change == 'title_only':
        corrected = deepcopy(original)
        corrected['artifact']['title'] += ' renamed'
        corrected['artifact_sha256'] = encode(corrected['artifact'])[1]
    elif change == 'different_field':
        corrected['artifact']['fields'][0]['id'] = '0' * 24
        corrected['artifact_sha256'] = encode(corrected['artifact'])[1]
    new_result = result(f.case, corrected, wrong=change == 'same_bad_value', phase='repair')
    old_run = {'run_id': old_result['run_id'], 'state': 'completed', 'plan': {'phase': 'original', 'input_snapshot': original}, 'result': {'extraction': old_result}}
    new_run = {'run_id': new_result['run_id'], 'state': 'completed', 'plan': {'phase': 'repair', 'input_snapshot': corrected}, 'result': {'extraction': new_result}}
    if change in ('unchanged', 'different_field'):
        with pytest.raises(ValueError):
            compare_repair(f.case, old_run, new_run)
    else:
        assert compare_repair(f.case, old_run, new_run)['repair_requirements_supported'] is (change is None)


def test_date_normalization_rejects_calendar_impossibility():
    assert canonical('2029-02-29', 'iso_date') == ('unrecognized', None)
    assert canonical('2028-02-29', 'iso_date') == ('value', '2028-02-29')
