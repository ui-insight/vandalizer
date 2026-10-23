"""Execute a preserved rubric against the enrollment pinned by the caller.

Only repository-managed, hash-verified course packages reach this runner. Each
async grading operation has its own progress binding, including concurrent users.
"""
from contextvars import ContextVar
from types import ModuleType
from pathlib import Path

from .catalog import CourseCatalogError, CoursePackage

_package: ContextVar[CoursePackage | None] = ContextVar('certification_grading_package', default=None)
_progress: ContextVar[object | None] = ContextVar('certification_grading_progress', default=None)


def selected_outcome_completion_available(package: CoursePackage) -> bool:
    """Advertise the existing write capability without making a draft enrollable."""
    if (package.entry.state == 'draft' or not package.entry.supported_for_existing
            or package.manifest.rubric_id != 'v5.0-competency-draft.1'):
        return False
    try:
        load_rubric(package)
    except CourseCatalogError:
        return False
    return True


def pinned_progress(user_id: str):
    progress = _progress.get()
    if progress is None or progress.user_id != user_id:
        raise CourseCatalogError('Grading requires an explicitly pinned enrollment')
    return progress


def pinned_package() -> CoursePackage:
    package = _package.get()
    if package is None:
        raise CourseCatalogError('Grading requires a verified course package')
    return package


def load_rubric(package: CoursePackage) -> ModuleType:
    if package.manifest.rubric_id == 'v5.0-competency-draft.1':
        from .rubrics import competency_v5
        competency_v5.verify_package(package)
        return competency_v5
    if package.manifest.rubric_id != 'legacy-2026-10-02':
        raise CourseCatalogError('This rubric does not yet have a supported runner')
    if 'outcomes.json' in package.manifest.artifacts:
        raise CourseCatalogError('The preserved legacy rubric cannot assess new competency outcomes')
    from .rubrics import legacy_20261002
    if Path(legacy_20261002.__file__).read_bytes() != package.read('rubric.py'):
        raise CourseCatalogError('Installed rubric differs from the pinned course package')
    manifest = package.manifest
    if ([module.id for module in manifest.modules] != legacy_20261002.MODULE_ORDER
            or {module.id: module.base_xp for module in manifest.modules} != legacy_20261002.MODULE_XP
            or manifest.star_bonus_xp != 25 or manifest.maximum_stars != 3
            or any(module.prerequisites for module in manifest.modules)):
        raise CourseCatalogError('Manifest requirements differ from the preserved rubric')
    if [(level['name'], level['xp']) for level in package.json('course-structure.json')['levels']] != legacy_20261002.LEVELS:
        raise CourseCatalogError('Displayed levels differ from the preserved rubric')
    lessons = package.json('lessons.json')
    assessment_keys = {module_id: tuple(question['key'] for question in data['assessment']['questions'])
                       for module_id, data in lessons.items() if data.get('assessment')}
    if assessment_keys != legacy_20261002.ASSESSMENT_KEYS:
        raise CourseCatalogError('Reflection questions differ from the preserved rubric requirements')
    return legacy_20261002


async def grade(package: CoursePackage, progress, module_id: str, *, preview: bool = False, assessment_selection=None) -> dict:
    manifest = package.manifest
    if not preview and (package.entry.state == 'draft' or not package.entry.supported_for_existing):
        raise CourseCatalogError('Only supported published requirements can grade an enrollment')
    if getattr(progress, 'course_version', None) != manifest.release_id:
        raise CourseCatalogError('Enrollment and rubric versions differ')
    if module_id not in {module.id for module in manifest.modules}:
        raise CourseCatalogError('Module is not part of this enrollment')
    token = _progress.set(progress)
    package_token = _package.set(package)
    try:
        rubric = load_rubric(package)
        if manifest.rubric_id == 'legacy-2026-10-02':
            if assessment_selection is not None:
                raise CourseCatalogError('The preserved legacy rubric cannot grade selected competency receipts')
            from .legacy_access import with_legacy_field_access
            result = await with_legacy_field_access(rubric.validate_module, progress.user_id)(progress.user_id, module_id)
            from .check_roles import legacy_check_roles
            result = legacy_check_roles(module_id, result)
        else:
            result = await rubric.validate_module(progress.user_id, module_id, assessment_selection=assessment_selection)
        return {**result, 'course_version': manifest.release_id,
                'manifest_sha256': package.manifest_sha256, 'rubric_id': manifest.rubric_id}
    finally:
        _progress.reset(token)
        _package.reset(package_token)
