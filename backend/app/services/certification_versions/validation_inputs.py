"""Freeze owned extraction instructions and both complete assigned test sources."""
import base64
import datetime
import hashlib
from typing import Literal

import fitz
from pydantic import Field
from pymongo.errors import DuplicateKeyError

from .source_access import owned_source
from app.models.search_set import SearchSet, SearchSetItem
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository, MAX_SNAPSHOT_BYTES
from .outcomes import ContractModel
from .validation_case import FIELDS, ValidationCase, load_validation_case


class ValidationCaptureRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    artifact_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['capture_validation_extraction_and_complete_sources']


def verify_artifact(artifact, artifact_id, user_id):
    fields = artifact['fields']
    if (artifact['uuid'] != artifact_id or artifact['user_id'] != user_id or artifact['set_type'] != 'extraction'
            or len(fields) != 3 or tuple(f['title'] for f in fields) != FIELDS
            or len({f['id'] for f in fields}) != 3 or len({f['searchphrase'] for f in fields}) != 3
            or any(not f['searchphrase'].strip() or f['searchtype'] != 'extraction' for f in fields)
            or any(f['text_blocks'] or f['pdf_binding'] for f in fields)):
        raise EnrollmentConflict('Use exactly the three named extraction fields with complete source context and no attached text overrides')


def pdf_pages(data):
    if not data or len(data) > 2 * 1024 * 1024:
        raise EnrollmentConflict('An assigned validation PDF exceeds the bounded source limit')
    with fitz.open(stream=data, filetype='pdf') as pdf:
        pages = [page.get_text() for page in pdf]
    if not pages or any(not page.strip() for page in pages):
        raise EnrollmentConflict('Every assigned validation page must have readable source text')
    return pages


