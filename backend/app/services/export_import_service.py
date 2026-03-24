"""Export / Import service for workflows, search sets, and verified catalogs."""

from __future__ import annotations

import datetime
import uuid as uuid_mod
from typing import TYPE_CHECKING

from beanie import PydanticObjectId

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeBase

from app.models.extraction_test_case import ExtractionTestCase
from app.models.search_set import SearchSet, SearchSetItem
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.services import search_set_service, verification_service, workflow_service

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------


def _envelope(export_type: str, user_email: str, items: list[dict]) -> dict:
    return {
        "vandalizer_export": True,
        "schema_version": SCHEMA_VERSION,
        "export_type": export_type,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "exported_by": user_email,
        "items": items,
    }


def validate_export_data(data: dict) -> str | None:
    """Return an error string if *data* is not a valid export envelope, else None."""
    if not isinstance(data, dict):
        return "Invalid JSON: expected an object"
    if not data.get("vandalizer_export"):
        return "Not a Vandalizer export file (missing vandalizer_export flag)"
    if data.get("schema_version") != SCHEMA_VERSION:
        return f"Unsupported schema version (expected {SCHEMA_VERSION})"
    if data.get("export_type") not in ("workflow", "search_set", "knowledge_base", "catalog"):
        return "Unknown export_type"
    if not isinstance(data.get("items"), list) or len(data["items"]) == 0:
        return "Export file contains no items"
    return None


# ---------------------------------------------------------------------------
# Workflow export / import
# ---------------------------------------------------------------------------


async def export_workflow(workflow_id: str, user_email: str) -> dict:
    wf_data = await workflow_service.get_workflow(workflow_id)
    if not wf_data:
        raise ValueError("Workflow not found")

    # Also fetch the raw workflow for extra fields
    wf = await Workflow.get(PydanticObjectId(workflow_id))

    steps = []
    for step in wf_data.get("steps", []):
        tasks = [
            {"name": t["name"], "data": t.get("data", {})}
            for t in step.get("tasks", [])
        ]
        steps.append({
            "name": step["name"],
            "data": step.get("data", {}),
            "is_output": step.get("is_output", False),
            "tasks": tasks,
        })

    # Only include text-based validation inputs (exclude document references)
    validation_inputs = []
    for vi in (wf.validation_inputs if wf else []):
        if vi.get("type") == "text":
            validation_inputs.append({
                "type": "text",
                "text": vi.get("text", ""),
                "label": vi.get("label", ""),
            })

    item = {
        "name": wf_data["name"],
        "description": wf_data.get("description"),
        "steps": steps,
        "input_config": wf.input_config if wf else {},
        "output_config": wf.output_config if wf else {},
        "resource_config": wf.resource_config if wf else {},
        "validation_plan": wf.validation_plan if wf else [],
        "validation_inputs": validation_inputs,
    }
    return _envelope("workflow", user_email, [item])


async def import_workflow(
    data: dict,
    user_id: str,
    team_id: str | None = None,
) -> dict:
    """Import a workflow from export data. Returns the new workflow dict."""
    err = validate_export_data(data)
    if err:
        raise ValueError(err)
    if data["export_type"] != "workflow":
        raise ValueError("Expected a workflow export file")

    item = data["items"][0]

    new_wf = Workflow(
        name=f"{item['name']} (Imported)",
        description=item.get("description"),
        user_id=user_id,
        team_id=team_id,
        created_by_user_id=user_id,
        input_config=item.get("input_config", {}),
        output_config=item.get("output_config", {}),
        resource_config=item.get("resource_config", {}),
        validation_plan=item.get("validation_plan", []),
        validation_inputs=item.get("validation_inputs", []),
    )
    await new_wf.insert()

    new_step_ids = []
    for step_data in item.get("steps", []):
        new_task_ids = []
        for task_data in step_data.get("tasks", []):
            new_task = WorkflowStepTask(
                name=task_data["name"],
                data=task_data.get("data", {}),
            )
            await new_task.insert()
            new_task_ids.append(new_task.id)

        new_step = WorkflowStep(
            name=step_data["name"],
            tasks=new_task_ids,
            data=step_data.get("data", {}),
            is_output=step_data.get("is_output", False),
        )
        await new_step.insert()
        new_step_ids.append(new_step.id)

    new_wf.steps = new_step_ids
    await new_wf.save()

    return await workflow_service.get_workflow(str(new_wf.id))


# ---------------------------------------------------------------------------
# Search set export / import
# ---------------------------------------------------------------------------


