"""Collect owned budget execution, arithmetic and authenticated explanations."""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .advanced_case import load_advanced_case
from .advanced_workflow_preparation import AdvancedWorkflowPreparation
from .advanced_workflow_reviews import AdvancedReviewRepository
from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import package_outcomes
from .practical_evidence import EvidenceAssemblyUnavailable


async def assemble_budget_review(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Budget assessment requires the authenticated learner')
    saved = await AdvancedReviewRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Save the calculation and dependency explanations before assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    package = operation.package
    case, contract = load_advanced_case(package), package_outcomes(package)
    run = AdvancedWorkflowPreparation.decode(saved['execution'])
    LabExecutionRepository.check_operation(operation, run['plan'])
    plan, result = run['plan'], run['result']
    snapshot = plan['input_snapshot']
    calculation = snapshot['calculation_snapshot']
    if (saved['case'] != case.public_definition() or snapshot['case'] != case.public_definition()
            or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json']
            or snapshot['rubric_id'] != contract.rubric_id):
        raise CourseCatalogError('The budget evidence does not bind the original assignment and rubric')
    evidence = []

    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Budget evidence exceeds review limits; nothing was truncated') from exc

    binding = {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'input_snapshot_id': snapshot['uuid'],
               'input_snapshot_sha256': plan['input_snapshot_sha256'], 'case_sha256': case.digest}
    document = calculation['document']
    for offset in range(0, max(1, len(document['text'])), 6000):
        add('assigned_document_snapshot', f'budget-source:{document["document_id"]}:{offset}', {
            **binding, 'provenance': 'original_captured_assigned_source_not_learner_interpretation',
            **{key: value for key, value in document.items() if key not in ('text', 'text_markers')},
            'text_offset': offset, 'text_length': len(document['text']), 'text': document['text'][offset:offset + 6000]})
    add('design_snapshot', 'budget-design:' + snapshot['uuid'], {
        **binding, 'configuration': snapshot['artifact'], 'effective_stages': plan['stage_plans'],
        'assignment': case.public_definition(), 'scope': plan['scope']})
    add('artifact_revision', 'budget-revision:' + snapshot['uuid'], {
        **binding, 'artifact_id': snapshot['artifact_id'], 'artifact_sha256': snapshot['artifact_sha256'],
        'configuration': snapshot['artifact'], 'captured_at': snapshot['captured_at']})
    calculation_id = 'budget-calculations:' + calculation['uuid']
    add('calculation_record', calculation_id, {
        **binding, 'calculation_snapshot_id': calculation['uuid'], 'calculation_snapshot_sha256': encode(calculation)[1],
        'provenance': 'authenticated_learner_inputs_with_server_checked_source_addition',
        'records': calculation['request']['records'], 'checks': calculation['checks'],
        'notice': 'Source-row addition does not establish policy, period compatibility or the learner interpretation.'})
    method_question = next(q for q in case.questions if q.id == 'method_choice')
    add('learner_decision', 'budget-method:' + snapshot['uuid'], {
        **binding, 'actor_user_id': actor_user_id, 'provenance': snapshot['method_choice_provenance'],
        'question': method_question.model_dump(mode='json'), 'answer': snapshot['request']['method_choice'],
        'captured_at': snapshot['captured_at']})
    add('learner_decision', 'budget-scope:' + run['authorization']['decision']['uuid'], {
        **binding, 'decision': run['authorization']['decision']})
    add('execution_receipt', 'budget-execution:' + run['run_id'], {
        **binding, 'authorization_sha256': encode(run['authorization'])[1], 'result_sha256': encode(result)[1],
        'result': {key: value for key, value in result.items() if key != 'final_output'}})
    for index, event in enumerate(run['task_events']):
        add('intermediate_snapshot', f'budget-task:{run["run_id"]}:{index}', {**binding, **event})
    add('intermediate_snapshot', 'budget-memo:' + run['run_id'], {
        **binding, 'role': 'actual_final_internal_memo', 'final_output': result['final_output']})
    for question in case.questions:
        if question.phase == 'after_execution':
            add('learner_decision', 'budget-answer:' + question.id, {
                **binding, 'submission_id': saved['uuid'], 'actor_user_id': actor_user_id,
                'submission_channel': saved['submission_channel'], 'submitted_at': saved['submitted_at'],
                'question': question.model_dump(mode='json'), 'answer': saved['submission']['answers'][question.id]})
    try:
        outcomes, checked, digest = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('Complete budget evidence does not fit the review packet; nothing was truncated') from exc
    if any(set(outcome.evidence) - {item.kind for item in checked} for outcome in outcomes):
        raise EvidenceAssemblyUnavailable('Required budget evidence is missing; no assessment was saved')
    passed = calculation['checks']['all_arithmetic_supported']
    check = {'outcome_id': 'advanced_nodes.checked_computation', 'check_id': 'budget-source-addition.1', 'passed': passed,
             'evidence_id': calculation_id,
             'quote': encode({'all_arithmetic_supported': passed})[0][1:-1],
             'explanation': ('Exact named source inputs and their stored additions agree. Interpretation still requires review.' if passed else
                             'At least one source input or recorded addition is incorrect or unresolved; model interpretation cannot override that check.'),
             'revision_instruction': '' if passed else 'Inspect the saved input checks and sums, correct or resolve the affected records, then run and review the updated evidence.'}
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True, 'evidence_sha256': digest,
            'evidence': [item.model_dump(mode='json') for item in checked],
            'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
            'provenance': {'record_kind': 'saved_budget_result_review', 'budget_review_submission_id': submission_id,
                'budget_review_submission_sha256': encode(saved)[1], 'run_id': run['run_id'],
                'result_sha256': encode(result)[1], 'case_sha256': case.digest, 'supporting_checks': [check],
                'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