class ValidationInputRepository(LabInputRepository):
    @staticmethod
    def decode(raw):
        saved = LabInputRepository.decode(raw)
        try:
            body = ValidationCaptureRequest.model_validate(saved['request'])
            case = ValidationCase.model_validate(saved['authored_case'])
            if (saved['record_kind'] != 'validation_extraction_input' or saved['module_id'] != 'validation_qa'
                    or body.request_id != saved['uuid'] or body.artifact_id != saved['artifact_id']
                    or body.case_sha256 != case.digest or saved['case'] != case.public_definition()
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or saved['artifact_sha256'] != encode(saved['artifact'])[1]
                    or len(saved['documents']) != 2 or len({s['document_id'] for s in saved['documents']}) != 2
                    or saved['execution_status'] != 'not_started' or saved['execution_authorized'] is not False
                    or saved['credit_awarded'] is not False or saved['module_completion_eligible'] is not False
                    or saved['outcomes_awarded'] != []):
                raise ValueError('The original capture identity or evidence boundary changed')
            verify_artifact(saved['artifact'], saved['artifact_id'], saved['user_id'])
            for source, assigned in zip(saved['documents'], case.sources):
                data = base64.b64decode(source['source_pdf_base64'], validate=True)
                pages = pdf_pages(data)
                case.verify_source(assigned.id, data, pages)
                if (source['source_id'] != assigned.id or source['assigned_filename'] != assigned.filename
                        or source['source_sha256'] != assigned.sha256 or source['pages'] != pages
                        or not source['text'].strip() or hashlib.sha256(source['text'].encode()).hexdigest() != source['text_sha256']):
                    raise ValueError('Original source bytes, pages or ingestion changed')
            return saved
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, RuntimeError) as exc:
            raise CourseCatalogError('Saved representative validation inputs failed integrity verification') from exc

    @staticmethod
    async def _read_artifact(user_id, artifact_id):
        artifact = await SearchSet.find_one({'uuid': artifact_id, 'user_id': user_id})
        if artifact is None:
            raise EnrollmentConflict('Select an extraction owned by this learner')
        items = await SearchSetItem.find({'searchset': artifact_id}).sort('_id').to_list()
        if any(item.user_id not in (None, user_id) for item in items):
            raise EnrollmentConflict('The extraction contains fields owned by another learner')
        result = artifact.model_dump(mode='json', include={
            'uuid', 'user_id', 'title', 'set_type', 'domain', 'extraction_config', 'extraction_config_override', 'cross_field_rules', 'item_order',
        })
        result['fields'] = sorted([item.model_dump(mode='json', include={
            'id', 'title', 'searchphrase', 'searchtype', 'is_optional', 'enum_values', 'text_blocks', 'pdf_binding',
        }) for item in items], key=lambda f: FIELDS.index(f['title']) if f['title'] in FIELDS else len(FIELDS))
        verify_artifact(result, artifact_id, user_id)
        return result

    async def capture(self, operation, body, *, actor_user_id, storage):
        body = ValidationCaptureRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Validation capture requires the authenticated learner')
        progress, package = operation.progress, operation.package
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': progress.enrollment_id,
                    'module_id': 'validation_qa', 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256, 'artifact_id': body.artifact_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        case = load_validation_case(package)
        if case.digest != body.case_sha256:
            raise EnrollmentConflict('The capture belongs to a different validation assignment')
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved[key] != value for key, value in identity.items()) or saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This capture identity belongs to different work or another learner')
            return saved

        await self._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        ids = progress.modules.get('validation_qa', {}).get('provisioned_docs', [])
        if (not isinstance(ids, list) or len(ids) != 2 or not all(isinstance(i, str) for i in ids)
                or len(set(ids)) != 2 or not progress.lab_folder_id):
            raise EnrollmentConflict('Provision both distinct assigned sources in this enrollment before capture')
        artifact = await self._read_artifact(actor_user_id, body.artifact_id)
        sources = []
        originals = []
        for document_id, assigned in zip(ids, case.sources):
            document = await owned_source(actor_user_id, document_id)
            if document is None or document.folder != progress.lab_folder_id:
                raise EnrollmentConflict('An assigned source is missing, inaccessible or outside the enrolled lab')
            if (document.processing or not document.valid or document.text_layer_rejected or not document.raw_text.strip()
                    or document.task_status == 'error' or document.ingestion_warnings or document.unread_pages):
                raise EnrollmentConflict('Finish and inspect both sources’ ingestion before saving the suite inputs')
            originals.append((document.uuid, document.model_dump(mode='json')))
            try:
                data = await storage.read(document.path)
                pages = pdf_pages(data)
                case.verify_source(assigned.id, data, pages)
            except (OSError, ValueError, RuntimeError) as exc:
                raise EnrollmentConflict('The complete assigned source bytes could not be verified') from exc
            sources.append({'source_id': assigned.id, 'document_id': document.uuid, 'assigned_filename': assigned.filename,
                'title': document.title, 'source_sha256': assigned.sha256, 'source_pdf_base64': base64.b64encode(data).decode('ascii'),
                'text': document.raw_text, 'text_sha256': hashlib.sha256(document.raw_text.encode()).hexdigest(),
                'text_markers': document.text_markers, 'pages': pages,
                'text_origin': 'original ingestion preserved separately from verified complete PDF page text'})
        for document_id, original in originals:
            current = await owned_source(actor_user_id, document_id)
            if current is None or current.model_dump(mode='json') != original:
                raise EnrollmentConflict('An assigned source changed during capture; inspect it again')
        if await self._read_artifact(actor_user_id, body.artifact_id) != artifact:
            raise EnrollmentConflict('The extraction changed during capture; inspect the revised fields')
        payload = {**identity, 'schema_version': 1, 'record_kind': 'validation_extraction_input',
            'request': request, 'request_sha256': request_hash, 'case': case.public_definition(), 'authored_case': case.model_dump(mode='json'),
            'rubric_id': package.manifest.rubric_id, 'exercise_sha256': package.manifest.artifacts['exercises.json'],
            'artifact': artifact, 'artifact_sha256': encode(artifact)[1], 'documents': sources, 'lab_folder_id': progress.lab_folder_id,
            'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'execution_status': 'not_started', 'execution_authorized': False, 'credit_awarded': False,
            'module_completion_eligible': False, 'outcomes_awarded': []}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('The complete validation inputs exceed the immutable storage limit')
        await self._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'record_kind': payload['record_kind'], 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The validation capture identity was claimed by another operation')
            return replay(existing)
        await self._check_lease(lease)
        return payload
