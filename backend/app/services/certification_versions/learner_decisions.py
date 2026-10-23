"""Save explicit learner decisions against a pinned practical run.

The authenticated HTTP caller supplies the actor; chat tools must not submit on
behalf of a learner. Saving a decision is evidence capture, never a grade.
"""
import datetime
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationLearnerDecision, CertificationLabExecution
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import package_outcomes
from .scope_proposal import ProposalSelection, capture_proposal, selection_matches_run
from .repair_case import capture_repair_case, repair_reference_matches


class DecisionValidationError(EnrollmentConflict):
    """Definite rejection before any receipt was written; answers may be edited."""


class DecisionPrompt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1, strict=True)
    module_id: str
    outcome_id: str
    phase: Literal['before_execution', 'after_execution']
    question: str = Field(min_length=20, max_length=3000)
    choices: dict[str, str] = Field(min_length=2, max_length=6)
    required_fields: tuple[str, ...] = ()
    execution_choice: str | None = None

    @model_validator(mode='after')
    def valid_fields(self):
        if (len(set(self.required_fields)) != len(self.required_fields)
                or any(not field.strip() for field in self.required_fields)
                or any(not key.strip() or not value.strip() for key, value in self.choices.items())
                or (self.phase == 'before_execution' and self.required_fields)):
            raise ValueError('Invalid decision prompt fields or choices')
        if self.execution_choice is not None and (self.phase != 'before_execution' or self.execution_choice not in self.choices):
            raise ValueError('Execution approval must name a before-execution choice')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]


class ValueCheck(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    field: str = Field(min_length=1, max_length=200)
    decision: Literal['supported', 'unsupported', 'unresolved']
    checked_value: str = Field(max_length=4000)
    source_document_id: str = Field(min_length=1, max_length=200)
    source_quote: str = Field(max_length=4000)
    reason: str = Field(min_length=10, max_length=4000)

    @model_validator(mode='after')
    def actual_content(self):
        if len(self.reason.strip()) < 10 or (self.decision == 'supported' and not self.source_quote.strip()):
            raise ValueError('Explain the source check; supported values require a source quote')
        return self


class DecisionSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    prompt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    choice: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=10, max_length=4000)
    value_checks: tuple[ValueCheck, ...] = Field(default=(), max_length=100)
    proposal_selection: ProposalSelection | None = None
    repair_case_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def actual_reason(self):
        if len(self.reason.strip()) < 10:
            raise ValueError('Explain the decision')
        return self


def load_prompt(package, module_id, prompt_id):
    path = f'decisions/{module_id}.json'
    if path not in package.manifest.artifacts:
        raise EnrollmentConflict('This course has no practical decision prompts for this module')
    try:
        prompts = [DecisionPrompt.model_validate(item) for item in package.json(path)]
        contract = package_outcomes(package)
        outcomes = {item.id for module in contract.modules if module.module_id == module_id for item in module.outcomes} if contract else set()
        if (not prompts or len({item.id for item in prompts}) != len(prompts)
                or any(item.module_id != module_id or item.outcome_id not in outcomes for item in prompts)):
            raise ValueError('Decision prompts do not match the packaged outcomes')
    except (TypeError, ValueError) as exc:
        raise CourseCatalogError('The practical decision prompts are invalid') from exc
    prompt = next((item for item in prompts if item.id == prompt_id), None)
    if prompt is None:
        raise EnrollmentConflict('This decision prompt is not part of the selected course')
    return prompt


def execution_requirement(package, module_id):
    path = f'decisions/{module_id}.json'
    if path not in package.manifest.artifacts:
        return None
    prompts = [load_prompt(package, module_id, item['id']) for item in package.json(path)]
    approvals = [prompt for prompt in prompts if prompt.execution_choice is not None]
    if len(approvals) > 1:
        raise CourseCatalogError('A practical run must have one unambiguous scope approval prompt')
    if not approvals:
        return None
    prompt = approvals[0]
    return {'prompt_id': prompt.id, 'prompt_sha256': prompt.digest, 'choice': prompt.execution_choice}


