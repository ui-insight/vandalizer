"""Resolve a bounded pilot, full batch or exact failed-item retry; no dispatch."""
from copy import deepcopy
import hashlib
from pathlib import Path

from .attempts import encode
from .batch_case import BatchCase
from .batch_checks import check_inventory, item_id
from .batch_inputs import BatchInputRepository
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import execution_plan, implementation_digest as extraction_implementation_digest


def implementation_digest():
    folder = Path(__file__).parent
    paths = sorted(folder.glob('batch_*.py')) + [folder / 'connected_workflow_approval.py', folder / 'validation_checks.py']
    return encode({'extraction': extraction_implementation_digest(),
        'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}})[1]


def embedded_input(snapshot):
    serialized, digest = encode(snapshot)
    return {**{key: snapshot[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'artifact_id')},
            'record_json': serialized, 'record_sha256': digest}


def _original_run(snapshot, run, phase):
    if (run is None or run['state'] != 'completed' or run['plan']['phase'] != phase
            or run['plan']['input_snapshot'] != snapshot or run['result']['status'] != 'completed'
            or any(run['plan'][key] != snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))):
        raise EnrollmentConflict('Use the exact complete original run, captured revision and course for this next action')


def bind_inputs(snapshot, case, *, run_id, phase, parent=None, failed_source_id=None, previous_retry=None):
    """Parents must be decoded by the trusted durable-run repository first."""
    snapshot = BatchInputRepository.decode(embedded_input(snapshot))
    if not isinstance(case, BatchCase) or snapshot['case'] != case.public_definition():
        raise EnrollmentConflict('The saved inputs must bind this exact original batch case')
    if phase == 'pilot':
        if parent is not None or previous_retry is not None or failed_source_id is not None:
            raise EnrollmentConflict('A new pilot cannot silently inherit another run or retry scope')
        sources, batch_id = case.pilot_source_ids, run_id
    elif phase == 'batch':
        if previous_retry is not None or failed_source_id is not None:
            raise EnrollmentConflict('A complete batch is not a targeted retry')
        _original_run(snapshot, parent, 'pilot')
        checks = check_inventory(case, snapshot, parent['result']['item_results'], batch_id=parent['run_id'],
            run_id=parent['run_id'], attempt_kind='pilot', source_ids=case.pilot_source_ids)
        if not checks['all_items_completed'] or not checks['all_values_source_supported']:
            raise EnrollmentConflict('Inspect and repair a complete source-supported pilot before scaling')
        sources, batch_id = tuple(s.id for s in case.sources), run_id
    elif phase == 'retry':
        _original_run(snapshot, parent, 'batch')
        original_results = parent['result']['item_results']
        check_inventory(case, snapshot, original_results, batch_id=parent['run_id'], run_id=parent['run_id'],
                        attempt_kind='batch', source_ids=tuple(s.id for s in case.sources))
        original = next((r for r in original_results if r['source_id'] == failed_source_id), None)
        if original is None or original['status'] != 'failed':
            raise EnrollmentConflict('Only an exact confirmed failed original item may be retried; preserve successful items')
        if previous_retry is not None:
            _original_run(snapshot, previous_retry, 'retry')
            if previous_retry['plan']['batch_id'] != parent['run_id'] or previous_retry['plan']['source_ids'] != [failed_source_id]:
                raise EnrollmentConflict('A subsequent retry must preserve the same failed item and original batch')
            checks = check_inventory(case, snapshot, previous_retry['result']['item_results'], batch_id=parent['run_id'],
                run_id=previous_retry['run_id'], attempt_kind='retry', source_ids=[failed_source_id])
            if not checks['failed_document_ids']:
                raise EnrollmentConflict('A successful retry cannot be repeated as failed work')
        sources, batch_id = (failed_source_id,), parent['run_id']
    else:
        raise EnrollmentConflict('Choose an explicit bounded pilot, complete batch or targeted retry')
    if parent is not None and run_id == parent['run_id'] or previous_retry is not None and run_id == previous_retry['run_id']:
        raise EnrollmentConflict('Each new execution must preserve a distinct request identity')
    return {'phase': phase, 'batch_id': batch_id, 'source_ids': list(sources),
        'parent_run_id': parent['run_id'] if parent else None, 'parent_run_sha256': encode(parent)[1] if parent else None,
        'failed_source_id': failed_source_id, 'previous_retry_id': previous_retry['run_id'] if previous_retry else None,
        'previous_retry_sha256': encode(previous_retry)[1] if previous_retry else None}


def item_plans(snapshot, *, run_id, batch_id, phase, source_ids):
    sources = {s['source_id']: s for s in snapshot['documents']}
    return [{'item_id': item_id(batch_id, sources[sid]['document_id']), 'batch_id': batch_id, 'run_id': run_id,
        'attempt_kind': phase, 'source_id': sid, 'document_id': sources[sid]['document_id'],
        'source_sha256': sources[sid]['source_sha256'], 'source_text_sha256': encode(sources[sid]['pages'])[1],
        'doc_texts': ['\n\n'.join(sources[sid]['pages'])], 'field_keys': [f['searchphrase'].strip() for f in snapshot['artifact']['fields']],
        'field_metadata': [{'key': f['searchphrase'].strip(), 'is_optional': f['is_optional'], 'enum_values': f['enum_values']}
                           for f in snapshot['artifact']['fields']]} for sid in source_ids]


def batch_plan(snapshot, case, system_config, *, run_id, phase, parent=None, failed_source_id=None, previous_retry=None):
    try:
        binding = bind_inputs(snapshot, case, run_id=run_id, phase=phase, parent=parent,
                              failed_source_id=failed_source_id, previous_retry=previous_retry)
    except CourseCatalogError as exc:
        raise EnrollmentConflict(str(exc)) from exc
    resolved = execution_plan({'artifact': snapshot['artifact']}, deepcopy(system_config))
    # Same instructions alone cannot justify scaling onto a different model or
    # route. Keep the exact effective configuration and provider settings bound
    # to the checked pilot; credential rotation is excluded by runtime_digest.
    for prior in (parent, previous_retry):
        if prior and any(prior['plan'].get(key) != resolved[key] for key in
                         ('runtime_config_sha256', 'effective_extraction_config', 'model_info', 'model_names', 'capture_sources')):
            raise EnrollmentConflict('This action changed the pilot or original batch model configuration; run a new pilot before scaling')
    return {**resolved, **binding, 'executor_id': 'saved-bounded-batch.1', 'implementation_sha256': implementation_digest(),
        'input_snapshot_sha256': encode(snapshot)[1], 'case_sha256': case.digest,
        'item_plans': item_plans(snapshot, run_id=run_id, batch_id=binding['batch_id'], phase=phase, source_ids=binding['source_ids']),
        'execution_authorized': False, 'credit_awarded': False, 'external_effects_authorized': False}
