#!/usr/bin/env python3
"""Print a read-only, exact-package certification publication impact report.

The JSON report goes to stdout; save it and pass the same file to publication.
A short reviewer summary of changes and blocking reasons goes to stderr.
Exit 2 means release gates remain open; no publication or migration is attempted.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.catalog import CourseCatalog, CourseCatalogError, configured_root  # noqa: E402
from app.services.certification_versions.catalog import QA_STAGING_WAIVABLE  # noqa: E402
from app.services.certification_versions.release_impact import change_summary  # noqa: E402
from app.services.certification_versions.release_impact import inspect_catalogs as inspect  # noqa: E402


def reviewer_summary(report):
    changes = change_summary(report)
    lines = [f"Target {changes['target']} manifest {changes['target_manifest_sha256']}",
             f"Compared with {changes['source']}; report {changes['report_sha256']}"]
    for kind in ('modules', 'lessons', 'outcomes', 'artifacts'):
        counts = ', '.join(f"{len(changes[f'{kind}_{change}'])} {change}" for change in ('added', 'removed', 'changed'))
        lines.append(f'{kind}: {counts}')
    if changes['outcomes_requiring_compatibility_review']:
        lines.append(f"Outcomes needing compatibility review: {len(changes['outcomes_requiring_compatibility_review'])}")
    for item in report['blocking_findings']:
        qa = ' [QA staging may waive]' if item['code'] in QA_STAGING_WAIVABLE else ''
        lines.append(f"BLOCKED {item['code']}{qa}: {item['action']}")
    if not report['blocking_findings']:
        lines.append('No blocking findings.')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-catalog-root', type=Path, default=None)
    parser.add_argument('--target-catalog-root', type=Path, default=None)
    parser.add_argument('--source-release-id', required=True)
    parser.add_argument('--target-release-id', required=True)
    parser.add_argument('--cohort-inventory', type=Path, help='Aggregate output of inventory_certification_cohorts.py; optional for draft inspection')
    args = parser.parse_args()
    try:
        inventory = json.loads(args.cohort_inventory.read_text()) if args.cohort_inventory else None
        report = inspect(CourseCatalog(args.source_catalog_root or configured_root()), args.source_release_id,
                         CourseCatalog(args.target_catalog_root or configured_root()), args.target_release_id, inventory=inventory)
    except (CourseCatalogError, ValueError, OSError) as exc:
        print(f'Impact inspection failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print(reviewer_summary(report), file=sys.stderr)
    return 2 if report['blocking_findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
