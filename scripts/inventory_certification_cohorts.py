#!/usr/bin/env python3
"""Explicit read-only aggregate inventory; no application startup or mutations."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from app.services.certification_versions.cohort_inventory import inventory  # noqa: E402


async def run(args):
    uri = os.environ.get('CERTIFICATION_INVENTORY_MONGO_URL')
    if not uri:
        raise ValueError('Set CERTIFICATION_INVENTORY_MONGO_URL explicitly; the application connection is never reused')
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000, appname='certification-read-only-inventory')
    try:
        report = await inventory(client[args.database], max_records=args.max_records)
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Explicit authorized database; use a read-only database credential')
    parser.add_argument('--max-records', type=int, default=100000)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # Driver errors can contain hostnames/URIs; do not echo secrets.
        print(f'Inventory failed ({type(exc).__name__}); no report was produced. Check connectivity, record limits and concurrent changes.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
