"""Collect exact source, pilot, inventory and recovery evidence for automatic review."""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .batch_case import load_batch_case
from .batch_preparation import BatchPreparation
from .batch_reviews import BatchReviewRepository
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import package_outcomes
from .practical_evidence import EvidenceAssemblyUnavailable

REQUIREMENT_KEYS = ('id', 'statement', 'method', 'evidence', 'passing_conditions', 'critical_failures')
REQUIREMENTS_SHA256 = '98998a3d3cee237eea5be427ef0383e80fed74ed5bca6a33a8e152cceecb0c59'


async def assemble_batch_review(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Batch assessment requires the authenticated learner')
    saved = await BatchReviewRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Save the actual batch interpretation before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    package = operation.package
    case, contract = load_batch_case(package), package_outcomes(package)
    original = BatchPreparation.decode(saved['execution'])
    pilot = BatchPreparation.decode(original['plan']['parent_run_record'])
    retries = [BatchPreparation.decode(raw) for raw in saved['retry_executions']]
    snapshot = original['plan']['input_snapshot']
    if (saved['case'] != case.public_definition() or snapshot['case'] != case.public_definition()
            or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json'] or snapshot['rubric_id'] != contract.rubric_id):
        raise CourseCatalogError('Batch evidence differs from the original assignment and rubric')
    # Include all failed earlier retries, not just the selected final attempt.
    ancestors = {}
    for run in retries:
        cursor = run
        while cursor:
            ancestors[cursor['run_id']] = cursor
            raw = cursor['plan']['previous_retry_record']
            cursor = BatchPreparation.decode(raw) if raw else None
    runs = [('pilot', pilot), ('batch', original), *[('retry', run) for run in ancestors.values()]]
    for _, run in runs:
        if any(item['status'] == 'completed' and not item['complete_values'] for item in run['result']['checks']['items']):
            raise EvidenceAssemblyUnavailable('Missing or uncomparable output values are unavailable evidence; inspect the saved item before assessment')
    evidence = []

    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Batch evidence exceeds review limits; no content was truncated') from exc

    def chunks(kind, identity, text, metadata):
        for offset in range(0, max(1, len(text)), 6000):
            add(kind, f'{identity}:{offset}', {**metadata, 'text_offset': offset, 'text_length': len(text), 'text': text[offset:offset + 6000]})

    binding = {'case_sha256': case.digest, 'batch_id': original['run_id'], 'pilot_run_id': pilot['run_id']}
    add('batch_result_snapshot', 'batch-assigned-inputs', {**binding,
        'documents': [{key: doc[key] for key in ('source_id', 'document_id', 'assigned_filename', 'source_sha256')} for doc in snapshot['documents']]})
    for document in snapshot['documents']:
        for page, text in enumerate(document['pages'], 1):
            chunks('batch_result_snapshot', f'batch-source:{document["source_id"]}:{page}', text,
                {**binding, 'source_id': document['source_id'], 'document_id': document['document_id'], 'page': page,
                 'source_sha256': document['source_sha256'], 'role': 'complete_original_pdf_page'})
    add('execution_receipt', 'batch-artifact', {**binding, 'artifact': snapshot['artifact'], 'artifact_sha256': snapshot['artifact_sha256'],
        'effective_extraction_config': original['plan']['effective_extraction_config'], 'model_names': original['plan']['model_names'],
        'notice': 'The checked pilot, original batch and retries use this exact same captured extraction and resolved models.'})
    for label, run in runs:
        result, plan = run['result'], run['plan']
        identity = label + ':' + run['run_id']
        kind = {'pilot': 'pilot_result_snapshot', 'batch': 'batch_result_snapshot', 'retry': 'retry_receipt'}[label]
        add('execution_receipt', 'batch-execution:' + identity, {**binding, 'phase': label, 'run_id': run['run_id'],
            'plan_sha256': run['plan_sha256'], 'result_sha256': encode(result)[1], 'state': run['state'],
            'implementation_sha256': plan['implementation_sha256'], 'model_names': plan['model_names'],
            'source_ids': plan['source_ids'], 'item_receipt_sha256s': [e['receipt_sha256'] for e in run['item_events']],
            'checks': result['checks'], 'started_at': result['started_at'], 'finished_at': result['finished_at'],
            'notice': 'Terminal coverage includes failed items. Usage and cost are unknown; elapsed time alone does not establish quality.'})
        for index, item in enumerate(result['item_results']):
            chunks(kind, f'batch-output:{identity}:{index}', encode(item)[0],
                {**binding, 'run_id': run['run_id'], 'item_result_sha256': encode(item)[1], 'role': 'actual_engine_item_result'})
        add('learner_decision', 'batch-scope:' + identity, {**binding, 'phase': label, 'authorization': run['authorization'],
            'notice': 'The authenticated reason was saved before this exact internal action. Approval is not evidence of a passing explanation.'})
    add('learner_decision', 'batch-answer:' + submission_id, {**binding, 'actor_user_id': actor_user_id,
        'submission_channel': saved['submission_channel'], 'submitted_at': saved['submitted_at'],
        'question': next(q.model_dump(mode='json') for q in case.questions if q.id == 'batch_review'),
        'answer': saved['submission']['answers']['batch_review']})
    check_id = 'batch-reconciled-original-inventory'
    reconciliation = saved['reconciliation']
    add('batch_result_snapshot', check_id, {**binding, **reconciliation,
        'notice': 'Original successful receipts and original failures remain preserved. Source checks may veto a favorable model verdict but cannot establish learner understanding.'})
    module = next(m for m in contract.modules if m.module_id == case.module_id)
    deterministic_required = [o for o in module.outcomes if o.method == 'deterministic']
    if (len(deterministic_required) != 1 or deterministic_required[0].id != 'batch_processing.assigned_coverage'
            or encode({key: deterministic_required[0].model_dump(mode='json')[key] for key in REQUIREMENT_KEYS})[1] != REQUIREMENTS_SHA256):
        raise CourseCatalogError('Batch coverage has no verified checker for these changed requirements')
    deterministic = {'outcome_id': 'batch_processing.assigned_coverage', 'method': 'deterministic',
        'status': 'requirements_supported', 'passed': True, 'checker_id': 'exact-assigned-batch-inventory.1',
        'requirements_sha256': REQUIREMENTS_SHA256, 'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'run_id': original['run_id'], 'plan_sha256': original['plan_sha256'], 'result_sha256': encode(original['result'])[1],
        'input_snapshot_sha256': encode(snapshot)[1], 'case_sha256': case.digest,
        'explanation': 'Every distinct assigned document has its own terminal receipt in the intended original batch, including the retained failure. This does not establish successful usable output or recovery.',
        'revision_instruction': '', 'credit_awarded': False, 'module_completion_eligible': False}
    passed = reconciliation['targeted_recovery_supported']
    supporting = [{'outcome_id': 'batch_processing.targeted_recovery', 'check_id': 'source-checked-targeted-batch-recovery.1',
        'passed': passed, 'evidence_id': check_id, 'quote': encode({'targeted_recovery_supported': passed})[0][1:-1],
        'explanation': 'The exact retry restores source-supported values while preserving original successful receipts; learner reasoning still requires review.' if passed else
            'The selected recovery leaves failed or source-incorrect results in the assigned inventory.',
        'revision_instruction': '' if passed else 'Inspect the original and linked item results, address unresolved failures or incorrect values, and preserve successful original receipts before claiming usable recovery.'}]
    try:
        outcomes, checked, digest = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('Complete batch evidence cannot fit the review packet; nothing was truncated') from exc
    if any(set(outcome.evidence) - {item.kind for item in checked} for outcome in outcomes):
        raise EvidenceAssemblyUnavailable('Required batch assessment evidence is missing')
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True, 'evidence_sha256': digest,
        'evidence': [item.model_dump(mode='json') for item in checked], 'credit_awarded': False,
        'module_completion_eligible': False, 'staff_review_required': False,
        'provenance': {'record_kind': 'saved_batch_result_review', 'batch_review_submission_id': submission_id,
            'batch_review_submission_sha256': encode(saved)[1], 'run_id': original['run_id'],
            'result_sha256': encode(original['result'])[1], 'case_sha256': case.digest,
            'supporting_checks': supporting, 'deterministic_outcomes': [deterministic],
            'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
