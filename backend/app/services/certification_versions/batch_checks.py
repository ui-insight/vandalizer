"""Exact per-input coverage and source checks over trusted actual batch receipts.

These functions do not authenticate client evidence, approve a retry or award
credit. Repositories must supply decoded captures and durable engine receipts.
"""
import datetime

from .attempts import encode
from .batch_case import FIELDS
from .catalog import CourseCatalogError
from .validation_checks import canonical as numeric_or_name


def canonical(value, comparison):
    if comparison != 'exact_text':
        return numeric_or_name(value, comparison)
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        return ('unrecognized', None)
    return ('value', ' '.join(value.split()).casefold())


def item_id(batch_id, document_id):
    return encode({'batch_id': batch_id, 'document_id': document_id})[1][:32]


def check_item(case, snapshot, result, *, batch_id, run_id, attempt_kind):
    source = next((s for s in snapshot['documents'] if s['source_id'] == result.get('source_id')), None)
    if (source is None or snapshot['case'] != case.public_definition()
            or result.get('document_id') != source['document_id'] or result.get('source_sha256') != source['source_sha256']
            or result.get('artifact_sha256') != snapshot['artifact_sha256']
            or result.get('batch_id') != batch_id or result.get('run_id') != run_id
            or result.get('item_id') != item_id(batch_id, source['document_id']) or result.get('attempt_kind') != attempt_kind
            or result.get('status') not in ('completed', 'failed') or type(result.get('elapsed_ms')) is not int
            or result['elapsed_ms'] < 0 or result.get('usage') is not None or result.get('cost') is not None
            or result.get('external_effects') is not False):
        raise CourseCatalogError('Batch checks require exact original input, revision, run and resource evidence')
    try:
        if any(datetime.datetime.fromisoformat(result[key]).tzinfo is None for key in ('started_at', 'finished_at')):
            raise ValueError('Missing timezone')
    except (KeyError, ValueError, TypeError) as exc:
        raise CourseCatalogError('A terminal item requires actual bounded execution timing') from exc
    controlled = result.get('reason') == 'controlled_training_rejection_before_dispatch'
    if result['status'] == 'failed':
        if (result.get('entities') is not None or result.get('reason') not in
                ('controlled_training_rejection_before_dispatch', 'extraction_unavailable')
                or controlled and (attempt_kind != 'batch' or source['source_id'] != case.controlled_failure_source_id
                                   or result.get('extraction_started') is not False)
                or not controlled and result.get('extraction_started') is not True):
            raise CourseCatalogError('The failed item changed its actual execution or disclosed failure boundary')
    elif result.get('reason') is not None or result.get('extraction_started') is not True:
        raise CourseCatalogError('A completed extraction requires an actual started extraction and no failure reason')
    fields = {field['title']: field['searchphrase'].strip() for field in snapshot['artifact']['fields']}
    if tuple(fields) != FIELDS:
        raise CourseCatalogError('Check each of the five original logical fields')
    entities = result.get('entities')
    complete = result['status'] == 'completed' and isinstance(entities, list) and len(entities) == 1 and isinstance(entities[0], dict)
    output = entities[0] if complete else {}
    expectations = {e.field: e for e in case.expectations if e.source_id == source['source_id']}
    checks = []
    for field in case.fields:
        key = fields[field.title]
        present = complete and key in output
        actual = canonical(output[key], field.comparison) if present else ('unavailable', None)
        expected = canonical(expectations[field.title].expected_value, field.comparison)
        comparable = present and actual[0] not in ('unrecognized', 'unavailable')
        checks.append({'field': field.title, 'actual_value': output.get(key) if present else None,
            'output_present': bool(present), 'output_comparable': bool(comparable),
            'matches_source': bool(comparable and actual == expected),
            'status': 'supported' if comparable and actual == expected else 'revision_required' if comparable else 'unavailable'})
    return {'source_id': source['source_id'], 'document_id': source['document_id'], 'item_id': result['item_id'],
        'batch_id': batch_id, 'run_id': run_id, 'status': result['status'], 'receipt_sha256': encode(result)[1],
        'fields': checks, 'complete_values': all(c['output_comparable'] for c in checks),
        'source_supported': all(c['matches_source'] for c in checks), 'credit_awarded': False}


