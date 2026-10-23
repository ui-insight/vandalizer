"""Durable completion journal for the staged versioned course runtime.

The preserved grader still examines mutable workspace artifacts. This journal
pins its requirements and returned judgment; it does not invent immutable lab
evidence or claim the new 5.0 outcomes have been assessed.
"""
import hashlib
import json
import re
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationAttempt, CertificationEnrollmentSelection
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .writes import require_lease


def encode(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return payload, hashlib.sha256(payload.encode()).hexdigest()


def progress_snapshot(progress):
    # Navigation is not assessed credit. Exclude its module-local cursor too.
    values = progress.model_dump(mode='json', include={
        'user_id', 'enrollment_id', 'course_version', 'modules', 'total_xp',
        'level', 'certified', 'certified_at', 'lab_folder_id',
    })
    for module_id, module in list(values['modules'].items()):
        if isinstance(module, dict):
            module.pop('learning_position', None)
            if not module:
                del values['modules'][module_id]
    return encode(values)


def progress_digest(progress):
    return progress_snapshot(progress)[1]


def normalize_assessment_selection(value):
    """An explicit choice of original receipts, never an assessment verdict."""
    if value is None:
        return None
    if (not isinstance(value, dict) or not value
            or set(value) - {'review_attempt_id', 'scenario_attempt_id'}
            or any(not isinstance(reference, str) or not re.fullmatch(r'[a-f0-9]{32}', reference)
                   for reference in value.values())):
        raise EnrollmentConflict('Select saved assessments by their exact references')
    return dict(value)


class AttemptRepository:
    @property
    def records(self):
        return CertificationAttempt.get_motor_collection()

    @staticmethod
    def payload(record, field):
        serialized, digest = record.get(field + '_json'), record.get(field + '_sha256')
        if not isinstance(serialized, str) or hashlib.sha256(serialized.encode()).hexdigest() != digest:
            raise CourseCatalogError('The saved assessment receipt failed its integrity check')
        try:
            value = json.loads(serialized)
        except ValueError as exc:
            raise CourseCatalogError('The saved assessment receipt is invalid') from exc
        if not isinstance(value, dict):
            raise CourseCatalogError('The saved assessment receipt must be an object')
        return value

    async def pending(self, operation):
        """Read-only resume hints; never grade, recover or clear a worker here."""
        identity = {'user_id': operation.user_id, 'enrollment_id': operation.progress.enrollment_id}
        records = await self.records.find({**identity, 'state': {'$in': ['evaluating', 'graded']}}).limit(2).to_list(2)
        if not records:
            return []
        selection = await CertificationEnrollmentSelection.get_motor_collection().find_one({'user_id': operation.user_id})
        busy = bool(selection and selection.get('in_flight_writes'))
        result = []
        for record in records:
            if (record.get('course_version'), record.get('manifest_sha256'), record.get('rubric_id')) != (
                operation.package.manifest.release_id, operation.package.manifest_sha256, operation.package.manifest.rubric_id,
            ) or record.get('module_id') not in {module.id for module in operation.package.manifest.modules}:
                raise CourseCatalogError('The pending assessment does not match the selected course')
            result.append({'attempt_id': record['uuid'], 'module_id': record['module_id'],
                'state': record['state'] if len(records) == 1 else 'review', 'in_flight': busy})
        return result

    @classmethod
    def assessment_selection(cls, record):
        if record.get('assessment_selection_json') is None and record.get('assessment_selection_sha256') is None:
            return None
        value = cls.payload(record, 'assessment_selection')
        try:
            return normalize_assessment_selection(value)
        except EnrollmentConflict as exc:
            raise CourseCatalogError('The saved assessment selection is invalid') from exc

    async def begin(self, operation, module_id, request_id=None, *, assessment_selection=None, transfer_request=None):
        """Caller holds the enrollment write boundary for the entire attempt."""
        progress, package = operation.progress, operation.package
        if not operation.writable or module_id not in {module.id for module in package.manifest.modules}:
            raise EnrollmentConflict('Assessment requires a writable enrolled module')
        if request_id is not None and not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Assessment request_id must be a 32-character lowercase hexadecimal identity')
        selected = normalize_assessment_selection(assessment_selection)
        if transfer_request is not None and selected is not None:
            raise EnrollmentConflict('A transfer cannot also submit a new assessment selection')
        if selected is not None and 'outcomes.json' not in package.manifest.artifacts:
            raise EnrollmentConflict('The preserved legacy rubric does not accept outcome-assessment selections')
        identity = {'user_id': progress.user_id, 'enrollment_id': progress.enrollment_id}
        existing = await self.records.find_one({'uuid': request_id}) if request_id else None
        if existing is None:
            pending = await self.records.find({**identity, 'state': {'$in': ['evaluating', 'graded']}}).limit(2).to_list(2)
            if pending:
                if len(pending) != 1 or pending[0]['module_id'] != module_id or request_id:
                    raise EnrollmentConflict('An unfinished assessment needs reconciliation before starting another request')
                existing = pending[0]
        if existing is not None:
            expected = (progress.user_id, progress.enrollment_id, module_id, package.manifest.release_id, package.manifest_sha256)
            actual = tuple(existing.get(key) for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
            if actual != expected:
                raise EnrollmentConflict('This assessment request belongs to another learner, module or course')
            if existing.get('rubric_id') != package.manifest.rubric_id or existing.get('artifact_sha256') != package.manifest.artifacts:
                raise CourseCatalogError('The assessment requirements no longer match the pinned course')
            self.payload(existing, 'progress')
            original_selection = self.assessment_selection(existing)
            if transfer_request is not None and self.payload(existing, 'transfer_request') != transfer_request:
                raise EnrollmentConflict('This transfer request already belongs to a different reviewed choice')
            if selected is not None and selected != original_selection:
                raise EnrollmentConflict('This completion request already belongs to a different saved assessment selection')
            lease = require_lease(progress.user_id, progress.enrollment_id)
            await self.bind_write(existing)
            if existing['state'] in ('evaluating', 'graded'):
                claimed = await self.records.update_one(
                    {'uuid': existing['uuid'], 'state': existing['state'], 'write_id': existing.get('write_id')},
                    {'$set': {'write_id': lease.write_id}},
                )
                if claimed.matched_count != 1:
                    raise EnrollmentConflict('Assessment ownership changed; reload its receipt')
                existing['write_id'] = lease.write_id
            return existing, False
        payload, digest = progress_snapshot(progress)
        selection_payload, selection_digest = encode(selected) if selected is not None else (None, None)
        transfer_payload, transfer_digest = encode(transfer_request) if transfer_request is not None else (None, None)
        record = CertificationAttempt(
            uuid=request_id or uuid4().hex, **identity, module_id=module_id,
            course_version=package.manifest.release_id, manifest_sha256=package.manifest_sha256,
            rubric_id=package.manifest.rubric_id, artifact_sha256=package.manifest.artifacts,
            progress_json=payload, progress_sha256=digest,
            assessment_selection_json=selection_payload, assessment_selection_sha256=selection_digest,
            transfer_request_json=transfer_payload, transfer_request_sha256=transfer_digest,
            write_id=require_lease(progress.user_id, progress.enrollment_id).write_id,
        ).model_dump(mode='python', exclude={'id'})
        # Record the complete insertion intent before creating the journal.
        # Recovery can materialize it if this worker stops before insertion;
        # the unique ID then also prevents a delayed insert from resurrecting it.
        await self.bind_write(record)
        try:
            await self.records.insert_one(record)
        except DuplicateKeyError as exc:
            raise EnrollmentConflict('Assessment request identity was already claimed; reload its receipt') from exc
        return record, True

    async def bind_write(self, record):
        lease = require_lease(record['user_id'], record['enrollment_id'])
        seed = {key: value for key, value in record.items() if key != '_id'}
        changed = await CertificationEnrollmentSelection.get_motor_collection().update_one(
            lease.selection_filter(),
            {'$set': {'active_write.attempt_id': record['uuid'], 'active_write.module_id': record['module_id'],
                      'active_write.attempt_seed': seed}},
        )
        if changed.matched_count != 1:
            raise EnrollmentConflict('The assessment no longer holds its enrollment write boundary')

    async def graded(self, record, validation):
        payload, digest = encode(validation)
        changed = await self.records.update_one(
            {'uuid': record['uuid'], 'state': 'evaluating',
             'write_id': require_lease(record['user_id'], record['enrollment_id']).write_id},
            {'$set': {'state': 'graded', 'validation_json': payload, 'validation_sha256': digest}},
        )
        if changed.modified_count != 1:
            raise EnrollmentConflict('Assessment grading state changed; reconcile its saved receipt')
        return {**record, 'state': 'graded', 'validation_json': payload, 'validation_sha256': digest}

    async def finish(self, record, result, *, failed=False):
        if failed:
            result = {**result, 'failure_kind': 'execution'}
        payload, digest = encode(result)
        state = 'failed' if failed else ('rejected' if result.get('error') else 'applied')
        changed = await self.records.update_one(
            {'uuid': record['uuid'], 'state': 'evaluating' if failed else 'graded',
             'write_id': require_lease(record['user_id'], record['enrollment_id']).write_id},
            {'$set': {'state': state, 'result_json': payload, 'result_sha256': digest}},
        )
        if changed.modified_count != 1:
            current = await self.records.find_one({'uuid': record['uuid']})
            if current is None or current.get('result_sha256') != digest:
                raise EnrollmentConflict('Assessment result changed; reconcile its original receipt')
        return result
