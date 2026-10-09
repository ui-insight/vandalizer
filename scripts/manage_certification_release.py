#!/usr/bin/env python3
"""Manage local course release metadata without changing any learner records."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.authoring import choose_default, publish, retire  # noqa: E402
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-root', type=Path, default=CATALOG_ROOT)
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('inspect', 'publish', 'retire', 'default', 'legacy-continuation'):
        command = actions.add_parser(action)
        command.add_argument('release_id')
        if action == 'publish':
            command.add_argument('--expected-manifest-sha256', required=True)
            command.add_argument('--impact-report', type=Path, help='Exact reviewed impact report; required for authored/outcome courses')
            command.add_argument('--source-catalog-root', type=Path, help='Source catalog used by the impact inspector; defaults to the target catalog')
            command.add_argument('--cohort-inventory', type=Path, help='Same aggregate inventory used in the reviewed impact report')
    args = parser.parse_args()
    catalog = CourseCatalog(args.catalog_root)
    if args.action == 'publish':
        report = json.loads(args.impact_report.read_text()) if args.impact_report else None
        inventory = json.loads(args.cohort_inventory.read_text()) if args.cohort_inventory else None
        source = CourseCatalog(args.source_catalog_root) if args.source_catalog_root else catalog
        publish(catalog, args.release_id, expected_digest=args.expected_manifest_sha256,
                impact_report=report, source_catalog=source, inventory=inventory)
    elif args.action == 'retire':
        retire(catalog, args.release_id)
    elif args.action in ('default', 'legacy-continuation'):
        choose_default(catalog, args.release_id, legacy_continuation=args.action == 'legacy-continuation')
    print(json.dumps(catalog.load(args.release_id, preview=True).summary(), indent=2))
    if args.action != 'inspect':
        print('Local release metadata updated. No learner records were changed.')


if __name__ == '__main__':
    try:
        main()
    except (CourseCatalogError, ValueError, OSError) as exc:
        print(f'Release operation refused: {exc}', file=sys.stderr)
        sys.exit(2)