class LearnerDecisionRepository:
    @property
    def records(self):
        return CertificationLearnerDecision.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Digest mismatch')
            record = json.loads(raw['record_json'])
            if any(record[key] != raw[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id',
                    'course_version', 'manifest_sha256', 'request_sha256', 'run_id', 'prompt_id')):
                raise ValueError('Decision identity mismatch')
            return record
        except (TypeError, ValueError, KeyError) as exc:
            raise CourseCatalogError('The saved learner decision failed integrity verification') from exc

    async def get(self, user_id, decision_id):
        raw = await self.records.find_one({'uuid': decision_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    @staticmethod
    def read_identity(operation, module_id):
        if module_id not in {item.id for item in operation.package.manifest.modules}:
            raise EnrollmentConflict('This module is not part of the selected course')
        return {'user_id': operation.user_id, 'enrollment_id': operation.progress.enrollment_id,
                'course_version': operation.package.manifest.release_id,
                'manifest_sha256': operation.package.manifest_sha256, 'module_id': module_id}

    async def runs(self, operation, module_id):
        query = self.read_identity(operation, module_id)
        records = await CertificationLabExecution.get_motor_collection().find(query,
            {'uuid': 1, 'state': 1}).sort('_id', -1).limit(51).to_list(None)
        return {'runs': [{'run_id': item['uuid'], 'state': item['state']} for item in records[:50]],
                'older_runs_available': len(records) > 50}

    async def context(self, operation, module_id, prompt_id, run_id):
        identity = self.read_identity(operation, module_id)
        prompt = load_prompt(operation.package, module_id, prompt_id)
        run = await LabExecutionRepository().get(operation.user_id, run_id)
        if run is None or any(run['plan'].get(key) != value for key, value in identity.items()):
            raise EnrollmentConflict('This run is not part of the selected learner, module and course')
        snapshot = await LabInputRepository().get(operation.user_id, run['plan']['input_snapshot_id'])
        if snapshot is None or encode(snapshot)[1] != run['plan']['input_snapshot_sha256']:
            raise EnrollmentConflict('The original run inputs are unavailable or changed')
        latest_query = {**identity, 'run_id': run_id, 'prompt_id': prompt_id}
        if prompt.execution_choice is not None:
            latest_query['uuid'] = run.get('scope_decision_id')
        latest = await self.records.find_one(latest_query, sort=[('_id', -1)])
        expected_state = 'prepared' if prompt.phase == 'before_execution' else 'completed'
        return {'enrollment_id': identity['enrollment_id'], 'module_id': module_id,
                'prompt': {**prompt.model_dump(mode='json'), 'prompt_sha256': prompt.digest},
                'run_id': run_id, 'run_state': run['state'], 'can_submit': run['state'] == expected_state,
                'lab_folder_id': snapshot.get('lab_folder_id'), 'artifact': snapshot['artifact'],
                'documents': snapshot['documents'], 'result': run['result'],
                'scope_proposal': ({**run['plan']['scope_proposal'], 'proposal_sha256': encode(run['plan']['scope_proposal'])[1]}
                                   if run['plan'].get('scope_proposal') else None),
                'repair_case': ({**run['plan']['repair_case'], 'repair_case_sha256': encode(run['plan']['repair_case'])[1]}
                                if run['plan'].get('repair_case') else None),
                'latest_decision': self.decode(latest) if latest else None}

    async def submit(self, operation, module_id, prompt_id, submission, *, actor_user_id):
        submission = DecisionSubmission.model_validate(submission)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can submit this decision')
        identity = {'uuid': submission.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': module_id, 'course_version': operation.package.manifest.release_id,
                    'manifest_sha256': operation.package.manifest_sha256, 'run_id': submission.run_id, 'prompt_id': prompt_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request_sha256 = encode({**identity, 'submission': submission.model_dump(mode='json', exclude_none=True)})[1]
        existing = await self.records.find_one({'uuid': submission.request_id})
        if existing is not None:
            if existing['request_sha256'] != request_sha256:
                raise EnrollmentConflict('This decision request already belongs to different answers or another learner')
            record = self.decode(existing)
            await self._link_scope(operation, record, replay=True)
            return record
        prompt = load_prompt(operation.package, module_id, prompt_id)
        if submission.prompt_sha256 != prompt.digest or submission.choice not in prompt.choices:
            raise EnrollmentConflict('Reload the pinned decision prompt before submitting')
        run = await LabExecutionRepository().get(actor_user_id, submission.run_id)
        if run is None or run['plan']['module_id'] != module_id:
            raise EnrollmentConflict('Select an owned run for this module')
        LabExecutionRepository.check_operation(operation, run['plan'])
        expected_state = 'prepared' if prompt.phase == 'before_execution' else 'completed'
        if run['state'] != expected_state:
            raise EnrollmentConflict('This decision must be recorded at the required stage of the run')
        snapshot = await LabInputRepository().get(actor_user_id, run['plan']['input_snapshot_id'])
        if snapshot is None or encode(snapshot)[1] != run['plan']['input_snapshot_sha256']:
            raise EnrollmentConflict('The original run inputs are unavailable or changed')
        repair = run['plan'].get('repair_case')
        if capture_repair_case(operation.package, snapshot) != repair:
            raise EnrollmentConflict('The saved repair case does not match this course and run')
        if not repair_reference_matches(repair, submission.repair_case_sha256):
            raise DecisionValidationError('Review the exact saved repair example before recording this decision')
        proposal = run['plan'].get('scope_proposal')
        if proposal is not None and prompt.execution_choice is not None:
            selection = submission.proposal_selection
            if (selection is None or selection.proposal_sha256 != encode(proposal)[1]
                    or selection.source_id not in {item['id'] for item in proposal['source_options']}):
                raise DecisionValidationError('Review the saved proposal and explicitly choose a source')
        elif submission.proposal_selection is not None:
            raise DecisionValidationError('This decision does not accept a proposal selection')
        fields = [item.field for item in submission.value_checks]
        if len(set(fields)) != len(fields) or set(fields) != set(prompt.required_fields):
            raise DecisionValidationError('Record one source check for each required field')
        documents = {item['document_id']: item for item in snapshot['documents']}
        for check in submission.value_checks:
            document = documents.get(check.source_document_id)
            if document is None or (check.source_quote and check.source_quote not in document['text']):
                raise DecisionValidationError('Each source check must cite the saved assigned document')
        record = {**identity, 'request_sha256': request_sha256, 'prompt': prompt.model_dump(mode='json'),
                  'prompt_sha256': prompt.digest, 'submission': submission.model_dump(mode='json', exclude_none=True),
                  'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': run['plan']['input_snapshot_sha256'],
                  'plan_sha256': run['plan_sha256'], 'run_state_at_submission': run['state'],
                  'execution_result_sha256': encode(run['result'])[1] if run['result'] else None,
                  'previous_scope_decision_id': run.get('scope_decision_id'),
                  'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'submission_channel': 'authenticated_learner_request', 'credit_awarded': False}
        serialized, digest = encode(record)
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_sha256,
                                           'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': submission.request_id})
            if existing is None or existing['request_sha256'] != request_sha256:
                raise EnrollmentConflict('This learner decision request was already claimed')
        record = await self.get(actor_user_id, submission.request_id)
        await self._link_scope(operation, record, replay=False)
        return record

    async def _link_scope(self, operation, record, *, replay):
        if record['prompt'].get('execution_choice') is None:
            return
        lease = LabExecutionRepository.check_operation(operation, record)
        runs = CertificationLabExecution.get_motor_collection()
        current = await LabExecutionRepository().get(operation.user_id, record['run_id'])
        if current is None:
            raise EnrollmentConflict('The reviewed run is unavailable')
        if current.get('scope_decision_id') == record['uuid']:
            return
        previous = record['previous_scope_decision_id']
        if current.get('scope_decision_id') != previous:
            if replay:
                return  # Historical replay cannot replace a newer choice.
            raise EnrollmentConflict('Another scope decision was saved; reload the run before continuing')
        await LabInputRepository._check_lease(lease)
        linked = await runs.update_one({'uuid': record['run_id'], 'user_id': operation.user_id,
            'state': 'prepared', 'plan_sha256': record['plan_sha256'], 'scope_decision_id': previous},
            {'$set': {'scope_decision_id': record['uuid'], 'scope_decision_sha256': encode(record)[1]}})
        if linked.modified_count != 1:
            latest = await runs.find_one({'uuid': record['run_id'], 'scope_decision_id': record['uuid']})
            if latest is None:
                raise EnrollmentConflict('The run or scope decision changed before this choice was linked')

    async def authorize(self, operation, run):
        """Read the currently linked consent, never an arbitrary passing answer."""
        LabExecutionRepository.check_operation(operation, run['plan'])
        return await self.inspect_authorization(operation.user_id, operation.progress.enrollment_id, operation.package, run)

    async def inspect_authorization(self, user_id, enrollment_id, package, run):
        """Validate linked consent without acquiring a write lease or dispatching."""
        identity = {'user_id': user_id, 'enrollment_id': enrollment_id,
                    'course_version': package.manifest.release_id, 'manifest_sha256': package.manifest_sha256}
        if any(run['plan'].get(key) != value for key, value in identity.items()):
            raise EnrollmentConflict('The saved execution belongs to a different learner or course')
        requirement = execution_requirement(package, run['plan']['module_id'])
        if requirement != run['plan'].get('approval_requirement'):
            raise EnrollmentConflict('Execution approval requirements changed; prepare a new run')
        if requirement is None:
            return None
        record = await self.get(user_id, run.get('scope_decision_id'))
        if record is None:
            raise EnrollmentConflict('Record your scope approval for this saved run before execution')
        if any(record.get(key) != value for key, value in identity.items()):
            raise EnrollmentConflict('The saved scope decision belongs to a different learner or course')
        if (encode(record)[1] != run.get('scope_decision_sha256')
                or record['module_id'] != run['plan']['module_id'] or record['run_id'] != run['run_id']
                or record['plan_sha256'] != run['plan_sha256']
                or record['input_snapshot_sha256'] != run['plan']['input_snapshot_sha256']
                or record['prompt_id'] != requirement['prompt_id'] or record['prompt_sha256'] != requirement['prompt_sha256']
                or record['run_state_at_submission'] != 'prepared'
                or record['submission_channel'] != 'authenticated_learner_request'):
            raise EnrollmentConflict('The saved scope decision does not authorize this exact run')
        if record['submission']['choice'] != requirement['choice']:
            raise EnrollmentConflict('Your latest scope decision does not approve execution; review it before running')
        snapshot = await LabInputRepository().get(user_id, run['plan']['input_snapshot_id'])
        if snapshot is None or encode(snapshot)[1] != run['plan']['input_snapshot_sha256']:
            raise EnrollmentConflict('The original run inputs are unavailable or changed')
        repair = run['plan'].get('repair_case')
        if (capture_repair_case(package, snapshot) != repair
                or not repair_reference_matches(repair, record['submission'].get('repair_case_sha256'))):
            raise EnrollmentConflict('The saved repair decision does not authorize this exact example and run')
        proposal = run['plan'].get('scope_proposal')
        if capture_proposal(package, snapshot) != proposal:
            raise EnrollmentConflict('The saved scope proposal does not match this course and run')
        if proposal is not None and not selection_matches_run(proposal,
                DecisionSubmission.model_validate(record['submission']).proposal_selection, snapshot):
            raise EnrollmentConflict('The source you selected does not match the assigned run; correct the scope before execution')
        return {'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'decision': record,
                'decision_sha256': encode(record)[1]}
