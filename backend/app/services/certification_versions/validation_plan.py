"""Resolve the exact complete-suite execution without calling a provider."""
from copy import deepcopy
import hashlib
from pathlib import Path

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import execution_plan, implementation_digest as extraction_implementation_digest
from .validation_case import ValidationCase
from .validation_checks import check_suite, verify_repair_inputs
from .validation_inputs import ValidationInputRepository
from .validation_suites import ValidationSuiteRepository, embedded_input


def implementation_digest():
    folder = Path(__file__).parent
    paths = sorted(folder.glob('validation_*.py')) + [folder / 'connected_workflow_approval.py']
    return encode({'extraction': extraction_implementation_digest(),
        'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}})[1]


def case_plans(snapshot):
    return [{'source_id': s['source_id'], 'document_id': s['document_id'], 'source_sha256': s['source_sha256'],
             'source_text_sha256': encode(s['pages'])[1], 'doc_texts': ['\n\n'.join(s['pages'])],
             'field_keys': [f['searchphrase'].strip() for f in snapshot['artifact']['fields']],
             'field_metadata': [{'key': f['searchphrase'].strip(), 'is_optional': f['is_optional'], 'enum_values': f['enum_values']}
                                for f in snapshot['artifact']['fields']]} for s in snapshot['documents']]


def validate_suite_binding(snapshot, suite, case, *, original_run=None):
    """`original_run` must already be decoded by the trusted run repository."""
    snapshot = ValidationInputRepository.decode(embedded_input(snapshot))
    serialized, digest = encode(suite)
    suite = ValidationSuiteRepository.decode({**suite, 'record_json': serialized, 'record_sha256': digest})
    original_snapshot = ValidationInputRepository.decode(suite['input_snapshot'])
    if not isinstance(case, ValidationCase) or snapshot['case'] != case.public_definition() or suite['case'] != case.public_definition():
        raise EnrollmentConflict('The saved suite and extraction must bind the same original case')
    if any(snapshot[key] != suite[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')):
        raise EnrollmentConflict('The saved suite and extraction belong to different learners or courses')
    if original_run is None:
        if snapshot != original_snapshot:
            raise EnrollmentConflict('An original run must execute the revision on which the learner designed this suite')
        changed = []
        phase = 'original'
    else:
        prior = original_run['plan']
        if (original_run['state'] != 'completed' or prior['phase'] != 'original'
                or prior['suite']['uuid'] != suite['uuid'] or encode(prior['suite'])[1] != digest
                or prior['input_snapshot'] != original_snapshot):
            raise EnrollmentConflict('A retest must preserve the actual original completed run and its checked suite')
        original_checks = check_suite(case, original_snapshot, suite['test_cases'], original_run['result']['case_results'])
        if not original_checks['complete'] or not original_checks['observed_semantic_failure']:
            raise EnrollmentConflict('A retest requires a complete actual original value mismatch; unavailable evidence is not that failure')
        try:
            changed = verify_repair_inputs(original_snapshot, snapshot, suite['test_cases'], suite['test_cases'])
        except CourseCatalogError as exc:
            raise EnrollmentConflict(str(exc)) from exc
        phase = 'retest'
    sources = {source['source_id']: source for source in snapshot['documents']}
    for test_case in suite['test_cases']:
        source = sources[test_case['source_id']]
        if (test_case['document_id'] != source['document_id'] or test_case['source_sha256'] != source['source_sha256']
                or test_case['source_text_sha256'] != encode(source['pages'])[1]):
            raise EnrollmentConflict('Retesting cannot substitute different sources or excerpts for the original suite')
    return phase, changed, digest


def validation_plan(snapshot, suite, case, system_config, *, original_run=None):
    phase, changed, digest = validate_suite_binding(snapshot, suite, case, original_run=original_run)
    # Reuse production extraction configuration resolution only. The validation
    # record remains a distinct kind and cannot enter the generic lab executor.
    resolved = execution_plan({'artifact': snapshot['artifact']}, deepcopy(system_config))
    return {**resolved, 'executor_id': 'saved-representative-validation.1', 'implementation_sha256': implementation_digest(),
        'input_snapshot_sha256': encode(snapshot)[1], 'case_sha256': case.digest, 'suite_sha256': suite['suite_sha256'],
        'suite_record_sha256': digest, 'phase': phase, 'changed_fields': changed, 'case_plans': case_plans(snapshot),
        'original_run_id': original_run['run_id'] if original_run else None,
        'original_run_sha256': encode(original_run)[1] if original_run else None,
        'execution_authorized': False, 'credit_awarded': False, 'external_effects_authorized': False}