async def export_search_set(search_set_uuid: str, user_email: str) -> dict:
    ss = await search_set_service.get_search_set(search_set_uuid)
    if not ss:
        raise ValueError("SearchSet not found")

    items_db = await ss.get_items()
    # Respect item_order
    if ss.item_order:
        order_map = {oid: idx for idx, oid in enumerate(ss.item_order)}
        items_db.sort(key=lambda i: order_map.get(str(i.id), len(order_map)))

    items_out = []
    for it in items_db:
        items_out.append({
            "searchphrase": it.searchphrase,
            "searchtype": it.searchtype,
            "title": it.title,
            "is_optional": it.is_optional,
            "enum_values": it.enum_values,
        })

    # Text-only test cases
    test_cases = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == search_set_uuid
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

    export_item = {
        "title": ss.title,
        "set_type": ss.set_type,
        "extraction_config": ss.extraction_config,
        "items": items_out,
        "test_cases": tc_out,
    }
    return _envelope("search_set", user_email, [export_item])


async def import_search_set(data: dict, user_id: str, team_id: str | None = None) -> SearchSet:
    """Import a search set from export data. Returns the new SearchSet."""
    err = validate_export_data(data)
    if err:
        raise ValueError(err)
    if data["export_type"] != "search_set":
        raise ValueError("Expected a search_set export file")

    item = data["items"][0]
    new_uuid = str(uuid_mod.uuid4())

    clone = SearchSet(
        title=f"{item['title']} (Imported)",
        uuid=new_uuid,
        team_id=team_id,
        status="active",
        set_type=item.get("set_type", "extraction"),
        user_id=user_id,
        created_by_user_id=user_id,
        extraction_config=item.get("extraction_config", {}),
    )
    await clone.insert()

    for field in item.get("items", []):
        new_item = SearchSetItem(
            searchphrase=field["searchphrase"],
            searchset=new_uuid,
            searchtype=field.get("searchtype", "extraction"),
            title=field.get("title", field["searchphrase"]),
            user_id=user_id,
            is_optional=field.get("is_optional", False),
            enum_values=field.get("enum_values", []),
        )
        await new_item.insert()

    # Import text-based test cases
    for tc_data in item.get("test_cases", []):
        tc = ExtractionTestCase(
            search_set_uuid=new_uuid,
            label=tc_data.get("label", "Imported test case"),
            source_type="text",
            source_text=tc_data.get("source_text", ""),
            expected_values=tc_data.get("expected_values", {}),
            user_id=user_id,
        )
        await tc.insert()

    return clone


# ---------------------------------------------------------------------------
# Knowledge base export / import
# ---------------------------------------------------------------------------


async def export_knowledge_base(kb_uuid: str, user_email: str) -> dict:
    """Export a knowledge base as a manifest with source list and cached content."""
    from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource

    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        raise ValueError("Knowledge base not found")

    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).to_list()

    sources_out = []
    for src in sources:
        entry = {
            "source_type": src.source_type,
            "url": src.url,
            "url_title": src.url_title,
            "document_uuid": src.document_uuid,
            "content": (src.content or "")[:100000],  # Truncate for export
        }
        sources_out.append(entry)

    item = {
        "title": kb.title,
        "description": kb.description,
        "sources": sources_out,
    }
    return _envelope("knowledge_base", user_email, [item])


async def import_knowledge_base(
    data: dict,
    user_id: str,
    team_id: str | None = None,
) -> "KnowledgeBase":
    """Import a knowledge base from export data."""
    from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
    from app.services import knowledge_service

    err = validate_export_data(data)
    if err:
        raise ValueError(err)
    if data["export_type"] != "knowledge_base":
        raise ValueError("Expected a knowledge_base export file")

    item = data["items"][0]
    kb = KnowledgeBase(
        title=f"{item['title']} (Imported)",
        description=item.get("description"),
        user_id=user_id,
        team_id=team_id,
    )
    await kb.insert()

    for src_data in item.get("sources", []):
        src = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type=src_data.get("source_type", "url"),
            url=src_data.get("url"),
            url_title=src_data.get("url_title"),
            document_uuid=src_data.get("document_uuid"),
            content=src_data.get("content"),
        )
        await src.insert()

        # Ingest from cached content or re-fetch
        if src.content:
            from app.services.document_manager import DocumentManager
            import asyncio
            dm = DocumentManager()
            try:
                chunk_count = await asyncio.to_thread(
                    dm.add_to_kb, kb.uuid, src.uuid,
                    src.url_title or src.url or "Imported", src.content,
                )
                src.chunk_count = chunk_count
                src.status = "ready"
                await src.save()
            except Exception:
                src.status = "error"
                await src.save()
        elif src.source_type == "url" and src.url:
            await knowledge_service._ingest_url_source(src, kb)
        elif src.source_type == "document" and src.document_uuid:
            await knowledge_service._ingest_document_source(src, kb)

    await knowledge_service.recalculate_stats(kb)
    return kb


