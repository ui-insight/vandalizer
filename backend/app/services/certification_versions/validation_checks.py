"""Source-bound validation comparisons; consistency never establishes accuracy.

These checks consume verified saved inputs/results. They cannot authenticate a
client result, provide a release grade or award credit. The automatic reviewer
still evaluates the learner's rationale, causal repair and coverage limits.
"""
from decimal import Decimal
import re

from .attempts import encode
from .catalog import CourseCatalogError
from .validation_case import FIELDS, ValidationCase

ABSENCE = {'not found', 'not stated', 'not named', 'none', 'null', 'n/a', 'na'}
AMOUNT = re.compile(r'^(?:USD\s*|\$\s*)?((?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?)(?:\s*USD)?$', re.I)


def canonical(value, comparison):
    """Deliberately bounded syntax, with no substring or approximate matching."""
    if value is None:
        return ('absent', None)
    if not isinstance(value, str) or len(value) > 1000:
        return ('unrecognized', None)
    value = ' '.join(value.split())
    if value.casefold() in ABSENCE:
        return ('absent', None)
    if not value:
        return ('unrecognized', None)
    if comparison == 'usd_amount':
        match = AMOUNT.fullmatch(value)
        return ('value', str(Decimal(match.group(1).replace(',', '')).normalize())) if match else ('unrecognized', None)
    if comparison in ('person_name', 'person_name_or_explicit_absence'):
        return ('value', re.sub(r'^dr\.?\s+', '', value.casefold()))
    raise CourseCatalogError('Unsupported validation comparison')


def check_case(case: ValidationCase, snapshot, suite_case, result):
    """Check all three fields, including explicit absence in an optional field.

    `result` is a durable engine receipt supplied by the authenticated collector,
    not a posted client answer. Technical incompleteness is never a value failure.
    """
    source_id = suite_case['source_id']
    source = next((s for s in snapshot['documents'] if s['source_id'] == source_id), None)
    if (source is None or snapshot['case'] != case.public_definition()
            or suite_case['source_sha256'] != source['source_sha256']
            or suite_case['document_id'] != source['document_id']
            or suite_case['source_text_sha256'] != encode(source['pages'])[1]
            or result.get('source_id') != source_id or result.get('source_sha256') != source['source_sha256']
            or result.get('artifact_sha256') != snapshot['artifact_sha256']):
        raise CourseCatalogError('Validation comparisons require the exact source and captured artifact revision')
    fields = {f['title']: f['searchphrase'].strip() for f in snapshot['artifact']['fields']}
    expectations = {e['field']: e for e in suite_case['expectations']}
    if len(expectations) != 3 or set(expectations) != set(FIELDS) or set(fields) != set(FIELDS):
        raise CourseCatalogError('Every required logical field must be represented exactly once')
    authored = {e.field: e for e in case.expectations if e.source_id == source_id}
    entities = result.get('entities')
    terminal = result.get('status') == 'completed'
    complete = terminal and isinstance(entities, list) and len(entities) == 1 and isinstance(entities[0], dict)
    output = entities[0] if complete else {}
    checks = []
    for field in case.fields:
        expected = expectations[field.title]
        target = canonical(authored[field.title].expected_value, field.comparison)
        learner = canonical(expected['expected_value'], field.comparison)
        kind_matches = expected['expected_kind'] == ('explicit_absence' if target[0] == 'absent' else 'value')
        expected_supported = learner == target and kind_matches
        present = complete and fields[field.title] in output
        actual = canonical(output[fields[field.title]], field.comparison) if present else ('unavailable', None)
        # Missing/malformed slots are incomplete evidence. A completed actual
        # value that disagrees with the source is an observed semantic mismatch.
        comparable = present and actual[0] != 'unrecognized'
        source_supported = comparable and actual == target
        checks.append({'field': field.title, 'output_key': fields[field.title],
            'expected_source_supported': expected_supported, 'output_present': bool(present),
            'output_comparable': bool(comparable), 'actual_value': output.get(fields[field.title]) if present else None,
            'matches_learner_expectation': bool(comparable and actual == learner),
            'matches_source': bool(source_supported), 'observed_value_mismatch': bool(comparable and not source_supported),
            'status': 'supported' if expected_supported and source_supported else 'unavailable' if not comparable else 'revision_required'})
    return {'source_id': source_id, 'source_sha256': source['source_sha256'], 'artifact_sha256': snapshot['artifact_sha256'],
        'result_sha256': encode(result)[1], 'all_fields_checked': all(c['output_comparable'] for c in checks),
        'all_expected_values_source_supported': all(c['expected_source_supported'] for c in checks),
        'all_results_source_supported': all(c['matches_source'] for c in checks),
        'observed_semantic_failure': any(c['observed_value_mismatch'] for c in checks), 'fields': checks,
        'optional_absence_checked': True, 'consistency_proves_accuracy': False, 'credit_awarded': False}


