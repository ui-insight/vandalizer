"""Explicit, restartable recovery of completion workers only.

No timeout or public recovery endpoint. The caller must review the exact active
write and selection revision. Provisioning and external jobs are not recoverable
here because revoking progress writes cannot undo their external side effects.
"""
import datetime
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .attempts import AttemptRepository, progress_digest
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .writes import WriteLease, closed_fence, lease_context, require_lease


COMPLETION_OPERATIONS = {'complete_module', 'complete_certification_module', 'reconcile_completion', 'apply_credit_transfer'}


class CompletionRecovery:
    def __init__(self, repository: EnrollmentRepository):
        self.repository = repository
        self.journal = AttemptRepository()

    async def recover_worker(self, user_id, enrollment_id, *, expected_write_id, expected_revision, reason):
        """Revoke one reviewed completion worker, then reconcile its journal.

        Failures retain the recovery marker. Repeat with the same write ID to
        finish; an old worker's finally block cannot release the new boundary.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise EnrollmentConflict('Record a reason for explicit assessment recovery')
        repo = self.repository
        enrollment = await repo._enrollment(user_id, enrollment_id)
        package = repo.catalog.load(enrollment.course_version)
        selection_filter = {'user_id': user_id, 'active_enrollment_id': enrollment_id, 'revision': expected_revision}
        selection = await repo.selections.find_one(selection_filter)
        if selection is None:
            raise EnrollmentConflict('The reviewed course selection changed')
        previous = selection.get('last_completion_recovery')
        if previous and previous.get('write_id') == expected_write_id:
            return previous
        marker = selection.get('active_write') or {}
        recovery_id = uuid5(NAMESPACE_URL, 'vandalizer:certification:recovery:' + expected_write_id).hex
        if marker.get('id') == expected_write_id:
            if marker.get('operation') not in COMPLETION_OPERATIONS or 'previous_fence' not in marker:
                raise EnrollmentConflict('This write is not a fenced completion; reconcile its side effects separately')
            if (marker.get('enrollment_id'), marker.get('course_version'), marker.get('manifest_sha256'), marker.get('rubric_id')) != (
                enrollment_id, enrollment.course_version, enrollment.manifest_sha256, package.manifest.rubric_id,
            ):
                raise EnrollmentConflict('The reviewed write does not match this enrollment')
            recovery_marker = {**marker, 'id': recovery_id, 'operation': 'recover_completion',
                'original_write_id': expected_write_id, 'recovery_reason': reason.strip(),
                'recovery_started_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat()}
            changed = await repo.selections.update_one(
                {**selection_filter, 'in_flight_writes': 1, 'active_write': marker},
                {'$set': {'active_write': recovery_marker}},
            )
            if changed.matched_count != 1:
                raise EnrollmentConflict('The reviewed write changed before recovery; inspect it again')
            marker = recovery_marker
        elif marker.get('id') != recovery_id or marker.get('original_write_id') != expected_write_id:
            raise EnrollmentConflict('The reviewed write is no longer active')

        lease = WriteLease(user_id, enrollment_id, enrollment.progress_id, recovery_id)
        # Known predecessors only: a concurrent recovery retry cannot revoke a
        # later worker after another retry has already released the selection.
        fenced = await repo.progress.update_one(
            {'_id': ObjectId(enrollment.progress_id), 'user_id': user_id,
             '_certification_write_fence': {'$in': [marker['previous_fence'], expected_write_id,
                                                  closed_fence(expected_write_id), recovery_id, closed_fence(recovery_id)]}},
            {'$set': {'_certification_write_fence': recovery_id}},
        )
        if fenced.matched_count != 1:
            latest = await repo.selections.find_one(selection_filter)
            completed = (latest or {}).get('last_completion_recovery') or {}
            if completed.get('write_id') == expected_write_id:
                return completed
            raise EnrollmentConflict('Progress ownership changed during recovery; inspect the saved boundary')
        token = lease_context.set(lease)
        try:
            progress = await repo.read_progress(user_id, enrollment_id)
            attempt_id = marker.get('attempt_id')
            if attempt_id:
                seed = marker.get('attempt_seed')
                if not seed or seed.get('uuid') != attempt_id:
                    raise EnrollmentConflict('The interrupted write has no recoverable assessment intent')
                self.journal.assessment_selection(seed)
                # Idempotent insertion covers death between intent and journal.
                # A delayed worker insert loses to the same unique request ID.
                try:
                    await self.journal.records.update_one({'uuid': attempt_id}, {'$setOnInsert': seed}, upsert=True)
                except DuplicateKeyError:
                    pass
                outcome = await self._reconcile(progress, package, attempt_id, marker['recovery_reason'],
                    expected_owners=[expected_write_id, seed.get('write_id'), recovery_id])
            else:
                # begin() binds intent before insert. Once the selection marker
                # is replaced, that worker cannot create an untracked attempt.
                outcome = {'status': 'no_assessment_started', 'attempt_id': None}
            receipt = {'write_id': expected_write_id, 'recovery_id': recovery_id,
                'enrollment_id': enrollment_id, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'reason': marker['recovery_reason'],
                'recovered_at': marker['recovery_started_at'], **outcome}
            # Leave a permanent closed fence before allowing another writer.
            await repo.progress.update_one(lease.progress_filter(),
                {'$set': {'_certification_write_fence': closed_fence(recovery_id)}})
            released = await repo.selections.update_one(lease.selection_filter(), {
                '$set': {'in_flight_writes': 0, 'last_completion_recovery': receipt},
                '$unset': {'active_write': ''},
            })
            if released.matched_count != 1:
                latest = await repo.selections.find_one(selection_filter)
                completed = (latest or {}).get('last_completion_recovery') or {}
                if completed.get('write_id') != expected_write_id:
                    raise EnrollmentConflict('Recovery receipt could not be recorded; inspect the selection')
                return completed
            return receipt
        finally:
            lease_context.reset(token)

    async def reconcile_attempt(self, user_id, enrollment_id, *, attempt_id, reason, expected_revision=None, recovery_request_id=None):
        """Explicit reconciliation when normal cleanup already released a lock."""
        if not isinstance(reason, str) or not reason.strip():
            raise EnrollmentConflict('Record a reason for explicit assessment recovery')
        async with self.repository.write_boundary(user_id, enrollment_id, operation='reconcile_completion', recovery_request_id=recovery_request_id) as progress:
            if expected_revision is not None and await self.repository.selections.find_one({
                **require_lease(user_id, enrollment_id).selection_filter(), 'revision': expected_revision,
            }) is None:
                raise EnrollmentConflict('The reviewed course selection changed')
            package = self.repository.catalog.load(progress.course_version)
            record = await self.journal.records.find_one({'uuid': attempt_id, 'user_id': user_id, 'enrollment_id': enrollment_id})
            if record is None:
                raise EnrollmentConflict('The assessment does not belong to the reviewed course')
            await self.journal.bind_write(record)
            return await self._reconcile(progress, package, attempt_id, reason.strip(),
                expected_owners=[record.get('write_id'), require_lease(user_id, enrollment_id).write_id])

    async def _reconcile(self, progress, package, attempt_id, reason, expected_owners=None):
        lease = require_lease(progress.user_id, progress.enrollment_id)
        record = await self.journal.records.find_one({'uuid': attempt_id})
        if record is None or (record.get('user_id'), record.get('enrollment_id'), record.get('course_version'), record.get('manifest_sha256')) != (
            progress.user_id, progress.enrollment_id, package.manifest.release_id, package.manifest_sha256,
        ):
            raise EnrollmentConflict('The assessment does not belong to the reviewed course')
        if record.get('rubric_id') != package.manifest.rubric_id or record.get('artifact_sha256') != package.manifest.artifacts:
            raise CourseCatalogError('Assessment requirements differ from the preserved course')
        self.journal.payload(record, 'progress')
        self.journal.assessment_selection(record)
        # Only this recovery lease can subsequently update a pending journal.
        # A grader racing this update either saves first or loses its CAS.
        record = await self.journal.records.find_one_and_update(
            {'uuid': attempt_id, 'state': {'$in': ['evaluating', 'graded']},
             'write_id': {'$in': expected_owners if expected_owners is not None else [record.get('write_id')]}},
            {'$set': {'write_id': lease.write_id, 'recovery': {'reason': reason, 'write_id': lease.write_id}}},
            return_document=ReturnDocument.AFTER,
        ) or await self.journal.records.find_one({'uuid': attempt_id})
        if record['state'] in ('applied', 'rejected', 'failed'):
            self.journal.payload(record, 'result')
            return {'status': 'saved_result', 'attempt_id': attempt_id}
        if record.get('write_id') != lease.write_id:
            raise EnrollmentConflict('Another worker owns the assessment; inspect its saved result')
        receipt = progress.completion_receipt
        if receipt and receipt.get('attempt_id') == attempt_id:
            if record['state'] != 'graded':
                raise EnrollmentConflict('Awarded credit has no saved grade; inspect the assessment')
            result = self.journal.payload(receipt, 'result')
            if result.get('attempt_id') != attempt_id:
                raise CourseCatalogError('The awarded receipt identifies another assessment')
            await self.journal.finish(record, result)
            return {'status': 'saved_result', 'attempt_id': attempt_id}
        if record['state'] == 'graded':
            self.journal.payload(record, 'validation')
            if progress_digest(progress) != record['progress_sha256']:
                raise EnrollmentConflict('Earned progress or answers changed; review the uncommitted grade separately')
            return {'status': 'retry_saved_grade', 'attempt_id': attempt_id}
        await self.journal.finish(record, {
            'error': 'Assessment was interrupted before a grade was saved; submit a new request to try again',
            'attempt_id': attempt_id,
        }, failed=True)
        return {'status': 'interrupted_before_grade', 'attempt_id': attempt_id}
