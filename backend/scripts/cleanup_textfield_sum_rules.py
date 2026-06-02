"""One-shot cleanup: repair sum_equals cross-field rules that include a
non-numeric (text/categorical) operand.

Before the suggester gained a numeric gate, it could pull a text field — e.g.
"Educational Materials Target Audience" — into a numeric sum_equals rule because
its name shared a part token ("materials"). Those operands never parse, so every
evaluation was silently dropped as "unparseable" and quietly eroded the pass
rate. New suggestions are now gated; this fixes rules already saved.

For each SearchSet with cross_field_rules, we recompute each field's numeric-ness
(from sampled validation-run values, then enum/name heuristics) and strip
non-numeric operands from sum_equals rules. A rule whose target is non-numeric,
or which drops below two numeric operands, is removed.

Idempotent: a search set whose rules are already clean is left untouched.

Usage:
    uv run python -m scripts.cleanup_textfield_sum_rules          # apply
    uv run python -m scripts.cleanup_textfield_sum_rules --dry-run  # report only
"""

from __future__ import annotations

import asyncio
import sys

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.search_set import SearchSet, SearchSetItem
from app.models.validation_run import ValidationRun
from app.services.cross_field_rules import (
    normalize_rules,
    sanitize_sum_equals_rules,
)
from app.services.search_set_service import (
    get_extraction_field_metadata,
    infer_numeric_fields,
)


async def cleanup(dry_run: bool = False) -> dict[str, int]:
    settings = Settings()
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_host)
    db = client[settings.mongo_db]
    await init_beanie(
        database=db,
        document_models=[SearchSet, SearchSetItem, ValidationRun],
    )

    scanned = 0
    changed = 0
    rules_removed = 0
    operands_removed = 0

    sets = await SearchSet.find({"cross_field_rules": {"$ne": []}}).to_list()
    for ss in sets:
        if not ss.cross_field_rules:
            continue
        scanned += 1

        field_metadata = await get_extraction_field_metadata(ss.uuid)
        numeric_by_field = await infer_numeric_fields(ss.uuid)
        for fm in field_metadata:
            if fm.get("key") in numeric_by_field:
                fm["is_numeric"] = numeric_by_field[fm["key"]]

        rules = ss.normalized_cross_field_rules()
        before = len(rules)
        cleaned, notes = sanitize_sum_equals_rules(field_metadata, rules)
        if not notes:
            continue

        changed += 1
        rules_removed += before - len(cleaned)
        operands_removed += sum(1 for n in notes if n.startswith("removed "))
        label = f"[{ss.uuid}] {ss.title!r}"
        print(f"{'(dry-run) ' if dry_run else ''}{label}")
        for note in notes:
            print(f"    - {note}")

        if not dry_run:
            ss.cross_field_rules = normalize_rules(cleaned)
            await ss.save()

    return {
        "scanned": scanned,
        "changed": changed,
        "rules_removed": rules_removed,
        "operands_removed": operands_removed,
    }


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = asyncio.run(cleanup(dry_run=dry))
    print(
        f"\n{'Dry run' if dry else 'Cleanup'} complete: "
        f"scanned={result['scanned']} sets, changed={result['changed']}, "
        f"rules_removed={result['rules_removed']}, "
        f"operands_removed={result['operands_removed']}"
    )
