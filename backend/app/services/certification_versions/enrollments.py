"""Explicit enrollment selection; never infer an upgrade from the newest release.

Initialization is restartable without transactions: deterministic initial IDs,
insert-only progress/enrollment writes, then a single atomic active selection.
No historical grade or credential field is rewritten by initialization.
"""
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, uuid4, uuid5
import datetime

from beanie import PydanticObjectId
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationEnrollment, CertificationEnrollmentSelection, CertificationProgress
from .catalog import CourseCatalog, CourseCatalogError
from .writes import WriteLease, closed_fence, lease_context, require_lease


class EnrollmentConflict(ValueError):
    pass


class EnrollmentRepository:
    def __init__(self, catalog: CourseCatalog | None = None):
        self.catalog = catalog or CourseCatalog()

    @property
    def enrollments(self):
        return CertificationEnrollment.get_motor_collection()

    @property
    def selections(self):
        return CertificationEnrollmentSelection.get_motor_collection()

    @property
    def progress(self):
        return CertificationProgress.get_motor_collection()

    async def _enrollment(self, user_id, enrollment_id):
        raw = await self.enrollments.find_one({'uuid': enrollment_id, 'user_id': user_id})
        if raw is None:
            raise EnrollmentConflict('The selected enrollment is unavailable; recover the existing selection before continuing')
        enrollment = CertificationEnrollment.model_validate(raw)
        package = self.catalog.load(enrollment.course_version)
        if package.manifest_sha256 != enrollment.manifest_sha256:
            raise CourseCatalogError('The enrollment definition no longer matches the published course')
        return enrollment

    async def current(self, user_id: str):
        selection = await self.selections.find_one({'user_id': user_id})
        if selection is None:
            return None
        return await self._enrollment(user_id, selection['active_enrollment_id'])

    async def ensure_initial(self, user_id: str):
        current = await self.current(user_id)
        if current is not None:
            return current
        initial_id = uuid5(NAMESPACE_URL, 'vandalizer:certification:initial:' + user_id).hex
        existing = await self.enrollments.find_one({'uuid': initial_id, 'user_id': user_id})
        if existing is None:
            legacy = await self.progress.find({'user_id': user_id, 'enrollment_id': None}).limit(2).to_list(2)
            if len(legacy) > 1:
                raise EnrollmentConflict('Multiple legacy progress records need reconciliation; none has been selected or overwritten')
            registry = self.catalog.registry()
            key = 'legacy_continuation' if legacy else 'new_enrollment_default'
            version = registry.get(key)
            if not version:
                raise CourseCatalogError('No supported initial course has been configured')
            package = self.catalog.load(version, new_enrollment=not legacy)
            progress_id = str(legacy[0]['_id']) if legacy else initial_id[:24]
            enrollment = CertificationEnrollment(
                uuid=initial_id, user_id=user_id, course_version=version,
                manifest_sha256=package.manifest_sha256, progress_id=progress_id,
                provenance='legacy_version_unknown' if legacy else 'new_enrollment',
                state='completed' if legacy and legacy[0].get('certified') else 'active',
            )
            try:
                await self.enrollments.update_one({'uuid': initial_id}, {'$setOnInsert': enrollment.model_dump(by_alias=True, exclude={'id'})}, upsert=True)
            except DuplicateKeyError:
                pass  # Another initializer won; always read its pinned definition.
        enrollment = await self._enrollment(user_id, initial_id)
        if enrollment.provenance == 'new_enrollment':
            initial_progress = CertificationProgress(user_id=user_id, enrollment_id=enrollment.uuid, course_version=enrollment.course_version)
            try:
                await self.progress.update_one(
                    {'_id': ObjectId(enrollment.progress_id), 'user_id': user_id},
                    {'$setOnInsert': initial_progress.model_dump(by_alias=True, exclude={'id'})}, upsert=True,
                )
            except DuplicateKeyError:
                pass  # Verify the winning record below, including its owner.
        elif await self.progress.find_one({'_id': ObjectId(enrollment.progress_id), 'user_id': user_id}) is None:
            raise EnrollmentConflict('Legacy progress is missing; earned history cannot be reconstructed automatically')
        await self.read_progress(user_id, enrollment.uuid)
        # Detect an older worker creating progress between the initial lookup
        # and selection. Rollout must still replace all unversioned writers;
        # this guard prevents a known race from silently hiding earned work.
        other_legacy = await self.progress.find_one({
            'user_id': user_id, 'enrollment_id': None,
            '_id': {'$ne': ObjectId(enrollment.progress_id)},
        })
        if other_legacy is not None:
            raise EnrollmentConflict('Legacy progress changed during initialization; reconcile it before selecting an enrollment')
        try:
            await self.selections.update_one({'user_id': user_id}, {'$setOnInsert': {
                'user_id': user_id, 'active_enrollment_id': initial_id, 'revision': 0, 'in_flight_writes': 0,
            }}, upsert=True)
        except DuplicateKeyError:
            pass
        return await self.current(user_id)

    async def read_progress(self, user_id: str, enrollment_id: str):
        enrollment = await self._enrollment(user_id, enrollment_id)
        raw = await self.progress.find_one({'_id': PydanticObjectId(enrollment.progress_id), 'user_id': user_id})
        if raw is None:
            raise EnrollmentConflict('Enrollment progress is unavailable')
        if raw.get('enrollment_id') not in (None, enrollment.uuid) or raw.get('course_version') not in (None, enrollment.course_version):
            raise EnrollmentConflict('Stored progress belongs to another enrollment or course')
        if enrollment.provenance != 'legacy_version_unknown' and (
            raw.get('enrollment_id') != enrollment.uuid or raw.get('course_version') != enrollment.course_version
        ):
            raise EnrollmentConflict('Versioned progress is missing its enrollment identity')
        progress = CertificationProgress.model_validate(raw)
        # These bindings are returned to the operation, not written to legacy data.
        progress.enrollment_id = enrollment.uuid
        progress.course_version = enrollment.course_version
        return progress

    @asynccontextmanager
    async def write_boundary(self, user_id: str, enrollment_id: str, *, operation: str = 'certification_write', recovery_request_id: str | None = None,
                             review_attempt_id: str | None = None, selection_request: dict | None = None):
        """Pin and serialize writes; an interrupted worker fails closed.

        The durable marker is intentionally not cleared by a timeout: a slow
        worker may still commit. Recovery must reconcile that operation first.
        """
        enrollment = await self._enrollment(user_id, enrollment_id)
        if enrollment.state == 'prepared':
            raise EnrollmentConflict('This prepared course is read-only until its original switch is confirmed')
        if enrollment.state not in ('active', 'completed'):
            raise EnrollmentConflict('This enrollment is read-only')
        package = self.catalog.load(enrollment.course_version)
        write_id = uuid4().hex
        lease = WriteLease(user_id, enrollment_id, enrollment.progress_id, write_id)
        # Capture before claiming selection. Recovery changes this value even
        # if a worker has not yet installed its fence, closing that race.
        raw = await self.progress.find_one({'_id': ObjectId(enrollment.progress_id), 'user_id': user_id})
        if raw is None:
            raise EnrollmentConflict('Enrollment progress is unavailable')
        previous_fence = raw.get('_certification_write_fence')
        selected = await self.selections.find_one_and_update(
            {'user_id': user_id, 'active_enrollment_id': enrollment_id, 'in_flight_writes': 0,
             'pending_transition_id': None},
            {'$set': {'in_flight_writes': 1, 'active_write': {
                'id': write_id, 'operation': operation, 'enrollment_id': enrollment_id,
                'previous_fence': previous_fence, 'recovery_request_id': recovery_request_id,
                **({'review_attempt_id': review_attempt_id} if review_attempt_id is not None else {}),
                **({'selection_request': selection_request} if selection_request is not None else {}),
                'course_version': enrollment.course_version, 'manifest_sha256': enrollment.manifest_sha256,
                'rubric_id': package.manifest.rubric_id,
                'started_at': datetime.datetime.now(tz=datetime.timezone.utc),
            }}}, return_document=ReturnDocument.AFTER,
        )
        if selected is None:
            raise EnrollmentConflict('The active enrollment changed, another write is in flight or a saved course switch needs its original receipt confirmed; reload before submitting')
        token = None
        try:
            acquired = await self.progress.update_one(
                {'_id': ObjectId(enrollment.progress_id), 'user_id': user_id,
                 '_certification_write_fence': previous_fence},
                {'$set': {'_certification_write_fence': write_id}},
            )
            if acquired.matched_count != 1:
                raise EnrollmentConflict('The write was revoked before it started; reload before submitting')
            token = lease_context.set(lease)
            yield await self.read_progress(user_id, enrollment_id)
        finally:
            if token is not None:
                lease_context.reset(token)
            # Revoke before releasing selection. A copied task context or a
            # delayed save cannot write after the boundary has closed.
            await self.progress.update_one(lease.progress_filter(),
                {'$set': {'_certification_write_fence': closed_fence(write_id)}})
            await self.selections.update_one(
                lease.selection_filter(),
                {'$set': {'in_flight_writes': 0}, '$unset': {'active_write': ''}},
            )

    async def activate(self, user_id: str, target_id: str, *, expected_source: str, expected_revision: int, decision: dict):
        """Internal activation boundary; callers must supply a reviewed transfer.

        No HTTP activation endpoint is exposed until credit previews, attempt
        reconciliation and transition receipts are implemented and validated.
        """
        target = await self._enrollment(user_id, target_id)
        if target_id == expected_source or target.provenance != 'explicit_upgrade' or target.source_enrollment_id != expected_source:
            raise EnrollmentConflict('The reviewed upgrade must preserve and reference its source enrollment')
        source = await self._enrollment(user_id, expected_source)
        if target.course_version == source.course_version:
            raise EnrollmentConflict('An upgrade must target a different reviewed course version')
        self.catalog.load(target.course_version, new_enrollment=True)
        if target.state not in ('active', 'completed'):
            raise EnrollmentConflict('This enrollment cannot be activated')
        if decision.get('accepted') is not True or decision.get('target_enrollment_id') != target_id:
            raise EnrollmentConflict('An explicit decision matching the reviewed target is required')
        from .credentials import CredentialRepository
        credentials = CredentialRepository()
        # Hold the same boundary as graduation from the preservation check
        # through selection. Otherwise a failed issuance could appear between
        # the check and the switch, stranding its pending record on the source.
        async with self.write_boundary(user_id, expected_source, operation='activate_enrollment') as source_progress:
            from app.models.certification import CertificationAttempt, CertificationLabInput, CertificationScenarioAttempt, CertificationLabExecution, CertificationReviewAttempt, CertificationLearnerDecision, CertificationProcessSubmission, CertificationWorkflowDesignSubmission
            pending_attempt = await CertificationAttempt.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
                'state': {'$in': ['evaluating', 'graded']},
            })
            if pending_attempt:
                raise EnrollmentConflict('Reconcile the unfinished assessment before changing courses')
            if await CertificationWorkflowDesignSubmission.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                raise EnrollmentConflict('Saved workflow approvals need an explicit disposition before changing courses')
            if await CertificationProcessSubmission.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                raise EnrollmentConflict('Saved process designs need an explicit disposition before changing courses')
            if await CertificationLearnerDecision.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                raise EnrollmentConflict('Saved learner decisions need an explicit disposition before changing courses')
            if await CertificationReviewAttempt.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                raise EnrollmentConflict('Saved automatic assessments need an explicit disposition before changing courses')
            if await CertificationLabExecution.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                # Protect execution receipts even when their input reference
                # cannot currently be resolved. No automatic retry or discard.
                raise EnrollmentConflict('Saved lab runs need an explicit disposition before changing courses')
            if await CertificationLabInput.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                # Input snapshots currently have no implemented execution /
                # assessment disposition. Do not strand them on a switch.
                raise EnrollmentConflict('Prepared lab evidence needs an explicit disposition before changing courses')
            if await CertificationScenarioAttempt.get_motor_collection().find_one({
                'user_id': user_id, 'enrollment_id': {'$in': [source.uuid, target.uuid]},
            }):
                # Includes receipts whose progress pointer was interrupted.
                raise EnrollmentConflict('Saved scenario answers need an explicit disposition before changing courses')
            for progress in (source_progress, await self.read_progress(user_id, target.uuid)):
                if progress.pending_credential or (progress.certified and await credentials.for_enrollment(user_id, progress.enrollment_id) is None):
                    raise EnrollmentConflict('Preserve the original credential and reconcile pending issuance before changing courses')
            result = await self.selections.find_one_and_update(
                {'user_id': user_id, 'active_enrollment_id': expected_source, 'revision': expected_revision,
                 'in_flight_writes': 1, 'active_write.id': require_lease(user_id, expected_source).write_id},
                {'$set': {'active_enrollment_id': target_id, 'last_transition': decision, 'in_flight_writes': 0},
                 '$unset': {'active_write': ''}, '$inc': {'revision': 1}},
                return_document=ReturnDocument.AFTER,
            )
            if result is None:
                raise EnrollmentConflict('Work is in flight or the selection changed; review the transition again')
        return target
