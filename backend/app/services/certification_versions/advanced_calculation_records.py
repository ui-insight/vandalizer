"""Preserve an authenticated calculation submission and its exact assigned PDF.

Uses the existing immutable lab-input collection and enrollment write boundary.
This is not workflow configuration, execution authority, a grade or earned credit.
"""
import base64
import binascii
import datetime
import hashlib
from typing import Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .source_access import owned_source
from .advanced_calculations import CalculationRecord, check_budget_calculations
from .advanced_case import AdvancedNodesCase, CALCULATIONS, load_advanced_case
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository, MAX_SNAPSHOT_BYTES
from .outcomes import ContractModel


class AdvancedCalculationSubmission(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    document_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    records: tuple[CalculationRecord, ...] = Field(min_length=3, max_length=3)
    previous_snapshot_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    consent: Literal['save_source_bound_budget_calculations']

    @model_validator(mode='after')
    def complete_checks(self):
        if {record.id for record in self.records} != set(CALCULATIONS):
            raise ValueError('Include every distinct required calculation')
        if self.previous_snapshot_id == self.request_id:
            raise ValueError('A revision requires a distinct new request identity')
        return self


class AdvancedCalculationRepository(LabInputRepository):
    @staticmethod
    def decode(raw):
        saved = LabInputRepository.decode(raw)
        try:
            body = AdvancedCalculationSubmission.model_validate(saved['request'])
            case = AdvancedNodesCase.model_validate(saved['authored_case'])
            source = saved['document']
            pdf = base64.b64decode(saved['source_pdf_base64'], validate=True)
            if (saved['record_kind'] != 'advanced_calculation_input' or saved['module_id'] != 'advanced_nodes'
                    or body.request_id != saved['uuid'] or body.document_id != saved['artifact_id']
                    or body.document_id != source['document_id'] or body.case_sha256 != case.digest
                    or saved['case'] != case.public_definition()
                    or encode(body.model_dump(mode='json'))[1] != saved['request_sha256']
                    or source['assigned_filename'] != case.source_filename or source['source_sha256'] != case.source_sha256
                    or hashlib.sha256(source['text'].encode()).hexdigest() != source['text_sha256']
                    or not source['text'].strip() or saved['execution_status'] != 'not_started'
                    or saved['execution_authorized'] is not False or saved['credit_awarded'] is not False
                    or saved['module_completion_eligible'] is not False or saved['outcomes_awarded'] != []
                    or saved['submission_channel'] != 'authenticated_learner_calculation_request'
                    or saved['checks'] != check_budget_calculations(case, body.records, source_bytes=pdf)):
                raise ValueError('Calculation inputs, source or stored checks changed')
            return saved
        except (KeyError, TypeError, ValueError, AttributeError, binascii.Error) as exc:
            raise CourseCatalogError('The saved calculation evidence failed integrity verification') from exc

    async def submit(self, operation, body, *, actor_user_id, storage):
        body = AdvancedCalculationSubmission.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Calculation evidence requires the authenticated learner')
        progress, package = operation.progress, operation.package
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': progress.enrollment_id,
                    'module_id': 'advanced_nodes', 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256, 'artifact_id': body.document_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        case = load_advanced_case(package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The calculation request belongs to another course case')
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved[key] != value for key, value in identity.items()) or saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This calculation request belongs to different work or another learner')
            return saved

        await self._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        previous = None
        if body.previous_snapshot_id:
            previous = await self.get(actor_user_id, body.previous_snapshot_id)
            if previous is None or any(previous[key] != value for key, value in identity.items() if key != 'uuid'):
                raise EnrollmentConflict('A revision must preserve an owned calculation on the same assigned source and course')
            if previous['case'] != case.public_definition():
                raise EnrollmentConflict('A revision cannot replace the original calculation case')
        if previous:
            source = previous['document']
            source_bytes = base64.b64decode(previous['source_pdf_base64'], validate=True)
        else:
            document_ids = progress.modules.get('advanced_nodes', {}).get('provisioned_docs', [])
            if document_ids != [body.document_id] or not progress.lab_folder_id:
                raise EnrollmentConflict('Select the exact assigned budget in this enrollment before recording calculations')
            document = await owned_source(actor_user_id, body.document_id)
            if document is None or document.folder != progress.lab_folder_id:
                raise EnrollmentConflict('The assigned source is missing, inaccessible or outside this enrollment’s lab')
            if (document.processing or not document.valid or document.text_layer_rejected or not document.raw_text.strip()
                    or document.task_status == 'error' or document.ingestion_warnings or document.unread_pages):
                raise EnrollmentConflict('Finish and inspect source ingestion before recording calculations')
            before = document.model_dump(mode='json')
            try:
                source_bytes = await storage.read(document.path)
            except (OSError, ValueError) as exc:
                raise EnrollmentConflict('The assigned budget bytes could not be verified') from exc
            if hashlib.sha256(source_bytes).hexdigest() != case.source_sha256:
                raise EnrollmentConflict('The assigned document bytes differ from the course budget')
            current = await owned_source(actor_user_id, body.document_id)
            if current is None or current.model_dump(mode='json') != before:
                raise EnrollmentConflict('The assigned source changed during capture; inspect it again')
            source = {'document_id': document.uuid, 'assigned_filename': case.source_filename, 'title': document.title,
                      'source_sha256': case.source_sha256, 'text_sha256': hashlib.sha256(document.raw_text.encode()).hexdigest(),
                      'text': document.raw_text, 'text_markers': document.text_markers,
                      'text_origin': 'owned workspace ingestion retained separately from PDF-based arithmetic checks'}
        checks = check_budget_calculations(case, body.records, source_bytes=source_bytes)
        record = {**identity, 'schema_version': 1, 'record_kind': 'advanced_calculation_input',
                  'request': request, 'request_sha256': request_hash, 'case': case.public_definition(),
                  'authored_case': case.model_dump(mode='json'), 'document': source,
                  'source_pdf_base64': base64.b64encode(source_bytes).decode('ascii'), 'checks': checks,
                  'rubric_id': package.manifest.rubric_id, 'exercise_sha256': package.manifest.artifacts['exercises.json'],
                  'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'submission_channel': 'authenticated_learner_calculation_request',
                  'execution_status': 'not_started', 'execution_authorized': False, 'outcomes_awarded': [],
                  'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(record)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('The complete calculation evidence exceeds the immutable storage budget')
        await self._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'record_kind': record['record_kind'], 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('This calculation reference was claimed by another operation')
            return replay(existing)
        await self._check_lease(lease)
        return record
