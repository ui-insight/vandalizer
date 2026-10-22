"""Collect original, immutable connected-run evidence for automatic review."""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .catalog import CourseCatalogError
from .connected_workflow_checks import check_connected_execution
from .connected_workflow_preparation import ConnectedWorkflowPreparation
from .connected_workflow_reviews import ConnectedReviewRepository
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .multi_step_case import load_multi_step_case
from .outcomes import package_outcomes
from .practical_evidence import EvidenceAssemblyUnavailable


async def assemble_connected_review(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Connected assessment requires the authenticated learner')
    saved = await ConnectedReviewRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Save the original/corrected result comparison before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    package = operation.package
    case, contract = load_multi_step_case(package), package_outcomes(package)
    if saved['case'] != case.public_definition():
        raise CourseCatalogError('The saved comparison does not match its original assigned case')
    runs = {name: ConnectedWorkflowPreparation.decode(saved[name + '_execution']) for name in ('original', 'corrected')}
    for run in runs.values():
        LabExecutionRepository.check_operation(operation, run['plan'])
        snapshot = run['plan']['input_snapshot']
        if (snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json']
                or snapshot['rubric_id'] != contract.rubric_id):
            raise CourseCatalogError('The saved execution does not bind the original exercise and rubric')
    evidence = []

    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Connected evidence exceeds review limits; nothing was truncated') from exc

    # This is assigned-source context, explicitly not a learner source check or run.
    add('source_reference', 'authored-source-context:' + case.id, {
        'provenance': case.provenance, 'case_sha256': case.digest,
        'case': case.model_dump(mode='json'),
        'notice': 'This assignment, flawed example and source expectations are authored teaching material, not learner actions '
                  'or execution results. They establish no learner repair or source review. Assess the saved actual runs and authenticated answers.'})
    document = runs['corrected']['plan']['input_snapshot']['documents'][0]
    for offset in range(0, max(1, len(document['text'])), 6000):
        add('source_reference', f'assigned-source:{document["document_id"]}:{offset}', {
            'provenance': 'original_captured_assigned_source_not_a_learner_check',
            **{key: value for key, value in document.items() if key not in ('text', 'text_markers')},
            'text_offset': offset, 'text_length': len(document['text']), 'text': document['text'][offset:offset + 6000]})
    for name, run in runs.items():
        plan, result = run['plan'], run['result']
        snapshot = plan['input_snapshot']
        binding = {'comparison_role': name, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                   'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': plan['input_snapshot_sha256']}
        add('artifact_revision', name + '-configuration:' + run['run_id'], {
            **binding, 'artifact_id': snapshot['artifact_id'], 'artifact_sha256': snapshot['artifact_sha256'],
            'configuration': snapshot['artifact'], 'effective_stage_plans': plan['stage_plans']})
        scope = run['authorization']['decision']
        add('learner_decision', name + '-scope:' + scope['uuid'], {**binding, 'decision': scope})
        add('execution_receipt', name + '-execution:' + run['run_id'], {
            **binding, 'authorization_sha256': encode(run['authorization'])[1], 'result_sha256': encode(result)[1],
            'result': {key: value for key, value in result.items() if key != 'final_output'}})
        for index, event in enumerate(run['stage_events']):
            add('intermediate_snapshot', f'{name}-stage:{run["run_id"]}:{index}', {**binding, **event})
        add('output_snapshot', name + '-output:' + run['run_id'], {
            **binding, 'result_sha256': encode(result)[1], 'final_output': result['final_output']})
    for question in case.questions:
        if question.phase != 'after_execution':
            continue
        add('learner_decision', 'connected-answer:' + question.id, {
            'submission_id': submission_id, 'actor_user_id': actor_user_id,
            'submission_channel': saved['submission_channel'], 'submitted_at': saved['submitted_at'],
            'question': question.model_dump(mode='json'), 'answer': saved['submission']['answers'][question.id],
            'comparison': {key: value for key, value in saved['comparison'].items() if not key.endswith('_final_output')}})
    try:
        outcomes, checked, digest = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('Connected evidence cannot fit the review packet; nothing was truncated') from exc
    present = {item.kind for item in checked}
    if any(set(outcome.evidence) - present for outcome in outcomes):
        raise EvidenceAssemblyUnavailable('The saved connected review lacks required evidence; no grade was recorded')
    deterministic = check_connected_execution(contract, case, runs['corrected'])
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True, 'evidence_sha256': digest,
            'evidence': [item.model_dump(mode='json') for item in checked],
            'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
            'provenance': {'record_kind': 'saved_connected_result_review', 'connected_review_submission_id': submission_id,
                           'connected_review_submission_sha256': encode(saved)[1], 'case_sha256': case.digest,
                           'original_run_id': runs['original']['run_id'], 'corrected_run_id': runs['corrected']['run_id'],
                           'original_result_sha256': encode(runs['original']['result'])[1],
                           'corrected_result_sha256': encode(runs['corrected']['result'])[1],
                           'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'deterministic_outcomes': [deterministic]}}
