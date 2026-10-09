#!/usr/bin/env python3
"""Verify packages and reject mutation/removal of previously published releases."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.catalog import CourseCatalog, CourseCatalogError  # noqa: E402
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', help='Git revision whose published packages must remain unchanged')
    args = parser.parse_args()
    catalog = CourseCatalog()
    current = catalog.registry()
    for release_id in current['releases']:
        package = catalog.load(release_id, preview=True)
        load_rubric(package)
        print(f'Verified {release_id} ({package.entry.state})')
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
