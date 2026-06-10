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
    python -m scripts.seed_catalog --reset                      # wipe catalog metadata, then re-seed
    python -m scripts.seed_catalog --prune                      # seed, then retire items dropped from the catalog
    python -m scripts.seed_catalog --prune --dry-run            # preview what --prune would retire (no changes)

The --reset flag clears the catalog "metadata layer" (VerifiedCollection,
VerifiedItemMetadata, verified LibraryItem records, and the verified Library
container) before re-seeding. The underlying Workflow / SearchSet /
KnowledgeBase documents (and any user-added LibraryItem bookmarks pointing
at them) are NOT deleted — the seed pass re-attaches existing entities to
fresh metadata via their stored seed_id markers.

The --prune flag handles the inverse: catalog UPGRADES that *remove* items.
Every seeded entity carries a seed_id (workflows/KBs in resource_config,
search sets in extraction_config). After seeding, prune compares the seed_ids
live in the seed files against the verified rows in the database and
soft-archives any verified item whose seed_id is gone — flipping it to
verified=False and detaching it from the explore catalog (LibraryItem,
VerifiedItemMetadata, collection membership) while preserving the underlying
row so the change is reversible. Items without a seed_id are never touched.
Pair with --dry-run to preview the retirement list before applying it.
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
VERSION_FILE = SEEDS_DIR / "VERSION"
SYSTEM_USER = "system"


def _read_seed_version() -> str:
    """Read the current catalog version from backend/seeds/VERSION.

    Treated as required: the file is checked in and CI gates seed-data PRs
    on a matching VERSION bump, so an absent or empty file is a packaging bug.
    """
    if not VERSION_FILE.exists():
        raise RuntimeError(f"missing seed version file: {VERSION_FILE}")
    text = VERSION_FILE.read_text().strip()
    if not text:
        raise RuntimeError(f"seed version file is empty: {VERSION_FILE}")
    return text

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
    seed_id = meta["seed_id"]
    item = data["items"][0]

    # Match on seed_id (provenance) first; fall back to title for legacy KBs
    # seeded before seed_id tracking existed, then stamp them so future runs
    # (and the prune pass) can identify them by seed_id.
    existing = await KnowledgeBase.find_one({"resource_config.seed_id": seed_id})
    if not existing:
        existing = await KnowledgeBase.find_one(
            KnowledgeBase.title == item["title"],
            KnowledgeBase.verified == True,  # noqa: E712
        )
    if existing:
        from app.services.knowledge_service import _ingest_url_source

        changed = False
        if existing.resource_config.get("seed_id") != seed_id:
            existing.resource_config = {**existing.resource_config, "seed_id": seed_id}
            changed = True
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
        resource_config={"seed_id": seed_id},
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
# Prune (retire stale seeded items)
# ---------------------------------------------------------------------------

# Per-type wiring for prune: how to find the seed_id on a live document, the
# seed directory to scan, the LibraryItemKind, and the metadata item_kind string.
_PRUNE_SPEC = {
    TYPE_WORKFLOWS: {
        "model": Workflow,
        "dir": "workflows",
        "cfg_field": "resource_config",
        "title_key": "name",  # field in seed items[0] holding the entity title
        "library_kind": LibraryItemKind.WORKFLOW,
        "meta_kind": "workflow",
        "label": "workflow",
        # Workflows have carried a seed_id in resource_config since their first
        # seed, so seed_id alone is a reliable identity — no title fallback.
        "title_fallback": False,
    },
    TYPE_EXTRACTIONS: {
        "model": SearchSet,
        "dir": "search_sets",
        "cfg_field": "extraction_config",
        "title_key": "title",
        "library_kind": LibraryItemKind.SEARCH_SET,
        "meta_kind": "search_set",
        "label": "search set",
        "title_fallback": False,
    },
    TYPE_KNOWLEDGE_BASES: {
        "model": KnowledgeBase,
        "dir": "knowledge_bases",
        "cfg_field": "resource_config",
        "title_key": "title",
        "library_kind": LibraryItemKind.KNOWLEDGE_BASE,
        "meta_kind": "knowledge_base",
        "label": "knowledge base",
        # KBs only gained seed_id tracking recently, so legacy rows have none.
        # Fall back to matching system-seeded KBs by title against the manifest.
        "title_fallback": True,
    },
}


