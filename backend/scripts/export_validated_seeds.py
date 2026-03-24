"""Export validated seed data back to seed JSON files.

After running real validations against seeded extraction templates,
this script captures the validation results (quality scores, tiers, grades)
back into the seed files so future deployments start with real quality data.

Usage:
    cd backend
    python -m scripts.export_validated_seeds
"""

import asyncio
import json
import logging
import pathlib

from app.config import Settings
from app.database import init_db
from app.models.extraction_test_case import ExtractionTestCase
from app.models.search_set import SearchSet, SearchSetItem
from app.models.verification import VerifiedItemMetadata

logger = logging.getLogger(__name__)

SEEDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "seeds" / "search_sets"


async def export_validated_seeds():
    """Export validated quality data back to seed JSON files."""
    print("Exporting validated seed data...\n")

    ss_dir = SEEDS_DIR
    updated = 0

    for ss_file in sorted(ss_dir.glob("*.json")):
        data = json.loads(ss_file.read_text())
        meta = data.get("_seed_meta", {})
        seed_id = meta.get("seed_id")
        if not seed_id:
            continue

        # Find the seeded search set in the database
        ss = await SearchSet.find_one({"extraction_config.seed_id": seed_id})
        if not ss:
            print(f"  SKIP {ss_file.name}: not found in database")
            continue

        # Get verified metadata with quality scores
        vm = await VerifiedItemMetadata.find_one(
            VerifiedItemMetadata.item_kind == "search_set",
            VerifiedItemMetadata.item_id == str(ss.id),
        )

        # Update quality data in seed meta
        if vm and vm.quality_score is not None:
            meta["quality_tier"] = vm.quality_tier
            meta["quality_score"] = vm.quality_score
            meta["quality_grade"] = vm.quality_grade
            if vm.last_validated_at:
                meta["last_validated_at"] = vm.last_validated_at.isoformat()
            print(f"  {meta.get('display_name', seed_id)}: "
                  f"score={vm.quality_score}, tier={vm.quality_tier}, grade={vm.quality_grade}")
        else:
            print(f"  {meta.get('display_name', seed_id)}: no validation data yet")

        # Export current items (in case fields were added/modified)
        items_db = await ss.get_items()
        if ss.item_order:
            order_map = {oid: idx for idx, oid in enumerate(ss.item_order)}
            items_db.sort(key=lambda i: order_map.get(str(i.id), len(order_map)))

        items_out = []
        for it in items_db:
            items_out.append({
                "searchphrase": it.searchphrase,
                "searchtype": it.searchtype,
                "is_optional": it.is_optional,
                "enum_values": it.enum_values,
            })

        # Export text-based test cases
        test_cases = await ExtractionTestCase.find(
            ExtractionTestCase.search_set_uuid == ss.uuid,
        ).to_list()
        tc_out = []
        for tc in test_cases:
            if tc.source_type == "text" and tc.source_text:
                tc_out.append({
                    "label": tc.label,
                    "source_type": tc.source_type,
                    "source_text": tc.source_text,
                    "expected_values": tc.expected_values,
                })

        # Rebuild the export item
        item = data["items"][0]
        item["items"] = items_out
        item["test_cases"] = tc_out

        data["_seed_meta"] = meta
        data["items"] = [item]

        # Write back
        ss_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        updated += 1

    print(f"\nDone! Updated {updated} seed file(s).")


async def main():
    settings = Settings()
    await init_db(settings)
    await export_validated_seeds()


if __name__ == "__main__":
    asyncio.run(main())