def check_suite(case, snapshot, cases, results):
    required = [s.id for s in case.sources]
    if ([s['source_id'] for s in cases] != required or [r.get('source_id') for r in results] != required):
        raise CourseCatalogError('Validation requires every distinct assigned case in its original order')
    checks = [check_case(case, snapshot, suite_case, result) for suite_case, result in zip(cases, results)]
    return {'case_sha256': case.digest, 'suite_sha256': encode(cases)[1], 'artifact_sha256': snapshot['artifact_sha256'],
        'cases': checks, 'complete': all(c['all_fields_checked'] for c in checks),
        'source_supported': all(c['all_expected_values_source_supported'] and c['all_results_source_supported'] for c in checks),
        'observed_semantic_failure': any(c['observed_semantic_failure'] for c in checks),
        'credit_awarded': False, 'module_completion_eligible': False}


def verify_repair_inputs(original_snapshot, corrected_snapshot, original_cases, corrected_cases):
    """A repaired revision preserves its source, learner and complete test suite."""
    for key in ('user_id', 'enrollment_id', 'course_version', 'manifest_sha256', 'artifact_id'):
        if original_snapshot[key] != corrected_snapshot[key]:
            raise CourseCatalogError('A repair must preserve the same learner, course and owned extraction')
    if original_cases != corrected_cases:
        raise CourseCatalogError('A repair cannot replace sources, expected values, source references or required cases')
    if original_snapshot['artifact_sha256'] == corrected_snapshot['artifact_sha256']:
        raise CourseCatalogError('A retest requires an actually changed saved extraction revision')
    # A title/config-only change cannot stand in for a repaired field instruction.
    original_fields = {f['title']: (f['id'], f['searchphrase'], f['is_optional'], f['enum_values']) for f in original_snapshot['artifact']['fields']}
    corrected_fields = {f['title']: (f['id'], f['searchphrase'], f['is_optional'], f['enum_values']) for f in corrected_snapshot['artifact']['fields']}
    if any(original_fields[title][0] != corrected_fields[title][0] for title in FIELDS):
        raise CourseCatalogError('Repair the same saved fields rather than replacing the assessed extraction')
    changed = [title for title in FIELDS if original_fields[title][1:] != corrected_fields[title][1:]]
    if not changed:
        raise CourseCatalogError('A field instruction or assessed field setting must actually change')
    return changed


def check_repair(case, original_snapshot, corrected_snapshot, original_cases, corrected_cases, original_results, corrected_results):
    """Require a real failure and the entire same suite on a changed revision."""
    changed = verify_repair_inputs(original_snapshot, corrected_snapshot, original_cases, corrected_cases)
    before = check_suite(case, original_snapshot, original_cases, original_results)
    after = check_suite(case, corrected_snapshot, corrected_cases, corrected_results)
    supported = before['complete'] and before['observed_semantic_failure'] and after['complete'] and after['source_supported']
    return {'before': before, 'after': after, 'changed_fields': changed,
        'repair_requirements_supported': supported, 'learner_explanation_requires_review': True,
        'credit_awarded': False, 'module_completion_eligible': False}
