"""Restartable target preparation; the source remains selected throughout.

Preparing an explicitly chosen course creates no assessed credit and cannot
activate it. A later selection commit must reacquire/revalidate the original
choice and reconcile saved operations. Existing target work is never reset.
"""
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationEnrollment, CertificationProgress
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .transition_records import TransitionRecordReconciliation
from .transition_preview import fingerprint
from .upgrade_decisions import UpgradeDecisionRepository
from .writes import require_lease


def target_identity(request_id):
    enrollment_id = uuid5(NAMESPACE_URL, 'vandalizer:certification:upgrade-target:' + request_id).hex
    return enrollment_id, enrollment_id[:24]


def initial_level(package):
    levels = package.json('course-structure.json').get('levels')
    if (not isinstance(levels, list) or not levels
            or any(not isinstance(level, dict) or not isinstance(level.get('name'), str) or not level['name'].strip()
                   or type(level.get('xp')) is not int or level['xp'] < 0 for level in levels)
            or levels[0]['xp'] != 0
            or levels[-1]['xp'] > sum(module.base_xp for module in package.manifest.modules)
            or len({level['name'] for level in levels}) != len(levels)
            or any(left['xp'] >= right['xp'] for left, right in zip(levels, levels[1:]))):
        raise EnrollmentConflict('The target needs valid pinned zero-XP progression before preparation')
    return levels[0]['name']


class UpgradeTargetRepository:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.decisions = UpgradeDecisionRepository(self.repository)

    async def prepare(self, user_id, request_id):
        async with self.decisions.hold_reviewed_choice(user_id, request_id) as (decision, source_progress, package):
            return await self.stage(decision, source_progress, package)

    async def stage(self, decision, source_progress, package):
        """Internal helper for a future commit holding the same reviewed guard."""
        user_id, source_id = decision.user_id, decision.request.source_enrollment_id
        lease = require_lease(user_id, source_id)
        if (source_progress.enrollment_id != source_id or str(source_progress.id) != lease.progress_id
                or package.manifest.release_id != decision.request.target_version
                or package.manifest_sha256 != decision.preview['target']['manifest_sha256']):
            raise EnrollmentConflict('Target preparation no longer matches the original choice')
        preservation = await TransitionRecordReconciliation(self.repository).inspect(user_id, source_id)
        target_id, progress_id = target_identity(decision.request.request_id)
        seed = CertificationProgress(user_id=user_id, enrollment_id=target_id,
            course_version=package.manifest.release_id, level=initial_level(package))
        enrollment = CertificationEnrollment(uuid=target_id, user_id=user_id,
            course_version=package.manifest.release_id, manifest_sha256=package.manifest_sha256,
            progress_id=progress_id, provenance='explicit_upgrade', source_enrollment_id=source_id, state='prepared')
        repo = self.repository
        # Check before each insertion; neither insertion selects the target.
        if (await repo.selections.find_one(lease.selection_filter()) is None
                or await repo.progress.find_one(lease.progress_filter()) is None):
            raise EnrollmentConflict('Target preparation lost its original course boundary')
        try:
            await repo.enrollments.update_one({'uuid': target_id},
                {'$setOnInsert': enrollment.model_dump(by_alias=True, exclude={'id'})}, upsert=True)
        except DuplicateKeyError:
            pass
        saved = await repo._enrollment(user_id, target_id)
        if any(getattr(saved, key) != getattr(enrollment, key) for key in
               ('uuid', 'user_id', 'course_version', 'manifest_sha256', 'progress_id', 'provenance', 'source_enrollment_id', 'state')):
            raise EnrollmentConflict('The prepared target already has a different enrollment identity')
        if (await repo.selections.find_one(lease.selection_filter()) is None
                or await repo.progress.find_one(lease.progress_filter()) is None):
            raise EnrollmentConflict('Target preparation lost its original course boundary')
        try:
            await repo.progress.update_one({'_id': ObjectId(progress_id), 'user_id': user_id},
                {'$setOnInsert': seed.model_dump(by_alias=True, exclude={'id'})}, upsert=True)
        except DuplicateKeyError:
            pass
        progress = await repo.read_progress(user_id, target_id)
        excluded = {'id', 'revision_id', 'created_at', 'updated_at'}
        if progress.model_dump(exclude=excluded) != seed.model_dump(exclude=excluded):
            raise EnrollmentConflict('The prepared target contains saved work; preserve and reconcile it instead of resetting it')
        if (await repo.selections.find_one(lease.selection_filter()) is None
                or await repo.progress.find_one(lease.progress_filter()) is None):
            raise EnrollmentConflict('Target preparation lost its original course boundary')
        return {'decision_id': decision.request.request_id, 'source_enrollment_id': source_id,
                'target_enrollment_id': target_id, 'target_course_version': saved.course_version,
                'target_manifest_sha256': saved.manifest_sha256, 'prepared': True, 'activated': False,
                'credit_transferred': False, 'target_xp': progress.total_xp,
                'source_reconciliation_sha256': preservation['reconciliation_sha256'],
                'target_enrollment_sha256': fingerprint(saved.model_dump(mode='json')),
                'target_progress_sha256': fingerprint(progress.model_dump(mode='json')),
                'requires_fresh_activation_check': True}
