"""Resolve the exact original diagnostic extraction after learner scope correction."""
from copy import deepcopy
import datetime
import hashlib
from pathlib import Path

from .attempts import encode
from .enrollments import EnrollmentConflict
from .governance_case import GovernanceCase
from .governance_checks import embedded_input
from .governance_inputs import GovernanceInputRepository
from .governance_scope import GovernanceScopeCorrection
from .lab_execution import execution_plan, implementation_digest as extraction_implementation_digest


def implementation_digest():
    folder = Path(__file__).parent
    paths = sorted(folder.glob('governance_*.py')) + [folder / 'connected_workflow_approval.py', folder / 'batch_checks.py', folder / 'validation_checks.py']
    return encode({'extraction': extraction_implementation_digest(), 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})[1]


def validate_scope_binding(snapshot, correction, case):
    snapshot = GovernanceInputRepository.decode(embedded_input(snapshot))
    serialized, digest = encode(correction)
    correction = GovernanceScopeCorrection.decode({**correction, 'record_json': serialized, 'record_sha256': digest})
    if (not isinstance(case, GovernanceCase) or snapshot['case'] != case.public_definition() or correction['case'] != case.public_definition()
            or GovernanceInputRepository.decode(correction['input_snapshot']) != snapshot
            or any(snapshot[key] != correction[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))):
        raise EnrollmentConflict('The original diagnostic run requires the learner correction for this exact captured revision and source scope')
    return digest


def extraction_input(snapshot, run_id, phase='original'):
    # Both complete records jointly inform one result. Preserve exact text and
    # source boundaries; do not let separate per-document outputs masquerade as
    # a reconciled award/amendment interpretation.
    text = '\n\n'.join(f"SOURCE {source['source_id']}: {source['assigned_filename']}\n" + '\n\n'.join(source['pages']) for source in snapshot['documents'])
    return {'run_id': run_id, 'phase': phase, 'artifact_sha256': snapshot['artifact_sha256'],
        'source_document_ids': [s['document_id'] for s in snapshot['documents']],
        'source_sha256s': [s['source_sha256'] for s in snapshot['documents']], 'doc_texts': [text],
        'field_keys': [f['searchphrase'].strip() for f in snapshot['artifact']['fields']],
        'field_metadata': [{'key': f['searchphrase'].strip(), 'is_optional': f['is_optional'], 'enum_values': f['enum_values']} for f in snapshot['artifact']['fields']]}


def validate_repair_binding(snapshot, correction, case, finding):
    from .governance_findings import GovernanceFindingRepository
    from .governance_preparation import GovernancePreparation
    snapshot = GovernanceInputRepository.decode(embedded_input(snapshot))
    serialized, digest = encode(finding)
    finding = GovernanceFindingRepository.decode({**finding, 'record_json': serialized, 'record_sha256': digest})
    original = GovernancePreparation.decode(finding['execution'])
    before = original['plan']['input_snapshot']
    validate_scope_binding(before, correction, case)
    if (snapshot['artifact_id'] != before['artifact_id'] or snapshot['artifact_sha256'] == before['artifact_sha256']
            or snapshot['artifact']['domain'] != before['artifact']['domain']
            or any(snapshot[k] != before[k] for k in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'documents', 'case'))
            or [f['id'] for f in snapshot['artifact']['fields']] != [f['id'] for f in before['artifact']['fields']]
            or datetime.datetime.fromisoformat(snapshot['captured_at']) <= datetime.datetime.fromisoformat(finding['submitted_at'])):
        raise EnrollmentConflict('Capture a changed revision of the same extraction after the saved finding, keeping both complete original sources')
    changed = [a['title'] for a, b in zip(before['artifact']['fields'], snapshot['artifact']['fields']) if a != b]
    if 'Funds Obligated to Date' not in changed:
        raise EnrollmentConflict('Repair the original funding field; changing a title or another field is not that repair')
    return original, changed, digest


def governance_plan(snapshot, correction, case, system_config, *, run_id, finding=None):
    original, changed, finding_hash = None, [], None
    if finding is None:
        digest = validate_scope_binding(snapshot, correction, case)
        phase = 'original'
    else:
        original, changed, finding_hash = validate_repair_binding(snapshot, correction, case, finding)
        digest, phase = encode(correction)[1], 'repair'
    resolved = execution_plan({'artifact': snapshot['artifact']}, deepcopy(system_config))
    if original is not None and any(resolved[k] != original['plan'][k] for k in
            ('runtime_config_sha256', 'effective_extraction_config', 'model_info', 'model_names', 'capture_sources')):
        raise EnrollmentConflict('Keep the original resolved model and settings for this instruction-repair retest')
    return {**resolved, 'executor_id': 'saved-governance-capstone.1', 'implementation_sha256': implementation_digest(),
        'input_snapshot_sha256': encode(snapshot)[1], 'case_sha256': case.digest, 'phase': phase,
        'scope_correction_id': correction['uuid'], 'scope_correction_sha256': digest,
        'source_finding_id': finding['uuid'] if finding else None, 'source_finding_sha256': finding_hash,
        'original_run_id': original['run_id'] if original else None,
        'original_run_sha256': encode(original)[1] if original else None, 'changed_fields': changed,
        'extraction_input': extraction_input(snapshot, run_id, phase),
        'execution_authorized': False, 'external_effects_authorized': False, 'credit_awarded': False}