def _collect_live_manifest(selected: set[str]) -> dict[str, dict[str, set[str]]]:
    """Scan the seed files for the selected types and return, per type, the
    seed_ids and entity titles the catalog currently ships. The prune pass diffs
    live items against this: a verified item whose seed_id (or, for legacy rows
    without one, whose title) is absent here was dropped from the catalog."""
    live: dict[str, dict[str, set[str]]] = {}
    for type_name in selected:
        spec = _PRUNE_SPEC[type_name]
        type_dir = SEEDS_DIR / spec["dir"]
        ids: set[str] = set()
        titles: set[str] = set()
        if type_dir.exists():
            for seed_file in sorted(type_dir.glob("*.json")):
                data = json.loads(seed_file.read_text())
                seed_id = data.get("_seed_meta", {}).get("seed_id")
                if seed_id:
                    ids.add(seed_id)
                items = data.get("items") or []
                if items:
                    title = items[0].get(spec["title_key"])
                    if title:
                        titles.add(title)
        live[type_name] = {"ids": ids, "titles": titles}
    return live


async def _retire_item(type_name: str, doc, verified_lib: Library, dry_run: bool) -> None:
    """Soft-archive a single seeded item: flip the underlying row to
    verified=False and strip every catalog attachment (verified LibraryItem,
    VerifiedItemMetadata, collection membership). The underlying
    Workflow/SearchSet/KnowledgeBase row is preserved so the change is
    reversible. A no-op when dry_run is True."""
    if dry_run:
        return
    spec = _PRUNE_SPEC[type_name]
    item_id_str = str(doc.id)

    # Detach the verified LibraryItem(s) and pull them from the verified library.
    lib_items = await LibraryItem.find(
        LibraryItem.item_id == doc.id,
        LibraryItem.kind == spec["library_kind"],
        LibraryItem.verified == True,  # noqa: E712
    ).to_list()
    for li in lib_items:
        if li.id in verified_lib.items:
            verified_lib.items.remove(li.id)
        await li.delete()

    # Drop the verified metadata record.
    await VerifiedItemMetadata.find(
        VerifiedItemMetadata.item_kind == spec["meta_kind"],
        VerifiedItemMetadata.item_id == item_id_str,
    ).delete()

    # Remove the item from any collection that references it.
    async for col in VerifiedCollection.find(VerifiedCollection.item_ids == item_id_str):
        col.item_ids = [i for i in col.item_ids if i != item_id_str]
        col.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await col.save()

    # Finally, unverify the underlying row (kept for reversibility).
    doc.verified = False
    if hasattr(doc, "updated_at"):
        doc.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await doc.save()


async def prune_stale_seeded_items(
    selected: set[str], dry_run: bool = False,
) -> list[dict]:
    """Retire verified items whose seed_id is no longer present in the seed
    files for their type. Only types in ``selected`` are considered, so a
    partial run (e.g. --only workflows) never touches other types.

    Items without a seed_id are ignored unless the type opts into a title
    fallback (knowledge bases, whose legacy rows predate seed_id tracking) and
    the row is system-seeded — this avoids retiring user-created entities or
    internal artifacts (e.g. a workflow's inline-extraction SearchSet).
    Returns a list of retired-item descriptors.
    """
    live = _collect_live_manifest(selected)
    verified_lib = await get_or_create_verified_library()
    retired: list[dict] = []

    for type_name in sorted(selected):
        spec = _PRUNE_SPEC[type_name]
        model = spec["model"]
        cfg_field = spec["cfg_field"]
        live_ids = live[type_name]["ids"]
        live_titles = live[type_name]["titles"]

        # Verified rows that either carry a seed_id marker or — for types with a
        # title fallback — are system-seeded (so legacy unstamped rows are seen).
        query: dict = {"verified": True}
        if spec["title_fallback"]:
            query["$or"] = [
                {f"{cfg_field}.seed_id": {"$exists": True, "$ne": None}},
                {"user_id": SYSTEM_USER},
            ]
        else:
            query[f"{cfg_field}.seed_id"] = {"$exists": True, "$ne": None}
        candidates = await model.find(query).to_list()

        for doc in candidates:
            seed_id = (getattr(doc, cfg_field, {}) or {}).get("seed_id")
            if seed_id:
                stale = seed_id not in live_ids
            elif spec["title_fallback"] and getattr(doc, "user_id", None) == SYSTEM_USER:
                # Legacy system-seeded row with no seed_id: match by title. After
                # a seed pass, a kept item is always stamped, so this only flags
                # genuinely-dropped items; in --dry-run it relies on the title.
                stale = getattr(doc, "title", None) not in live_titles
            else:
                continue
            if not stale:
                continue
            await _retire_item(type_name, doc, verified_lib, dry_run)
            retired.append({
                "type": type_name,
                "label": spec["label"],
                "seed_id": seed_id or "(legacy/no seed_id)",
                "name": getattr(doc, "name", None) or getattr(doc, "title", None) or str(doc.id),
                "id": str(doc.id),
            })

    if not dry_run and retired:
        await verified_lib.save()
    return retired


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