def check_inventory(case, snapshot, results, *, batch_id, run_id, attempt_kind, source_ids):
    required = tuple(s.id for s in case.sources)
    allowed = case.pilot_source_ids if attempt_kind == 'pilot' else required if attempt_kind == 'batch' else None
    if (attempt_kind not in ('pilot', 'batch', 'retry') or allowed is not None and tuple(source_ids) != allowed
            or attempt_kind == 'retry' and (len(source_ids) != 1 or source_ids[0] not in required)
            or [r.get('source_id') for r in results] != list(source_ids)):
        raise CourseCatalogError('A batch inventory must retain the exact distinct assigned input set and order')
    checks = [check_item(case, snapshot, result, batch_id=batch_id, run_id=run_id, attempt_kind=attempt_kind) for result in results]
    if len({c['document_id'] for c in checks}) != len(source_ids):
        raise CourseCatalogError('Repeated inputs cannot replace missing assigned documents')
    return {'batch_id': batch_id, 'run_id': run_id, 'attempt_kind': attempt_kind,
        'source_ids': list(source_ids), 'document_ids': [c['document_id'] for c in checks],
        'items': checks, 'terminal_coverage_complete': True,
        'all_items_completed': all(c['status'] == 'completed' for c in checks),
        'all_values_complete': all(c['complete_values'] for c in checks),
        'all_values_source_supported': all(c['source_supported'] for c in checks),
        'completed_document_ids': [c['document_id'] for c in checks if c['status'] == 'completed'],
        'failed_document_ids': [c['document_id'] for c in checks if c['status'] == 'failed'],
        'elapsed_ms': sum(r['elapsed_ms'] for r in results), 'usage': None, 'cost': None,
        'credit_awarded': False, 'module_completion_eligible': False}


def check_recovery(case, snapshot, originals, retries, *, batch_id):
    """Reconcile final retry receipts selected by a trusted saved recovery chain.

    Every retry must target an originally failed item. A caller cannot use a
    favorable response for an originally successful item, or erase that item.
    Retry repository claims separately enforce one active recovery per item and
    preserve all earlier failed/uncertain attempts; this checker grants no claim.
    """
    baseline = check_inventory(case, snapshot, originals, batch_id=batch_id, run_id=batch_id,
                               attempt_kind='batch', source_ids=tuple(s.id for s in case.sources))
    if len({r.get('source_id') for r in retries}) != len(retries):
        raise CourseCatalogError('A reconciled inventory requires one selected final retry per failed item')
    failed = {r['source_id']: r for r in originals if r['status'] == 'failed'}
    replacements = {}
    for retry in retries:
        original = failed.get(retry.get('source_id'))
        if original is None or retry.get('run_id') == batch_id:
            raise CourseCatalogError('Only a confirmed failed original item can have a distinct targeted retry')
        checked = check_item(case, snapshot, retry, batch_id=batch_id, run_id=retry['run_id'], attempt_kind='retry')
        replacements[retry['source_id']] = checked
    items = [replacements.get(c['source_id'], c) for c in baseline['items']]
    return {'batch_id': batch_id, 'original_inventory': baseline, 'reconciled_items': items,
        'original_successes_preserved': [{'document_id': c['document_id'], 'receipt_sha256': c['receipt_sha256']}
                                         for c in baseline['items'] if c['status'] == 'completed'],
        'original_failed_document_ids': baseline['failed_document_ids'],
        'retry_document_ids': [r['document_id'] for r in retries],
        'all_assigned_terminal': True, 'all_assigned_successful': all(c['status'] == 'completed' for c in items),
        'all_values_source_supported': all(c['source_supported'] for c in items),
        'targeted_recovery_supported': bool(retries) and all(c['status'] == 'completed' and c['source_supported'] for c in items),
        'credit_awarded': False, 'module_completion_eligible': False}
