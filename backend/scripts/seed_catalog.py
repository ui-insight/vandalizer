"""Seed the verified catalog with research administration workflows and extraction templates.

Creates verified workflows, search sets, metadata, and collections in the explore system.
Idempotent — safe to run multiple times; existing items are skipped.

Usage:
    cd backend
    python -m scripts.seed_catalog
"""

import asyncio
import datetime
import json
import logging
import pathlib
import uuid as uuid_mod

from beanie import PydanticObjectId

from app.config import Settings
from app.database import init_db
from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
from app.models.search_set import SearchSet, SearchSetItem
from app.models.verification import VerifiedCollection, VerifiedItemMetadata
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask

logger = logging.getLogger(__name__)

SEEDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "seeds"
SYSTEM_USER = "system"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_or_create_verified_library() -> Library:
    """Return the global verified library, creating if needed."""
    lib = await Library.find_one(Library.scope == LibraryScope.VERIFIED)
    if not lib:
        now = datetime.datetime.now(datetime.timezone.utc)
        lib = Library(
            scope=LibraryScope.VERIFIED,
            title="Verified Library",
            owner_user_id=SYSTEM_USER,
            created_at=now,
            updated_at=now,
        )
        await lib.insert()
    return lib


async def ensure_collection(title: str, description: str) -> VerifiedCollection:
    """Get or create a VerifiedCollection by title."""
    existing = await VerifiedCollection.find_one(VerifiedCollection.title == title)
    if existing:
        return existing
    now = datetime.datetime.now(datetime.timezone.utc)
    col = VerifiedCollection(
        title=title,
        description=description,
        item_ids=[],
        created_by_user_id=SYSTEM_USER,
        created_at=now,
        updated_at=now,
    )
    await col.insert()
    return col


async def add_to_collection(collection: VerifiedCollection, item_id: str):
    """Add an item ID to a collection if not already present."""
    if item_id not in collection.item_ids:
        collection.item_ids.append(item_id)
        collection.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await collection.save()


async def create_verified_metadata(
    item_kind: str, item_id: str, display_name: str, description: str, quality_tier: str = "gold",
):
    """Create VerifiedItemMetadata if it doesn't already exist."""
    existing = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    if existing:
        return existing
    now = datetime.datetime.now(datetime.timezone.utc)
    meta = VerifiedItemMetadata(
        item_kind=item_kind,
        item_id=item_id,
        display_name=display_name,
        description=description,
        quality_tier=quality_tier,
        quality_grade="A",
        quality_score=95,
        organization_ids=[],  # empty = globally visible
        updated_at=now,
    )
    await meta.insert()
    return meta


async def create_library_item(
    verified_lib: Library, item_id: PydanticObjectId, kind: LibraryItemKind,
):
    """Create a LibraryItem and add it to the verified library."""
    now = datetime.datetime.now(datetime.timezone.utc)
    lib_item = LibraryItem(
        item_id=item_id,
        kind=kind,
        added_by_user_id=SYSTEM_USER,
        verified=True,
        created_at=now,
    )
    await lib_item.insert()
    if lib_item.id not in verified_lib.items:
        verified_lib.items.append(lib_item.id)
    return lib_item


# ---------------------------------------------------------------------------
# Workflow seeding
# ---------------------------------------------------------------------------

