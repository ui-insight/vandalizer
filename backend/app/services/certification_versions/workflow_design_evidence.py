"""Collect approved configuration evidence; do not imply a tested execution."""
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
from .workflow_design_case import load_workflow_design_case
from .workflow_design_submissions import WorkflowDesignSubmissionRepository


def require_resolved_configuration(artifact):
    """This staged collector supports inline design and captured extractions.

    Unsupported resource dependencies are a technical gap, never a learner
    failure or an invitation to inspect current workspace records instead.
    Incorrect supported configuration remains visible for rubric assessment.
    """
    workflow = artifact['workflow']
    if (workflow.get('attachments') or workflow.get('resource_config') or workflow.get('output_config')
            or workflow.get('input_config', {}).get('fixed_documents')):
        raise EvidenceAssemblyUnavailable('This design references resources not captured for assessment; no grade was recorded')
    references = set()
    allowed = {
        'Document': {'doc_uuids'},
        'Prompt': {'prompt', 'model', 'input_sources', 'input_source', 'selected_document_uuid'},
        'Formatter': {'format_template', 'model', 'input_sources', 'input_source', 'selected_document_uuid'},
        'Extraction': {'extractions', 'search_set_uuid', 'model', 'input_sources', 'input_source', 'selected_document_uuid'},
    }
    for item in artifact['steps']:
        settings = [item['step']['data']]
        for task in item['tasks']:
            data = task['data']
            if task['name'] not in allowed or set(data) - allowed[task['name']]:
                raise EvidenceAssemblyUnavailable('This task configuration is not supported by the saved-design collector yet')
            settings.append(data)
            if task['name'] == 'Extraction' and data.get('search_set_uuid'):
                references.add(data['search_set_uuid'])
        for data in settings:
            if (data.get('selected_document_uuid') or data.get('doc_uuids')
                    or data.get('input_source') == 'selected_document'
                    or 'selected_document' in (data.get('input_sources') or [])):
                raise EvidenceAssemblyUnavailable('A selected source reference has not been captured for this design assessment')
    captured = artifact.get('referenced_extraction_sets', {})
    if set(captured) != references or any(value.get('uuid') != key for key, value in captured.items()):
        raise EvidenceAssemblyUnavailable('Referenced extraction definitions are missing or do not match the saved tasks')


async def assemble_workflow_design(operation, submission_id, *, actor_user_id):
    if actor_user_id != operation.user_id:
        raise EnrollmentConflict('Workflow Design assessment requires the authenticated learner')
    saved = await WorkflowDesignSubmissionRepository().get(actor_user_id, submission_id)
    if saved is None:
        raise EvidenceAssemblyUnavailable('Approve the exact saved workflow design before requesting assessment')
    lease = LabExecutionRepository.check_operation(operation, saved)
    case = load_workflow_design_case(operation.package)
    snapshot = saved['input_snapshot']
    if snapshot['case'] != case.public_definition() or saved['submission']['case_sha256'] != case.digest:
        raise CourseCatalogError('The saved approval does not match its original Workflow Design case')
    try:
        require_resolved_configuration(snapshot['artifact'])
    except (KeyError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('The saved configuration cannot be resolved for assessment') from exc
    evidence = []

    def add(kind, identity, value):
        try:
            evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(value)[0]).model_dump(mode='json'))
        except ValidationError as exc:
            raise EvidenceAssemblyUnavailable('Saved design evidence exceeds review limits; nothing was truncated') from exc

    add('proposal_snapshot', 'authored-design-proposal:' + case.id, {
        'provenance': case.provenance, 'case_sha256': case.digest, 'case': case.model_dump(mode='json'),
        'notice': 'The flawed proposal and supplied example are authored teaching material, not learner actions. '
                  'Assess the actual approved configuration and decisions. No runtime behavior or institutional approval is established.'})
    add('artifact_revision', 'saved-workflow-revision:' + snapshot['uuid'], {
        'provenance': 'owned_saved_configuration_not_execution', 'input_snapshot_id': snapshot['uuid'],
        'artifact_id': snapshot['artifact_id'], 'artifact_sha256': snapshot['artifact_sha256'],
        'captured_at': snapshot['captured_at'], 'configuration': snapshot['artifact'],
        'notice': 'These are saved settings and resolved owned extraction definitions. They are not source contents or an execution receipt.'})
    add('design_snapshot', 'approved-workflow-design:' + submission_id, {
        'provenance': saved['submission_channel'], 'submission_id': submission_id,
        'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': saved['submission']['input_snapshot_sha256'],
        'artifact_sha256': snapshot['artifact_sha256'], 'handoff': snapshot['handoff'],
        'submitted_at': saved['submitted_at'], 'consent': saved['submission']['consent'],
        'execution_authorized': False,
        'notice': 'The learner approved this captured revision for assessment only. A supplied map is not learner work or credit. '
                  'Review the linked artifact configuration; explanations alone cannot establish connections.'})
    for question in case.questions:
        add('learner_decision', 'workflow-design-decision:' + question.id, {
            'submission_id': submission_id, 'actor_user_id': actor_user_id,
            'input_snapshot_id': snapshot['uuid'], 'artifact_sha256': snapshot['artifact_sha256'],
            'submitted_at': saved['submitted_at'], 'submission_channel': saved['submission_channel'],
            'question': question.model_dump(mode='json'), 'answer': saved['submission']['answers'][question.id]})
    try:
        _, checked, _ = review_packet(package_outcomes(operation.package), case.module_id, evidence)
    except (ValueError, TypeError) as exc:
        raise EvidenceAssemblyUnavailable('The saved design cannot fit the review packet; nothing was truncated') from exc
    await LabInputRepository._check_lease(lease)
    return {'module_id': case.module_id, 'collection_complete': True,
            'evidence': [item.model_dump(mode='json') for item in checked],
            'provenance': {'record_kind': 'approved_workflow_design', 'workflow_design_submission_id': submission_id,
                           'workflow_design_submission_sha256': encode(saved)[1], 'case_sha256': case.digest,
                           'input_snapshot_id': snapshot['uuid'], 'artifact_sha256': snapshot['artifact_sha256'],
                           'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
