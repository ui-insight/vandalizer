#!/usr/bin/env python3
"""Verify packages and reject mutation/removal of previously published releases.

Also keeps QA staging releases out of the application catalog, and requires a
current recorded compatibility review for an authored course offered to new
learners: a watched product change after the reviewed commit fails the check.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from app.services.certification_versions.catalog import CATALOG_ROOT, QA_STAGING_MARKER, CourseCatalog, CourseCatalogError  # noqa: E402
from app.services.certification_versions.compatibility_reviews import REVIEWS_ROOT, require_compatible, stale_paths  # noqa: E402
from app.services.certification_versions.grading import load_rubric  # noqa: E402

REGISTRY = 'backend/certification-data/courses/registry.json'


def check_published_history(previous: dict, current: dict):
    for release_id, old in previous.get('releases', {}).items():
        if old['state'] == 'draft':
            continue
        new = current.get('releases', {}).get(release_id)
        if new is None or new['manifest_sha256'] != old['manifest_sha256'] or new['state'] == 'draft':
            raise CourseCatalogError(f'Published course {release_id} was removed or changed; create a new release instead')
        if old['supported_for_existing'] and not new['supported_for_existing']:
            raise CourseCatalogError(f'Existing support for {release_id} cannot be silently removed')


def check_no_qa_staging(package):
    if package.entry.qa_staging or QA_STAGING_MARKER in package.manifest.artifacts:
        raise CourseCatalogError(f'{package.manifest.release_id} is a QA staging release; keep it in a separate staging catalog')


def check_current_review(catalog: CourseCatalog, root: Path = ROOT, reviews_root: Path = REVIEWS_ROOT, head: str = 'HEAD'):
    """The advertised course needs a review newer than every watched product change."""
    release_id = catalog.registry().get('new_enrollment_default')
    if not release_id:
        return None
    review = require_compatible(catalog.load(release_id, new_enrollment=True), reviews_root)
    if review is None:
        return None
    from inspect_certification_product_changes import inspect
    try:
        subprocess.run(['git', 'merge-base', '--is-ancestor', review.product_commit, head], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise CourseCatalogError(f'The compatibility review for {release_id} names a commit outside this history') from exc
    changed = stale_paths(inspect(root, review.product_commit, head)['changed_paths'])
    if changed:
        listed = ', '.join(item['path'] for item in changed[:10])
        raise CourseCatalogError(f'Product changes since the compatibility review of {release_id} require a new recorded review '
                                 f'before it stays the current course: {listed}')
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', help='Git revision whose published packages must remain unchanged')
    args = parser.parse_args()
    # Always the repository catalog, never a configured staging catalog.
    catalog = CourseCatalog(CATALOG_ROOT)
    current = catalog.registry()
    for release_id in current['releases']:
        package = catalog.load(release_id, preview=True)
        check_no_qa_staging(package)
        load_rubric(package)
        print(f'Verified {release_id} ({package.entry.state})')
    check_current_review(catalog)
    if args.base_ref:
        # A missing registry at a valid base is the initial introduction. A missing
        # git object is an error, never a reason to skip the publication guard.
        subprocess.run(['git', 'rev-parse', '--verify', f'{args.base_ref}^{{commit}}'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        listing = subprocess.check_output(['git', 'ls-tree', '--name-only', args.base_ref, REGISTRY], cwd=ROOT, text=True)
        if listing.strip():
            previous = json.loads(subprocess.check_output(['git', 'show', f'{args.base_ref}:{REGISTRY}'], cwd=ROOT))
            check_published_history(previous, current)


if __name__ == '__main__':
    main()
