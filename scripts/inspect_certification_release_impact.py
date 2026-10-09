#!/usr/bin/env python3
"""Print a read-only, exact-package certification publication impact report.

Exit 2 means release gates remain open; no publication or migration is attempted.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError  # noqa: E402
from app.services.certification_versions.release_impact import inspect_catalogs as inspect  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-catalog-root', type=Path, default=CATALOG_ROOT)
    parser.add_argument('--target-catalog-root', type=Path, default=CATALOG_ROOT)
    parser.add_argument('--source-release-id', required=True)
    parser.add_argument('--target-release-id', required=True)
    parser.add_argument('--cohort-inventory', type=Path, help='Aggregate output of inventory_certification_cohorts.py; optional for draft inspection')
    args = parser.parse_args()
    try:
        inventory = json.loads(args.cohort_inventory.read_text()) if args.cohort_inventory else None
        report = inspect(CourseCatalog(args.source_catalog_root), args.source_release_id,
                         CourseCatalog(args.target_catalog_root), args.target_release_id, inventory=inventory)
    except (CourseCatalogError, ValueError, OSError) as exc:
        print(f'Impact inspection failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report['blocking_findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
