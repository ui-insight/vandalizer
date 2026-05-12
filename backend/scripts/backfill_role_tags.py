"""One-shot backfill: derive role_tags for existing verified items.

Walks every APPROVED VerificationRequest, finds (or creates) the corresponding
VerifiedItemMetadata, runs the role_inference normalizer over the submitter's
declared role + intended-use tags, and writes role_tags if currently empty.

Idempotent: only writes when role_tags is empty. Safe to re-run.

Usage:
    uv run python -m scripts.backfill_role_tags --dry-run
    uv run python -m scripts.backfill_role_tags

The --dry-run flag prints proposed changes without writing. Run dry first
on prod to inspect the role distribution and flag any unexpected tokens
that should be added to the keyword map in app/services/role_inference.py.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
from collections import Counter

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.verification import (
    VerificationRequest,
    VerificationStatus,
    VerifiedItemMetadata,
)
from app.services.role_inference import normalize_role_tags


async def backfill(dry_run: bool) -> dict[str, int]:
    settings = Settings()
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_host)
    db = client[settings.mongo_db]
    await init_beanie(
        database=db,
        document_models=[VerificationRequest, VerifiedItemMetadata],
    )

    approved = await VerificationRequest.find(
        VerificationRequest.status == VerificationStatus.APPROVED.value
    ).to_list()

    role_dist: Counter[str] = Counter()
    untagged_examples: list[str] = []
    counts = {
        "approved_requests": len(approved),
        "tagged": 0,
        "skipped_already_tagged": 0,
        "skipped_no_signal": 0,
        "metadata_created": 0,
        "metadata_updated": 0,
    }

    now = datetime.datetime.now(datetime.timezone.utc)

    for req in approved:
        derived = normalize_role_tags(req.submitter_role, req.intended_use_tags)

        if not derived:
            counts["skipped_no_signal"] += 1
            if req.submitter_role or req.intended_use_tags:
                # Capture a few examples of inputs that normalized to nothing,
                # so we can tune the keyword map.
                if len(untagged_examples) < 10:
                    untagged_examples.append(
                        f"  submitter_role={req.submitter_role!r} "
                        f"intended_use_tags={req.intended_use_tags!r}"
                    )
            continue

        meta = await VerifiedItemMetadata.find_one(
            VerifiedItemMetadata.item_kind == req.item_kind,
            VerifiedItemMetadata.item_id == str(req.item_id),
        )

        if meta and meta.role_tags:
            counts["skipped_already_tagged"] += 1
            continue

        for r in derived:
            role_dist[r] += 1

        if dry_run:
            counts["tagged"] += 1
            print(
                f"  WOULD tag {req.item_kind}/{req.item_id} → {derived} "
                f"(from submitter_role={req.submitter_role!r}, "
                f"intended_use_tags={req.intended_use_tags!r})"
            )
            continue

        if meta:
            meta.role_tags = derived
            meta.updated_at = now
            await meta.save()
            counts["metadata_updated"] += 1
        else:
            meta = VerifiedItemMetadata(
                item_kind=req.item_kind,
                item_id=str(req.item_id),
                role_tags=derived,
                updated_at=now,
            )
            await meta.insert()
            counts["metadata_created"] += 1
        counts["tagged"] += 1

    print()
    print("=" * 60)
    print(f"Backfill complete (dry_run={dry_run})")
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print()
    print("Role distribution (each tag = +1 to role's count):")
    for role, n in role_dist.most_common():
        print(f"  {role}: {n}")
    if untagged_examples:
        print()
        print(f"Examples of inputs that did not match any role keyword ({len(untagged_examples)} shown):")
        for ex in untagged_examples:
            print(ex)
        print()
        print(
            "Consider adding new keywords to app/services/role_inference.py "
            "if any of these should map to a canonical role."
        )

    return counts


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed changes without writing.",
    )
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    _main()
