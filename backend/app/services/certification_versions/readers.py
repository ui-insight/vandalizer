"""Non-enrolling reads for home, feedback and background engagement."""
from collections import Counter, defaultdict

from pydantic import ValidationError

from app.models.certification import CertificationEnrollment, CertificationProgress
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .catalog import CourseCatalogError


async def has_earned_certification(user_id: str) -> bool:
    """An optional new enrollment does not remove a previous credential signal.

    This Boolean asserts only that a stored completion exists, not which
    historical course/outcomes it proves. Immutable issuance replaces this
    legacy signal when that migration is implemented.
    """
    return await CertificationProgress.find_one({'user_id': user_id, 'certified': True}) is not None


async def existing_active_progress(user_id: str):
    """Never initialize an enrollment merely to evaluate a background prompt.

    Honor an existing selection even when the rollout flag is disabled. Falling
    back to an arbitrary user-only row would hide or confuse earned history.
    """
    repository = EnrollmentRepository()
    enrollment = await repository.current(user_id)
    if enrollment is not None:
        return await repository.read_progress(user_id, enrollment.uuid)
    rows = await repository.progress.find({'user_id': user_id}).limit(2).to_list(2)
    if not rows:
        return None
    if len(rows) != 1 or rows[0].get('enrollment_id'):
        raise EnrollmentConflict('Certification history needs reconciliation before choosing a course')
    return CertificationProgress.model_validate(rows[0])


async def support_metadata_many(progresses: list[CertificationProgress]) -> dict[str, dict]:
    """Describe a complete set of stored rows with two bulk metadata reads.

    The administrator list already loads all progress for sorting/counting.
    Reuse that set, and verify each distinct package once for this request.
    This snapshot is display-only: every write rechecks live selection/bindings.
    """
    from app.services.certification_service import MODULE_ORDER
    from .progression_policy import package_progression_policy
    from .runtime import versioning_enabled
    if not progresses:
        return {}
    repository = EnrollmentRepository()
    user_ids = list({progress.user_id for progress in progresses})
    enrollments = await repository.enrollments.find({'user_id': {'$in': user_ids}}).to_list(None)
    selections = await repository.selections.find({'user_id': {'$in': user_ids}}).to_list(None)
    by_progress, by_identity, by_user_selection = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in enrollments:
        by_progress[(row.get('user_id'), row.get('progress_id'))].append(row)
        by_identity[(row.get('user_id'), row.get('uuid'))].append(row)
    for row in selections:
        by_user_selection[row.get('user_id')].append(row)
    counts = Counter(progress.user_id for progress in progresses)
    packages = {}
    policies = {}

    def verified_enrollment(raw):
        enrollment = CertificationEnrollment.model_validate(raw)
        version = enrollment.course_version
        if version not in packages:
            try:
                packages[version] = repository.catalog.load(version)
                policies[version] = package_progression_policy(packages[version])
            except CourseCatalogError as exc:
                packages[version] = exc
        package = packages[version]
        if isinstance(package, CourseCatalogError):
            raise package
        if enrollment.manifest_sha256 != package.manifest_sha256:
            raise CourseCatalogError('The enrollment definition no longer matches the published course')
        return enrollment, package

    result = {}
    for progress in progresses:
        progress_id = str(progress.id)
        try:
            bindings = by_progress[(progress.user_id, progress_id)]
            if not bindings:
                if progress.enrollment_id or counts[progress.user_id] != 1:
                    raise EnrollmentConflict('Unbound or duplicate progress needs reconciliation')
                result[progress_id] = {
                    'progress_id': progress_id, 'course_title': 'Legacy course — historical version unknown',
                    'module_ids': MODULE_ORDER, 'can_unlock': not versioning_enabled(),
                }
                continue
            if len(bindings) != 1:
                raise EnrollmentConflict('Multiple enrollments reference this progress record')
            enrollment, package = verified_enrollment(bindings[0])
            policy = policies.get(enrollment.course_version)
            if progress.enrollment_id not in (None, enrollment.uuid) or progress.course_version not in (None, enrollment.course_version):
                raise EnrollmentConflict('Stored progress belongs to another enrollment or course')
            if enrollment.provenance != 'legacy_version_unknown' and (
                progress.enrollment_id != enrollment.uuid or progress.course_version != enrollment.course_version
            ):
                raise EnrollmentConflict('Versioned progress is missing its enrollment identity')
            selection_rows = by_user_selection[progress.user_id]
            if len(selection_rows) > 1:
                raise EnrollmentConflict('Multiple active selections need reconciliation')
            selected = False
            if selection_rows:
                selected_rows = by_identity[(progress.user_id, selection_rows[0].get('active_enrollment_id'))]
                if len(selected_rows) != 1:
                    raise EnrollmentConflict('The selected enrollment is unavailable; recover the existing selection before continuing')
                current, _ = verified_enrollment(selected_rows[0])
                selected = current.uuid == enrollment.uuid
            result[progress_id] = {
                'progress_id': progress_id, 'enrollment_id': enrollment.uuid,
                'course_version': enrollment.course_version, 'course_title': package.manifest.title,
                'enrollment_state': enrollment.state, 'is_active': selected,
                'module_ids': [module.id for module in package.manifest.modules],
                'can_unlock': selected and enrollment.state in ('active', 'completed') and policy is None,
                **({'progression_policy_id': policy.policy_id, 'learning_order': policy.learning_order,
                    'unlock_unavailable_reason': 'This course allows any study order. Every required outcome still needs assessed evidence.'} if policy else {}),
            }
        except (CourseCatalogError, EnrollmentConflict, ValidationError) as exc:
            result[progress_id] = {
                'progress_id': progress_id, 'course_title': 'Course needs reconciliation',
                'module_ids': [], 'can_unlock': False, 'reconciliation_error': str(exc),
            }
    return result


