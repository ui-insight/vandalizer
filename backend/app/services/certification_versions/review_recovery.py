"""Reconcile expired automatic-review workers without staff or repeated grading.

Only tool-free structured review is eligible. Execution, provisioning and earned
credit operations cannot use this recovery. A late provider result loses its CAS;
recovery does not claim the provider call was cancelled.
"""
import datetime
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId

from app.models.certification import CertificationEnrollmentSelection
from .attempts import encode
from .enrollments import EnrollmentConflict
from .writes import WriteLease, closed_fence

REVIEW_RECOVERY_SECONDS = 300
REVIEW_OPERATION = 'evaluate_automatic_review'


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def expired(value, now):
    if not isinstance(value, datetime.datetime):
        return False
    return value.replace(tzinfo=datetime.timezone.utc) <= now


async def bind_review_worker(saved, lease):
    selections = CertificationEnrollmentSelection.get_motor_collection()
    current = await selections.find_one(lease.selection_filter())
    marker = (current or {}).get('active_write') or {}
    if marker.get('operation') != REVIEW_OPERATION or marker.get('review_attempt_id') not in (None, saved['attempt_id']):
        raise EnrollmentConflict('Automatic grading requires its own review write boundary')
    if marker.get('review_record_sha256') is not None:
        if marker['review_record_sha256'] != saved['record_sha256']:
            raise EnrollmentConflict('The review write already belongs to different evidence')
        return {key: marker[key] for key in ('review_started_at', 'review_deadline_at')}
    started = utc_now()
    timing = {'review_started_at': started, 'review_deadline_at': started + datetime.timedelta(seconds=REVIEW_RECOVERY_SECONDS)}
    changed = await selections.update_one({**lease.selection_filter(), 'active_write': marker},
        {'$set': {'active_write.review_attempt_id': saved['attempt_id'],
                  'active_write.review_record_sha256': saved['record_sha256'],
                  **{'active_write.' + key: value for key, value in timing.items()}}})
    if changed.modified_count != 1:
        raise EnrollmentConflict('The grading write changed before dispatch')
    return timing


