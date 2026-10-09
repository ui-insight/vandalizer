"""Reviewed completion recovery with durable operator intent and receipts."""
import json
import re

from bson import json_util
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationRecoveryRecord
from .attempts import AttemptRepository, encode, progress_digest
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .recovery import COMPLETION_OPERATIONS, CompletionRecovery


class RecoveryWorkflow:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.recovery = CompletionRecovery(self.repository)

    @property
    def records(self):
        return CertificationRecoveryRecord.get_motor_collection()

    async def inspect(self, user_id, enrollment_id):
        repo = self.repository
        enrollment = await repo._enrollment(user_id, enrollment_id)
        selection = await repo.selections.find_one({'user_id': user_id})
        is_active = bool(selection and selection.get('active_enrollment_id') == enrollment_id)
        progress = await repo.read_progress(user_id, enrollment_id)
        package = repo.catalog.load(enrollment.course_version)
        pending = await self.recovery.journal.records.find({
            'user_id': user_id, 'enrollment_id': enrollment_id, 'state': {'$in': ['evaluating', 'graded']},
        }).limit(2).to_list(2)
        marker = (selection.get('active_write') or {}) if is_active else {}
        active = bool(is_active and selection.get('in_flight_writes'))
        kind, write_id, attempt_id, allowed = 'none', None, None, False
        explanation = 'No interrupted completion needs recovery.'
        if active:
            write_id = marker.get('original_write_id') if marker.get('operation') == 'recover_completion' else marker.get('id')
            attempt_id = marker.get('attempt_id')
            allowed = bool(write_id and 'previous_fence' in marker and (
                marker.get('operation') in COMPLETION_OPERATIONS or marker.get('operation') == 'recover_completion'))
            kind = 'worker'
            explanation = ('Revoke this completion worker and reconcile its saved result. A saved grade is retained; an evaluation without a saved grade ends without credit.'
                           if allowed else 'This operation is not eligible for completion recovery. Its side effects need separate review.')
        elif pending:
            record = pending[0]
            kind, attempt_id = 'attempt', record['uuid']
            allowed = len(pending) == 1
            explanation = 'Reconcile this interrupted evaluation without grading again. A saved result is retained; an evaluation without a saved grade ends without credit.'
            if record['state'] == 'graded':
                allowed = False
                explanation = ('A grade is already saved. Ask the learner to check the saved result in their course.'
                               if progress_digest(progress) == record['progress_sha256'] or (progress.completion_receipt or {}).get('attempt_id') == attempt_id
                               else 'Answers or earned progress changed after grading. Review the uncommitted grade separately.')
            if len(pending) > 1:
                explanation = 'Multiple unfinished assessments need separate reconciliation.'
        if not is_active:
            allowed = False
            explanation = 'This is preserved enrollment history. Only the selected course can be recovered.'
        record = next((item for item in pending if item['uuid'] == attempt_id), None)
        module_id = record.get('module_id') if record else marker.get('module_id')
        review = {
            'user_id': user_id, 'enrollment_id': enrollment_id, 'course_version': enrollment.course_version,
            'course_title': package.manifest.title, 'manifest_sha256': enrollment.manifest_sha256,
            'selection_revision': (selection or {}).get('revision', 0), 'is_active': is_active, 'kind': kind, 'write_id': write_id,
            'attempt_id': attempt_id, 'module_id': module_id,
            'module_title': next((module.title for module in package.manifest.modules if module.id == module_id), None),
            'attempt_state': record.get('state') if record else None,
            'in_flight': active, 'can_recover': allowed, 'explanation': explanation,
            'operation': marker.get('operation'), 'started_at': str(marker.get('started_at')) if marker else None,
            'total_xp': progress.total_xp, 'certified': progress.certified,
            # Digests detect a changed reviewed snapshot without exposing its
            # stored reflection answers or internal journal insertion payload.
            'progress_sha256': progress_digest(progress),
            'marker_sha256': encode(json.loads(json_util.dumps(marker)))[1],
            'attempts_sha256': encode({'attempts': json.loads(json_util.dumps(pending))})[1],
        }
        review['review_sha256'] = encode(review)[1]
        return review

    async def history(self, user_id, enrollment_id):
        rows = await self.records.find({'user_id': user_id, 'enrollment_id': enrollment_id}).sort('created_at', -1).limit(10).to_list(10)
        results = []
        for row in rows:
            request = AttemptRepository.payload(row, 'request')
            review = AttemptRepository.payload(row, 'review')
            results.append({'request_id': row['uuid'], 'actor_user_id': row['actor_user_id'],
                'reason': request['reason'], 'state': row['state'], 'created_at': row['created_at'],
                'attempt_id': review['attempt_id'], 'write_id': review['write_id'],
                'review_sha256': request['review_sha256'], 'review': review,
                'result': AttemptRepository.payload(row, 'result') if row['state'] == 'completed' else None})
        return results

    async def submit(self, actor_user_id, user_id, enrollment_id, *, request_id, review_sha256, reason):
        if not re.fullmatch(r'[a-f0-9]{32}', request_id) or not re.fullmatch(r'[a-f0-9]{64}', review_sha256):
            raise EnrollmentConflict('A valid recovery request and reviewed snapshot are required')
        if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 1000:
            raise EnrollmentConflict('Record a recovery reason between 5 and 1000 characters')
        request = {'actor_user_id': actor_user_id, 'user_id': user_id, 'enrollment_id': enrollment_id,
            'request_id': request_id, 'review_sha256': review_sha256, 'reason': reason.strip()}
        payload, digest = encode(request)
        record = await self.records.find_one({'uuid': request_id})
        if record is None:
            review = await self.inspect(user_id, enrollment_id)
            if review['review_sha256'] != review_sha256:
                raise EnrollmentConflict('The assessment changed since review; refresh and review it again')
            if not review['can_recover']:
                raise EnrollmentConflict(review['explanation'])
            review_payload, review_digest = encode({key: value for key, value in review.items() if key != 'review_sha256'})
            record = CertificationRecoveryRecord(uuid=request_id, actor_user_id=actor_user_id,
                user_id=user_id, enrollment_id=enrollment_id, request_json=payload, request_sha256=digest,
                review_json=review_payload, review_sha256=review_digest).model_dump(mode='python', exclude={'id'})
            # No recovery can happen unless durable operator intent exists.
            try:
                await self.records.insert_one(record)
            except DuplicateKeyError:
                pass
            record = await self.records.find_one({'uuid': request_id})
        if record is None or record['request_sha256'] != digest:
            raise EnrollmentConflict('This recovery request belongs to another reviewed action')
        AttemptRepository.payload(record, 'request')
        if record['state'] == 'completed':
            return AttemptRepository.payload(record, 'result')
        review = AttemptRepository.payload(record, 'review')
        if record['review_sha256'] != review_sha256:
            raise EnrollmentConflict('The preserved review differs from the approved request')
        if review['kind'] == 'worker':
            selected = await self.repository.selections.find_one({'user_id': user_id})
            marker = (selected or {}).get('active_write') or {}
            previous = (selected or {}).get('last_completion_recovery') or {}
            if previous.get('write_id') == review['write_id'] and previous.get('enrollment_id') == enrollment_id:
                outcome = previous
            elif review['write_id'] not in (marker.get('id'), marker.get('original_write_id')):
                # The worker can finish between the review/intent and revocation.
                # Close this intent honestly without acting on a replacement.
                outcome = {'status': 'review_changed', 'attempt_id': review['attempt_id']}
            else:
                outcome = await self.recovery.recover_worker(user_id, enrollment_id,
                    expected_write_id=review['write_id'], expected_revision=review['selection_revision'], reason=reason.strip())
        else:
            selection = await self.repository.selections.find_one({'user_id': user_id, 'active_enrollment_id': enrollment_id})
            marker = (selection or {}).get('active_write') or {}
            if marker.get('recovery_request_id') == request_id:
                await self.recovery.recover_worker(user_id, enrollment_id,
                    expected_write_id=marker.get('original_write_id', marker['id']),
                    expected_revision=review['selection_revision'], reason=reason.strip())
            outcome = await self.recovery.reconcile_attempt(user_id, enrollment_id,
                attempt_id=review['attempt_id'], reason=reason.strip(), expected_revision=review['selection_revision'],
                recovery_request_id=request_id)
        # Recovery's internal timestamps are strings; the response is stable
        # across a lost response and retry of the same reviewed request.
        result = {'request_id': request_id, 'enrollment_id': enrollment_id,
            'course_version': review['course_version'], 'actor_user_id': actor_user_id,
            'reason': reason.strip(), **outcome}
        result_json, result_sha256 = encode(result)
        await self.records.update_one({'uuid': request_id, 'state': 'started'},
            {'$set': {'state': 'completed', 'result_json': result_json, 'result_sha256': result_sha256}})
        saved = await self.records.find_one({'uuid': request_id})
        return AttemptRepository.payload(saved, 'result')
