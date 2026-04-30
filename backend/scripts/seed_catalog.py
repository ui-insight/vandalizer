"""Seed the verified catalog with research administration workflows and extraction templates.

Creates verified workflows, search sets, metadata, and collections in the explore system.
Idempotent — safe to run multiple times. Existing items are preserved: top-level fields
are refreshed from seed files and any new nested items (search set items, KB sources,
test cases) are added, but no nested data is removed or overwritten.

Usage:
    cd backend
    python -m scripts.seed_catalog                              # seed everything (default)
    python -m scripts.seed_catalog --only workflows
    python -m scripts.seed_catalog --only extractions,knowledge-bases
    python -m scripts.seed_catalog --only kbs                   # alias for knowledge-bases
"""

import argparse
import asyncio
import datetime
import json
import logging
import pathlib
import uuid as uuid_mod
from typing import Literal

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

SeedResult = Literal["created", "updated", "skipped"]

# Canonical type names used internally
TYPE_WORKFLOWS = "workflows"
TYPE_EXTRACTIONS = "extractions"
TYPE_KNOWLEDGE_BASES = "knowledge_bases"
ALL_TYPES = {TYPE_WORKFLOWS, TYPE_EXTRACTIONS, TYPE_KNOWLEDGE_BASES}

# CLI aliases → canonical names
TYPE_ALIASES = {
    "workflows": TYPE_WORKFLOWS,
    "workflow": TYPE_WORKFLOWS,
    "extractions": TYPE_EXTRACTIONS,
    "extraction": TYPE_EXTRACTIONS,
    "search-sets": TYPE_EXTRACTIONS,
    "search_sets": TYPE_EXTRACTIONS,
    "searchsets": TYPE_EXTRACTIONS,
    "knowledge-bases": TYPE_KNOWLEDGE_BASES,
    "knowledge_bases": TYPE_KNOWLEDGE_BASES,
    "knowledgebases": TYPE_KNOWLEDGE_BASES,
    "kbs": TYPE_KNOWLEDGE_BASES,
    "kb": TYPE_KNOWLEDGE_BASES,
}


def _parse_types(only: str | None) -> set[str]:
    """Parse the --only argument into a set of canonical type names."""
    if not only:
        return set(ALL_TYPES)
    requested: set[str] = set()
    for raw in only.split(","):
        key = raw.strip().lower()
        if not key:
            continue
        canonical = TYPE_ALIASES.get(key)
        if not canonical:
            valid = sorted({"workflows", "extractions", "knowledge-bases", "kbs"})
            raise ValueError(f"Unknown seed type: {raw!r}. Valid: {', '.join(valid)}")
        requested.add(canonical)
    return requested or set(ALL_TYPES)


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


async def upsert_verified_metadata(
    item_kind: str, item_id: str, display_name: str, description: str,
    quality_tier: str | None = None, quality_score: float | None = None,
    quality_grade: str | None = None,
):
    """Create or refresh VerifiedItemMetadata.

    If quality_score/grade are provided (e.g. from a previous validation export),
    they are used directly. If the metadata already exists, display_name and
    description are refreshed from the seed; existing quality fields are only
    overwritten when the caller passes new values (so previously validated
    records don't lose their scores to a later unvalidated seed run).
    """
    existing = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    if existing:
        existing.display_name = display_name
        existing.description = description
        if quality_tier is not None:
            existing.quality_tier = quality_tier
        if quality_score is not None:
            existing.quality_score = quality_score
        if quality_grade is not None:
            existing.quality_grade = quality_grade
        existing.updated_at = now
        await existing.save()
        return existing
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


# Backwards-compat alias for existing call sites.
create_verified_metadata = upsert_verified_metadata


async def ensure_library_item(
    verified_lib: Library, item_id: PydanticObjectId, kind: LibraryItemKind,
):
    """Create a LibraryItem if one doesn't already exist for (item_id, kind),
    and make sure the verified library references it."""
    existing = await LibraryItem.find_one(
        LibraryItem.item_id == item_id,
        LibraryItem.kind == kind,
    )
    if existing:
        if existing.id not in verified_lib.items:
            verified_lib.items.append(existing.id)
        return existing
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


# Backwards-compat alias.
create_library_item = ensure_library_item


# ---------------------------------------------------------------------------
# Workflow seeding
# ---------------------------------------------------------------------------

