#!/usr/bin/env python3
"""Print this process's certification release fingerprint; never reads learners.

Run it inside every API and Celery worker container (same environment as the
service). All workers must print the same fingerprint before a course release
is enabled. Exit 2 means a non-draft release cannot be served with its rubric
or the fingerprint differs from --expect.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.catalog import CourseCatalog, CourseCatalogError, configured_root  # noqa: E402
from app.services.certification_versions.release_coherence import deployment_identity  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-root', type=Path, default=None)
    parser.add_argument('--expect', help='Fingerprint printed by another worker')
    args = parser.parse_args()
    try:
        identity = deployment_identity(CourseCatalog(args.catalog_root or configured_root()))
    except (CourseCatalogError, OSError) as exc:
        print(f'Cannot read the course catalog: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(identity, indent=2, sort_keys=True))
    problems = [f'{release_id}: {row.get("reason", "unavailable")}' for release_id, row in identity['releases'].items()
                if row.get('package') == 'unavailable']
    if args.expect and args.expect != identity['fingerprint']:
        problems.append(f'fingerprint {identity["fingerprint"]} differs from expected {args.expect}')
    for problem in problems:
        print(f'INCOHERENT {problem}', file=sys.stderr)
    return 2 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
