"""Freeze an owned workflow and assigned subaward; this grants no run authority."""
import datetime
import hashlib
from typing import Literal

from pydantic import Field
from pymongo.errors import DuplicateKeyError

from .source_access import owned_source
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository, MAX_SNAPSHOT_BYTES
from .multi_step_case import load_multi_step_case
from .outcomes import ContractModel
from .workflow_design_inputs import WorkflowDesignInputRepository
from .writes import require_lease


class ConnectedCaptureRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    workflow_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['capture_connected_workflow_inputs']


class ConnectedWorkflowInputRepository(WorkflowDesignInputRepository):
    """Reuse only the owned configuration reader; capture has its own contract."""

    @staticmethod
    def decode(record):
        saved = LabInputRepository.decode(record)
        try:
            body = ConnectedCaptureRequest.model_validate(saved['request'])
            source = saved['documents'][0]
            if (saved['record_kind'] != 'connected_workflow_input' or saved['module_id'] != 'multi_step'
                    or body.request_id != saved['uuid'] or body.workflow_id != saved['artifact_id']
                    or body.case_sha256 != saved['case']['case_sha256']
                    or saved['case']['module_id'] != 'multi_step'
                    or saved['case']['provenance'] != 'authored_connected_workflow_case_not_execution'
                    or encode(body.model_dump(mode='json'))[1] != saved['request_sha256']
                    or encode(saved['artifact'])[1] != saved['artifact_sha256']
                    or saved['artifact']['workflow']['id'] != saved['artifact_id']
                    or saved['artifact']['workflow']['user_id'] != saved['user_id']
                    or saved['artifact']['capture_scope'] != 'saved_workflow_step_task_configuration_only'
                    or len(saved['documents']) != 1 or not source['text'].strip()
                    or source['assigned_filename'] != saved['case']['source_filename']
                    or source['source_sha256'] != saved['case']['source_sha256']
                    or hashlib.sha256(source['text'].encode()).hexdigest() != source['text_sha256']
                    or saved['execution_status'] != 'not_started' or saved['outcomes_awarded'] != []
                    or saved['execution_authorized'] is not False or saved['credit_awarded'] is not False
                    or saved['module_completion_eligible'] is not False
                    or 'review_guidance' in saved['case'] or 'source_expectations' in saved['case']):
                raise ValueError('The saved source, configuration or evidence boundary changed')
            return saved
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            raise CourseCatalogError('Saved connected-workflow inputs failed integrity verification') from exc

    async def capture(self, operation, body, *, actor_user_id, storage):
        body = ConnectedCaptureRequest.model_validate(body)
        progress, package = operation.progress, operation.package
        if (not operation.writable or actor_user_id != operation.user_id or progress.user_id != operation.user_id
                or progress.course_version != package.manifest.release_id):
            raise EnrollmentConflict('Connected capture requires the authenticated learner and writable pinned course')
        lease = require_lease(operation.user_id, progress.enrollment_id)
        if str(progress.id) != lease.progress_id:
            raise EnrollmentConflict('Connected capture does not own this progress record')
        case = load_multi_step_case(package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The capture request belongs to another connected case')
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]
        identity = {'uuid': body.request_id, 'user_id': operation.user_id, 'enrollment_id': progress.enrollment_id,
                    'module_id': 'multi_step', 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256, 'artifact_id': body.workflow_id}

        def replay(raw):
            saved = self.decode(raw)
            if any(saved[key] != value for key, value in identity.items()) or saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This capture reference belongs to another connected-workflow request')
            return saved

        await self._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        document_ids = progress.modules.get('multi_step', {}).get('provisioned_docs', [])
        if (not isinstance(document_ids, list) or len(document_ids) != 1
                or not isinstance(document_ids[0], str) or not progress.lab_folder_id):
            raise EnrollmentConflict('Provision the assigned subaward in this enrollment before capturing inputs')
        artifact = await self._read_artifact(operation.user_id, body.workflow_id)
        document = await owned_source(operation.user_id, document_ids[0])
        if document is None or document.folder != progress.lab_folder_id:
            raise EnrollmentConflict('The assigned source is missing, inaccessible or outside this enrollment’s lab')
        if (document.processing or not document.valid or document.text_layer_rejected or not document.raw_text.strip()
                or document.task_status == 'error' or document.ingestion_warnings or document.unread_pages):
            raise EnrollmentConflict('Finish and inspect source ingestion before capturing an assessed workflow')
        before = document.model_dump(mode='json')
        try:
            source_hash = hashlib.sha256(await storage.read(document.path)).hexdigest()
        except (OSError, ValueError) as exc:
            raise EnrollmentConflict('The assigned subaward bytes could not be verified') from exc
        if source_hash != case.source_sha256:
            raise EnrollmentConflict('The assigned document bytes differ from this course’s subaward')
        current = await owned_source(operation.user_id, document.uuid)
        if current is None or current.model_dump(mode='json') != before:
            raise EnrollmentConflict('The assigned source changed during capture; inspect it again')
        if await self._read_artifact(operation.user_id, body.workflow_id) != artifact:
            raise EnrollmentConflict('The workflow configuration changed during capture; inspect it again')
        sources = [{'document_id': document.uuid, 'assigned_filename': case.source_filename, 'title': document.title,
                    'source_sha256': source_hash, 'text_sha256': hashlib.sha256(document.raw_text.encode()).hexdigest(),
                    'text': document.raw_text, 'text_markers': document.text_markers,
                    'text_origin': 'workspace ingestion text captured at preparation; source bytes verified against course asset'}]
        payload = {**identity, 'schema_version': 1, 'record_kind': 'connected_workflow_input',
                   'request': request, 'request_sha256': request_hash, 'case': case.public_definition(),
                   'rubric_id': package.manifest.rubric_id, 'exercise_sha256': package.manifest.artifacts['exercises.json'],
                   'artifact': artifact, 'artifact_sha256': encode(artifact)[1], 'documents': sources,
                   'lab_folder_id': progress.lab_folder_id,
                   'captured_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                   'execution_status': 'not_started', 'execution_authorized': False, 'outcomes_awarded': [],
                   'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('Connected workflow inputs exceed the immutable snapshot size limit')
        await self._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The connected capture reference was claimed by another operation')
            return replay(existing)
        await self._check_lease(lease)
        return payload
