"""Assemble draft Foundations evidence from owned saved records, never chat prose.

Internal only. Coverage is not a grade. In particular, an approved execution plan
does not establish the original intentional mismatch or the learner's correction.
"""
import hashlib
from pathlib import Path

from pydantic import ValidationError

from .attempts import encode
from .automatic_review import ReviewEvidence, review_packet
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import DecisionSubmission, LearnerDecisionRepository, execution_requirement, load_prompt
from .outcomes import package_outcomes
from .scope_proposal import capture_proposal, selection_matches_run
from .practical_checks import check_foundations_execution


class EvidenceAssemblyUnavailable(EnrollmentConflict):
    """A technical collection limit or unavailable record, never a failed grade."""


class PracticalEvidenceRepository:
    async def assemble_foundations(self, operation, run_id, *, actor_user_id):
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Evidence assembly requires the authenticated learner')
        run = await LabExecutionRepository().get(actor_user_id, run_id)
        if run is None or run['plan']['module_id'] != 'foundations':
            raise EnrollmentConflict('Select an owned Foundations run')
        lease = LabExecutionRepository.check_operation(operation, run['plan'])
        if run['state'] != 'completed':
            raise EvidenceAssemblyUnavailable('Finish the assigned run before collecting assessment evidence')
        snapshot = await LabInputRepository().get(actor_user_id, run['plan']['input_snapshot_id'])
        if snapshot is None:
            raise EvidenceAssemblyUnavailable('The original assigned inputs are unavailable')
        LabExecutionRepository.check_operation(operation, snapshot)
        package = operation.package
        contract = package_outcomes(package)
        if contract is None:
            raise EnrollmentConflict('Evidence assembly requires the pinned outcome contract')
        if (snapshot['module_id'] != 'foundations' or encode(snapshot)[1] != run['plan']['input_snapshot_sha256']
                or encode(snapshot['artifact'])[1] != snapshot['artifact_sha256']
                or snapshot['exercise_sha256'] != package.manifest.artifacts['exercises.json']
                or snapshot['rubric_id'] != contract.rubric_id):
            raise CourseCatalogError('The assigned inputs do not match the saved run and requirements')
        documents = snapshot['documents']
        expected = package.json('exercises.json')['foundations']['documents']
        if ([item['assigned_filename'] for item in documents] != expected
                or len({item['document_id'] for item in documents}) != len(documents)
                or run['result']['documents_executed'] != [item['document_id'] for item in documents]
                or any(item['source_sha256'] != package.manifest.artifacts['documents/' + item['assigned_filename']]
                       or item['text_sha256'] != hashlib.sha256(item['text'].encode()).hexdigest() for item in documents)):
            raise CourseCatalogError('The completed run does not bind the exact assigned sources')
        requirement = execution_requirement(package, 'foundations')
        authorization = run['authorization']
        if (requirement is None or requirement != run['plan']['approval_requirement'] or authorization is None):
            raise EvidenceAssemblyUnavailable('This run has no preserved required scope authorization')
        scope = authorization['decision']
        self._check_decision(operation, run, scope, requirement['prompt_id'], 'prepared')
        if scope['submission']['choice'] != requirement['choice']:
            raise CourseCatalogError('The preserved scope decision did not authorize execution')
        proposal = run['plan'].get('scope_proposal')
        if proposal != capture_proposal(package, snapshot):
            raise CourseCatalogError('The saved proposal does not match the assigned course and run')
        if proposal is not None and not selection_matches_run(proposal,
                DecisionSubmission.model_validate(scope['submission']).proposal_selection, snapshot):
            raise CourseCatalogError('The learner did not select the assigned source before execution')

        # Choose the latest saved value review under the enrollment write boundary.
        # A caller cannot select an older, more favorable answer for this run.
        decisions = LearnerDecisionRepository()
        latest = await decisions.records.find_one({'user_id': actor_user_id, 'enrollment_id': snapshot['enrollment_id'],
            'module_id': 'foundations', 'run_id': run_id, 'prompt_id': 'value_review'}, sort=[('_id', -1)])
        values = decisions.decode(latest) if latest else None
        if values is not None:
            self._check_decision(operation, run, values, 'value_review', 'completed')
            checks = values['submission']['value_checks']
            prompt = load_prompt(package, 'foundations', 'value_review')
            by_id = {item['document_id']: item for item in documents}
            if (len(checks) != len(prompt.required_fields)
                    or {item['field'] for item in checks} != set(prompt.required_fields)
                    or any(item['source_document_id'] not in by_id
                           or item['source_quote'] not in by_id[item['source_document_id']]['text'] for item in checks)):
                raise CourseCatalogError('The saved value checks do not match the assigned source')

        evidence = []

        def add(kind, identity, payload):
            try:
                evidence.append(ReviewEvidence(id=identity, kind=kind, text=encode(payload)[0]).model_dump(mode='json'))
            except ValidationError as exc:
                raise EvidenceAssemblyUnavailable('Saved evidence exceeds the review item limit; no evidence was truncated') from exc

        add('artifact_revision', 'artifact:' + snapshot['uuid'], {
            'input_snapshot_id': snapshot['uuid'], 'artifact_sha256': snapshot['artifact_sha256'],
            'lab_folder_id': snapshot.get('lab_folder_id'), 'artifact': snapshot['artifact']})
        for index, document in enumerate(documents):
            # Preserve all source text, with identity and position on every chunk.
            # JSON escaping can expand characters; the item limit is still checked.
            source_text = document['text']
            for offset in range(0, max(1, len(source_text)), 6000):
                add('assigned_document_snapshot', f'source:{snapshot["uuid"]}:{index}:{offset}', {
                    **{key: value for key, value in document.items() if key not in ('text', 'text_markers')},
                    'input_snapshot_id': snapshot['uuid'], 'text_offset': offset, 'text_length': len(source_text),
                    'text': source_text[offset:offset + 6000]})
        add('learner_decision', 'scope:' + scope['uuid'], scope)
        if proposal is not None:
            add('proposal_snapshot', 'proposal:' + run_id, {
                **proposal, 'proposal_sha256': encode(proposal)[1], 'prepared_at': run['plan']['prepared_at'],
                'authorized_selection': scope['submission']['proposal_selection'], 'decision_id': scope['uuid']})
        add('execution_receipt', 'execution:' + run_id, {
            'run_id': run_id, 'plan_sha256': run['plan_sha256'],
            'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': run['plan']['input_snapshot_sha256'],
            'authorization_sha256': run['result']['authorization_sha256'],
            **{key: value for key, value in run['result'].items() if key != 'entities'}})
        add('output_snapshot', 'output:' + run_id, {
            'run_id': run_id, 'result_sha256': encode(run['result'])[1], 'entities': run['result']['entities']})
        if values is not None:
            add('learner_decision', 'values:' + values['uuid'], values)
            add('source_reference', 'checks:' + values['uuid'], {
                'run_id': run_id, 'decision_id': values['uuid'], 'value_checks': values['submission']['value_checks']})
        try:
            outcomes, checked, digest = review_packet(contract, 'foundations', evidence)
        except ValueError as exc:
            raise EvidenceAssemblyUnavailable('Saved evidence exceeds review limits or does not match the rubric; nothing was truncated') from exc
        present = {item.kind for item in checked}
        missing = {outcome.id: sorted(set(outcome.evidence) - present) for outcome in outcomes if set(outcome.evidence) - present}
        deterministic = check_foundations_execution(contract, run, snapshot)
        await LabInputRepository._check_lease(lease)
        return {'module_id': 'foundations', 'run_id': run_id, 'evidence': evidence, 'evidence_sha256': digest,
                'missing_evidence': missing, 'collection_complete': not missing,
                'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
                'provenance': {'assembler_id': 'saved-foundations-evidence.1',
                    'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': encode(snapshot)[1],
                    'run_id': run_id, 'plan_sha256': run['plan_sha256'], 'result_sha256': encode(run['result'])[1],
                    'scope_decision_id': scope['uuid'], 'scope_decision_sha256': encode(scope)[1],
                    'proposal_sha256': encode(proposal)[1] if proposal is not None else None,
                    'deterministic_outcomes': [deterministic],
                    'value_decision_id': values['uuid'] if values else None,
                    'value_decision_sha256': encode(values)[1] if values else None}}

    @staticmethod
    def _check_decision(operation, run, decision, prompt_id, state):
        LabExecutionRepository.check_operation(operation, decision)
        prompt = load_prompt(operation.package, 'foundations', prompt_id)
        try:
            submission = DecisionSubmission.model_validate(decision['submission'])
            if (decision['module_id'] != 'foundations' or decision['run_id'] != run['run_id']
                    or decision['prompt_id'] != prompt_id or decision['prompt'] != prompt.model_dump(mode='json')
                    or decision['prompt_sha256'] != prompt.digest or submission.prompt_sha256 != prompt.digest
                    or submission.run_id != run['run_id'] or submission.request_id != decision['uuid']
                    or submission.choice not in prompt.choices or decision['plan_sha256'] != run['plan_sha256']
                    or decision['input_snapshot_id'] != run['plan']['input_snapshot_id']
                    or decision['input_snapshot_sha256'] != run['plan']['input_snapshot_sha256']
                    or decision['run_state_at_submission'] != state
                    or decision['execution_result_sha256'] != (encode(run['result'])[1] if state == 'completed' else None)
                    or decision['submission_channel'] != 'authenticated_learner_request'):
                raise ValueError('Decision provenance mismatch')
        except (ValueError, KeyError, TypeError) as exc:
            raise CourseCatalogError('The saved learner decision does not bind this evidence') from exc
