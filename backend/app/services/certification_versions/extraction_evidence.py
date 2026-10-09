"""Collect an owned NIH repair, retaining authored and executed provenance."""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .extraction_checks import check_extraction_execution
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import DecisionSubmission, LearnerDecisionRepository, execution_requirement, load_prompt
from .outcomes import package_outcomes
from .practical_evidence import EvidenceAssemblyUnavailable
from .repair_case import capture_repair_case, load_repair_case, repair_reference_matches

MODULE = 'extraction_engine'


def verify_decision(operation, run, record, prompt_id, state):
    LabExecutionRepository.check_operation(operation, record)
    prompt = load_prompt(operation.package, MODULE, prompt_id)
    try:
        submission = DecisionSubmission.model_validate(record['submission'])
        if (record['module_id'] != MODULE or record['run_id'] != run['run_id']
                or record['prompt_id'] != prompt_id or record['prompt'] != prompt.model_dump(mode='json')
                or record['prompt_sha256'] != prompt.digest or submission.prompt_sha256 != prompt.digest
                or submission.run_id != run['run_id'] or submission.request_id != record['uuid']
                or submission.choice not in prompt.choices or record['plan_sha256'] != run['plan_sha256']
                or record['input_snapshot_id'] != run['plan']['input_snapshot_id']
                or record['input_snapshot_sha256'] != run['plan']['input_snapshot_sha256']
                or record['run_state_at_submission'] != state
                or record['execution_result_sha256'] != (encode(run['result'])[1] if state == 'completed' else None)
                or record['submission_channel'] != 'authenticated_learner_request'
                or not repair_reference_matches(run['plan']['repair_case'], submission.repair_case_sha256)):
            raise ValueError('Unbound repair decision')
    except (ValueError, KeyError, TypeError) as exc:
        raise CourseCatalogError('The saved repair decision does not bind this evidence') from exc


