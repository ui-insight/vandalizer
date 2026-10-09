"""Collect owned process-design evidence; never manufacture executed work."""
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
from .process_case import load_process_case
from .process_submissions import ProcessSubmissionRepository


async def assemble_process(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Process assessment requires the authenticated learner')
    saved = await ProcessSubmissionRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Select your saved process design before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    case = load_process_case(operation.package)
    contract = package_outcomes(operation.package)
    if (saved['module_id'] != case.module_id or saved['case'] != case.public_definition()
            or saved['submission']['case_sha256'] != case.digest):
        raise CourseCatalogError('The saved process design does not match its original assigned case')
    evidence = []

    def add(kind, identity, value):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(value)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Process evidence exceeds review limits; nothing was truncated') from exc

    add('scenario_revision', 'authored-process:' + case.id, {
        'provenance': 'authored_fictional_design_case_not_execution', 'case_sha256': case.digest,
        'case': case.model_dump(mode='json'),
        'assessor_instruction': 'This is the assigned fictional design problem and private rubric guidance. It is not learner work, a completed run or proof that the learner corrected the proposal. Assess the saved learner map and explicit decisions. A process design needs no execution receipt.'})
    answers = saved['submission']['answers']
    add('process_map_snapshot', 'saved-process-map:' + submission_id, {
        'provenance': 'authenticated_learner_process_request', 'submission_id': submission_id,
        'case_sha256': case.digest, 'previous_submission_id': saved['submission']['previous_submission_id'],
        'map': answers['human_checkpoint'], 'task_brief': answers['bounded_scope'],
        'notice': 'This is the exact saved design, not an executed workflow or a quality verdict.'})
    for question in case.questions:
        add('learner_decision', 'process-decision:' + question.id, {
            'submission_id': submission_id, 'actor_user_id': actor_user_id,
            'submitted_at': saved['submitted_at'], 'submission_channel': saved['submission_channel'],
            'question': question.model_dump(mode='json'), 'answer': answers[question.id],
            'case_sha256': case.digest, 'consent': saved['submission']['consent']})
    try:
        _, checked, _ = review_packet(contract, case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('The original process evidence cannot fit the review packet; nothing was truncated') from exc
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True,
            'evidence': [item.model_dump(mode='json') for item in checked],
            'provenance': {'record_kind': 'saved_process_design', 'process_submission_id': submission_id,
                           'process_submission_sha256': encode(saved)[1], 'case_sha256': case.digest,
                           'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
