"""Local release authoring. These operations never read or change learners."""
from contextlib import contextmanager
import datetime
import fcntl
import json
import os
from pathlib import Path
import tempfile

from .catalog import (CATALOG_ROOT, QA_STAGING_MARKER, QA_STAGING_WAIVABLE, CourseCatalog, CourseCatalogError,
                      PublicationRecord, production_environment)
from .grading import load_rubric


@contextmanager
def authoring_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    # Lock a stable inode; replacing registry.json must not invalidate the lock.
    with (root / '.authoring.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_registry(root: Path, registry: dict):
    """Validate the whole proposed registry before an atomic replacement."""
    with tempfile.TemporaryDirectory(prefix='.registry-', dir=root) as staging:
        candidate = Path(staging) / 'registry.json'
        candidate.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n')
        CourseCatalog(Path(staging)).registry()
        with candidate.open('rb') as handle:
            os.fsync(handle.fileno())
        os.replace(candidate, root / 'registry.json')


def publish(catalog: CourseCatalog, release_id: str, *, expected_digest: str,
            impact_report=None, source_catalog=None, inventory=None, qa_staging=None):
    """Publish exactly a reviewed draft; do not choose any enrollment default.

    ``qa_staging`` ({'reason', 'actor'}) publishes a marked QA package to a
    separate staging catalog. Only the production-evidence findings named in
    QA_STAGING_WAIVABLE are waived, and the registry records that the release
    is not production-authorized; production processes refuse to serve it.
    """
    with authoring_lock(catalog.root):
        package = catalog.load(release_id, preview=True)
        if package.entry.state != 'draft' or package.manifest_sha256 != expected_digest:
            raise CourseCatalogError('Publication requires the exact reviewed draft')
        marked = QA_STAGING_MARKER in package.manifest.artifacts
        if qa_staging is not None:
            if production_environment():
                raise CourseCatalogError('QA staging publication is refused in a production environment')
            if catalog.root.resolve() == CATALOG_ROOT.resolve():
                raise CourseCatalogError('QA staging releases belong in a separate staging catalog, never the application catalog')
            if not marked:
                raise CourseCatalogError('QA staging publication requires a package built with its QA staging marker')
        elif marked:
            raise CourseCatalogError('A QA staging package cannot be published for production')
        from .outcomes import package_outcomes
        outcomes = package_outcomes(package)
        if outcomes is not None and outcomes.state != 'release_candidate':
            raise CourseCatalogError('Publication requires verified outcome assessments and authored teaching')
        from .progression_policy import package_progression_policy
        policy = package_progression_policy(package)
        if policy is not None and policy.state != 'release_candidate':
            raise CourseCatalogError('Publication requires the reviewed progression policy')
        load_rubric(package)
        # Initial preservation of the frozen continuation baseline retains its
        # existing path. Authored courses and outcome-based courses additionally
        # need the exact impact review; readiness metadata alone is insufficient.
        record = {'mode': 'production', 'production_authorized': True,
                  'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        if outcomes is not None or package.manifest.historical_provenance != 'continuation-baseline' or qa_staging is not None:
            from .release_impact import require_publication_impact
            current = require_publication_impact(catalog, release_id, report=impact_report,
                                                 source_catalog=source_catalog, inventory=inventory,
                                                 waivable=QA_STAGING_WAIVABLE if qa_staging is not None else ())
            record.update(impact_report_sha256=current['report_sha256'],
                          source_release_id=current['source']['course_version'])
            if qa_staging is not None:
                record.update(mode='qa_staging', production_authorized=False,
                              waived_findings=sorted(item['code'] for item in current['blocking_findings']),
                              reason=str(qa_staging.get('reason') or '').strip(),
                              actor=str(qa_staging.get('actor') or '').strip())
        try:
            PublicationRecord.model_validate(record)
        except ValueError as exc:
            raise CourseCatalogError('QA staging publication needs a reason of at least five characters and an actor') from exc
        registry = catalog.registry()
        registry['releases'][release_id].update(state='published', supported_for_existing=True, publication=record)
        write_registry(catalog.root, registry)
        return record


def retire(catalog: CourseCatalog, release_id: str):
    """Close new enrollment while retaining supported requirements and assets."""
    with authoring_lock(catalog.root):
        package = catalog.load(release_id)
        if package.entry.state != 'published':
            raise CourseCatalogError('Only a published course can be retired')
        registry = catalog.registry()
        if registry.get('new_enrollment_default') == release_id:
            raise CourseCatalogError('Choose a supported new learner default before retiring this course')
        registry['releases'][release_id]['state'] = 'retired'
        write_registry(catalog.root, registry)


def choose_default(catalog: CourseCatalog, release_id: str, *, legacy_continuation: bool = False, reviews_root=None):
    """Set initialization policy only; existing selections are never updated."""
    with authoring_lock(catalog.root):
        package = catalog.load(release_id, new_enrollment=not legacy_continuation)
        if legacy_continuation and package.manifest.historical_provenance != 'continuation-baseline':
            raise CourseCatalogError('Unknown legacy history requires a continuation baseline')
        if not legacy_continuation:
            # Offering an authored course to new learners advertises it as
            # current; that needs a recorded review of this exact manifest.
            from .compatibility_reviews import REVIEWS_ROOT, require_compatible
            require_compatible(package, reviews_root or REVIEWS_ROOT)
        registry = catalog.registry()
        key = 'legacy_continuation' if legacy_continuation else 'new_enrollment_default'
        registry[key] = release_id
        registry['transition_policy'] = 'optional'
        write_registry(catalog.root, registry)
