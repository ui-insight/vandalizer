"""SearchSet CRUD service."""

import asyncio
import uuid as uuid_mod
from typing import Optional

from beanie import PydanticObjectId

from app.models.document import SmartDocument
from app.models.search_set import SearchSet, SearchSetItem
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_engine import ExtractionEngine


# ---------------------------------------------------------------------------
# SearchSet CRUD
# ---------------------------------------------------------------------------

async def create_search_set(title: str, space: str, set_type: str, user_id: str, extraction_config: dict | None = None) -> SearchSet:
    ss = SearchSet(
        title=title,
        uuid=str(uuid_mod.uuid4()),
        space=space,
        status="active",
        set_type=set_type,
        user_id=user_id,
        created_by_user_id=user_id,
        extraction_config=extraction_config or {},
    )
    await ss.insert()
    return ss


async def list_search_sets(space: str | None = None, user_id: str | None = None) -> list[SearchSet]:
    query = {}
    if space:
        query["space"] = space
    return await SearchSet.find(query).to_list()


async def get_search_set(search_set_uuid: str) -> SearchSet | None:
    return await SearchSet.find_one(SearchSet.uuid == search_set_uuid)


async def update_search_set(search_set_uuid: str, title: str | None = None, extraction_config: dict | None = None) -> SearchSet | None:
    ss = await get_search_set(search_set_uuid)
    if not ss:
        return None
    if title is not None:
        ss.title = title
    if extraction_config is not None:
        ss.extraction_config = extraction_config
    await ss.save()
    return ss


async def delete_search_set(search_set_uuid: str) -> bool:
    ss = await get_search_set(search_set_uuid)
    if not ss:
        return False
    # Delete associated items
    await SearchSetItem.find(SearchSetItem.searchset == search_set_uuid).delete()
    await ss.delete()
    return True


async def clone_search_set(search_set_uuid: str, user_id: str) -> SearchSet | None:
    original = await get_search_set(search_set_uuid)
    if not original:
        return None
    new_uuid = str(uuid_mod.uuid4())
    clone = SearchSet(
        title=f"{original.title} (Copy)",
        uuid=new_uuid,
        space=original.space,
        status="active",
        set_type=original.set_type,
        user_id=user_id,
        created_by_user_id=user_id,
        extraction_config=original.extraction_config,
    )
    await clone.insert()

    # Clone items
    items = await original.get_items()
    for item in items:
        new_item = SearchSetItem(
            searchphrase=item.searchphrase,
            searchset=new_uuid,
            searchtype=item.searchtype,
            title=item.title,
            user_id=user_id,
            space_id=item.space_id,
        )
        await new_item.insert()

    return clone


# ---------------------------------------------------------------------------
# SearchSetItem CRUD
# ---------------------------------------------------------------------------

async def update_item(item_id: str, searchphrase: str | None = None, title: str | None = None) -> SearchSetItem | None:
    item = await SearchSetItem.get(PydanticObjectId(item_id))
    if not item:
        return None
    if searchphrase is not None:
        item.searchphrase = searchphrase
    if title is not None:
        item.title = title
    await item.save()
    return item


async def add_item(search_set_uuid: str, searchphrase: str, searchtype: str = "extraction", title: str | None = None, user_id: str | None = None, space_id: str | None = None) -> SearchSetItem:
    item = SearchSetItem(
        searchphrase=searchphrase,
        searchset=search_set_uuid,
        searchtype=searchtype,
        title=title or searchphrase,
        user_id=user_id,
        space_id=space_id,
    )
    await item.insert()
    return item


async def list_items(search_set_uuid: str) -> list[SearchSetItem]:
    return await SearchSetItem.find(SearchSetItem.searchset == search_set_uuid).to_list()


async def delete_item(item_id: str) -> bool:
    item = await SearchSetItem.get(PydanticObjectId(item_id))
    if not item:
        return False
    await item.delete()
    return True