async def assemble_extraction(operation, run_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Repair assessment requires the authenticated learner')
    run = await LabExecutionRepository().get(actor_user_id, run_id)
    if run is None or run['plan']['module_id'] != MODULE:
        raise EnrollmentConflict('Select an owned Extraction Engine run')
    lease = LabExecutionRepository.check_operation(operation, run['plan'])
    if run['state'] != 'completed':
        raise EvidenceAssemblyUnavailable('Finish the assigned revised run before requesting assessment')
    snapshot = await LabInputRepository().get(actor_user_id, run['plan']['input_snapshot_id'])
    if snapshot is None:
        raise EvidenceAssemblyUnavailable('The original revised inputs are unavailable')
    LabExecutionRepository.check_operation(operation, snapshot)
    package = operation.package
    contract, case = package_outcomes(package), load_repair_case(package, MODULE)
    if contract is None or case is None:
        raise CourseCatalogError('Repair assessment requires the pinned outcome contract and authored case')
    if (snapshot['module_id'] != MODULE or encode(snapshot)[1] != run['plan']['input_snapshot_sha256']
            or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json']
            or snapshot['rubric_id'] != contract.rubric_id
            or run['plan'].get('repair_case') != capture_repair_case(package, snapshot)):
        raise CourseCatalogError('The repair example does not bind the saved assigned revision')
    document = snapshot['documents'][0]
    if (document['text_sha256'] != hashlib.sha256(document['text'].encode()).hexdigest()
            or run['result']['documents_executed'] != [document['document_id']]):
        raise CourseCatalogError('The revised run does not preserve the original assigned source')
    requirement = execution_requirement(package, MODULE)
    authorization = run.get('authorization')
    if requirement is None or requirement != run['plan']['approval_requirement'] or authorization is None:
        raise EvidenceAssemblyUnavailable('The revised run has no preserved required scope authorization')
    scope = authorization['decision']
    verify_decision(operation, run, scope, case.scope_prompt_id, 'prepared')
    if scope['submission']['choice'] != requirement['choice']:
        raise CourseCatalogError('The saved scope decision did not approve the revised run')
    decisions = LearnerDecisionRepository()
    raw = await decisions.records.find_one({'user_id': actor_user_id, 'enrollment_id': snapshot['enrollment_id'],
        'module_id': MODULE, 'run_id': run_id, 'prompt_id': case.value_prompt_id}, sort=[('_id', -1)])
    values = decisions.decode(raw) if raw else None
    if values is not None:
        verify_decision(operation, run, values, case.value_prompt_id, 'completed')
        checks = values['submission']['value_checks']
        if (len(checks) != len(case.expectations) or {item['field'] for item in checks} != {item.field for item in case.expectations}
                or any(item['source_document_id'] != document['document_id'] or item['source_quote'] not in document['text'] for item in checks)):
            raise CourseCatalogError('The saved repair source checks are incomplete or unbound')
    evidence = []

    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Repair evidence exceeds review limits; nothing was truncated') from exc

    add('repair_baseline', 'authored-case:' + case.id, {
        'provenance': 'authored_flawed_example_not_an_execution', 'case_sha256': case.digest,
        'case': case.model_dump(mode='json'), 'prepared_binding': run['plan']['repair_case'],
        'assessor_instruction': 'The baseline and expected source values are authored course material. They do not establish learner execution or a successful repair. Compare the actual revised fields, actual output and authenticated source checks.'})
    add('artifact_revision', 'revised-artifact:' + snapshot['uuid'], {
        'artifact': snapshot['artifact'], 'artifact_sha256': snapshot['artifact_sha256'], 'input_snapshot_id': snapshot['uuid']})
    text = document['text']
    for offset in range(0, max(1, len(text)), 6000):
        add('assigned_document_snapshot', f'source:{snapshot["uuid"]}:{offset}', {
            **{key: value for key, value in document.items() if key not in ('text', 'text_markers')},
            'input_snapshot_id': snapshot['uuid'], 'text_offset': offset, 'text_length': len(text), 'text': text[offset:offset + 6000]})
    add('learner_decision', 'repair-scope:' + scope['uuid'], scope)
    add('execution_receipt', 'revised-execution:' + run_id, {
        'run_id': run_id, 'plan_sha256': run['plan_sha256'], 'input_snapshot_sha256': encode(snapshot)[1],
        'effective_extraction_config': run['plan']['effective_extraction_config'],
        **{key: value for key, value in run['result'].items() if key != 'entities'}})
    add('output_snapshot', 'revised-output:' + run_id, {
        'run_id': run_id, 'result_sha256': encode(run['result'])[1], 'entities': run['result']['entities']})
    if values is not None:
        add('learner_decision', 'repair-values:' + values['uuid'], values)
        add('source_reference', 'repair-checks:' + values['uuid'], {
            'run_id': run_id, 'decision_id': values['uuid'], 'value_checks': values['submission']['value_checks']})
    try:
        outcomes, checked, digest = review_packet(contract, MODULE, evidence)
    except ValueError as exc:
        raise EvidenceAssemblyUnavailable('Repair evidence exceeds review limits or differs from the rubric; nothing was truncated') from exc
    present = {item.kind for item in checked}
    missing = {outcome.id: sorted(set(outcome.evidence) - present) for outcome in outcomes if set(outcome.evidence) - present}
    deterministic = check_extraction_execution(contract, run, snapshot)
    await LabInputRepository._check_lease(lease)
    return {'module_id': MODULE, 'run_id': run_id, 'evidence': evidence, 'evidence_sha256': digest,
            'missing_evidence': missing, 'collection_complete': not missing,
            'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
            'provenance': {'assembler_id': 'saved-nih-repair-evidence.1',
                'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': encode(snapshot)[1],
                'run_id': run_id, 'plan_sha256': run['plan_sha256'], 'result_sha256': encode(run['result'])[1],
                'case_sha256': case.digest, 'repair_case_sha256': encode(run['plan']['repair_case'])[1],
                'scope_decision_id': scope['uuid'], 'scope_decision_sha256': encode(scope)[1],
                'value_decision_id': values['uuid'] if values else None,
                'value_decision_sha256': encode(values)[1] if values else None,
                'deterministic_outcomes': [deterministic]}}
