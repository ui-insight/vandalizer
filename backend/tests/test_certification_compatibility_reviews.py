"""A material product change forces a recorded review before a course stays current."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.services.certification_versions.authoring import choose_default
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.compatibility_reviews import CHECKS

SOURCE = 'legacy-2026-10-02.1'
AUTHORED = 'authored-course-test'
SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
spec = importlib.util.spec_from_file_location('cert_release_check', SCRIPTS / 'check_certification_releases.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode().strip()


def review(manifest_sha256, commit='a' * 40, *, failed=()):
    return {'schema_version': 1, 'release_id': AUTHORED, 'manifest_sha256': manifest_sha256,
            'product_commit': commit, 'product_change_report_sha256': 'c' * 64,
            'checks': {name: {'result': 'failed' if name in failed else 'passed', 'evidence': f'{name} evidence'} for name in CHECKS},
            'result': 'incompatible' if failed else 'compatible', 'unresolved_limits': [],
            'reviewer_role': 'Course owner', 'reviewed_at': datetime.datetime(2026, 10, 15, tzinfo=datetime.timezone.utc).isoformat()}


def authored_catalog(root):
    """A published authored course; registry written directly as in a reviewed repository."""
    courses = root / 'backend/certification-data/courses'
    shutil.copytree(CATALOG_ROOT, courses)
    shutil.copytree(courses / SOURCE, courses / AUTHORED)
    manifest = json.loads((courses / AUTHORED / 'manifest.json').read_text())
    manifest.update(release_id=AUTHORED, historical_provenance='authored-release')
    (courses / AUTHORED / 'manifest.json').write_text(json.dumps(manifest))
    registry = json.loads((courses / 'registry.json').read_text())
    registry['releases'][AUTHORED] = {'state': 'published', 'supported_for_existing': True,
                                      'manifest_sha256': hashlib.sha256((courses / AUTHORED / 'manifest.json').read_bytes()).hexdigest()}
    (courses / 'registry.json').write_text(json.dumps(registry))
    return CourseCatalog(courses)


def write_review(reviews, value):
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / f'{AUTHORED}.json').write_text(json.dumps(value))


def test_authored_course_cannot_be_offered_as_current_without_a_matching_compatible_review(tmp_path):
    catalog = authored_catalog(tmp_path)
    reviews = tmp_path / 'reviews'
    digest = catalog.load(AUTHORED).manifest_sha256
    with pytest.raises(CourseCatalogError, match='Record a compatibility review'):
        choose_default(catalog, AUTHORED, reviews_root=reviews)
    write_review(reviews, review('d' * 64))
    with pytest.raises(CourseCatalogError, match='different manifest'):
        choose_default(catalog, AUTHORED, reviews_root=reviews)
    write_review(reviews, review(digest, failed=('labs',)))
    with pytest.raises(CourseCatalogError, match='incompatible: labs'):
        choose_default(catalog, AUTHORED, reviews_root=reviews)
    incomplete = review(digest)
    incomplete['checks'].pop('rubrics')
    write_review(reviews, incomplete)
    with pytest.raises(CourseCatalogError, match='every maintenance check'):
        choose_default(catalog, AUTHORED, reviews_root=reviews)
    assert 'new_enrollment_default' not in catalog.registry()
    write_review(reviews, review(digest))
    choose_default(catalog, AUTHORED, reviews_root=reviews)
    assert catalog.registry()['new_enrollment_default'] == AUTHORED
    # The continuation baseline is preservation, not a new current-course claim.
    registry = catalog.registry()
    registry['releases'][SOURCE].update(state='published', supported_for_existing=True)
    (catalog.root / 'registry.json').write_text(json.dumps(registry))
    choose_default(catalog, SOURCE, reviews_root=tmp_path / 'none')


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    catalog = authored_catalog(root)
    registry = catalog.registry()
    registry['new_enrollment_default'] = AUTHORED
    (catalog.root / 'registry.json').write_text(json.dumps(registry))
    git(root, 'init')
    git(root, 'config', 'user.name', 'Synthetic QA')
    git(root, 'config', 'user.email', 'qa@example.test')
    (root / 'backend/app/services').mkdir(parents=True)
    (root / 'backend/app/services/workflow_engine.py').write_text('VERSION = 1\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Reviewed product')
    reviews = root / 'backend/certification-data/compatibility-reviews'
    write_review(reviews, review(catalog.load(AUTHORED).manifest_sha256, git(root, 'rev-parse', 'HEAD')))
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Record the compatibility review')
    return root, catalog, reviews


def test_ci_requires_a_new_review_after_a_material_product_change(repository):
    root, catalog, reviews = repository
    assert checker.check_current_review(catalog, root, reviews).result == 'compatible'
    (root / 'notes.md').write_text('Not a product input\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Notes only')
    assert checker.check_current_review(catalog, root, reviews) is not None
    (root / 'backend/app/services/workflow_engine.py').write_text('VERSION = 2\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Changed lab execution')
    with pytest.raises(CourseCatalogError, match='require a new recorded review.*workflow_engine.py'):
        checker.check_current_review(catalog, root, reviews)
    updated = review(catalog.load(AUTHORED).manifest_sha256, git(root, 'rev-parse', 'HEAD'))
    write_review(reviews, updated)
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Record the new review')
    assert checker.check_current_review(catalog, root, reviews).product_commit == updated['product_commit']


def test_ci_rejects_a_review_of_an_unrelated_commit_and_qa_releases_in_the_application_catalog(repository):
    root, catalog, reviews = repository
    write_review(reviews, review(catalog.load(AUTHORED).manifest_sha256, 'f' * 40))
    with pytest.raises(CourseCatalogError, match='outside this history'):
        checker.check_current_review(catalog, root, reviews)
    registry = catalog.registry()
    registry['releases'][AUTHORED]['publication'] = {
        'mode': 'qa_staging', 'production_authorized': False, 'recorded_at': '2026-10-15T00:00:00+00:00',
        'impact_report_sha256': 'e' * 64, 'source_release_id': SOURCE, 'waived_findings': ['rollout_evidence_required'],
        'reason': 'Staging QA', 'actor': 'qa-operator'}
    (catalog.root / 'registry.json').write_text(json.dumps(registry))
    with pytest.raises(CourseCatalogError, match='separate staging catalog'):
        checker.check_no_qa_staging(catalog.load(AUTHORED, preview=True))