async def reset_verified_catalog() -> dict[str, int]:
    """Wipe the catalog metadata layer so the next seed pass rebuilds it cleanly.

    Deletes all VerifiedCollection, VerifiedItemMetadata, and verified=True
    LibraryItem documents, and removes the verified Library container. The
    underlying Workflow / SearchSet / KnowledgeBase entities (and any
    user-added LibraryItem bookmarks pointing at them) are NOT touched —
    a subsequent seed_catalog() run re-attaches them via their stored
    seed_id markers.
    """
    deleted: dict[str, int] = {}

    res = await VerifiedCollection.find_all().delete()
    deleted["collections"] = getattr(res, "deleted_count", 0) or 0

    res = await VerifiedItemMetadata.find_all().delete()
    deleted["metadata"] = getattr(res, "deleted_count", 0) or 0

    res = await LibraryItem.find(LibraryItem.verified == True).delete()  # noqa: E712
    deleted["library_items"] = getattr(res, "deleted_count", 0) or 0

    res = await Library.find(Library.scope == LibraryScope.VERIFIED).delete()
    deleted["libraries"] = getattr(res, "deleted_count", 0) or 0

    return deleted


# ---------------------------------------------------------------------------
# Diff / preview (powers the in-app "catalog update available" feature)
# ---------------------------------------------------------------------------

def _version_newer(candidate: str | None, current: str | None) -> bool:
    """True if dotted-numeric ``candidate`` is a higher version than ``current``.
    An absent current version means anything is newer. Non-numeric versions fall
    back to a simple inequality so we still surface a change."""
    if not candidate:
        return False
    if not current:
        return True

    def _parts(v: str):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except ValueError:
            return None

    cp, kp = _parts(candidate), _parts(current)
    if cp is None or kp is None:
        return candidate != current
    return cp > kp


def _scan_seed_entries(type_name: str) -> list[dict]:
    """Read the seed files for a type and return one entry per item:
    {seed_id, name, title}. ``name`` is the human display label, ``title`` the
    underlying entity title used for legacy (seed_id-less) matching."""
    spec = _PRUNE_SPEC[type_name]
    type_dir = SEEDS_DIR / spec["dir"]
    entries: list[dict] = []
    if not type_dir.exists():
        return entries
    for seed_file in sorted(type_dir.glob("*.json")):
        data = json.loads(seed_file.read_text())
        meta = data.get("_seed_meta", {})
        seed_id = meta.get("seed_id")
        if not seed_id:
            continue
        items = data.get("items") or []
        title = items[0].get(spec["title_key"]) if items else None
        entries.append({
            "seed_id": seed_id,
            "title": title,
            "name": meta.get("display_name") or title or seed_id,
        })
    return entries


async def _db_identity(type_name: str) -> tuple[set[str], set[str]]:
    """Return (seed_ids, titles) for the verified rows of a type already in the
    DB — the 'what's installed' side of the diff."""
    spec = _PRUNE_SPEC[type_name]
    model = spec["model"]
    cfg_field = spec["cfg_field"]
    rows = await model.find({"verified": True}).to_list()
    ids: set[str] = set()
    titles: set[str] = set()
    for row in rows:
        sid = (getattr(row, cfg_field, {}) or {}).get("seed_id")
        if sid:
            ids.add(sid)
        title = getattr(row, "title", None) or getattr(row, "name", None)
        if title and getattr(row, "user_id", None) == SYSTEM_USER:
            titles.add(title)
    return ids, titles


