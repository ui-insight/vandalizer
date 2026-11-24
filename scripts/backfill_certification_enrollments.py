#!/usr/bin/env python3
"""Legacy certification enrollment backfill: read-only dry run by default.

Run the dry run (a read-only database credential is sufficient), review the
plan, then apply exactly that plan with --apply --expected-plan-sha256. Apply
never writes legacy progress; rerun the dry run after any interruption.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from app.services.certification_versions import legacy_backfill  # noqa: E402
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog  # noqa: E402


async def run(args):
    uri = os.environ.get('CERTIFICATION_BACKFILL_MONGO_URL')
    if not uri:
        raise ValueError('Set CERTIFICATION_BACKFILL_MONGO_URL explicitly; the application connection is never reused')
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000, appname='certification-legacy-backfill')
    catalog = CourseCatalog(Path(args.catalog_root))
    try:
        database = client[args.database]
        if not args.apply:
            report = await legacy_backfill.dry_run(database, catalog, max_records=args.max_records)
        else:
            from beanie import init_beanie
            from app.models.certification import CertificationEnrollment, CertificationEnrollmentSelection, CertificationProgress
            from app.services.certification_versions.enrollments import EnrollmentRepository
            await init_beanie(database=database, document_models=[CertificationEnrollment, CertificationEnrollmentSelection, CertificationProgress])
            report = await legacy_backfill.apply(EnrollmentRepository(catalog), database,
                                                 expected_plan_sha256=args.expected_plan_sha256, max_records=args.max_records)
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0 if args.apply is False or report['reconciled'] else 3
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Explicit authorized database')
    parser.add_argument('--catalog-root', default=str(CATALOG_ROOT))
    parser.add_argument('--max-records', type=int, default=100000)
    parser.add_argument('--apply', action='store_true', help='Write enrollments for the reviewed plan')
    parser.add_argument('--expected-plan-sha256', help='plan_sha256 from the reviewed dry run (required with --apply)')
    args = parser.parse_args()
    if args.apply and not args.expected_plan_sha256:
        parser.error('--apply requires --expected-plan-sha256 from a reviewed dry run')
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        # Driver errors can contain hostnames/URIs; do not echo secrets.
        print(f'Backfill failed ({type(exc).__name__}); rerun the dry run to see the current state before retrying.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
