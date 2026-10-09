"""Capture owned, assigned extraction inputs before execution.

Internal foundation only: no execution, grade, transfer or credit is produced.
The current legacy grader is unchanged. A future runner must consume this saved
payload, bind its execution receipt, and record learner decisions separately.
"""
import datetime
import hashlib
import json
import re

from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationLabInput, CertificationProgress
from .source_access import owned_source
from app.models.search_set import SearchSet, SearchSetItem
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .writes import require_lease

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


class LabInputRepository:
    @property
    def records(self):
        return CertificationLabInput.get_motor_collection()

    @staticmethod
    def decode(record):
        try:
            if hashlib.sha256(record['record_json'].encode()).hexdigest() != record['record_sha256']:
                raise ValueError('Digest mismatch')
            payload = json.loads(record['record_json'])
            if any(payload[key] != record[key] for key in (
                'uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'artifact_id',
            )):
                raise ValueError('Identity mismatch')
            return payload
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('Saved lab inputs failed integrity verification') from exc

    async def get(self, user_id, snapshot_id):
        raw = await self.records.find_one({'uuid': snapshot_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def capture_extraction(self, operation, module_id, artifact_id, request_id, storage):
        """Only owned artifacts and currently readable owned sources qualify.

        The caller holds the enrollment write boundary. Retrying an identical
        request returns the original inputs even if live artifacts have changed.
        This method never infers an artifact from workspace activity or a title.
        """
        if not operation.writable or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Lab input capture requires a writable course operation and valid request identity')
        progress, package = operation.progress, operation.package
        lease = require_lease(operation.user_id, progress.enrollment_id)
        identity = {'uuid': request_id, 'user_id': operation.user_id, 'enrollment_id': progress.enrollment_id,
                    'module_id': module_id, 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256, 'artifact_id': artifact_id}
        if (progress.user_id != operation.user_id or progress.course_version != package.manifest.release_id
                or str(progress.id) != lease.progress_id):
            raise EnrollmentConflict('Lab inputs must match the pinned learner and course')
        exercises = package.json('exercises.json')
        filenames = exercises.get(module_id, {}).get('documents', [])
        if not filenames or len(filenames) != len(set(filenames)):
            raise EnrollmentConflict('This module has no valid assigned document set')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            if any(existing.get(key) != value for key, value in identity.items()):
                raise EnrollmentConflict('This lab request belongs to another learner, course, module or artifact')
            return self.decode(existing)
        await self._check_lease(lease)
        document_ids = progress.modules.get(module_id, {}).get('provisioned_docs', [])
        if (not isinstance(document_ids, list) or not all(isinstance(value, str) for value in document_ids)
                or len(document_ids) != len(filenames) or len(set(document_ids)) != len(document_ids)):
            raise EnrollmentConflict('Provision the complete assigned document set before preparing an assessed run')
        artifact = await SearchSet.find_one({'uuid': artifact_id, 'user_id': operation.user_id})
        if artifact is None:
            raise EnrollmentConflict('The selected extraction must be owned by this learner')
        items = await SearchSetItem.find({'searchset': artifact_id}).sort('_id').to_list()
        fields = [item for item in items if item.searchtype == 'extraction' and item.searchphrase.strip()]
        if not fields or any(item.user_id not in (None, operation.user_id) for item in fields):
            raise EnrollmentConflict('The selected extraction has no valid owned fields')
        artifact_state = artifact.model_dump(mode='json')
        item_states = [item.model_dump(mode='json') for item in items]
        documents = []
        for document_id, filename in zip(document_ids, filenames):
            document = await owned_source(operation.user_id, document_id)
            if document is None or document.folder != progress.lab_folder_id or not progress.lab_folder_id:
                raise EnrollmentConflict('An assigned document is missing, inaccessible or outside this enrollment’s lab')
            if (document.processing or not document.valid or document.text_layer_rejected or not document.raw_text.strip()
                    or document.task_status == 'error' or document.ingestion_warnings or document.unread_pages):
                raise EnrollmentConflict('Finish and inspect document ingestion before preparing an assessed run')
            before = document.model_dump(mode='json')
            expected_hash = package.manifest.artifacts['documents/' + filename]
            try:
                actual_hash = hashlib.sha256(await storage.read(document.path)).hexdigest()
            except (OSError, ValueError) as exc:
                raise EnrollmentConflict('An assigned source file could not be verified') from exc
            if actual_hash != expected_hash:
                raise EnrollmentConflict('An assigned document’s bytes differ from this course’s source; matching filenames do not establish evidence')
            current = await owned_source(operation.user_id, document_id)
            if current is None or current.model_dump(mode='json') != before:
                raise EnrollmentConflict('An assigned document changed during preparation; review it again')
            documents.append({
                'document_id': document.uuid, 'assigned_filename': filename, 'title': document.title,
                'source_sha256': actual_hash, 'text_sha256': hashlib.sha256(document.raw_text.encode()).hexdigest(),
                'text': document.raw_text, 'text_markers': document.text_markers,
                'text_origin': 'workspace ingestion text captured at preparation; source bytes verified against course asset',
            })
        current_artifact = await SearchSet.find_one({'uuid': artifact_id, 'user_id': operation.user_id})
        current_items = await SearchSetItem.find({'searchset': artifact_id}).sort('_id').to_list()
        if (current_artifact is None or current_artifact.model_dump(mode='json') != artifact_state
                or [item.model_dump(mode='json') for item in current_items] != item_states):
            raise EnrollmentConflict('The extraction changed during preparation; review its current revision')
        artifact_snapshot = {key: artifact_state[key] for key in (
            'uuid', 'title', 'set_type', 'domain', 'extraction_config', 'extraction_config_override', 'cross_field_rules', 'item_order',
        )}
        artifact_snapshot['fields'] = [item.model_dump(mode='json', include={
            'id', 'searchphrase', 'searchtype', 'title', 'is_optional', 'enum_values', 'text_blocks', 'pdf_binding',
        }) for item in fields]
        payload = {**identity, 'schema_version': 1, 'rubric_id': package.manifest.rubric_id,
                   'exercise_sha256': package.manifest.artifacts['exercises.json'],
                   'artifact': artifact_snapshot, 'artifact_sha256': encode(artifact_snapshot)[1], 'documents': documents,
                   'lab_folder_id': progress.lab_folder_id,
                   'captured_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                   'execution_status': 'not_started', 'learner_decisions': [], 'outcomes_awarded': []}
        serialized, digest = encode(payload)
        if len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
            raise EnrollmentConflict('Lab inputs exceed the immutable snapshot size limit')
        await self._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': request_id})
            if existing is None or any(existing.get(key) != value for key, value in identity.items()):
                raise EnrollmentConflict('Lab request identity was claimed by another operation')
            return self.decode(existing)
        return payload

    @staticmethod
    async def _check_lease(lease):
        if await CertificationProgress.get_motor_collection().find_one(lease.progress_filter(), {'_id': 1}) is None:
            raise EnrollmentConflict('Lab preparation no longer owns the enrollment write boundary')