async def compute_catalog_diff(types: set[str] | None = None) -> dict:
    """Compute what a catalog upgrade would change, without mutating anything.

    Returns the applied vs. bundled version, whether an upgrade is available,
    and the lists of items that would be added and retired plus a refreshed
    count. Powers the admin "catalog update available" banner and preview.
    """
    selected = set(types) if types else set(ALL_TYPES)
    bundled = _read_seed_version()

    from app.models.system_config import SystemConfig
    cfg = await SystemConfig.get_config()
    applied = cfg.catalog_version

    new_items: list[dict] = []
    refreshed = 0
    for type_name in sorted(selected):
        spec = _PRUNE_SPEC[type_name]
        db_ids, db_titles = await _db_identity(type_name)
        for entry in _scan_seed_entries(type_name):
            known = entry["seed_id"] in db_ids or (
                spec["title_fallback"] and entry.get("title") in db_titles
            )
            if known:
                refreshed += 1
            else:
                new_items.append({
                    "type": type_name,
                    "label": spec["label"],
                    "seed_id": entry["seed_id"],
                    "name": entry["name"],
                })

    retiring = await prune_stale_seeded_items(selected, dry_run=True)

    return {
        "applied_version": applied,
        "bundled_version": bundled,
        "update_available": _version_newer(bundled, applied),
        "counts": {
            "new": len(new_items),
            "refreshed": refreshed,
            "retiring": len(retiring),
        },
        "new": new_items,
        "retiring": retiring,
    }


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

    seed_version = _read_seed_version()
    # Machine-readable line that setup.sh greps for to learn the applied version.
    print(f"Catalog version: {seed_version}")
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
    counts_by_type: dict[str, dict[str, int]] = {}

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
        counts_by_type[TYPE_WORKFLOWS] = wf_counts

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
        counts_by_type[TYPE_EXTRACTIONS] = ss_counts

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
        counts_by_type[TYPE_KNOWLEDGE_BASES] = kb_counts

    # --- Save verified library ---
    await verified_lib.save()

    # --- Record the applied catalog version on the singleton config ---
    # Only when seeding everything; partial seeds (--only) shouldn't claim the
    # full catalog is at this version because some types were skipped.
    if selected == ALL_TYPES:
        from app.models.system_config import SystemConfig
        cfg = await SystemConfig.get_config()
        cfg.catalog_version = seed_version
        cfg.catalog_version_applied_at = datetime.datetime.now(datetime.timezone.utc)
        await cfg.save()
        print(f"Recorded catalog_version={seed_version} on SystemConfig.")

    # --- Summary ---
    print("\nDone! " + " | ".join(summary))

    def _totals(key: str) -> int:
        return sum(c.get(key, 0) for c in counts_by_type.values())

    return {
        "version": seed_version,
        "by_type": counts_by_type,
        "created": _totals("created"),
        "updated": _totals("updated"),
        "skipped": _totals("skipped"),
    }


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
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Wipe catalog metadata (collections, verified metadata, verified "
            "library items, verified library) before re-seeding. Underlying "
            "Workflow/SearchSet/KnowledgeBase rows are preserved."
        ),
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help=(
            "After seeding, retire verified items whose seed_id is no longer in "
            "the seed files (soft-archive: verified=False, removed from the "
            "explore catalog, underlying row kept). Use to drop items dropped "
            "from the catalog on an upgrade."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Preview the prune pass only: list the items that --prune would "
            "retire, without seeding or modifying anything. Implies --prune."
        ),
    )
    args = parser.parse_args()
    types = _parse_types(args.only)

    settings = Settings()
    await init_db(settings)

    # Dry run: preview retirements only — no seeding, no mutations.
    if args.dry_run:
        stale = await prune_stale_seeded_items(types, dry_run=True)
        _print_prune_summary(stale, dry_run=True)
        return

    if args.reset:
        print("Resetting verified catalog metadata...")
        deleted = await reset_verified_catalog()
        print(
            f"  Deleted: {deleted['collections']} collection(s), "
            f"{deleted['metadata']} metadata record(s), "
            f"{deleted['library_items']} verified library item(s), "
            f"{deleted['libraries']} verified library container(s)."
        )
    await seed_catalog(types=types)

    if args.prune:
        retired = await prune_stale_seeded_items(types, dry_run=False)
        _print_prune_summary(retired, dry_run=False)


def _print_prune_summary(items: list[dict], dry_run: bool) -> None:
    """Render the prune result. The 'Retiring N item(s)' line is machine-readable
    — setup.sh greps it to decide whether to prompt for confirmation."""
    verb = "Would retire" if dry_run else "Retired"
    print(f"\n--- Prune ({'dry run' if dry_run else 'applied'}) ---")
    print(f"Retiring {len(items)} item(s) no longer in the catalog.")
    for it in items:
        print(f"  - [{it['label']}] {it['name']}  (seed_id={it['seed_id']})")
    if not items:
        print("  (nothing to retire — every verified seeded item is still in the seed files)")
    else:
        print(f"{verb} {len(items)} stale catalog item(s).")


if __name__ == "__main__":
    asyncio.run(main())
