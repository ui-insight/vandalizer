"""Local release authoring. These operations never read or change learners."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from .catalog import CourseCatalog, CourseCatalogError
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
            impact_report=None, source_catalog=None, inventory=None):
    """Publish exactly a reviewed draft; do not choose any enrollment default."""
    with authoring_lock(catalog.root):
        package = catalog.load(release_id, preview=True)
        if package.entry.state != 'draft' or package.manifest_sha256 != expected_digest:
            raise CourseCatalogError('Publication requires the exact reviewed draft')
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
        if outcomes is not None or package.manifest.historical_provenance != 'continuation-baseline':
            from .release_impact import require_publication_impact
            require_publication_impact(catalog, release_id, report=impact_report,
                                       source_catalog=source_catalog, inventory=inventory)
        registry = catalog.registry()
        registry['releases'][release_id].update(state='published', supported_for_existing=True)
        write_registry(catalog.root, registry)


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


def choose_default(catalog: CourseCatalog, release_id: str, *, legacy_continuation: bool = False):
    """Set initialization policy only; existing selections are never updated."""
    with authoring_lock(catalog.root):
        package = catalog.load(release_id, new_enrollment=not legacy_continuation)
        if legacy_continuation and package.manifest.historical_provenance != 'continuation-baseline':
            raise CourseCatalogError('Unknown legacy history requires a continuation baseline')
        registry = catalog.registry()
        key = 'legacy_continuation' if legacy_continuation else 'new_enrollment_default'
        registry[key] = release_id
        registry['transition_policy'] = 'optional'
        write_registry(catalog.root, registry)
