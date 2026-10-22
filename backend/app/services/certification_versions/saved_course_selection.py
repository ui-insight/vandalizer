"""Internal reviewed rollback/resume preserving both existing enrollments.

Returning never copies old credit over new work, creates a replacement target,
revokes a credential or replays an assessment. Public delivery remains gated.
"""
from copy import deepcopy
import datetime
import hashlib
import json
from typing import Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationSavedCourseSelection
from .attempts import AttemptRepository, encode
from .catalog import CourseCatalogError
from .credentials import CredentialRepository
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .grading import load_rubric
from .selection_journal import SelectionJournal
from .transition_preview import fingerprint, without_owned_write
from .transition_records import TransitionRecordReconciliation
from .upgrade_activation import UpgradeActivationRepository
from .writes import closed_fence, require_lease


Action = Literal['return_to_original_course', 'resume_upgraded_course']


class SavedCourseSelectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    activation_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    action: Action
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['select_saved_course_preserving_both_histories_and_credit']


class SavedCourseSelectionRepository(SelectionJournal):
    receipt_id_field = 'selection_id'

    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.activations = UpgradeActivationRepository(self.repository)
        self.work = TransitionRecordReconciliation(self.repository)

    @property
    def records(self):
        return CertificationSavedCourseSelection.get_motor_collection()

    async def pair(self, user_id, activation_id, action):
        if action not in ('return_to_original_course', 'resume_upgraded_course'):
            raise EnrollmentConflict('Choose whether to return to the original course or resume the saved upgrade')
        raw = await self.activations.records.find_one({'uuid': activation_id, 'user_id': user_id})
        if raw is None:
            raise EnrollmentConflict('The original course upgrade is unavailable')
        self.activations.decode(raw)
        if raw['state'] != 'applied':
            raise EnrollmentConflict('Confirm the original upgrade receipt before choosing another saved course')
        result = AttemptRepository.payload(raw, 'result')
        original, upgraded = result['source_enrollment_id'], result['target_enrollment_id']
        return (upgraded, original) if action == 'return_to_original_course' else (original, upgraded)

    async def collect(self, user_id, source_id, target_id, *, held=False):
        repo = self.repository
        selection = await repo.selections.find_one({'user_id': user_id})
        if (not selection or selection['active_enrollment_id'] != source_id
                or selection.get('pending_transition_id')):
            raise EnrollmentConflict('The selected course changed or an earlier switch still needs confirmation')
        state, summaries = {'selection': selection}, {}
        for label, enrollment_id in (('source', source_id), ('target', target_id)):
            enrollment = await repo._enrollment(user_id, enrollment_id)
            package = repo.catalog.load(enrollment.course_version)
            if package.manifest_sha256 != enrollment.manifest_sha256:
                raise CourseCatalogError('The saved course no longer matches its original requirements')
            if label == 'target':
                if enrollment.state not in ('active', 'completed') or package.entry.state == 'draft' or not package.entry.supported_for_existing:
                    raise EnrollmentConflict('The saved destination course is no longer supported for continued learning')
                load_rubric(package)
            raw = await repo.progress.find_one({'_id': ObjectId(enrollment.progress_id), 'user_id': user_id})
            progress = await repo.read_progress(user_id, enrollment_id)
            credential = await CredentialRepository().for_enrollment(user_id, enrollment_id)
            if progress.pending_credential or (progress.certified and credential is None):
                raise EnrollmentConflict('Preserve both original credentials before changing the selected course')
            inventory = await self.work.inventory(user_id, enrollment_id)
            self.work.verify_inventory(inventory, enrollment, package)
            if label == 'source' and held:
                state['selection'], raw = without_owned_write(selection, raw, user_id, source_id)
            state[label] = {'enrollment': enrollment.model_dump(mode='json'), 'progress': raw,
                            'records_sha256': fingerprint(inventory),
                            'credential': credential.model_dump(mode='json') if credential else None,
                            'supported': package.entry.supported_for_existing, 'release_state': package.entry.state}
            summaries[label] = {'enrollment_id': enrollment_id, 'course_version': enrollment.course_version,
                'course_title': package.manifest.title, 'manifest_sha256': package.manifest_sha256,
                'total_xp': progress.total_xp, 'completed_modules': sum(isinstance(value, dict) and value.get('completed') is True for value in progress.modules.values()),
                'credential_id': credential.credential_id if credential else None,
                'has_saved_place': progress.learning_position is not None,
                'record_counts': {kind: len(rows) for kind, rows in inventory.items()}}
        if state['selection'].get('in_flight_writes'):
            raise EnrollmentConflict('Finish or reconcile the current course operation before choosing a saved course')
        return state, summaries

    async def preview(self, user_id, activation_id, action, *, _held=False):
        source_id, target_id = await self.pair(user_id, activation_id, action)
        before, summaries = await self.collect(user_id, source_id, target_id, held=_held)
        after, current = await self.collect(user_id, source_id, target_id, held=_held)
        if fingerprint(before) != fingerprint(after) or summaries != current:
            raise EnrollmentConflict('Saved course work changed during review; refresh the preservation preview')
        stable = deepcopy(before)
        stable['selection'].pop('active_write', None)
        for label in ('source', 'target'):
            stable[label]['progress'].pop('_certification_write_fence', None)
        result = {'schema_version': 1, 'activation_id': activation_id, 'action': action,
                  'read_only': True, 'can_activate': False, 'credit_transferred': False,
                  'selection_revision': before['selection']['revision'], **summaries,
                  'preservation_policy': 'keep_both_existing_enrollments_and_original_workspace_references',
                  'state_sha256': fingerprint(stable)}
        return {**result, 'preview_sha256': encode(result)[1]}

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Saved course choice changed')
            intent = json.loads(raw['record_json'])
            request = SavedCourseSelectionRequest.model_validate(intent['request'])
            preview = intent['preview']
            if (intent['schema_version'] != 1 or intent['user_id'] != raw['user_id'] or request.request_id != raw['uuid']
                    or request.activation_id != preview['activation_id'] or request.action != preview['action']
                    or request.preview_sha256 != preview['preview_sha256']
                    or encode({key: value for key, value in preview.items() if key != 'preview_sha256'})[1] != request.preview_sha256
                    or preview['credit_transferred'] is not False or preview['read_only'] is not True
                    or preview['preservation_policy'] != 'keep_both_existing_enrollments_and_original_workspace_references'
                    or raw['state'] not in ('prepared', 'applied')):
                raise ValueError('Saved course choice identity changed')
            datetime.datetime.fromisoformat(intent['prepared_at'])
            if raw['state'] == 'applied':
                SavedCourseSelectionRepository.verify_receipt(raw, AttemptRepository.payload(raw, 'result'))
            elif raw.get('result_json') is not None or raw.get('result_sha256') is not None:
                raise ValueError('An unconfirmed choice contains an applied receipt')
            return intent
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved course-selection intent failed integrity verification') from exc

    @staticmethod
    def verify_receipt(raw, result):
        intent = json.loads(raw['record_json'])
        preview = intent['preview']
        expected = {'kind': 'saved_course_selection.1', 'selection_id': raw['uuid'],
                    'intent_sha256': raw['record_sha256'], 'activation_id': preview['activation_id'],
                    'action': preview['action'], 'source_enrollment_id': preview['source']['enrollment_id'],
                    'target_enrollment_id': preview['target']['enrollment_id'],
                    'target_course_version': preview['target']['course_version'],
                    'target_manifest_sha256': preview['target']['manifest_sha256'],
                    'previous_revision': preview['selection_revision'], 'revision': preview['selection_revision'] + 1,
                    'status': 'applied', 'credit_transferred': False, 'both_histories_preserved': True}
        if (any(result.get(key) != value for key, value in expected.items()) or result.get('credit_transferred') is not False
                or result.get('both_histories_preserved') is not True
                or encode({key: value for key, value in result.items() if key != 'receipt_sha256'})[1] != result.get('receipt_sha256')):
            raise CourseCatalogError('The saved return/resume receipt differs from its original choice')
        datetime.datetime.fromisoformat(result['selected_at'])
        return result

    async def owned(self, user_id, request):
        raw = await self.records.find_one({'uuid': request.request_id})
        if raw is None:
            return None
        if raw['user_id'] != user_id:
            raise EnrollmentConflict('The saved course-selection request is unavailable')
        if self.decode(raw)['request'] != request.model_dump(mode='json'):
            raise EnrollmentConflict('This request already belongs to a different saved-course choice')
        return raw

    async def select(self, user_id, body):
        request = SavedCourseSelectionRequest.model_validate(body)
        existing = await self.owned(user_id, request)
        if existing:
            result = await self.resume_receipt(existing)
            if result is not None:
                return result
        source_id, _ = await self.pair(user_id, request.activation_id, request.action)
        async with self.repository.write_boundary(user_id, source_id, operation='select_saved_course',
                selection_request=request.model_dump(mode='json')):
            preview = await self.preview(user_id, request.activation_id, request.action, _held=True)
            if preview['preview_sha256'] != request.preview_sha256:
                raise EnrollmentConflict('Work changed after review; confirm a fresh saved-course preservation preview')
            if existing:
                if self.decode(existing)['preview'] != preview:
                    raise EnrollmentConflict('The original saved-course choice no longer matches current work')
                raw = existing
            else:
                payload, digest = encode({'schema_version': 1, 'user_id': user_id, 'request': request.model_dump(mode='json'),
                    'preview': preview, 'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
                seed = CertificationSavedCourseSelection(uuid=request.request_id, user_id=user_id,
                    record_json=payload, record_sha256=digest).model_dump(mode='python', exclude={'id'})
                try:
                    await self.records.insert_one(seed)
                except DuplicateKeyError:
                    pass
                raw = await self.owned(user_id, request)
                if raw is None:
                    raise EnrollmentConflict('The original saved-course selection intent could not be confirmed')
            return await self.commit(raw)

    async def commit(self, raw):
        intent = self.decode(raw)
        original = intent['preview']
        user_id = raw['user_id']
        source_id = original['source']['enrollment_id']
        lease = require_lease(user_id, source_id)
        current = await self.preview(user_id, original['activation_id'], original['action'], _held=True)
        if current != original:
            raise EnrollmentConflict('Course work or support changed before selection; keep both original histories')
        changed = await self.repository.progress.update_one(lease.progress_filter(),
            {'$set': {'_certification_write_fence': closed_fence(lease.write_id)}})
        if changed.matched_count != 1:
            raise EnrollmentConflict('The current course write boundary changed before selection')
        result = {'kind': 'saved_course_selection.1', 'selection_id': raw['uuid'], 'intent_sha256': raw['record_sha256'],
            'activation_id': original['activation_id'], 'action': original['action'], 'source_enrollment_id': source_id,
            'target_enrollment_id': original['target']['enrollment_id'], 'target_course_version': original['target']['course_version'],
            'target_manifest_sha256': original['target']['manifest_sha256'], 'previous_revision': original['selection_revision'],
            'revision': original['selection_revision'] + 1, 'status': 'applied', 'credit_transferred': False,
            'both_histories_preserved': True, 'selected_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        result['receipt_sha256'] = encode(result)[1]
        selected = await self.repository.selections.find_one_and_update(
            {**lease.selection_filter(), 'revision': original['selection_revision'], 'pending_transition_id': None},
            {'$set': {'active_enrollment_id': result['target_enrollment_id'], 'last_transition': result,
                      'pending_transition_id': raw['uuid'], 'in_flight_writes': 0},
             '$unset': {'active_write': ''}, '$inc': {'revision': 1}}, return_document=ReturnDocument.AFTER)
        if selected is None:
            raise EnrollmentConflict('The selected course changed before the return/resume choice could commit')
        return await self.finalize(raw, result)
