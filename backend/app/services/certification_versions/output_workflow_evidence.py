"""Assemble exact file contents, private receipt facts and learner interpretations."""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import package_outcomes
from .output_case import load_output_case
from .output_file_reviews import OutputFileReviewRepository
from .output_outcome_reviews import OutputOutcomeReviewRepository, restore_handoff
from .output_workflow_preparation import OutputWorkflowPreparation
from .practical_evidence import EvidenceAssemblyUnavailable


async def assemble_output_review(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Output assessment requires the authenticated learner')
    saved = await OutputOutcomeReviewRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Save the actual handoff interpretation before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    package = operation.package
    case, contract = load_output_case(package), package_outcomes(package)
    review = OutputFileReviewRepository.decode(saved['file_review'])
    run = OutputWorkflowPreparation.decode(review['execution'])
    plan, result = run['plan'], run['result']
    snapshot, artifacts = plan['input_snapshot'], result['generated_artifacts']
    handoff = restore_handoff(saved['handoff'], artifacts)
    if (saved['case'] != case.public_definition() or snapshot['case'] != case.public_definition()
            or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json']
            or snapshot['rubric_id'] != contract.rubric_id):
        raise CourseCatalogError('Output evidence does not bind the original assignment and rubric')
    evidence = []
    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Output evidence exceeds review limits; nothing was truncated') from exc
    binding = {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'result_sha256': encode(result)[1],
        'case_sha256': case.digest, 'artifacts_sha256': encode(artifacts)[1],
        'file_review_id': review['uuid'], 'file_review_sha256': encode(review)[1]}
    add('execution_receipt', 'output-execution:' + run['run_id'], {**binding,
        'provenance': 'actual_completed_owned_generation_not_delivery_or_credit',
        'authorization': run['authorization'], 'scope': plan['scope'], 'effective_stages': plan['stage_plans'],
        'result': {key: value for key, value in result.items() if key != 'generated_artifacts'},
        'assignment': case.public_definition()})
    # Source content is part of file inspection evidence, not a model-generated
    # replacement source or an unsupported additional rubric evidence kind.
    for document in snapshot['documents']:
        for offset in range(0, max(1, len(document['text'])), 6000):
            add('artifact_file_snapshot', f'output-source:{document["document_id"]}:{offset}', {**binding,
                'role': 'original_assigned_source_for_comparison', 'document_id': document['document_id'],
                'source_sha256': document['source_sha256'], 'text_offset': offset, 'text_length': len(document['text']),
                'text': document['text'][offset:offset + 6000]})
    for index, file in enumerate(artifacts['files']):
        metadata = {key: value for key, value in file.items() if key not in ('data_base64', 'inspection')}
        inspection = file['inspection']
        # The entire extracted content is chunked, not summarized or truncated.
        # CSV text retains all original header/row values; parsed rows are not
        # duplicated into the packet.
        for offset in range(0, max(1, len(inspection['text'])), 6000):
            add('artifact_file_snapshot', f'output-file:{index}:{offset}', {**binding, **metadata,
                'role': 'actual_generated_file_content', 'inspection': {key: value for key, value in inspection.items()
                                                                       if key not in ('text', 'rows')},
                'text_offset': offset, 'text_length': len(inspection['text']),
                'text': inspection['text'][offset:offset + 6000]})
    bundle = {key: value for key, value in artifacts['download'].items() if key != 'data_base64'}
    add('artifact_file_snapshot', 'output-bundle:' + run['run_id'], {**binding,
        'role': 'verified_actual_download_members', 'download': bundle,
        'members': [{key: file[key] for key in ('filename', 'sha256', 'size_bytes', 'file_type')} for file in artifacts['files']],
        'all_required_files_parseable': artifacts['all_required_files_parseable'],
        'notice': 'Server parsing and member verification do not establish learner inspection, source correctness or a passing grade.'})
    add('destination_snapshot', 'output-destination:' + handoff['uuid'], {**binding,
        'destination': handoff['destination'], 'external_delivery': False,
        'notice': 'Contained learner-only training inbox; no sponsor submission, email or staff recipient.'})
    receipts = [handoff['previous_failed_receipt'], handoff] if handoff['previous_failed_receipt'] else [handoff]
    for receipt in receipts:
        add('delivery_receipt', 'output-handoff:' + receipt['uuid'], {**binding,
            **{key: value for key, value in receipt.items() if key not in ('destination_copy', 'previous_failed_receipt', 'release_authorization')},
            'receipt_sha256': encode(receipt)[1],
            'destination_copy_sha256': encode(receipt['destination_copy'])[1] if receipt['destination_copy'] else None,
            'notice': 'First rejection is authored training behavior. A saved private copy is not an external delivery.'})
    add('learner_decision', 'output-inspection:' + review['uuid'], {**binding,
        'actor_user_id': actor_user_id, 'submission_channel': review['submission_channel'], 'submitted_at': review['submitted_at'],
        'submission': review['submission'], 'questions': [q.model_dump(mode='json') for q in case.questions
                                                        if q.phase == 'after_generation_before_release'],
        'notice': 'Opening acknowledgements and prose must be assessed against actual file content; their presence is not a passing criterion.'})
    add('learner_decision', 'output-interpretation:' + saved['uuid'], {**binding,
        'actor_user_id': actor_user_id, 'submission_channel': saved['submission_channel'], 'submitted_at': saved['submitted_at'],
        'question': next(q.model_dump(mode='json') for q in case.questions if q.id == 'delivery_review'),
        'handoff_id': handoff['uuid'], 'answer': saved['submission']['delivery_review']})
    try:
        outcomes, checked, digest = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('Complete output evidence does not fit the review packet; nothing was truncated') from exc
    if any(set(outcome.evidence) - {item.kind for item in checked} for outcome in outcomes):
        raise EvidenceAssemblyUnavailable('Required output evidence is missing; no assessment was saved')
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True, 'evidence_sha256': digest,
        'evidence': [item.model_dump(mode='json') for item in checked],
        'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
        'provenance': {'record_kind': 'saved_output_result_review', 'output_review_submission_id': submission_id,
            'output_review_submission_sha256': encode(saved)[1], 'run_id': run['run_id'],
            'result_sha256': encode(result)[1], 'case_sha256': case.digest,
            'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