class ReviewRecovery:
    def __init__(self, repository):
        self.repository = repository

    async def reconcile(self, user_id, enrollment_id, attempt_id):
        from .review_attempts import ReviewAttemptRepository
        repo, reviews = self.repository, ReviewAttemptRepository()
        enrollment = await repo._enrollment(user_id, enrollment_id)
        raw = await reviews.records.find_one({'uuid': attempt_id, 'user_id': user_id, 'enrollment_id': enrollment_id})
        if raw is None:
            raise EnrollmentConflict('This saved review is unavailable for the selected learner and course')
        saved = reviews.decode(raw)
        if (saved['record']['course_version'] != enrollment.course_version
                or saved['record']['manifest_sha256'] != enrollment.manifest_sha256):
            raise EnrollmentConflict('The saved review belongs to different course requirements')
        selection = await repo.selections.find_one({'user_id': user_id, 'active_enrollment_id': enrollment_id})
        if selection is None:
            raise EnrollmentConflict('Review recovery requires the selected enrollment')
        marker = selection.get('active_write') or {}
        now = utc_now()
        recovering = marker.get('operation') == 'recover_automatic_review' and marker.get('review_attempt_id') == attempt_id
        owns_boundary = marker.get('review_attempt_id') == attempt_id and marker.get('operation') == REVIEW_OPERATION
        if owns_boundary:
            deadline = marker.get('review_deadline_at')
            if deadline is None and isinstance(marker.get('started_at'), datetime.datetime):
                deadline = marker['started_at'] + datetime.timedelta(seconds=REVIEW_RECOVERY_SECONDS)
            if not expired(deadline, now):
                return saved
            if (marker.get('review_record_sha256') not in (None, saved['record_sha256'])
                    or marker.get('course_version') != enrollment.course_version
                    or marker.get('manifest_sha256') != enrollment.manifest_sha256
                    or marker.get('enrollment_id') != enrollment_id or 'previous_fence' not in marker
                    or (raw['state'] == 'evaluating' and raw.get('worker_id') != marker['id'])):
                raise EnrollmentConflict('The expired grading boundary does not match its saved review')
            recovery_id = uuid5(NAMESPACE_URL, 'vandalizer:automatic-review-recovery:' + marker['id']).hex
            replacement = {**marker, 'id': recovery_id, 'original_write_id': marker['id'],
                           'operation': 'recover_automatic_review', 'recovered_at': now.isoformat()}
            changed = await repo.selections.update_one({'user_id': user_id, 'active_enrollment_id': enrollment_id,
                'revision': selection['revision'], 'in_flight_writes': 1, 'active_write': marker},
                {'$set': {'active_write': replacement}})
            if changed.modified_count != 1:
                # Normal cleanup or another recovery won. Re-read, never erase a later writer.
                return await reviews.get(user_id, attempt_id)
            marker, recovering = replacement, True
        if recovering:
            original = marker['original_write_id']
            recovery_lease = WriteLease(user_id, enrollment_id, enrollment.progress_id, marker['id'])
            fenced = await repo.progress.update_one({'_id': ObjectId(enrollment.progress_id), 'user_id': user_id,
                '_certification_write_fence': {'$in': [marker['previous_fence'], original, closed_fence(original),
                                                       marker['id'], closed_fence(marker['id'])]}},
                {'$set': {'_certification_write_fence': marker['id']}})
            if fenced.matched_count != 1:
                latest = await repo.selections.find_one({'user_id': user_id, 'active_enrollment_id': enrollment_id})
                if ((latest or {}).get('last_automatic_review_recovery') or {}).get('recovery_id') == marker['id']:
                    return await reviews.get(user_id, attempt_id)
                raise EnrollmentConflict('Progress ownership changed during automatic review recovery')
            await self._finish_interrupted(reviews, raw, now, original)
            receipt = {'attempt_id': attempt_id, 'original_write_id': original, 'recovery_id': marker['id'],
                       'recovered_at': marker['recovered_at'], 'staff_review_required': False}
            await repo.progress.update_one(recovery_lease.progress_filter(),
                {'$set': {'_certification_write_fence': closed_fence(marker['id'])}})
            await repo.selections.update_one(recovery_lease.selection_filter(),
                {'$set': {'in_flight_writes': 0, 'last_automatic_review_recovery': receipt}, '$unset': {'active_write': ''}})
        elif raw['state'] == 'evaluating' and expired(raw.get('review_deadline_at'), now):
            # Normal finally cleanup may already have released the boundary.
            # A different active writer is never revoked by this record-only path.
            if marker.get('id') == raw.get('worker_id'):
                raise EnrollmentConflict('This grading worker has no recognized recoverable boundary')
            await self._finish_interrupted(reviews, raw, now, raw['worker_id'])
        return await reviews.get(user_id, attempt_id)

    @staticmethod
    async def _finish_interrupted(reviews, raw, now, original_worker):
        saved = reviews.decode(raw)
        if saved['state'] not in ('prepared', 'evaluating'):
            return  # A terminal result racing recovery always wins.
        assessment = reviews.with_saved_checks(saved, reviews._unavailable('review_interrupted'))
        result = {'attempt_id': saved['attempt_id'], 'record_sha256': saved['record_sha256'],
                  'assessment': assessment,
                  'started_at': (raw.get('review_started_at') or now).replace(tzinfo=datetime.timezone.utc).isoformat(),
                  'finished_at': now.isoformat(), 'recovery': {'original_worker_id': original_worker,
                    'provider_cancellation_confirmed': False, 'method': 'automatic_review_reconciliation.1'}}
        serialized, digest = encode(result)
        query = {'uuid': saved['attempt_id'], 'record_sha256': saved['record_sha256'],
                 '$or': [{'state': 'prepared', 'worker_id': None}, {'state': 'evaluating', 'worker_id': original_worker}]}
        await reviews.records.update_one(query,
            {'$set': {'state': 'unavailable', 'result_json': serialized, 'result_sha256': digest}})