async def seed_workflow(
    data: dict, meta: dict, verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> bool:
    """Seed a single workflow. Returns True if created, False if skipped."""
    seed_id = meta["seed_id"]

    # Idempotency: check if already seeded
    existing = await Workflow.find_one({"resource_config.seed_id": seed_id})
    if existing:
        return False

    item = data["items"][0]
    now = datetime.datetime.now(datetime.timezone.utc)

    # Create workflow steps and tasks
    step_ids: list[PydanticObjectId] = []
    for step_data in item.get("steps", []):
        task_ids: list[PydanticObjectId] = []
        for task_data in step_data.get("tasks", []):
            task = WorkflowStepTask(name=task_data["name"], data=task_data.get("data", {}))
            await task.insert()
            task_ids.append(task.id)

        step = WorkflowStep(
            name=step_data["name"],
            tasks=task_ids,
            data=step_data.get("data", {}),
            is_output=step_data.get("is_output", False),
        )
        await step.insert()
        step_ids.append(step.id)

    # Create workflow
    wf = Workflow(
        name=item["name"],
        description=item.get("description"),
        user_id=SYSTEM_USER,
        created_by_user_id=SYSTEM_USER,
        space="global",
        verified=True,
        steps=step_ids,
        resource_config={"seed_id": seed_id},
        input_config=item.get("input_config", {}),
        output_config=item.get("output_config", {}),
        validation_plan=item.get("validation_plan", []),
        validation_inputs=item.get("validation_inputs", []),
        created_at=now,
        updated_at=now,
    )
    await wf.insert()

    # Library item + metadata
    await create_library_item(verified_lib, wf.id, LibraryItemKind.WORKFLOW)
    await create_verified_metadata(
        "workflow", str(wf.id),
        meta.get("display_name", item["name"]),
        meta.get("description", item.get("description", "")),
        meta.get("quality_tier", "gold"),
    )

    # Add to collections
    for slug in meta.get("collections", []):
        col = slug_to_collection.get(slug)
        if col:
            await add_to_collection(col, str(wf.id))

    return True


# ---------------------------------------------------------------------------
# Search set seeding
# ---------------------------------------------------------------------------

async def seed_search_set(
    data: dict, meta: dict, verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> bool:
    """Seed a single search set. Returns True if created, False if skipped."""
    seed_id = meta["seed_id"]

    # Idempotency: check if already seeded
    existing = await SearchSet.find_one({"extraction_config.seed_id": seed_id})
    if existing:
        return False

    # Also skip if the old seed_domain_templates.py already created a matching template
    item = data["items"][0]
    old_template = await SearchSet.find_one(
        SearchSet.title == item["title"],
        SearchSet.verified == True,  # noqa: E712
    )
    if old_template:
        # Adopt the existing template: add metadata and collection membership
        await create_verified_metadata(
            "search_set", str(old_template.id),
            meta.get("display_name", item["title"]),
            meta.get("description", ""),
            meta.get("quality_tier", "gold"),
        )
        await create_library_item(verified_lib, old_template.id, LibraryItemKind.SEARCH_SET)
        for slug in meta.get("collections", []):
            col = slug_to_collection.get(slug)
            if col:
                await add_to_collection(col, str(old_template.id))
        # Mark as seeded for future runs
        old_template.extraction_config = {**old_template.extraction_config, "seed_id": seed_id}
        await old_template.save()
        return True

    # Create new search set
    ss_uuid = str(uuid_mod.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc)
    ss = SearchSet(
        title=item["title"],
        uuid=ss_uuid,
        space="global",
        status="active",
        set_type=item.get("set_type", "extraction"),
        is_global=True,
        verified=True,
        domain=meta.get("domain"),
        extraction_config={**item.get("extraction_config", {}), "seed_id": seed_id},
        created_at=now,
    )
    await ss.insert()

    # Create items
    item_order: list[str] = []
    for field in item.get("items", []):
        ssi = SearchSetItem(
            searchphrase=field["searchphrase"],
            searchset=ss_uuid,
            searchtype=field.get("searchtype", "extraction"),
            is_optional=field.get("is_optional", False),
            enum_values=field.get("enum_values", []),
        )
        await ssi.insert()
        item_order.append(str(ssi.id))

    ss.item_order = item_order
    await ss.save()

    # Library item + metadata
    await create_library_item(verified_lib, ss.id, LibraryItemKind.SEARCH_SET)
    await create_verified_metadata(
        "search_set", str(ss.id),
        meta.get("display_name", item["title"]),
        meta.get("description", ""),
        meta.get("quality_tier", "gold"),
    )

    # Add to collections
    for slug in meta.get("collections", []):
        col = slug_to_collection.get(slug)
        if col:
            await add_to_collection(col, str(ss.id))

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("Seeding verified catalog...")

    settings = Settings()
    await init_db(settings)

    verified_lib = await get_or_create_verified_library()

    # --- Phase 1: Collections ---
    print("\n--- Collections ---")
    collections_path = SEEDS_DIR / "collections.json"
    collections_data = json.loads(collections_path.read_text())
    slug_to_collection: dict[str, VerifiedCollection] = {}
    for coll in collections_data["collections"]:
        col = await ensure_collection(coll["title"], coll["description"])
        slug_to_collection[coll["slug"]] = col
        print(f"  {coll['title']}")

    # --- Phase 2: Workflows ---
    print("\n--- Workflows ---")
    wf_dir = SEEDS_DIR / "workflows"
    wf_created = 0
    wf_skipped = 0
    for wf_file in sorted(wf_dir.glob("*.json")):
        data = json.loads(wf_file.read_text())
        meta = data.get("_seed_meta", {})
        if not meta.get("seed_id"):
            print(f"  SKIP {wf_file.name}: missing _seed_meta.seed_id")
            continue
        created = await seed_workflow(data, meta, verified_lib, slug_to_collection)
        name = meta.get("display_name", wf_file.stem)
        if created:
            print(f"  + {name}")
            wf_created += 1
        else:
            print(f"  = {name} (already exists)")
            wf_skipped += 1

    # --- Phase 3: Search Sets ---
    print("\n--- Search Sets ---")
    ss_dir = SEEDS_DIR / "search_sets"
    ss_created = 0
    ss_skipped = 0
    for ss_file in sorted(ss_dir.glob("*.json")):
        data = json.loads(ss_file.read_text())
        meta = data.get("_seed_meta", {})
        if not meta.get("seed_id"):
            print(f"  SKIP {ss_file.name}: missing _seed_meta.seed_id")
            continue
        created = await seed_search_set(data, meta, verified_lib, slug_to_collection)
        name = meta.get("display_name", ss_file.stem)
        if created:
            print(f"  + {name}")
            ss_created += 1
        else:
            print(f"  = {name} (already exists)")
            ss_skipped += 1

    # --- Save verified library ---
    await verified_lib.save()

    # --- Summary ---
    print(f"\nDone! Workflows: {wf_created} created, {wf_skipped} skipped. "
          f"Search sets: {ss_created} created, {ss_skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(main())
