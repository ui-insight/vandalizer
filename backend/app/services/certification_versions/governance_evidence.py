"""Collect complete observed capstone work and authenticated learner explanations for automatic review."""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .governance_case import load_governance_case
from .governance_preparation import GovernancePreparation
from .governance_reviews import GovernanceReviewRepository
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import package_outcomes
from .practical_evidence import EvidenceAssemblyUnavailable


async def assemble_governance_review(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Governance assessment requires the authenticated learner')
    saved = await GovernanceReviewRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Save the actual capstone interpretation before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    package = operation.package
    case, contract = load_governance_case(package), package_outcomes(package)
    handoff = saved['handoff']
    release, memo = handoff['release'], handoff['release']['memo']
    repaired = GovernancePreparation.decode(memo['execution'])
    finding = repaired['plan']['source_finding']
    original = GovernancePreparation.decode(finding['execution'])
    correction = original['plan']['scope_correction']
    snapshot = original['plan']['input_snapshot']
    if (saved['case'] != case.public_definition() or snapshot['case'] != case.public_definition()
            or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json'] or snapshot['rubric_id'] != contract.rubric_id):
        raise CourseCatalogError('The preserved capstone evidence differs from its original assignment and rubric')
    if not original['result']['checks']['complete'] or not repaired['result']['checks']['complete']:
        raise EvidenceAssemblyUnavailable('Missing or uncomparable values are unavailable evidence, not learner failure')
    evidence = []

    def add(kind, identity, payload):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Complete capstone evidence exceeds review limits; nothing was truncated') from exc

    def chunks(kind, identity, text, metadata):
        for offset in range(0, max(1, len(text)), 6000):
            add(kind, f'{identity}:{offset}', {**metadata, 'text_offset': offset, 'text_length': len(text), 'text': text[offset:offset + 6000]})

    binding = {'case_sha256': case.digest, 'original_run_id': original['run_id'], 'repair_run_id': repaired['run_id']}
    add('capstone_attempt', 'governance-assignment', {**binding, 'task': case.task, 'notice': case.notice,
        'flawed_proposal': case.flawed_proposal, 'original_field_flaw': case.original_field_flaw,
        'review_submission_id': saved['uuid'], 'handoff_id': handoff['uuid'], 'memo_id': memo['uuid'],
        'notice_of_limits': 'Authored flaws and controlled rejections are disclosed training behavior, not observed model failures or real external outages. Authenticated explanations require review; their presence is not a passing grade.'})
    for source in snapshot['documents']:
        for page, text in enumerate(source['pages'], 1):
            chunks('source_reference', f'governance-source:{source["source_id"]}:{page}', text,
                {**binding, 'source_id': source['source_id'], 'document_id': source['document_id'],
                    'source_sha256': source['source_sha256'], 'page': page, 'role': 'complete_original_pdf_page'})
    for label, run in [('original', original), ('repair', repaired)]:
        plan, result = run['plan'], run['result']
        captured = plan['input_snapshot']
        chunks('artifact_revision', 'governance-artifact:' + label, encode(captured['artifact'])[0],
            {**binding, 'phase': label, 'artifact_sha256': captured['artifact_sha256'], 'captured_at': captured['captured_at']})
        chunks('execution_receipt', 'governance-actual-result:' + label, encode(result['extraction'])[0],
            {**binding, 'phase': label, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                'result_sha256': encode(result)[1], 'model_names': plan['model_names'],
                'effective_extraction_config': plan['effective_extraction_config'],
                'checkpoint_sha256s': [e['receipt_sha256'] for e in run['extraction_events']],
                'started_at': result['started_at'], 'finished_at': result['finished_at']})
        add('learner_decision', 'governance-execution-approval:' + label,
            {**binding, 'phase': label, 'authorization': run['authorization']})
        add('validation_receipt', 'governance-source-checks:' + label, {**binding, **result['checks']})
    for label, record in [('scope-correction', correction), ('source-finding', finding), ('release', release), ('final-supervision', saved)]:
        add('learner_decision', 'governance-decision:' + label, {**binding, 'record_id': record['uuid'],
            'record_sha256': encode(record)[1], 'actor_user_id': record['user_id'], 'submitted_at': record['submitted_at'],
            'submission_channel': record['submission_channel'], 'question': record['prompt'], 'submission': record['submission']})
    chunks('handoff_snapshot', 'governance-memo', encode(memo['file']['memo'])[0],
        {**binding, 'filename': memo['file']['filename'], 'file_sha256': memo['file']['sha256'], 'byte_length': memo['file']['byte_length'],
            'memo_id': memo['uuid'], 'role': 'exact_checked_json_memo_and_learner_authored_accountability'})
    for label, receipt in [('first-failure', handoff['previous_failed_receipt']), ('explicit-retry', handoff)]:
        add('delivery_receipt', 'governance-handoff:' + label, {**binding, 'receipt_id': receipt['uuid'], 'receipt_sha256': encode(receipt)[1],
            'submission': receipt['submission'], 'submitted_at': receipt['submitted_at'], 'status': receipt['status'], 'reason': receipt['reason'],
            'destination': receipt['destination'], 'destination_written': receipt['destination_written'],
            'destination_file_sha256': receipt['destination_copy']['sha256'] if receipt['destination_copy'] else None,
            'external_delivery': receipt['external_delivery'], 'authenticated_actor_user_id': receipt['user_id']})
    check_id = 'governance-observed-chain-checks'
    checked_chain = {'repair_requirements_supported': repaired['result']['repair_checks']['repair_requirements_supported'],
        'source_supported': repaired['result']['checks']['source_supported'],
        'same_checked_bytes_delivered': handoff['destination_copy'] == memo['file'], 'original_no_write_failure_preserved': handoff['previous_failed_receipt']['destination_written'] is False}
    add('validation_receipt', check_id, {**binding, **checked_chain,
        'notice': 'These observed checks cannot establish the quality of learner reasoning or generalize to real external delivery.'})
    passed = all(checked_chain.values())
    supporting = [{'outcome_id': outcome, 'check_id': 'exact-private-capstone-supervision.1', 'passed': passed, 'evidence_id': check_id,
        'quote': encode({'same_checked_bytes_delivered': checked_chain['same_checked_bytes_delivered']})[0][1:-1],
        'explanation': 'The exact observed source-correct repair and private same-bytes recovery chain is preserved; learner accountability and supervision reasoning still require review.' if passed else 'The observed repair or private-copy chain is incomplete or unsupported.',
        'revision_instruction': '' if passed else 'Inspect and correct the original source, revision and private handoff evidence before claiming successful supervision.'}
        for outcome in ('governance.accountable_handoff', 'governance.capstone_supervision')]
    try:
        outcomes, checked, digest = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('The complete capstone cannot fit the review packet; nothing was truncated') from exc
    if any(set(outcome.evidence) - {item.kind for item in checked} for outcome in outcomes):
        raise EvidenceAssemblyUnavailable('Required capstone evidence is missing')
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True, 'evidence_sha256': digest,
        'evidence': [item.model_dump(mode='json') for item in checked], 'credit_awarded': False,
        'module_completion_eligible': False, 'staff_review_required': False,
        'provenance': {'record_kind': 'saved_governance_result_review', 'governance_review_submission_id': submission_id,
            'governance_review_submission_sha256': encode(saved)[1], 'run_id': repaired['run_id'],
            'result_sha256': encode(repaired['result'])[1], 'case_sha256': case.digest,
            'supporting_checks': supporting, 'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