async def support_metadata(progress: CertificationProgress) -> dict:
    """Identify one stored row using the same checks as the administrator list."""
    rows = await CertificationProgress.find({'user_id': progress.user_id}).to_list()
    return (await support_metadata_many(rows)).get(str(progress.id), {
        'progress_id': str(progress.id), 'course_title': 'Course needs reconciliation',
        'module_ids': [], 'can_unlock': False, 'reconciliation_error': 'Enrollment progress is unavailable',
    })


async def set_support_unlock(user_id: str, unlocked: bool, enrollment_id: str | None, *, actor_user_id: str, reason: str, request_id: str):
    """Target the reviewed row, under the same boundary as learner writes."""
    from .support_access import AccessChangeRequest, apply_access_change
    request = AccessChangeRequest(request_id=request_id, unlocked=unlocked, reason=reason)
    from .runtime import versioning_enabled
    from .progression_policy import package_progression_policy
    repository = EnrollmentRepository()
    selected = await repository.current(user_id)
    if selected is not None:
        if enrollment_id != selected.uuid:
            raise EnrollmentConflict('The selected course changed; refresh the administrator list before saving')
        package = repository.catalog.load(selected.course_version)
        if package_progression_policy(package) is not None:
            raise EnrollmentConflict('This course allows any study order; an unlock cannot waive its required assessed outcomes')
        async with repository.write_boundary(user_id, enrollment_id, operation='admin_unlock') as progress:
            from .writes import progress_filter
            return await apply_access_change(repository, progress, request, actor_user_id, progress_filter(progress))
    if enrollment_id or versioning_enabled():
        raise EnrollmentConflict('Load and reconcile this learner enrollment before changing prerequisites')
    progress = await existing_active_progress(user_id)
    if progress is None:
        raise EnrollmentConflict('Load existing progress before changing prerequisites')
    # Legacy reads have no enrolled write lease. Never replace their complete
    # document: an assessment or lesson save may have committed since this read.
    # Compare only the reviewed access/binding, then return the fresh saved row.
    access_filter = {'unlocked': True} if progress.unlocked else {
        '$or': [{'unlocked': False}, {'unlocked': {'$exists': False}}],
    }
    return await apply_access_change(repository, progress, request, actor_user_id,
        {'enrollment_id': None, 'course_version': None, **access_filter,
         '_certification_write_fence': {'$exists': False}})
