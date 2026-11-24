#!/usr/bin/env python3
"""Manage local course release metadata without changing any learner records."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.authoring import choose_default, publish, retire  # noqa: E402
from app.services.certification_versions.catalog import CourseCatalog, CourseCatalogError, configured_root  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-root', type=Path, default=None,
                        help='Catalog to edit; defaults to CERTIFICATION_CATALOG_ROOT or the application catalog')
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('inspect', 'publish', 'retire', 'default', 'legacy-continuation'):
        command = actions.add_parser(action)
        command.add_argument('release_id')
        if action == 'publish':
            command.add_argument('--expected-manifest-sha256', required=True)
            command.add_argument('--impact-report', type=Path, help='Exact reviewed impact report; required for authored/outcome courses')
            command.add_argument('--source-catalog-root', type=Path, help='Source catalog used by the impact inspector; defaults to the target catalog')
            command.add_argument('--cohort-inventory', type=Path, help='Same aggregate inventory used in the reviewed impact report')
            command.add_argument('--qa-staging', action='store_true',
                                 help='Publish a marked QA package to a separate staging catalog; recorded as not production-authorized')
            command.add_argument('--reason', help='Why this QA staging publication is needed (required with --qa-staging)')
            command.add_argument('--actor', help='Who authorized this QA staging publication (required with --qa-staging)')
    args = parser.parse_args()
    catalog = CourseCatalog(args.catalog_root if args.catalog_root is not None else configured_root())
    print(f'Catalog: {catalog.root}', file=sys.stderr)
    record = None
    if args.action == 'publish':
        report = json.loads(args.impact_report.read_text()) if args.impact_report else None
        inventory = json.loads(args.cohort_inventory.read_text()) if args.cohort_inventory else None
        source = CourseCatalog(args.source_catalog_root) if args.source_catalog_root else catalog
        qa = {'reason': args.reason, 'actor': args.actor} if args.qa_staging else None
        record = publish(catalog, args.release_id, expected_digest=args.expected_manifest_sha256,
                         impact_report=report, source_catalog=source, inventory=inventory, qa_staging=qa)
    elif args.action == 'retire':
        retire(catalog, args.release_id)
    elif args.action in ('default', 'legacy-continuation'):
        choose_default(catalog, args.release_id, legacy_continuation=args.action == 'legacy-continuation')
    output = {'release': catalog.load(args.release_id, preview=True).summary()}
    if record is not None:
        output['publication'] = record
        if report is not None:
            from app.services.certification_versions.release_impact import change_summary
            output['changes'] = change_summary(report)
    if args.action != 'inspect':
        registry = catalog.registry()
        output['registry'] = {key: registry.get(key) for key in ('new_enrollment_default', 'legacy_continuation')}
    print(json.dumps(output, indent=2))
    if args.action != 'inspect':
        print('Local release metadata updated. No learner records were changed.')


if __name__ == '__main__':
    try:
        main()
    except (CourseCatalogError, ValueError, OSError) as exc:
        print(f'Release operation refused: {exc}', file=sys.stderr)
        sys.exit(2)
