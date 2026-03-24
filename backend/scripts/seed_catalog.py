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
from app.models.extraction_test_case import ExtractionTestCase
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
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


async def ensure_collection(title: str, description: str, featured: bool = False) -> VerifiedCollection:
    """Get or create a VerifiedCollection by title."""
    existing = await VerifiedCollection.find_one(VerifiedCollection.title == title)
    if existing:
        if featured and not existing.featured:
            existing.featured = True
            await existing.save()
        return existing
    now = datetime.datetime.now(datetime.timezone.utc)
    col = VerifiedCollection(
        title=title,
        description=description,
        featured=featured,
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
    item_kind: str, item_id: str, display_name: str, description: str,
    quality_tier: str | None = None, quality_score: float | None = None,
    quality_grade: str | None = None,
):
    """Create VerifiedItemMetadata if it doesn't already exist.

    If quality_score/grade are provided (e.g. from a previous validation export),
    they are used directly. Otherwise the item is created without quality data,
    indicating it has not yet been validated.
    """
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
        quality_grade=quality_grade,
        quality_score=quality_score,
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
        quality_tier=meta.get("quality_tier"),
        quality_score=meta.get("quality_score"),
        quality_grade=meta.get("quality_grade"),
    )

    # Add to collections
    for slug in meta.get("collections", []):
        col = slug_to_collection.get(slug)
        if col:
            await add_to_collection(col, str(wf.id))

    return True


# ---------------------------------------------------------------------------
# Test case seeding
# ---------------------------------------------------------------------------

async def _seed_test_cases(search_set_uuid: str, test_cases: list[dict]) -> int:
    """Create ExtractionTestCase records from seed data. Returns count created."""
    created = 0
    for tc_data in test_cases:
        label = tc_data.get("label", "Seed test case")
        # Idempotency: skip if a test case with this label already exists
        existing = await ExtractionTestCase.find_one(
            ExtractionTestCase.search_set_uuid == search_set_uuid,
            ExtractionTestCase.label == label,
        )
        if existing:
            continue
        tc = ExtractionTestCase(
            search_set_uuid=search_set_uuid,
            label=label,
            source_type="text",
            source_text=tc_data.get("source_text", ""),
            expected_values=tc_data.get("expected_values", {}),
            user_id=SYSTEM_USER,
        )
        await tc.insert()
        created += 1
    return created


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
            quality_tier=meta.get("quality_tier"),
            quality_score=meta.get("quality_score"),
            quality_grade=meta.get("quality_grade"),
        )
        await create_library_item(verified_lib, old_template.id, LibraryItemKind.SEARCH_SET)
        for slug in meta.get("collections", []):
            col = slug_to_collection.get(slug)
            if col:
                await add_to_collection(col, str(old_template.id))
        # Seed test cases for adopted template
        tc_count = await _seed_test_cases(old_template.uuid, item.get("test_cases", []))
        if tc_count:
            print(f"    + {tc_count} test case(s)")
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

    # Create test cases from seed data
    tc_count = await _seed_test_cases(ss_uuid, item.get("test_cases", []))
    if tc_count:
        print(f"    + {tc_count} test case(s)")

    # Library item + metadata
    await create_library_item(verified_lib, ss.id, LibraryItemKind.SEARCH_SET)
    await create_verified_metadata(
        "search_set", str(ss.id),
        meta.get("display_name", item["title"]),
        meta.get("description", ""),
        quality_tier=meta.get("quality_tier"),
        quality_score=meta.get("quality_score"),
        quality_grade=meta.get("quality_grade"),
    )

    # Add to collections
    for slug in meta.get("collections", []):
        col = slug_to_collection.get(slug)
        if col:
            await add_to_collection(col, str(ss.id))

    return True


# ---------------------------------------------------------------------------
# Knowledge base seeding
# ---------------------------------------------------------------------------