# ---------------------------------------------------------------------------
# Catalog export / import
# ---------------------------------------------------------------------------


async def export_catalog(user_email: str) -> dict:
    """Export all verified catalog items with their full definitions."""
    result = await verification_service.list_verified_items(limit=10000)
    verified = result["items"]
    catalog_items: list[dict] = []

    for vi in verified:
        item_kind = vi["kind"]
        item_id = vi["item_id"]

        # Build the definition
        definition: dict | None = None
        if item_kind == "workflow":
            try:
                wf_export = await export_workflow(item_id, user_email)
                definition = wf_export["items"][0]
            except Exception:
                continue
        elif item_kind == "search_set":
            # item_id for search_set catalog items is the ObjectId string;
            # we need the uuid
            ss = await SearchSet.get(PydanticObjectId(item_id))
            if not ss:
                continue
            try:
                ss_export = await export_search_set(ss.uuid, user_email)
                definition = ss_export["items"][0]
            except Exception:
                continue

        if not definition:
            continue

        catalog_items.append({
            "item_kind": item_kind,
            "metadata": {
                "display_name": vi.get("display_name") or vi.get("name"),
                "description": vi.get("description"),
                "quality_tier": vi.get("quality_tier"),
                "quality_grade": vi.get("quality_grade"),
            },
            "definition": definition,
        })

    # Also include verified knowledge bases (which are in LibraryItem now)
    from app.models.knowledge import KnowledgeBase as KB
    for vi in verified:
        if vi["kind"] != "knowledge_base":
            continue
        kb = await KB.get(PydanticObjectId(vi["item_id"]))
        if not kb:
            continue
        try:
            kb_export = await export_knowledge_base(kb.uuid, user_email)
            definition = kb_export["items"][0]
        except Exception:
            continue
        catalog_items.append({
            "item_kind": "knowledge_base",
            "metadata": {
                "display_name": vi.get("display_name") or vi.get("name"),
                "description": vi.get("description"),
                "quality_tier": vi.get("quality_tier"),
                "quality_grade": vi.get("quality_grade"),
            },
            "definition": definition,
        })

    return _envelope("catalog", user_email, catalog_items)


def preview_catalog_import(data: dict) -> list[dict]:
    """Parse a catalog export and return a preview list (no DB writes)."""
    err = validate_export_data(data)
    if err:
        raise ValueError(err)
    if data["export_type"] != "catalog":
        raise ValueError("Expected a catalog export file")

    preview = []
    for idx, item in enumerate(data["items"]):
        defn = item.get("definition", {})
        meta = item.get("metadata", {})
        preview.append({
            "index": idx,
            "item_kind": item.get("item_kind", "unknown"),
            "name": meta.get("display_name") or defn.get("name") or defn.get("title") or "Unnamed",
            "description": meta.get("description") or "",
            "quality_tier": meta.get("quality_tier"),
            "quality_grade": meta.get("quality_grade"),
        })
    return preview


async def import_catalog_items(
    data: dict,
    selected_indices: list[int],
    user_id: str,
    space: str | None = None,
    team_id: str | None = None,
) -> list[dict]:
    """Import selected catalog items. Returns list of created item summaries."""
    err = validate_export_data(data)
    if err:
        raise ValueError(err)
    if data["export_type"] != "catalog":
        raise ValueError("Expected a catalog export file")

    results: list[dict] = []
    for idx in selected_indices:
        if idx < 0 or idx >= len(data["items"]):
            continue
        catalog_item = data["items"][idx]
        item_kind = catalog_item.get("item_kind")
        definition = catalog_item.get("definition", {})

        if item_kind == "workflow":
            wrapper = _envelope("workflow", "", [definition])
            wf = await import_workflow(wrapper, user_id, team_id=team_id)
            results.append({"kind": "workflow", "id": wf["id"], "name": wf["name"]})
        elif item_kind == "search_set":
            wrapper = _envelope("search_set", "", [definition])
            ss = await import_search_set(wrapper, user_id, team_id=team_id)
            results.append({"kind": "search_set", "uuid": ss.uuid, "name": ss.title})
        elif item_kind == "knowledge_base":
            wrapper = _envelope("knowledge_base", "", [definition])
            kb = await import_knowledge_base(wrapper, user_id, team_id=team_id)
            results.append({"kind": "knowledge_base", "uuid": kb.uuid, "name": kb.title})

    return results