async def _patch_inline_extractions(wf: Workflow, seed_item: dict) -> int:
    """Patch existing seeded workflows whose Extraction tasks have inline
    searchphrases but no linked SearchSet. Returns count of tasks patched."""
    now = datetime.datetime.now(datetime.timezone.utc)
    patched = 0
    for step_id in wf.steps:
        step = await WorkflowStep.get(step_id)
        if not step:
            continue
        for task_id in step.tasks:
            task = await WorkflowStepTask.get(task_id)
            if not task or task.name != "Extraction":
                continue
            if task.data.get("search_set_uuid"):
                continue  # already linked
            raw = task.data.get("searchphrases")
            if not raw:
                continue
            keys = [k.strip() for k in raw.split(",") if k.strip()]
            ss_uuid = str(uuid_mod.uuid4())
            ss = SearchSet(
                title=f"{wf.name} — Extraction",
                uuid=ss_uuid,
                space="global",
                status="active",
                set_type="extraction",
                is_global=True,
                verified=True,
                created_at=now,
            )
            await ss.insert()
            for key in keys:
                ssi = SearchSetItem(
                    searchphrase=key,
                    searchset=ss_uuid,
                    searchtype="extraction",
                )
                await ssi.insert()
            task.data = {
                k: v for k, v in task.data.items() if k != "searchphrases"
            }
            task.data["search_set_uuid"] = ss_uuid
            task.data["name"] = ss.title
            await task.save()
            patched += 1
    return patched


