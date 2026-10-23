"""Internal, restartable zero-credit selection commit. No HTTP surface.

Only the selected enrollment reference changes. Original progress, credentials,
workspace files and jobs retain their identities and owners. Certification
workers must be settled under the source guard; independent workspace activity
is neither transferred nor dispatched/cancelled by a course selection.
"""
import datetime
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationUpgradeActivation
from .attempts import AttemptRepository, encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .grading import selected_outcome_completion_available
from .selection_journal import SelectionJournal
from .transition_preview import fingerprint
from .upgrade_decisions import UpgradeDecisionRepository
from .upgrade_targets import UpgradeTargetRepository, target_identity
from .writes import closed_fence, require_lease


class UpgradeActivationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    decision_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    consent: Literal['activate_optional_upgrade_preserving_original_work_without_credit_transfer']


class UpgradeActivationRepository(SelectionJournal):
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.decisions = UpgradeDecisionRepository(self.repository)
        self.targets = UpgradeTargetRepository(self.repository)

    @property
    def records(self):
        return CertificationUpgradeActivation.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Changed activation intent')
            intent = json.loads(raw['record_json'])
            request = UpgradeActivationRequest.model_validate(intent['request'])
            target_id, _ = target_identity(request.decision_id)
            target = intent['target']
            if (intent['schema_version'] != 1 or request.request_id != raw['uuid']
                    or request.decision_id != raw['decision_id'] or intent['user_id'] != raw['user_id']
                    or target['target_enrollment_id'] != target_id or target['decision_id'] != request.decision_id
                    or target['source_enrollment_id'] != intent['source_enrollment_id']
                    or target['prepared'] is not True or target['activated'] is not False
                    or target['credit_transferred'] is not False or target['target_xp'] != 0
                    or type(intent['selection_revision']) is not int or intent['selection_revision'] < 0
                    or intent['workspace_policy'] != 'retain_original_identity_without_dispatch_or_cancellation'
                    or raw['state'] not in ('prepared', 'applied')):
                raise ValueError('Changed activation identity or preservation policy')
            datetime.datetime.fromisoformat(intent['prepared_at'])
            if raw['state'] == 'applied':
                UpgradeActivationRepository.verify_receipt(raw, AttemptRepository.payload(raw, 'result'))
            elif raw.get('result_json') is not None or raw.get('result_sha256') is not None:
                raise ValueError('Unconfirmed activation contains an applied receipt')
            return intent
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The original course-switch intent needs integrity reconciliation') from exc

    @staticmethod
    def verify_receipt(raw, result):
        # Do not recursively call decode: applied journals verify their receipt
        # here after the intent envelope has been checked.
        intent = json.loads(raw['record_json'])
        target = intent['target']
        expected = {'kind': 'optional_upgrade_selection.1', 'activation_id': raw['uuid'],
                    'decision_id': raw['decision_id'], 'intent_sha256': raw['record_sha256'],
                    'source_enrollment_id': intent['source_enrollment_id'],
                    'target_enrollment_id': target['target_enrollment_id'],
                    'target_course_version': target['target_course_version'],
                    'target_manifest_sha256': target['target_manifest_sha256'],
                    'previous_revision': intent['selection_revision'], 'revision': intent['selection_revision'] + 1,
                    'status': 'applied', 'credit_transferred': False, 'source_history_preserved': True}
        if (any(result.get(key) != value for key, value in expected.items())
                or result.get('credit_transferred') is not False or result.get('source_history_preserved') is not True
                or encode({key: value for key, value in result.items() if key != 'receipt_sha256'})[1] != result.get('receipt_sha256')):
            raise CourseCatalogError('The saved selection receipt differs from its original intent')
        datetime.datetime.fromisoformat(result['selected_at'])
        return result

    async def owned(self, user_id, request):
        raw = await self.records.find_one({'uuid': request.request_id})
        if raw is None:
            return None
        if raw['user_id'] != user_id:
            raise EnrollmentConflict('The course-switch request is unavailable')
        intent = self.decode(raw)
        if intent['request'] != request.model_dump(mode='json'):
            raise EnrollmentConflict('This request already belongs to a different course-switch decision')
        return raw

    async def clear_pending(self, raw, result):
        # A staged course is not writable or active in history. Promote only
        # after the original selection and journal have both committed; retain
        # the pending marker until promotion succeeds. Old replay does not edit
        # later enrollment state or another selection.
        selected = await self.repository.selections.find_one({'user_id': raw['user_id'],
            'active_enrollment_id': result['target_enrollment_id'], 'revision': result['revision'],
            'pending_transition_id': raw['uuid'], 'in_flight_writes': 0, 'active_write': None})
        if selected is None:
            return
        if selected.get('last_transition') != result:
            raise CourseCatalogError('The pending upgrade differs from its original committed receipt')
        intent = self.decode(raw)
        target = await self.repository._enrollment(raw['user_id'], result['target_enrollment_id'])
        if target.state not in ('prepared', 'active'):
            raise EnrollmentConflict('The prepared course changed lifecycle before activation could be confirmed')
        # Preserve compatibility with an already-committed internal activation
        # from the earlier rehearsal, without converting unrelated history.
        expected = intent['target']['target_enrollment_sha256']
        prepared = target.model_copy(update={'state': 'prepared'})
        if fingerprint(prepared.model_dump(mode='json')) != expected:
            if target.state != 'active' or fingerprint(target.model_dump(mode='json')) != expected:
                raise CourseCatalogError('The original prepared enrollment identity changed')
        if target.state == 'prepared':
            changed = await self.repository.enrollments.update_one({'uuid': target.uuid, 'user_id': raw['user_id'],
                'state': 'prepared', 'course_version': target.course_version, 'manifest_sha256': target.manifest_sha256,
                'progress_id': target.progress_id, 'source_enrollment_id': target.source_enrollment_id,
                'created_at': target.created_at, 'provenance': target.provenance},
                {'$set': {'state': 'active'}})
            if changed.matched_count != 1:
                current = await self.repository._enrollment(raw['user_id'], target.uuid)
                if current.model_dump(mode='json') != target.model_copy(update={'state': 'active'}).model_dump(mode='json'):
                    raise EnrollmentConflict('The original prepared enrollment changed during confirmation')
        await super().clear_pending(raw, result)

    async def activate(self, user_id, body):
        request = UpgradeActivationRequest.model_validate(body)
        existing = await self.owned(user_id, request)
        if existing:
            recovered = await self.resume_receipt(existing)
            if recovered is not None:
                return recovered
        async with self.decisions.hold_reviewed_choice(user_id, request.decision_id,
                activation_request=request.model_dump(mode='json')) as (decision, progress, package):
            target = await self.targets.stage(decision, progress, package)
            lease = require_lease(user_id, decision.request.source_enrollment_id)
            selected = await self.repository.selections.find_one(lease.selection_filter())
            if selected is None:
                raise EnrollmentConflict('The reviewed selection boundary changed')
            intent = {'schema_version': 1, 'request': request.model_dump(mode='json'), 'user_id': user_id,
                      'source_enrollment_id': decision.request.source_enrollment_id,
                      'decision_sha256': encode(decision.model_dump(mode='json'))[1],
                      'selection_revision': selected['revision'], 'target': target,
                      'workspace_policy': 'retain_original_identity_without_dispatch_or_cancellation',
                      'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            if existing:
                original = self.decode(existing)
                if {k: v for k, v in original.items() if k != 'prepared_at'} != {k: v for k, v in intent.items() if k != 'prepared_at'}:
                    raise EnrollmentConflict('The saved switch intent no longer matches the reviewed source and target')
                raw = existing
            else:
                payload, digest = encode(intent)
                seed = CertificationUpgradeActivation(uuid=request.request_id, user_id=user_id, decision_id=request.decision_id,
                    record_json=payload, record_sha256=digest).model_dump(mode='python', exclude={'id'})
                try:
                    await self.records.insert_one(seed)
                except DuplicateKeyError:
                    pass
                raw = await self.owned(user_id, request)
                if raw is None:
                    raise EnrollmentConflict('This preservation choice already has another switch request; resume the original request')
            return await self.commit(raw, lease, package)

    async def commit(self, raw, lease, package):
        """Commit only while holding the revalidated original course boundary."""
        from .upgrade_comparison import UpgradeComparison
        intent = self.decode(raw)
        if require_lease(raw['user_id'], intent['source_enrollment_id']) != lease:
            raise EnrollmentConflict('The reviewed switch no longer owns its source boundary')
        source = await self.repository._enrollment(raw['user_id'], intent['source_enrollment_id'])
        offered, _ = UpgradeComparison(self.repository).target(source.course_version, package.manifest.release_id)
        if (offered.manifest_sha256 != intent['target']['target_manifest_sha256']
                or not selected_outcome_completion_available(offered)):
            raise EnrollmentConflict('The target changed before selection; review it again')
        target = intent['target']
        staged = await self.repository._enrollment(raw['user_id'], target['target_enrollment_id'])
        progress = await self.repository.read_progress(raw['user_id'], staged.uuid)
        if (fingerprint(staged.model_dump(mode='json')) != target['target_enrollment_sha256']
                or fingerprint(progress.model_dump(mode='json')) != target['target_progress_sha256']):
            raise EnrollmentConflict('The prepared target changed before selection; preserve its saved work')
        # Fence source writers BEFORE making the new selection visible. A
        # delayed worker cannot use a copied context after the switch.
        changed = await self.repository.progress.update_one(lease.progress_filter(),
            {'$set': {'_certification_write_fence': closed_fence(lease.write_id)}})
        if changed.matched_count != 1:
            raise EnrollmentConflict('The source write boundary changed before selection')
        result = {'kind': 'optional_upgrade_selection.1', 'activation_id': raw['uuid'],
                  'decision_id': raw['decision_id'], 'intent_sha256': raw['record_sha256'],
                  'source_enrollment_id': source.uuid, 'target_enrollment_id': target['target_enrollment_id'],
                  'target_course_version': target['target_course_version'], 'target_manifest_sha256': target['target_manifest_sha256'],
                  'previous_revision': intent['selection_revision'], 'revision': intent['selection_revision'] + 1,
                  'selected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': 'applied',
                  'credit_transferred': False, 'source_history_preserved': True}
        result['receipt_sha256'] = encode(result)[1]
        selection = await self.repository.selections.find_one_and_update(
            {**lease.selection_filter(), 'revision': intent['selection_revision'], 'pending_transition_id': None},
            {'$set': {'active_enrollment_id': target['target_enrollment_id'], 'last_transition': result,
                      'pending_transition_id': raw['uuid'], 'in_flight_writes': 0},
             '$unset': {'active_write': ''}, '$inc': {'revision': 1}}, return_document=ReturnDocument.AFTER)
        if selection is None:
            raise EnrollmentConflict('The selection changed; the original course-switch request was not committed')
        return await self.finalize(raw, result)
