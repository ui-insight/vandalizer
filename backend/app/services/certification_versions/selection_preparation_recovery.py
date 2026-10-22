"""Fence uncommitted course-selection preparation without restarting any work.

Only the two selection operations carry a validated original request in their
write marker. Generic assessment, workspace and review operations are excluded.
The replacement marker is claimed before fencing progress, preventing a late
selection CAS. The recovery journal commits before the marker is released.
"""
import datetime
import json
import re
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationSelectionPreparationRecovery
from .attempts import AttemptRepository, encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .saved_course_selection import SavedCourseSelectionRepository, SavedCourseSelectionRequest
from .upgrade_activation import UpgradeActivationRepository, UpgradeActivationRequest
from .writes import closed_fence


def plain(value):
    return json.loads(json.dumps(value, default=str))


class PreparationRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['stop_uncommitted_course_preparation_preserving_all_work']


class SelectionPreparationRecovery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    @property
    def records(self):
        return CertificationSelectionPreparationRecovery.get_motor_collection()

    async def inspect(self, user_id):
        selection = await self.repository.selections.find_one({'user_id': user_id})
        marker = (selection or {}).get('active_write') or {}
        if (not selection or selection.get('in_flight_writes') != 1 or selection.get('pending_transition_id')
                or marker.get('operation') not in ('activate_optional_upgrade', 'select_saved_course')
                or not re.fullmatch(r'[a-f0-9]{32}', str(marker.get('id', '')))):
            raise EnrollmentConflict('Only an original uncommitted course-selection preparation can be stopped here')
        source_id = await self.original_source(user_id, marker)
        source = await self.repository._enrollment(user_id, source_id)
        if (selection['active_enrollment_id'] != source_id or marker.get('enrollment_id') != source_id
                or marker.get('course_version') != source.course_version or marker.get('manifest_sha256') != source.manifest_sha256):
            raise EnrollmentConflict('The preparation no longer matches its original selected course')
        progress = await self.repository.progress.find_one({'_id': ObjectId(source.progress_id), 'user_id': user_id})
        allowed = (marker.get('previous_fence'), marker['id'], closed_fence(marker['id']))
        if progress is None or progress.get('_certification_write_fence') not in allowed:
            raise EnrollmentConflict('The original progress fence changed; this preparation cannot release it')
        if await self.repository.selections.find_one({'user_id': user_id}) != selection:
            raise EnrollmentConflict('The course operation changed during recovery review')
        snapshot = {'schema_version': 1, 'user_id': user_id, 'selection': plain(selection),
                    'progress_id': source.progress_id, 'progress_fence': progress.get('_certification_write_fence')}
        return snapshot

    async def original_source(self, user_id, marker):
        try:
            if marker['operation'] == 'activate_optional_upgrade':
                request = UpgradeActivationRequest.model_validate(marker['selection_request'])
                service = UpgradeActivationRepository(self.repository)
                decision = await service.decisions.get(user_id, request.decision_id)
                if decision is None:
                    raise EnrollmentConflict('The original preservation choice is unavailable')
                source_id = decision.request.source_enrollment_id
            else:
                request = SavedCourseSelectionRequest.model_validate(marker['selection_request'])
                service = SavedCourseSelectionRepository(self.repository)
                source_id, _ = await service.pair(user_id, request.activation_id, request.action)
            original = await service.owned(user_id, request)
            if original and original['state'] == 'applied':
                raise EnrollmentConflict('This selection already committed; confirm its original saved receipt')
            return source_id
        except (KeyError, TypeError, ValueError) as exc:
            raise EnrollmentConflict('The preparation does not contain a valid owned selection request') from exc

    async def preview(self, user_id):
        first = await self.inspect(user_id)
        if await self.inspect(user_id) != first:
            raise EnrollmentConflict('The preparation changed; refresh its recovery review')
        marker = first['selection']['active_write']
        return {'read_only': True, 'selection_changed': False, 'credit_changed': False,
                'enrollment_id': first['selection']['active_enrollment_id'], 'course_version': marker['course_version'],
                'original_request_id': marker['selection_request']['request_id'], 'write_id': marker['id'],
                'operation': marker['operation'], 'preview_sha256': encode(first)[1]}

    async def delivery_status(self, user_id, selection):
        marker = selection.get('active_write') or {}
        if marker.get('operation') == 'recover_selection_preparation':
            raw = await self.records.find_one({'uuid': marker.get('recovery_id'), 'user_id': user_id})
            if raw is None:
                raise EnrollmentConflict('The original preparation recovery is unavailable')
            intent = self.decode(raw)
            if await self.repository.selections.find_one(self.query(raw, intent)) != selection:
                raise EnrollmentConflict('The preparation recovery changed during review')
            original = intent['snapshot']['selection']['active_write']
            result = {'read_only': True, 'selection_changed': False, 'credit_changed': False,
                'enrollment_id': intent['snapshot']['selection']['active_enrollment_id'],
                'course_version': original['course_version'], 'original_request_id': original['selection_request']['request_id'],
                'write_id': original['id'], 'operation': original['operation'],
                'preview_sha256': intent['request']['preview_sha256'], 'request_id': raw['uuid'], 'state': 'recovery_pending'}
        elif marker.get('operation') in ('activate_optional_upgrade', 'select_saved_course'):
            result = await self.preview(user_id)
            # The same reviewed snapshot has the same request across devices.
            # No browser storage is needed to recover a lost insertion reply.
            result.update(state='preparing', request_id=uuid5(NAMESPACE_URL,
                'vandalizer:certification:stop-preparation:' + user_id + ':' + result['preview_sha256']).hex)
        else:
            return None
        if await self.repository.selections.find_one({'user_id': user_id}) != selection:
            raise EnrollmentConflict('The course preparation changed during status review')
        return result

    @staticmethod
    def decode(raw):
        try:
            intent = AttemptRepository.payload(raw, 'record')
            request = PreparationRecoveryRequest.model_validate(intent['request'])
            snapshot = intent['snapshot']
            marker = snapshot['selection']['active_write']
            if (raw['user_id'] != snapshot['user_id'] or raw['uuid'] != request.request_id
                    or request.preview_sha256 != encode(snapshot)[1] or snapshot['schema_version'] != 1
                    or snapshot['selection']['user_id'] != raw['user_id']
                    or marker['operation'] not in ('activate_optional_upgrade', 'select_saved_course')
                    or marker['enrollment_id'] != snapshot['selection']['active_enrollment_id']
                    or snapshot['selection'].get('pending_transition_id')
                    or snapshot['selection']['in_flight_writes'] != 1
                    or type(snapshot['selection']['revision']) is not int or snapshot['selection']['revision'] < 0
                    or not re.fullmatch(r'[a-f0-9]{32}', marker['id'])
                    or not re.fullmatch(r'[a-f0-9]{24}', snapshot['progress_id'])
                    or snapshot['progress_fence'] not in (marker.get('previous_fence'), marker['id'], closed_fence(marker['id']))
                    or raw['state'] not in ('prepared', 'applied')):
                raise ValueError('Recovery identity changed')
            if marker['operation'] == 'activate_optional_upgrade':
                UpgradeActivationRequest.model_validate(marker['selection_request'])
            else:
                SavedCourseSelectionRequest.model_validate(marker['selection_request'])
            datetime.datetime.fromisoformat(intent['requested_at'])
            if raw['state'] == 'applied':
                if AttemptRepository.payload(raw, 'result') != SelectionPreparationRecovery.result(raw, intent):
                    raise ValueError('Recovery result changed')
            elif raw.get('result_json') is not None or raw.get('result_sha256') is not None:
                raise ValueError('Unconfirmed recovery contains an applied result')
            return intent
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The preparation recovery record failed integrity verification') from exc

    @staticmethod
    def result(raw, intent):
        selection = intent['snapshot']['selection']
        marker = selection['active_write']
        return {'kind': 'selection_preparation_recovery.1', 'recovery_id': raw['uuid'],
                'intent_sha256': raw['record_sha256'], 'enrollment_id': selection['active_enrollment_id'],
                'course_version': marker['course_version'], 'original_request_id': marker['selection_request']['request_id'],
                'original_write_id': marker['id'], 'selection_revision': selection['revision'],
                'requested_at': intent['requested_at'], 'status': 'preparation_stopped',
                'selection_changed': False, 'credit_changed': False, 'assessments_repeated': False}

    @staticmethod
    def marker(raw, intent):
        snapshot = intent['snapshot']
        original = snapshot['selection']['active_write']
        return {'id': raw['uuid'], 'operation': 'recover_selection_preparation', 'recovery_id': raw['uuid'],
                'enrollment_id': snapshot['selection']['active_enrollment_id'], 'original_write_id': original['id'],
                'original_marker_sha256': encode(original)[1]}

    def query(self, raw, intent):
        selection = intent['snapshot']['selection']
        return {'user_id': raw['user_id'], 'active_enrollment_id': selection['active_enrollment_id'],
                'revision': selection['revision'], 'in_flight_writes': 1, 'pending_transition_id': None,
                'active_write': self.marker(raw, intent)}

    async def clear(self, raw, intent):
        await self.repository.selections.update_one(self.query(raw, intent),
            {'$set': {'in_flight_writes': 0}, '$unset': {'active_write': ''}})

    async def recover(self, user_id, body):
        request = PreparationRecoveryRequest.model_validate(body)
        raw = await self.records.find_one({'uuid': request.request_id})
        if raw is None:
            snapshot = await self.inspect(user_id)
            if encode(snapshot)[1] != request.preview_sha256:
                raise EnrollmentConflict('The preparation changed after review; refresh before stopping it')
            payload, digest = encode({'request': request.model_dump(mode='json'), 'snapshot': snapshot,
                'requested_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
            seed = CertificationSelectionPreparationRecovery(uuid=request.request_id, user_id=user_id,
                record_json=payload, record_sha256=digest).model_dump(mode='python', exclude={'id'})
            try:
                await self.records.insert_one(seed)
            except DuplicateKeyError:
                pass
            raw = await self.records.find_one({'uuid': request.request_id})
        if raw is None or raw['user_id'] != user_id:
            raise EnrollmentConflict('The preparation recovery request is unavailable')
        intent = self.decode(raw)
        if intent['request'] != request.model_dump(mode='json'):
            raise EnrollmentConflict('This request already records another preparation recovery')
        if raw['state'] == 'applied':
            await self.clear(raw, intent)
            return AttemptRepository.payload(raw, 'result')
        original_marker = intent['snapshot']['selection']['active_write']
        source_id = await self.original_source(user_id, original_marker)
        source = await self.repository._enrollment(user_id, source_id)
        if (source_id != intent['snapshot']['selection']['active_enrollment_id']
                or source.progress_id != intent['snapshot']['progress_id']
                or source.course_version != original_marker['course_version']
                or source.manifest_sha256 != original_marker['manifest_sha256']):
            raise CourseCatalogError('Recovery must retain its original source enrollment and progress identity')
        selection = await self.repository.selections.find_one({'user_id': user_id})
        expected = intent['snapshot']['selection']
        if plain(selection) == expected:
            # Claim selection first. A late original worker's commit and cleanup
            # require its old marker ID and cannot affect the replacement.
            selected = await self.repository.selections.find_one_and_update({
                'user_id': user_id, 'active_enrollment_id': expected['active_enrollment_id'],
                'revision': expected['revision'], 'in_flight_writes': 1, 'pending_transition_id': None,
                'active_write': selection['active_write']},
                {'$set': {'active_write': self.marker(raw, intent)}}, return_document=ReturnDocument.AFTER)
            if selected is None:
                raise EnrollmentConflict('The selection changed before preparation could be stopped')
        elif await self.repository.selections.find_one(self.query(raw, intent)) is None:
            # A concurrent recovery may already have finished. Its immutable
            # receipt can be replayed, but no newer worker can be cleared.
            latest = await self.records.find_one({'uuid': raw['uuid'], 'user_id': user_id})
            if latest and latest['state'] == 'applied':
                self.decode(latest)
                await self.clear(latest, intent)
                return AttemptRepository.payload(latest, 'result')
            raise EnrollmentConflict('The original selection changed; keep its committed result or active worker')
        return await self.finish(raw, intent)

    async def finish(self, raw, intent):
        snapshot = intent['snapshot']
        marker = snapshot['selection']['active_write']
        if await self.repository.selections.find_one(self.query(raw, intent)) is None:
            raise EnrollmentConflict('Recovery no longer owns the original selection preparation')
        # Include the pre-acquisition and pre-CAS closed fence. Once changed,
        # neither a delayed acquisition nor the old finally block can revive it.
        changed = await self.repository.progress.update_one({'_id': ObjectId(snapshot['progress_id']), 'user_id': raw['user_id'],
            '_certification_write_fence': {'$in': [marker.get('previous_fence'), marker['id'], closed_fence(marker['id']), closed_fence(raw['uuid'])]}},
            {'$set': {'_certification_write_fence': closed_fence(raw['uuid'])}})
        if changed.matched_count != 1 or await self.repository.selections.find_one(self.query(raw, intent)) is None:
            raise EnrollmentConflict('The original recovery fence changed; no worker was released')
        result = self.result(raw, intent)
        payload, digest = encode(result)
        await self.records.update_one({'uuid': raw['uuid'], 'user_id': raw['user_id'], 'state': 'prepared', 'record_sha256': raw['record_sha256']},
            {'$set': {'state': 'applied', 'result_json': payload, 'result_sha256': digest}})
        saved = await self.records.find_one({'uuid': raw['uuid'], 'user_id': raw['user_id']})
        if saved is None or saved['state'] != 'applied':
            raise EnrollmentConflict('Confirm the original preparation recovery before continuing')
        self.decode(saved)
        await self.clear(saved, intent)
        return result