async def seed_workflow(
    data: dict, meta: dict, verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> SeedResult:
    """Seed a single workflow. Returns "created", "updated", or "skipped"."""
    seed_id = meta["seed_id"]
    item = data["items"][0]

    # Upsert: update top-level fields and metadata on existing workflows; don't
    # touch the step graph (may have run history referencing it).
    existing = await Workflow.find_one({"resource_config.seed_id": seed_id})
    if existing:
        patched = await _patch_inline_extractions(existing, item)
        if patched:
            print(f"    (patched {patched} extraction task(s))")

        changed = False
        new_name = item["name"]
        if existing.name != new_name:
            existing.name = new_name
            changed = True
        new_desc = item.get("description")
        if existing.description != new_desc:
            existing.description = new_desc
            changed = True
        if "input_config" in item and existing.input_config != item["input_config"]:
            existing.input_config = item["input_config"]
            changed = True
        if "output_config" in item and existing.output_config != item["output_config"]:
            existing.output_config = item["output_config"]
            changed = True
        if "validation_plan" in item and existing.validation_plan != item["validation_plan"]:
            existing.validation_plan = item["validation_plan"]
            changed = True
        if "validation_inputs" in item and existing.validation_inputs != item["validation_inputs"]:
            existing.validation_inputs = item["validation_inputs"]
            changed = True
        if changed:
            existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
            await existing.save()

        await ensure_library_item(verified_lib, existing.id, LibraryItemKind.WORKFLOW)
        await upsert_verified_metadata(
            "workflow", str(existing.id),
            meta.get("display_name", item["name"]),
            meta.get("description", item.get("description", "")),
            quality_tier=meta.get("quality_tier"),
            quality_score=meta.get("quality_score"),
            quality_grade=meta.get("quality_grade"),
        )
        for slug in meta.get("collections", []):
            col = slug_to_collection.get(slug)
            if col:
                await add_to_collection(col, str(existing.id))
        return "updated"

    now = datetime.datetime.now(datetime.timezone.utc)

    # Create workflow steps and tasks
    step_ids: list[PydanticObjectId] = []
    for step_data in item.get("steps", []):
        task_ids: list[PydanticObjectId] = []
        for task_data in step_data.get("tasks", []):
            td = dict(task_data.get("data", {}))

            # Materialise a SearchSet for Extraction tasks with inline searchphrases
            if task_data["name"] == "Extraction" and "searchphrases" in td:
                raw = td.pop("searchphrases")
                keys = [k.strip() for k in raw.split(",") if k.strip()]
                ss_uuid = str(uuid_mod.uuid4())
                ss = SearchSet(
                    title=f"{item['name']} — Extraction",
                    uuid=ss_uuid,
                    space="global",
                    status="active",
                    set_type="extraction",
                    is_global=True,
                    verified=True,
                    created_at=now,
                )
                await ss.insert()
                for key in keys:
                    ssi = SearchSetItem(
                        searchphrase=key,
                        searchset=ss_uuid,
                        searchtype="extraction",
                    )
                    await ssi.insert()
                td["search_set_uuid"] = ss_uuid
                td["name"] = ss.title

            task = WorkflowStepTask(name=task_data["name"], data=td)
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

    return "created"


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

async def _refresh_search_set(
    ss: SearchSet, item: dict, meta: dict, seed_id: str,
    verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> None:
    """Apply updates to an existing SearchSet: refresh top-level fields, add any
    missing items from the seed (matched by searchphrase), add missing test cases,
    and refresh metadata/library/collections."""
    changed = False
    if ss.title != item["title"]:
        ss.title = item["title"]
        changed = True
    new_domain = meta.get("domain")
    if new_domain is not None and ss.domain != new_domain:
        ss.domain = new_domain
        changed = True
    seed_cfg = {**item.get("extraction_config", {}), "seed_id": seed_id}
    merged_cfg = {**ss.extraction_config, **seed_cfg}
    if ss.extraction_config != merged_cfg:
        ss.extraction_config = merged_cfg
        changed = True

    # Add any items from the seed that don't already exist on this search set.
    existing_items = await SearchSetItem.find(
        SearchSetItem.searchset == ss.uuid,
    ).to_list()
    existing_phrases = {i.searchphrase for i in existing_items}
    item_order = list(ss.item_order or [])
    for field in item.get("items", []):
        phrase = field["searchphrase"]
        if phrase in existing_phrases:
            continue
        ssi = SearchSetItem(
            searchphrase=phrase,
            searchset=ss.uuid,
            searchtype=field.get("searchtype", "extraction"),
            is_optional=field.get("is_optional", False),
            enum_values=field.get("enum_values", []),
        )
        await ssi.insert()
        item_order.append(str(ssi.id))
        changed = True
    if changed:
        ss.item_order = item_order
        await ss.save()

    tc_count = await _seed_test_cases(ss.uuid, item.get("test_cases", []))
    if tc_count:
        print(f"    + {tc_count} test case(s)")

    await ensure_library_item(verified_lib, ss.id, LibraryItemKind.SEARCH_SET)
    await upsert_verified_metadata(
        "search_set", str(ss.id),
        meta.get("display_name", item["title"]),
        meta.get("description", ""),
        quality_tier=meta.get("quality_tier"),
        quality_score=meta.get("quality_score"),
        quality_grade=meta.get("quality_grade"),
    )
    for slug in meta.get("collections", []):
        col = slug_to_collection.get(slug)
        if col:
            await add_to_collection(col, str(ss.id))


async def seed_search_set(
    data: dict, meta: dict, verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> SeedResult:
    """Seed a single search set. Returns "created", "updated", or "skipped"."""
    seed_id = meta["seed_id"]
    item = data["items"][0]

    existing = await SearchSet.find_one({"extraction_config.seed_id": seed_id})
    if existing:
        await _refresh_search_set(existing, item, meta, seed_id, verified_lib, slug_to_collection)
        return "updated"

    # Adopt legacy templates seeded by seed_domain_templates.py (matched by title).
    old_template = await SearchSet.find_one(
        SearchSet.title == item["title"],
        SearchSet.verified == True,  # noqa: E712
    )
    if old_template:
        await _refresh_search_set(old_template, item, meta, seed_id, verified_lib, slug_to_collection)
        return "updated"

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

    return "created"


# ---------------------------------------------------------------------------
# Knowledge base seeding
# ---------------------------------------------------------------------------

async def _recalc_kb_stats(kb: KnowledgeBase) -> None:
    """Recompute KB aggregates (total_sources, sources_ready, etc.) from its sources."""
    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
    ).to_list()
    kb.total_sources = len(sources)
    kb.sources_ready = sum(1 for s in sources if s.status == "ready")
    kb.sources_failed = sum(1 for s in sources if s.status == "error")
    kb.total_chunks = sum(s.chunk_count for s in sources)
    if kb.sources_ready > 0:
        kb.status = "ready"
    elif kb.total_sources > 0 and kb.sources_failed == kb.total_sources:
        kb.status = "error"
    else:
        kb.status = "empty"
    await kb.save()


async def seed_knowledge_base(
    data: dict, meta: dict, verified_lib: Library, slug_to_collection: dict[str, VerifiedCollection],
) -> SeedResult:
    """Seed a single knowledge base. Returns "created", "updated", or "skipped"."""
    item = data["items"][0]

    existing = await KnowledgeBase.find_one(
        KnowledgeBase.title == item["title"],
        KnowledgeBase.verified == True,  # noqa: E712
    )
    if existing:
        from app.services.knowledge_service import _ingest_url_source

        changed = False
        new_desc = item.get("description")
        if new_desc is not None and existing.description != new_desc:
            existing.description = new_desc
            changed = True
        if changed:
            existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
            await existing.save()

        # Add any URL sources from the seed that aren't already present, and
        # ingest just those new ones. Existing sources are left alone.
        current_sources = await KnowledgeBaseSource.find(
            KnowledgeBaseSource.knowledge_base_uuid == existing.uuid,
        ).to_list()
        existing_urls = {s.url for s in current_sources if s.url}
        new_sources_ingested = 0
        for src_data in item.get("sources", []):
            url = src_data.get("url")
            if not url or url in existing_urls:
                continue
            src = KnowledgeBaseSource(
                knowledge_base_uuid=existing.uuid,
                source_type=src_data.get("source_type", "url"),
                url=url,
                url_title=src_data.get("url_title"),
                status="pending",
            )
            await src.insert()
            if src.source_type == "url":
                try:
                    await _ingest_url_source(src, existing)
                    new_sources_ingested += 1
                except Exception as e:
                    logger.warning("Failed to ingest seed URL %s: %s", src.url, e)
        if new_sources_ingested:
            print(f"    + {new_sources_ingested} new source(s)")
            await _recalc_kb_stats(existing)

        await ensure_library_item(verified_lib, existing.id, LibraryItemKind.KNOWLEDGE_BASE)
        await upsert_verified_metadata(
            "knowledge_base", str(existing.id),
            meta.get("display_name", item["title"]),
            meta.get("description", item.get("description", "")),
            quality_tier=meta.get("quality_tier"),
            quality_score=meta.get("quality_score"),
            quality_grade=meta.get("quality_grade"),
        )
        for slug in meta.get("collections", []):
            col = slug_to_collection.get(slug)
            if col:
                await add_to_collection(col, str(existing.id))
        return "updated"

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

    for src_data in item.get("sources", []):
        src = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type=src_data.get("source_type", "url"),
            url=src_data.get("url"),
            url_title=src_data.get("url_title"),
            status="pending",
        )
        await src.insert()

        # Ingest URL sources inline so KBs have chunks on first run
        if src.source_type == "url" and src.url:
            try:
                await _ingest_url_source(src, kb)
            except Exception as e:
                logger.warning("Failed to ingest seed URL %s: %s", src.url, e)

    await _recalc_kb_stats(kb)

    # Library item + metadata
    await ensure_library_item(verified_lib, kb.id, LibraryItemKind.KNOWLEDGE_BASE)
    await upsert_verified_metadata(
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

    return "created"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def seed_catalog(types: set[str] | None = None):
    """Seed the verified catalog. Expects Beanie to be already initialized.

    Args:
        types: Subset of {"workflows", "extractions", "knowledge_bases"} controlling
               which resource types to seed. ``None`` (default) seeds all three.
               Collections are always ensured because the other types reference them.
    """
    selected = set(types) if types else set(ALL_TYPES)
    unknown = selected - ALL_TYPES
    if unknown:
        raise ValueError(f"Unknown seed types: {sorted(unknown)}")

    print(f"Seeding verified catalog (types: {', '.join(sorted(selected))})...")

    verified_lib = await get_or_create_verified_library()

    # --- Phase 1: Collections (always run — referenced by all other types) ---
    print("\n--- Collections ---")
    collections_path = SEEDS_DIR / "collections.json"
    collections_data = json.loads(collections_path.read_text())
    slug_to_collection: dict[str, VerifiedCollection] = {}
    for coll in collections_data["collections"]:
        col = await ensure_collection(coll["title"], coll["description"], featured=coll.get("featured", False))
        slug_to_collection[coll["slug"]] = col
        print(f"  {coll['title']}{' [featured]' if coll.get('featured') else ''}")

    def _tally(counts: dict[str, int], result: SeedResult, label: str, name: str):
        counts[result] = counts.get(result, 0) + 1
        if result == "created":
            print(f"  + {name}")
        elif result == "updated":
            print(f"  ~ {name} (updated)")
        else:
            print(f"  = {name} (skipped)")

    summary: list[str] = []

    # --- Phase 2: Workflows ---
    if TYPE_WORKFLOWS in selected:
        print("\n--- Workflows ---")
        wf_dir = SEEDS_DIR / "workflows"
        wf_counts: dict[str, int] = {}
        for wf_file in sorted(wf_dir.glob("*.json")):
            data = json.loads(wf_file.read_text())
            meta = data.get("_seed_meta", {})
            if not meta.get("seed_id"):
                print(f"  SKIP {wf_file.name}: missing _seed_meta.seed_id")
                continue
            result = await seed_workflow(data, meta, verified_lib, slug_to_collection)
            _tally(wf_counts, result, "workflow", meta.get("display_name", wf_file.stem))
        summary.append(
            f"Workflows: {wf_counts.get('created', 0)} created, "
            f"{wf_counts.get('updated', 0)} updated, "
            f"{wf_counts.get('skipped', 0)} skipped"
        )

    # --- Phase 3: Search Sets (extractions) ---
    if TYPE_EXTRACTIONS in selected:
        print("\n--- Extractions (search sets) ---")
        ss_dir = SEEDS_DIR / "search_sets"
        ss_counts: dict[str, int] = {}
        for ss_file in sorted(ss_dir.glob("*.json")):
            data = json.loads(ss_file.read_text())
            meta = data.get("_seed_meta", {})
            if not meta.get("seed_id"):
                print(f"  SKIP {ss_file.name}: missing _seed_meta.seed_id")
                continue
            result = await seed_search_set(data, meta, verified_lib, slug_to_collection)
            _tally(ss_counts, result, "search set", meta.get("display_name", ss_file.stem))
        summary.append(
            f"Extractions: {ss_counts.get('created', 0)} created, "
            f"{ss_counts.get('updated', 0)} updated, "
            f"{ss_counts.get('skipped', 0)} skipped"
        )

    # --- Phase 4: Knowledge Bases ---
    if TYPE_KNOWLEDGE_BASES in selected:
        print("\n--- Knowledge Bases ---")
        kb_dir = SEEDS_DIR / "knowledge_bases"
        kb_counts: dict[str, int] = {}
        if kb_dir.exists():
            for kb_file in sorted(kb_dir.glob("*.json")):
                data = json.loads(kb_file.read_text())
                meta = data.get("_seed_meta", {})
                if not meta.get("seed_id"):
                    print(f"  SKIP {kb_file.name}: missing _seed_meta.seed_id")
                    continue
                result = await seed_knowledge_base(data, meta, verified_lib, slug_to_collection)
                _tally(kb_counts, result, "knowledge base", meta.get("display_name", kb_file.stem))
        summary.append(
            f"Knowledge bases: {kb_counts.get('created', 0)} created, "
            f"{kb_counts.get('updated', 0)} updated, "
            f"{kb_counts.get('skipped', 0)} skipped"
        )

    # --- Save verified library ---
    await verified_lib.save()

    # --- Summary ---
    print("\nDone! " + " | ".join(summary))


async def main():
    parser = argparse.ArgumentParser(
        description="Seed the verified catalog with research admin templates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m scripts.seed_catalog\n"
            "  python -m scripts.seed_catalog --only workflows\n"
            "  python -m scripts.seed_catalog --only extractions,knowledge-bases\n"
            "  python -m scripts.seed_catalog --only kbs\n\n"
            "Seeds are upserted: existing items keep their nested data and have\n"
            "top-level fields refreshed from the seed file; any new nested items\n"
            "(search set fields, KB sources, test cases) are added."
        ),
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help=(
            "Comma-separated list of resource types to seed. "
            "Valid: workflows, extractions, knowledge-bases (alias: kbs). "
            "Default: seed everything."
        ),
    )
    args = parser.parse_args()
    types = _parse_types(args.only)

    settings = Settings()
    await init_db(settings)
    await seed_catalog(types=types)


if __name__ == "__main__":
    asyncio.run(main())
