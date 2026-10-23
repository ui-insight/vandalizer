"""Internal immutable saved-design capture. No run, grade or credit is created."""
import datetime
from typing import Literal

from bson import ObjectId
from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.models.search_set import SearchSet, SearchSetItem
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository, MAX_SNAPSHOT_BYTES
from .outcomes import ContractModel
from .process_submissions import ProcessSubmissionRepository
from .workflow_design_case import load_workflow_design_case
from .writes import require_lease


class DesignCaptureRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    workflow_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    handoff: Literal['owned_saved_process_submission', 'supplied_example']
    process_submission_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    consent: Literal['capture_saved_workflow_design']

    @model_validator(mode='after')
    def validate_choice(self):
        if (self.handoff == 'owned_saved_process_submission') != (self.process_submission_id is not None):
            raise ValueError('Only an owned-map choice requires a saved submission reference')
        return self


class WorkflowDesignInputRepository(LabInputRepository):
    @staticmethod
    def decode(record):
        saved = LabInputRepository.decode(record)
        try:
            body = DesignCaptureRequest.model_validate(saved['request'])
            if (saved['record_kind'] != 'saved_workflow_design' or saved['module_id'] != 'workflow_design'
                    or body.request_id != saved['uuid'] or body.workflow_id != saved['artifact_id']
                    or body.case_sha256 != saved['case']['case_sha256']
                    or encode(body.model_dump(mode='json'))[1] != saved['request_sha256']
                    or encode(saved['artifact'])[1] != saved['artifact_sha256']
                    or saved['artifact']['workflow']['id'] != saved['artifact_id']
                    or saved['artifact']['workflow']['user_id'] != saved['user_id']
                    or saved['artifact']['capture_scope'] != 'saved_workflow_step_task_configuration_only'
                    or saved['handoff']['kind'] != body.handoff
                    or saved['execution_status'] != 'not_started' or saved['outcomes_awarded'] != []
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False
                    or 'review_guidance' in saved['case']):
                raise ValueError('Saved design identity or evidence boundary changed')
            if body.handoff == 'owned_saved_process_submission':
                original = saved['handoff']['original_submission']
                if (original['uuid'] != body.process_submission_id
                        or any(original[key] != saved[key] for key in ('user_id', 'enrollment_id', 'course_version', 'manifest_sha256'))
                        or encode(original)[1] != saved['handoff']['original_sha256']):
                    raise ValueError('Original process-map identity changed')
            elif saved['handoff']['supplied_map'] != saved['case']['supplied_map']:
                raise ValueError('Supplied example changed')
            return saved
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('Saved workflow design failed integrity verification') from exc

    async def _read_artifact(self, user_id, workflow_id):
        workflow = await Workflow.find_one({'_id': ObjectId(workflow_id), 'user_id': user_id})
        if workflow is None:
            raise EnrollmentConflict('Select a workflow owned by this learner')
        if not workflow.steps or len(workflow.steps) != len(set(workflow.steps)) or len(workflow.steps) > 100:
            raise EnrollmentConflict('The saved workflow needs a bounded, unambiguous step list')
        steps, task_ids, extraction_sets = [], set(), {}
        for step_id in workflow.steps:
            step = await WorkflowStep.get(step_id)
            if step is None or not step.tasks or len(step.tasks) > 100:
                raise EnrollmentConflict('A referenced workflow step or task is missing')
            tasks = []
            for task_id in step.tasks:
                if task_id in task_ids:
                    raise EnrollmentConflict('The saved workflow reuses a task reference ambiguously')
                task_ids.add(task_id)
                task = await WorkflowStepTask.get(task_id)
                if task is None:
                    raise EnrollmentConflict('A referenced workflow task is missing')
                tasks.append(task.model_dump(mode='json'))
                reference = task.data.get('search_set_uuid') if task.name == 'Extraction' else None
                if reference is not None:
                    if not isinstance(reference, str) or not reference.strip():
                        raise EnrollmentConflict('An extraction task has an invalid template reference')
                    if reference not in extraction_sets:
                        extraction_sets[reference] = await self._read_extraction(user_id, reference)
            steps.append({'step': step.model_dump(mode='json'), 'tasks': tasks})
        # Freeze owned template fields too. Other external resources and source
        # documents remain references, not captured or executed evidence.
        return {'capture_scope': 'saved_workflow_step_task_configuration_only',
                'workflow': workflow.model_dump(mode='json', exclude={'share_token'}), 'steps': steps,
                'referenced_extraction_sets': extraction_sets}

    @staticmethod
    async def _read_extraction(user_id, reference):
        matches = await SearchSet.find({'uuid': reference, 'user_id': user_id, 'set_type': 'extraction'}).limit(2).to_list()
        if len(matches) != 1:
            raise EnrollmentConflict('Every referenced extraction template must be owned by this learner')
        artifact = matches[0]
        items = await SearchSetItem.find({'searchset': reference}).sort('_id').to_list()
        if any(item.user_id not in (None, user_id) for item in items):
            raise EnrollmentConflict('A referenced extraction field belongs to another learner')
        fields = [item for item in items if item.searchtype == 'extraction']
        names = [item.searchphrase.strip().casefold() for item in fields]
        if not fields or not all(names) or len(names) != len(set(names)):
            raise EnrollmentConflict('A referenced extraction template has missing or ambiguous field definitions')
        state = artifact.model_dump(mode='json', include={
            'uuid', 'title', 'set_type', 'domain', 'extraction_config', 'extraction_config_override', 'cross_field_rules', 'item_order',
        })
        state['fields'] = [item.model_dump(mode='json', include={
            'id', 'searchphrase', 'searchtype', 'title', 'is_optional', 'enum_values', 'text_blocks', 'pdf_binding',
        }) for item in fields]
        return state

    async def capture(self, operation, body, *, actor_user_id):
        body = DesignCaptureRequest.model_validate(body)
        progress, package = operation.progress, operation.package
        if (not operation.writable or actor_user_id != operation.user_id or progress.user_id != operation.user_id
                or progress.course_version != package.manifest.release_id):
            raise EnrollmentConflict('Design capture requires the authenticated learner and writable pinned course')
        lease = require_lease(operation.user_id, progress.enrollment_id)
        if str(progress.id) != lease.progress_id:
            raise EnrollmentConflict('Design capture does not own this progress record')
        case = load_workflow_design_case(package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The design request belongs to another authored case')
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]
        identity = {'uuid': body.request_id, 'user_id': operation.user_id, 'enrollment_id': progress.enrollment_id,
                    'module_id': 'workflow_design', 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256, 'artifact_id': body.workflow_id}

        def replay(raw):
            saved = self.decode(raw)
            if any(saved[key] != value for key, value in identity.items()) or saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This capture reference already belongs to another design request')
            return saved

        await self._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        if body.handoff == 'owned_saved_process_submission':
            original = await ProcessSubmissionRepository().get(operation.user_id, body.process_submission_id)
            if (original is None or any(original[key] != identity[key] for key in
                    ('user_id', 'enrollment_id', 'course_version', 'manifest_sha256'))
                    or original['case']['case_sha256'] != case.source_process_case_sha256):
                raise EnrollmentConflict('Choose an owned original process submission from this course and case')
            from .process_case import load_process_case
            if original['case'] != load_process_case(package).public_definition():
                raise EnrollmentConflict('The original process case no longer matches its pinned definition')
            handoff = {'kind': body.handoff, 'original_submission': original, 'original_sha256': encode(original)[1]}
        else:
            handoff = {'kind': body.handoff, 'supplied_map': case.supplied_map.model_dump(mode='json')}
        artifact = await self._read_artifact(operation.user_id, body.workflow_id)
        if await self._read_artifact(operation.user_id, body.workflow_id) != artifact:
            raise EnrollmentConflict('The workflow changed during capture; inspect the current revision')
        payload = {**identity, 'schema_version': 1, 'record_kind': 'saved_workflow_design',
                   'rubric_id': package.manifest.rubric_id, 'exercise_sha256': package.manifest.artifacts['exercises.json'],
                   'request': request, 'request_sha256': request_hash, 'case': case.public_definition(), 'handoff': handoff,
                   'artifact': artifact, 'artifact_sha256': encode(artifact)[1],
                   'captured_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                   'execution_status': 'not_started', 'outcomes_awarded': [],
                   'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('The saved design exceeds the immutable snapshot size limit')
        await self._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The design capture reference could not be recovered')
            return replay(existing)
        await self._check_lease(lease)
        return payload
