"""Assemble the original suite, failure, repaired revision and learner rationale."""
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
from .practical_evidence import EvidenceAssemblyUnavailable
from .validation_case import load_validation_case
from .validation_preparation import ValidationPreparation
from .validation_reviews import ValidationReviewRepository


async def assemble_validation_review(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Validation assessment requires the authenticated learner')
    saved = await ValidationReviewRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Save the actual repair interpretation before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    package = operation.package
    case, contract = load_validation_case(package), package_outcomes(package)
    corrected = ValidationPreparation.decode(saved['execution'])
    original = ValidationPreparation.decode(corrected['plan']['original_run_record'])
    suite = corrected['plan']['suite']
    snapshot = corrected['plan']['input_snapshot']
    if (saved['case'] != case.public_definition() or snapshot['case'] != case.public_definition()
            or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json']
            or snapshot['rubric_id'] != contract.rubric_id):
        raise CourseCatalogError('Validation evidence differs from the original assignment and rubric')
    if not original['result']['checks']['complete'] or not corrected['result']['checks']['complete']:
        raise EvidenceAssemblyUnavailable('Incomplete or uncomparable case outputs are unavailable evidence; inspect them before assessment')
    evidence = []

    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Validation evidence exceeds review limits; no content was truncated') from exc

    def chunks(kind, identity, text, metadata):
        for offset in range(0, max(1, len(text)), 6000):
            add(kind, f'{identity}:{offset}', {**metadata, 'text_offset': offset, 'text_length': len(text), 'text': text[offset:offset + 6000]})

    binding = {'case_sha256': case.digest, 'suite_id': suite['uuid'], 'suite_sha256': suite['suite_sha256'],
        'original_run_id': original['run_id'], 'corrected_run_id': corrected['run_id']}
    for document in snapshot['documents']:
        for page, text in enumerate(document['pages'], 1):
            chunks('source_reference', f'validation-source:{document["source_id"]}:{page}', text,
                {**binding, 'source_id': document['source_id'], 'document_id': document['document_id'], 'page': page,
                 'source_sha256': document['source_sha256'], 'role': 'complete_original_pdf_page_used_by_both_runs'})
    add('test_case_snapshot', 'validation-suite:' + suite['uuid'], {**binding,
        'provenance': 'authenticated_learner_expectations_preserved_before_original_execution',
        'test_cases': suite['test_cases'], 'source_correctness_verified_at_submission': False,
        'notice': 'A matching source quote is traceability, not proof that an expected value is correct.'})
    for label, run in (('original', original), ('corrected', corrected)):
        plan, result = run['plan'], run['result']
        add('artifact_revision', f'validation-artifact:{label}', {**binding, 'role': label, 'run_id': run['run_id'],
            'artifact': plan['input_snapshot']['artifact'], 'artifact_sha256': plan['input_snapshot']['artifact_sha256'],
            'plan_sha256': run['plan_sha256'], 'effective_extraction_config': plan['effective_extraction_config'],
            'model_names': plan['model_names'], 'implementation_sha256': plan['implementation_sha256']})
        add('validation_receipt', f'validation-run:{label}', {**binding, 'role': label, 'run_id': run['run_id'],
            'plan_sha256': run['plan_sha256'], 'result_sha256': encode(result)[1], 'state': run['state'],
            'case_event_sha256s': [event['receipt_sha256'] for event in run['case_events']],
            'checks': result['checks'], 'repair_checks': result['repair_checks'],
            'notice': 'Actual source comparisons, not historical badge, node count or consistency score. Semantic checks cannot assess the learner’s explanation.'})
        for index, actual in enumerate(result['case_results']):
            chunks('validation_receipt', f'validation-result:{label}:{index}', encode(actual)[0],
                   {**binding, 'role': 'actual_engine_case_output', 'run_id': run['run_id'], 'case_result_sha256': encode(actual)[1]})
        add('learner_decision', f'validation-scope:{label}', {**binding, 'role': label,
            'authorization': run['authorization'], 'notice': 'Approval authorizes this exact internal suite, not a passing grade.'})
    add('learner_decision', 'validation-suite-design:' + suite['uuid'], {**binding, 'actor_user_id': actor_user_id,
        'submission_channel': suite['submission_channel'], 'submitted_at': suite['submitted_at'],
        'question': next(q.model_dump(mode='json') for q in case.questions if q.id == 'suite_design'),
        'answer': suite['submission']['suite_design']})
    add('learner_decision', 'validation-repair-answer:' + saved['uuid'], {**binding, 'actor_user_id': actor_user_id,
        'submission_channel': saved['submission_channel'], 'submitted_at': saved['submitted_at'],
        'question': next(q.model_dump(mode='json') for q in case.questions if q.id == 'repair_review'),
        'answer': saved['submission']['answers']['repair_review']})
    check_id = 'validation-source-and-retest-checks'
    expected_supported = all(c['all_expected_values_source_supported'] for c in original['result']['checks']['cases'])
    mechanical = {'expectations_source_supported': expected_supported,
                  'repair_requirements_supported': corrected['result']['repair_checks']['repair_requirements_supported']}
    add('validation_receipt', check_id, {**binding, **mechanical,
        'notice': 'These checks may veto a favorable model verdict but cannot upgrade unclear learner explanations or award credit.'})
    try:
        outcomes, checked, digest = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('Complete validation evidence does not fit the review packet; nothing was truncated') from exc
    if any(set(outcome.evidence) - {item.kind for item in checked} for outcome in outcomes):
        raise EvidenceAssemblyUnavailable('Required validation evidence is missing')
    supporting = []
    for outcome, key, explanation, instruction in (
        ('validation_qa.representative_tests', 'expectations_source_supported',
         'At least one saved expected value or explicit-absence interpretation disagrees with its original source.',
         'Recheck the affected expected value and source meaning, then save and execute a new complete source-checked suite.'),
        ('validation_qa.repair_and_retest', 'repair_requirements_supported',
         'The preserved failure and complete retest do not establish a source-supported repair.',
         'Inspect every saved comparison, repair unresolved field behavior and rerun the entire unchanged suite on the corrected revision.'),
    ):
        passed = mechanical[key]
        supporting.append({'outcome_id': outcome, 'check_id': 'source-checked-representative-suite.1', 'passed': passed,
            'evidence_id': check_id, 'quote': encode({key: passed})[0][1:-1],
            'explanation': 'Saved source checks support the mechanical requirement; learner reasoning still requires review.' if passed else explanation,
            'revision_instruction': '' if passed else instruction})
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True, 'evidence_sha256': digest,
        'evidence': [item.model_dump(mode='json') for item in checked], 'credit_awarded': False,
        'module_completion_eligible': False, 'staff_review_required': False,
        'provenance': {'record_kind': 'saved_validation_result_review', 'validation_review_submission_id': submission_id,
            'validation_review_submission_sha256': encode(saved)[1], 'run_id': corrected['run_id'],
            'result_sha256': encode(corrected['result'])[1], 'case_sha256': case.digest, 'supporting_checks': supporting,
            'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
