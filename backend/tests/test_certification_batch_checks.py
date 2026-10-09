"""Exact batch coverage and source quality remain distinct through recovery."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.batch_case import BatchCase
from app.services.certification_versions.batch_checks import check_inventory, check_recovery, item_id
from app.services.certification_versions.catalog import CourseCatalogError

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def work():
    case = BatchCase.model_validate_json((DRAFT / 'batch-processing-case.json').read_bytes())
    snapshot = {'case': case.public_definition(), 'artifact_sha256': 'a' * 64,
        'artifact': {'fields': [{'title': f.title, 'searchphrase': f.meaning} for f in case.fields]},
        'documents': [{'source_id': s.id, 'document_id': uuid4().hex, 'source_sha256': s.sha256} for s in case.sources]}
    batch_id = uuid4().hex
    results = []
    for source in snapshot['documents']:
        expected = {e.field: e.expected_value for e in case.expectations if e.source_id == source['source_id']}
        results.append({**source, 'batch_id': batch_id, 'run_id': batch_id, 'attempt_kind': 'batch',
            'item_id': item_id(batch_id, source['document_id']), 'artifact_sha256': snapshot['artifact_sha256'],
            'status': 'completed', 'reason': None, 'entities': [{f.meaning: expected[f.title] for f in case.fields}],
            'extraction_started': True, 'started_at': '2026-10-07T10:00:00+00:00', 'finished_at': '2026-10-07T10:00:01+00:00',
            'elapsed_ms': 1000, 'usage': None, 'cost': None, 'external_effects': False})
    return case, snapshot, batch_id, results


def inventory(work, *, kind='batch', source_ids=None):
    case, snapshot, batch_id, results = work
    return check_inventory(case, snapshot, results, batch_id=batch_id, run_id=batch_id, attempt_kind=kind,
                           source_ids=source_ids or [s.id for s in case.sources])


def fail_middle(work):
    work[3][1].update(status='failed', reason='controlled_training_rejection_before_dispatch', entities=None, extraction_started=False)


def retry_middle(work):
    item = deepcopy(work[3][1])
    item.update(run_id=uuid4().hex, attempt_kind='retry')
    return item


def test_complete_exact_inventory_checks_every_actual_field_without_awarding_credit(work):
    checked = inventory(work)
    assert checked['terminal_coverage_complete'] and checked['all_values_source_supported']
    assert len(checked['items']) == 3 and all(len(i['fields']) == 5 for i in checked['items'])
    assert checked['document_ids'] == [s['document_id'] for s in work[1]['documents']]
    assert checked['usage'] is checked['cost'] is None and checked['elapsed_ms'] == 3000
    assert checked['credit_awarded'] is checked['module_completion_eligible'] is False
    assert 'expected_value' not in json.dumps(checked)


def test_mixed_terminal_coverage_does_not_claim_success_or_erase_failed_receipt(work):
    fail_middle(work)
    checked = inventory(work)
    assert checked['terminal_coverage_complete'] is True and checked['all_items_completed'] is False
    assert checked['all_values_source_supported'] is False
    assert checked['failed_document_ids'] == [work[1]['documents'][1]['document_id']]
    assert len(checked['completed_document_ids']) == 2


def test_targeted_retry_preserves_original_success_bytes_and_failure(work):
    retry = retry_middle(work)
    fail_middle(work)
    before = deepcopy(work[3])
    result = check_recovery(work[0], work[1], work[3], [retry], batch_id=work[2])
    assert result['targeted_recovery_supported'] and result['all_assigned_successful'] and result['all_values_source_supported']
    assert result['original_failed_document_ids'] == result['retry_document_ids']
    assert [s['receipt_sha256'] for s in result['original_successes_preserved']] == [encode(before[i])[1] for i in (0, 2)]
    assert work[3] == before and work[3][1]['status'] == 'failed'
    assert result['credit_awarded'] is False


@pytest.mark.parametrize('change', ['duplicate', 'missing', 'reordered', 'foreign_document', 'foreign_source', 'artifact', 'other_batch',
    'other_run', 'other_item', 'other_phase', 'queued', 'unknown_status', 'fabricated_cost', 'negative_time', 'float_time', 'missing_time',
    'no_timezone', 'external_effect', 'invented_success', 'unexplained_failure', 'controlled_wrong_source', 'controlled_after_dispatch'])
def test_rejects_unrelated_incomplete_or_invented_receipt_inventory(work, change):
    results = work[3]
    if change == 'duplicate':
        results[1] = deepcopy(results[0])
    elif change == 'missing':
        results.pop()
    elif change == 'reordered':
        results.reverse()
    else:
        target = results[0]
        mutations = {'foreign_document': ('document_id', uuid4().hex), 'foreign_source': ('source_sha256', '0' * 64),
            'artifact': ('artifact_sha256', '0' * 64), 'other_batch': ('batch_id', uuid4().hex), 'other_run': ('run_id', uuid4().hex),
            'other_item': ('item_id', uuid4().hex), 'other_phase': ('attempt_kind', 'pilot'), 'queued': ('status', 'queued'),
            'unknown_status': ('status', 'uncertain'), 'fabricated_cost': ('cost', 0.01), 'negative_time': ('elapsed_ms', -1),
            'float_time': ('elapsed_ms', 1.1), 'missing_time': ('finished_at', None), 'no_timezone': ('started_at', '2026-10-07T10:00:00'),
            'external_effect': ('external_effects', True), 'invented_success': ('extraction_started', False)}
        if change in mutations:
            key, value = mutations[change]
            target[key] = value
        elif change == 'unexplained_failure':
            target.update(status='failed', entities=None)
        elif change == 'controlled_wrong_source':
            target.update(status='failed', entities=None, reason='controlled_training_rejection_before_dispatch', extraction_started=False)
        elif change == 'controlled_after_dispatch':
            fail_middle(work)
            results[1]['extraction_started'] = True
    with pytest.raises(CourseCatalogError):
        inventory(work)


@pytest.mark.parametrize('change', ['wrong_pi', 'wrong_amount', 'wrong_sponsor', 'missing_field', 'malformed', 'multiple', 'empty', 'bad_number'])
def test_terminal_success_never_hides_wrong_or_missing_source_values(work, change):
    target = work[3][0]
    keys = [f.meaning for f in work[0].fields]
    if change == 'wrong_pi':
        target['entities'][0][keys[0]] = 'Dr. Robert Kim'
    elif change == 'wrong_amount':
        target['entities'][0][keys[2]] = '32000'
    elif change == 'wrong_sponsor':
        target['entities'][0][keys[4]] = 'Department of Energy'
    elif change == 'missing_field':
        del target['entities'][0][keys[3]]
    elif change == 'malformed':
        target['entities'] = {'answer': 'plausible'}
    elif change == 'multiple':
        target['entities'] *= 2
    elif change == 'empty':
        target['entities'] = []
    else:
        target['entities'][0][keys[2]] = '320000 or 410000'
    checked = inventory(work)
    assert checked['all_items_completed'] is True and checked['all_values_source_supported'] is False
    assert checked['all_values_complete'] is (change in ('wrong_pi', 'wrong_amount', 'wrong_sponsor'))


@pytest.mark.parametrize('change', ['retry_success', 'duplicate_retry', 'same_run', 'wrong_source', 'still_failed', 'wrong_value', 'no_retry'])
def test_recovery_cannot_repeat_success_or_claim_unresolved_work_passed(work, change):
    retry = retry_middle(work)
    fail_middle(work)
    retries = [retry]
    if change == 'retry_success':
        retry = deepcopy(work[3][0])
        retry.update(run_id=uuid4().hex, attempt_kind='retry')
        retries = [retry]
    elif change == 'duplicate_retry':
        retries.append(deepcopy(retry))
    elif change == 'same_run':
        retry['run_id'] = work[2]
    elif change == 'wrong_source':
        retry['source_sha256'] = work[0].sources[0].sha256
    elif change == 'still_failed':
        retry.update(status='failed', reason='extraction_unavailable', entities=None)
    elif change == 'wrong_value':
        retry['entities'][0][work[0].fields[2].meaning] = '999999'
    else:
        retries = []
    if change in ('still_failed', 'wrong_value', 'no_retry'):
        result = check_recovery(work[0], work[1], work[3], retries, batch_id=work[2])
        assert not result['targeted_recovery_supported'] and not result['all_values_source_supported']
    else:
        with pytest.raises(CourseCatalogError):
            check_recovery(work[0], work[1], work[3], retries, batch_id=work[2])


def test_pilot_requires_exact_two_case_subset_and_cannot_substitute_a_single_easy_case(work):
    case, snapshot, batch_id, results = work
    selected = [results[0], results[2]]
    for item in selected:
        item['attempt_kind'] = 'pilot'
    assert inventory((case, snapshot, batch_id, selected), kind='pilot', source_ids=case.pilot_source_ids)['all_values_source_supported']
    with pytest.raises(CourseCatalogError):
        inventory((case, snapshot, batch_id, selected[:1]), kind='pilot', source_ids=['proposal_1'])
