"""Source-grounded checks over trusted complete capstone extraction receipts."""
import datetime
import re

from .attempts import encode
from .batch_checks import canonical as canonical_field
from .catalog import CourseCatalogError
from .governance_case import FIELDS
from .governance_inputs import GovernanceInputRepository


def embedded_input(snapshot):
    payload, digest = encode(snapshot)
    return {**{key: snapshot[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'artifact_id')},
            'record_json': payload, 'record_sha256': digest}


def canonical(value, comparison):
    if comparison != 'iso_date':
        return canonical_field(value, comparison)
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value.strip()):
        return ('unrecognized', None)
    try:
        return ('value', datetime.date.fromisoformat(value.strip()).isoformat())
    except ValueError:
        return ('unrecognized', None)


def check_result(case, snapshot, result, *, run_id, phase):
    snapshot = GovernanceInputRepository.decode(embedded_input(snapshot))
    if (snapshot['case'] != case.public_definition() or phase not in ('original', 'repair')
            or result.get('run_id') != run_id or result.get('phase') != phase
            or result.get('artifact_sha256') != snapshot['artifact_sha256']
            or result.get('source_sha256s') != [source['source_sha256'] for source in snapshot['documents']]
            or result.get('status') not in ('completed', 'failed') or result.get('credit_awarded') is not False):
        raise CourseCatalogError('Source checking requires the exact run, captured revision and both original records')
    if result['status'] == 'failed' and (result.get('entities') is not None or result.get('reason') != 'extraction_unavailable'):
        raise CourseCatalogError('A failed extraction cannot invent usable result values')
    if result['status'] == 'completed' and result.get('reason') is not None:
        raise CourseCatalogError('A completed extraction cannot hide a failure reason')
    entities = result.get('entities')
    complete = result['status'] == 'completed' and isinstance(entities, list) and len(entities) == 1 and isinstance(entities[0], dict)
    output = entities[0] if complete else {}
    fields = snapshot['artifact']['fields']
    if tuple(f['title'] for f in fields) != FIELDS:
        raise CourseCatalogError('The capstone source check requires every original field')
    checked = []
    for field, definition, expectation in zip(fields, case.fields, case.expectations):
        key = field['searchphrase'].strip()
        present = complete and key in output
        actual = canonical(output[key], definition.comparison) if present else ('unavailable', None)
        expected = canonical(expectation.expected_value, definition.comparison)
        comparable = present and actual[0] not in ('unrecognized', 'unavailable')
        checked.append({'field': field['title'], 'actual_value': output.get(key) if present else None,
            'output_present': bool(present), 'output_comparable': bool(comparable), 'matches_source': bool(comparable and actual == expected),
            'status': 'supported' if comparable and actual == expected else 'revision_required' if comparable else 'unavailable'})
    all_comparable = all(f['output_comparable'] for f in checked)
    supported = all(f['matches_source'] for f in checked)
    return {'run_id': run_id, 'phase': phase, 'fields': checked, 'complete': all_comparable, 'source_supported': supported,
        'observed_semantic_failure': all_comparable and not supported, 'result_sha256': encode(result)[1],
        'credit_awarded': False, 'module_completion_eligible': False}


def compare_repair(case, original, repaired):
    """Caller first decodes owned durable runs; this grants no dispatch authority."""
    before, after = original['plan']['input_snapshot'], repaired['plan']['input_snapshot']
    if (original['state'] != 'completed' or repaired['state'] != 'completed' or original['run_id'] == repaired['run_id']
            or original['plan']['phase'] != 'original' or repaired['plan']['phase'] != 'repair'
            or before['artifact_id'] != after['artifact_id'] or before['artifact_sha256'] == after['artifact_sha256']
            or any(before[key] != after[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'documents'))
            or [f['id'] for f in before['artifact']['fields']] != [f['id'] for f in after['artifact']['fields']]):
        raise CourseCatalogError('Repair must preserve the original assignment, sources and owned extraction fields while changing their instructions')
    old = check_result(case, before, original['result']['extraction'], run_id=original['run_id'], phase='original')
    new = check_result(case, after, repaired['result']['extraction'], run_id=repaired['run_id'], phase='repair')
    changed = [first['title'] for first, second in zip(before['artifact']['fields'], after['artifact']['fields']) if first != second]
    return {'original_run_id': original['run_id'], 'repaired_run_id': repaired['run_id'], 'changed_fields': changed,
        'original_checks': old, 'repaired_checks': new,
        'repair_requirements_supported': bool(changed) and old['observed_semantic_failure'] and new['source_supported'],
        'credit_awarded': False, 'module_completion_eligible': False}
