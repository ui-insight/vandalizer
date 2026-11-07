"""What this process serves, as one comparable fingerprint, and why a course is unavailable.

A course release is coherent only when every API and Celery worker serves the
same registry, the same verified packages (content, exercises, cases, rubric
bytes), the same installed grading runner and the same certification code that
defines the tool and panel contracts. Enrollments pin a release identity and
manifest digest, and each request re-verifies the package from disk, so a worker
holding a different or missing package refuses that enrollment instead of
serving mixed content. The fingerprint lets operators confirm all workers
agree before enabling a release, and lets support see which worker differs.
No learner records are read here.
"""
import hashlib
from pathlib import Path

from .catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError, production_environment

CODE_ROOTS = (
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parents[1] / 'certification_service.py',
    Path(__file__).resolve().parents[2] / 'routers' / 'certification.py',
)
INTACT_WORK = ('Learner progress, saved answers, attempts and credentials are stored in the database and are not '
               'changed by this failure. Do not edit the package, re-enroll or reset the learner.')


def code_digest() -> str:
    """Certification services, rubric runners, tool contracts and routes installed in this process."""
    files = []
    for root in CODE_ROOTS:
        files.extend(sorted(root.rglob('*.py')) if root.is_dir() else [root] if root.exists() else [])
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def deployment_identity(catalog: CourseCatalog | None = None) -> dict:
    from app.config import Settings
    from .grading import load_rubric
    catalog = catalog or CourseCatalog()
    registry_bytes = (catalog.root / 'registry.json').read_bytes()
    registry = catalog.registry()
    releases = {}
    for release_id, entry in sorted(registry['releases'].items()):
        row = {'state': entry['state'], 'manifest_sha256': entry['manifest_sha256'],
               'qa_staging': (entry.get('publication') or {}).get('mode') == 'qa_staging'}
        if entry['state'] != 'draft':
            try:
                load_rubric(catalog.load(release_id, preview=True))
                row['package'] = 'verified_with_installed_runner'
            except CourseCatalogError as exc:
                row['package'] = 'unavailable'
                row['reason'] = str(exc)
        releases[release_id] = row
    identity = {
        'registry_sha256': hashlib.sha256(registry_bytes).hexdigest(),
        'catalog_source': 'application' if catalog.root.resolve() == CATALOG_ROOT.resolve() else 'configured',
        'new_enrollment_default': registry.get('new_enrollment_default'),
        'legacy_continuation': registry.get('legacy_continuation'),
        'releases': releases,
        'certification_code_sha256': code_digest(),
        'versioning_enabled': Settings().certification_versioning_enabled,
        'production_environment': production_environment(),
    }
    identity['fingerprint'] = hashlib.sha256(repr(sorted(identity.items())).encode()).hexdigest()
    return identity


def diagnose_release(catalog: CourseCatalog, release_id: str) -> dict:
    """Plain-language support diagnosis for one course version on this worker."""
    from .grading import load_rubric
    result = {'course_version': release_id, 'learner_work': INTACT_WORK}
    try:
        registry = catalog.registry()
    except CourseCatalogError:
        return {**result, 'status': 'catalog_unavailable',
                'explanation': 'This worker cannot read a valid course registry.',
                'next_step': 'Restore the deployed registry.json on every worker and compare deployment fingerprints.'}
    if release_id not in registry['releases']:
        return {**result, 'status': 'unknown_on_this_worker',
                'explanation': 'This worker does not have the course version the learner is enrolled in.',
                'next_step': 'Deploy the same course catalog to every API and Celery worker, then compare fingerprints.'}
    try:
        package = catalog.load(release_id, preview=True)
    except CourseCatalogError as exc:
        cause = exc.__cause__
        detail = str(cause) if isinstance(cause, ValueError) else 'A packaged file is missing or unreadable'
        return {**result, 'status': 'integrity_failed', 'detail': detail,
                'explanation': 'The installed package differs from the digest the learner\'s enrollment pins.',
                'next_step': 'Restore the exact published package bytes; never re-hash or edit a published release.'}
    try:
        catalog.load(release_id)
    except CourseCatalogError as exc:
        return {**result, 'status': 'qa_staging_only' if package.entry.qa_staging else 'not_available_for_enrollment',
                'detail': str(exc),
                'explanation': 'The package is intact but this worker\'s lifecycle policy refuses it.',
                'next_step': 'Check the registry state and environment for this worker.'}
    try:
        load_rubric(package)
    except CourseCatalogError as exc:
        return {**result, 'status': 'runner_unavailable', 'detail': str(exc),
                'explanation': 'Teaching is available but this worker cannot grade the pinned rubric.',
                'next_step': 'Deploy the application build whose installed runner matches the package rubric.'}
    return {**result, 'status': 'available', 'manifest_sha256': package.manifest_sha256,
            'explanation': 'This worker serves the exact pinned package and its grading runner.'}