async def get_extraction_keys(search_set_uuid: str) -> list[str]:
    """Get list of extraction key phrases for a search set."""
    items = await SearchSetItem.find(
        SearchSetItem.searchset == search_set_uuid,
        SearchSetItem.searchtype == "extraction",
    ).to_list()
    return [item.searchphrase for item in items]


# ---------------------------------------------------------------------------
# Build from document (AI-powered field generation)
# ---------------------------------------------------------------------------

BUILD_FROM_DOC_SYSTEM_PROMPT = (
    "You are a data scientist working on a project to extract entities and their "
    "properties from a passage. You are tasked with extracting the entities and "
    "their properties from the following passage. Ensure all entity names are "
    "Human Readable with spaces, not underscores."
)

BUILD_FROM_DOC_USER_PROMPT = """Your job is to build an extraction set from the following information. \
Take the information given, and the instructions to extract the important information \
from this text. You will create an array of entities that an LLM could use and \
faithfully reproduce to extract the same values from this text every time. \
When asked to populate values for the entity types you return, it should give the user \
the important information from this document every time. \
Return an array formatted as json with the format {{"entities": ["value1", "value2", "etc"]}} \
containing entities for important information in the text. \
Do not nest values, keep the array flat and one-dimensional. \
Do not include the values, just the entity names in a single array of string values.

Important: The entity names should be Human Readable. Do not use underscores or camelCase. \
Use spaces and Title Case. For example, use "Invoice Number" instead of "invoice_number".

Passage:
{doc_text}"""


async def build_from_documents(
    search_set_uuid: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
) -> list[str]:
    """Use an LLM to analyze documents and suggest extraction field names."""
    import json as _json
    from app.services.llm_service import create_chat_agent

    # Load document texts
    doc_text = ""
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if doc and doc.raw_text:
            doc_text += doc.raw_text + "\n"

    if not doc_text.strip():
        return []

    # Resolve model
    if not model:
        model = await get_user_model_name(user_id)

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    agent = create_chat_agent(
        model,
        system_prompt=BUILD_FROM_DOC_SYSTEM_PROMPT,
        system_config_doc=sys_config_doc,
    )

    prompt = BUILD_FROM_DOC_USER_PROMPT.format(doc_text=doc_text[:100000])
    try:
        result = await agent.run(prompt)
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}") from e
    response_text = result.output

    # Parse JSON from response
    text = response_text.strip()
    # Strip markdown code blocks if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = _json.loads(text)
    except _json.JSONDecodeError:
        # Try to find JSON object in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = _json.loads(text[start:end])
        else:
            return []

    entities = parsed.get("entities", [])
    if not isinstance(entities, list):
        return []

    # Add items to the search set
    added = []
    for entity_name in entities:
        if not isinstance(entity_name, str) or not entity_name.strip():
            continue
        name = entity_name.strip()
        await add_item(search_set_uuid, name, searchtype="extraction", title=name, user_id=user_id)
        added.append(name)

    return added


# ---------------------------------------------------------------------------
# Run extraction
# ---------------------------------------------------------------------------

async def run_extraction_sync(
    search_set_uuid: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
    extraction_config_override: dict | None = None,
) -> list:
    """Run extraction synchronously via asyncio.to_thread."""
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        return []

    # Pre-load document texts
    doc_texts = []
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if doc and doc.raw_text:
            doc_texts.append(doc.raw_text)

    if not doc_texts:
        return []

    # Resolve model
    if not model:
        model = await get_user_model_name(user_id)

    # Load per-searchset config override
    ss = await get_search_set(search_set_uuid)
    combined_override = {}
    if ss and ss.extraction_config:
        combined_override.update(ss.extraction_config)
    if extraction_config_override:
        combined_override.update(extraction_config_override)

    # Pre-fetch system config for sync engine
    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}

    engine = ExtractionEngine(system_config_doc=sys_config_doc)

    # Run in thread to avoid blocking the event loop
    result = await asyncio.to_thread(
        engine.extract,
        extract_keys=keys,
        model=model,
        doc_texts=doc_texts,
        extraction_config_override=combined_override or None,
    )
    return result