async def seed_knowledge_base(
    data: dict, meta: dict, verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> bool:
    """Seed a single knowledge base. Returns True if created, False if skipped."""
    seed_id = meta["seed_id"]

    # Idempotency: check if already seeded via title match
    existing = await KnowledgeBase.find_one(
        KnowledgeBase.title == data["items"][0]["title"],
        KnowledgeBase.verified == True,  # noqa: E712
    )
    if existing:
        return False

    item = data["items"][0]
    now = datetime.datetime.now(datetime.timezone.utc)

    kb = KnowledgeBase(
        title=item["title"],
        description=item.get("description"),
        user_id=SYSTEM_USER,
        space="global",
        verified=True,
        status="ready",
        created_at=now,
        updated_at=now,
    )
    await kb.insert()

    # Create source records and ingest URL sources
    from app.services.knowledge_service import _ingest_url_source

    source_count = 0
    for src_data in item.get("sources", []):
        src = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type=src_data.get("source_type", "url"),
            url=src_data.get("url"),
            url_title=src_data.get("url_title"),
            status="pending",
        )
        await src.insert()
        source_count += 1

        # Ingest URL sources inline so KBs have chunks on first run
        if src.source_type == "url" and src.url:
            try:
                await _ingest_url_source(src, kb)
            except Exception as e:
                logger.warning("Failed to ingest seed URL %s: %s", src.url, e)

    # Recalculate stats from ingested sources
    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
    ).to_list()
    kb.total_sources = len(sources)
    kb.sources_ready = sum(1 for s in sources if s.status == "ready")
    kb.sources_failed = sum(1 for s in sources if s.status == "error")
    kb.total_chunks = sum(s.chunk_count for s in sources)
    kb.status = "ready" if kb.sources_ready > 0 else ("error" if kb.sources_failed == kb.total_sources else "empty")
    await kb.save()

    # Library item + metadata
    await create_library_item(verified_lib, kb.id, LibraryItemKind.KNOWLEDGE_BASE)
    await create_verified_metadata(
        "knowledge_base", str(kb.id),
        meta.get("display_name", item["title"]),
        meta.get("description", item.get("description", "")),
        quality_tier=meta.get("quality_tier"),
        quality_score=meta.get("quality_score"),
        quality_grade=meta.get("quality_grade"),
    )

    # Add to collections
    for slug in meta.get("collections", []):
        col = slug_to_collection.get(slug)
        if col:
            await add_to_collection(col, str(kb.id))

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def seed_catalog():
    """Seed the verified catalog. Expects Beanie to be already initialized."""
    print("Seeding verified catalog...")

    verified_lib = await get_or_create_verified_library()

    # --- Phase 1: Collections ---
    print("\n--- Collections ---")
    collections_path = SEEDS_DIR / "collections.json"
    collections_data = json.loads(collections_path.read_text())
    slug_to_collection: dict[str, VerifiedCollection] = {}
    for coll in collections_data["collections"]:
        col = await ensure_collection(coll["title"], coll["description"], featured=coll.get("featured", False))
        slug_to_collection[coll["slug"]] = col
        print(f"  {coll['title']}{' [featured]' if coll.get('featured') else ''}")

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

    # --- Phase 4: Knowledge Bases ---
    print("\n--- Knowledge Bases ---")
    kb_dir = SEEDS_DIR / "knowledge_bases"
    kb_created = 0
    kb_skipped = 0
    if kb_dir.exists():
        for kb_file in sorted(kb_dir.glob("*.json")):
            data = json.loads(kb_file.read_text())
            meta = data.get("_seed_meta", {})
            if not meta.get("seed_id"):
                print(f"  SKIP {kb_file.name}: missing _seed_meta.seed_id")
                continue
            created = await seed_knowledge_base(data, meta, verified_lib, slug_to_collection)
            name = meta.get("display_name", kb_file.stem)
            if created:
                print(f"  + {name}")
                kb_created += 1
            else:
                print(f"  = {name} (already exists)")
                kb_skipped += 1

    # --- Save verified library ---
    await verified_lib.save()

    # --- Summary ---
    print(f"\nDone! Workflows: {wf_created} created, {wf_skipped} skipped. "
          f"Search sets: {ss_created} created, {ss_skipped} skipped. "
          f"Knowledge bases: {kb_created} created, {kb_skipped} skipped.")


async def main():
    settings = Settings()
    await init_db(settings)
    await seed_catalog()


if __name__ == "__main__":
    asyncio.run(main())
