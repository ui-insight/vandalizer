"""SearchSet CRUD service."""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from typing import TYPE_CHECKING

from beanie import PydanticObjectId

from app.models.document import SmartDocument
from app.models.search_set import SearchSet, SearchSetItem
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_engine import ExtractionEngine

if TYPE_CHECKING:
    from app.models.user import User


# ---------------------------------------------------------------------------
# SearchSet CRUD
# ---------------------------------------------------------------------------

async def create_search_set(
    title: str,
    user_id: str,
    set_type: str,
    extraction_config: dict | None = None,
    team_id: str | None = None,
) -> SearchSet:
    ss = SearchSet(
        title=title,
        uuid=str(uuid_mod.uuid4()),
        status="active",
        set_type=set_type,
        user_id=user_id,
        team_id=team_id,
        created_by_user_id=user_id,
        extraction_config=extraction_config or {},
    )
    await ss.insert()
    return ss


async def list_search_sets(
    user: User | None = None,
    skip: int = 0,
    limit: int = 100,
    scope: str | None = None,
    search: str | None = None,
) -> list[SearchSet]:
    if user is None:
        return await SearchSet.find().skip(skip).limit(limit).to_list()

    # Scope queries to the user's current team (matches Library behavior)
    current_team = str(user.current_team) if user.current_team else None

    if scope == "mine":
        # User's own search sets within the current team
        query: dict = {"user_id": user.user_id}
        if current_team:
            query["team_id"] = {"$in": [current_team, None]}
    elif scope == "team":
        if not current_team:
            return []
        query = {"team_id": current_team, "user_id": {"$ne": user.user_id}}
    else:
        # Default: user's own (in current team) + all current team items
        if current_team:
            conditions: list[dict] = [
                {"user_id": user.user_id, "team_id": {"$in": [current_team, None]}},
                {"team_id": current_team},
            ]
            query = {"$or": conditions}
        else:
            query = {"user_id": user.user_id}

    # Add text search filter
    if search:
        query["title"] = {"$regex": search, "$options": "i"}

    return await SearchSet.find(query).skip(skip).limit(limit).to_list()


async def get_search_set(search_set_uuid: str) -> SearchSet | None:
    return await SearchSet.find_one(SearchSet.uuid == search_set_uuid)


async def get_search_set_item(item_id: str) -> SearchSetItem | None:
    try:
        return await SearchSetItem.get(PydanticObjectId(item_id))
    except Exception:
        return None


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
        status="active",
        set_type=original.set_type,
        user_id=user_id,
        team_id=original.team_id,
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
            is_optional=item.is_optional,
            enum_values=item.enum_values,
        )
        await new_item.insert()

    # Add clone to user's personal library
    from app.models.user import User as UserModel
    user = await UserModel.find_one(UserModel.user_id == user_id)
    if user:
        from app.services.library_service import get_or_create_personal_library, add_item
        lib = await get_or_create_personal_library(user_id)
        await add_item(str(lib.id), user, str(clone.id), "search_set")

    return clone


# ---------------------------------------------------------------------------
# SearchSetItem CRUD
# ---------------------------------------------------------------------------

async def update_item(
    item_id: str,
    searchphrase: str | None = None,
    title: str | None = None,
    is_optional: bool | None = None,
    enum_values: list[str] | None = None,
) -> SearchSetItem | None:
    item = await SearchSetItem.get(PydanticObjectId(item_id))
    if not item:
        return None
    if searchphrase is not None:
        item.searchphrase = searchphrase
    if title is not None:
        item.title = title
    if is_optional is not None:
        item.is_optional = is_optional
    if enum_values is not None:
        item.enum_values = enum_values
    await item.save()
    return item


async def add_item(
    search_set_uuid: str,
    searchphrase: str,
    searchtype: str = "extraction",
    title: str | None = None,
    user_id: str | None = None,
    is_optional: bool = False,
    enum_values: list[str] | None = None,
) -> SearchSetItem:
    item = SearchSetItem(
        searchphrase=searchphrase,
        searchset=search_set_uuid,
        searchtype=searchtype,
        title=title or searchphrase,
        user_id=user_id,
        is_optional=is_optional,
        enum_values=enum_values or [],
    )
    await item.insert()
    return item


async def list_items(search_set_uuid: str) -> list[SearchSetItem]:
    items = await SearchSetItem.find(SearchSetItem.searchset == search_set_uuid).to_list()
    # Respect item_order if set on the parent SearchSet
    ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    if ss and ss.item_order:
        order_map = {oid: idx for idx, oid in enumerate(ss.item_order)}
        items.sort(key=lambda it: order_map.get(str(it.id), len(order_map)))
    return items


async def reorder_items(search_set_uuid: str, item_ids: list[str]) -> bool:
    ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    if not ss:
        return False
    ss.item_order = item_ids
    await ss.save()
    return True


async def delete_item(item_id: str) -> bool:
    item = await get_search_set_item(item_id)
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


async def get_extraction_field_metadata(search_set_uuid: str) -> list[dict]:
    """Get per-field metadata (is_optional, enum_values) for a search set."""
    items = await SearchSetItem.find(
        SearchSetItem.searchset == search_set_uuid,
        SearchSetItem.searchtype == "extraction",
    ).to_list()
    return [
        {
            "key": item.searchphrase,
            "is_optional": item.is_optional,
            "enum_values": item.enum_values,
        }
        for item in items
    ]


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
Return JSON with the format {{"title": "Short Descriptive Name", "entities": ["value1", "value2", "etc"]}}. \
Do not nest values, keep the entities array flat and one-dimensional. \
Do not include the values, just the entity names in a single array of string values.

Important: The entity names should be Human Readable. Do not use underscores or camelCase. \
Use spaces and Title Case. For example, use "Invoice Number" instead of "invoice_number".

The "title" should be a short (3-8 word), specific, content-aware name for this kind of \
extraction template, reusable across similar documents. Prefer the document type plus a \
distinguishing identifier when one is clearly present (agency, program, award number, form \
number, contract ID, etc.). Examples: "NSF Award Notice Extraction", "NIH R01 Progress Report", \
"IRS Form 990 Extraction", "DOE SBIR Phase II Award". Avoid generic titles like "Extraction" \
or "Document Fields". Use Title Case. Do not include file extensions or timestamps.

Passage:
{doc_text}"""


async def build_from_documents(
    search_set_uuid: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
) -> tuple[list[str], str | None]:
    """Use an LLM to analyze documents and suggest extraction field names.

    Returns a tuple of (field_names, suggested_title). The suggested title is
    a short, content-aware name callers can use when the user didn't supply
    one explicitly; it may be None if the LLM didn't produce a usable value.
    """
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
            return [], None

    entities = parsed.get("entities", [])
    if not isinstance(entities, list):
        return [], None

    suggested_title = parsed.get("title")
    if isinstance(suggested_title, str):
        suggested_title = suggested_title.strip() or None
    else:
        suggested_title = None

    # Add items to the search set
    added = []
    for entity_name in entities:
        if not isinstance(entity_name, str) or not entity_name.strip():
            continue
        name = entity_name.strip()
        await add_item(search_set_uuid, name, searchtype="extraction", title=name, user_id=user_id)
        added.append(name)

    return added, suggested_title


# ---------------------------------------------------------------------------
# Run extraction
# ---------------------------------------------------------------------------

async def run_extraction_sync(
    search_set_uuid: str,
    document_uuids: list[str],
    user_id: str,
    model: str | None = None,
    extraction_config_override: dict | None = None,
    combined_context: bool = False,
) -> list:
    """Run extraction synchronously via asyncio.to_thread."""
    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        return []

    # Wait for any documents still being processed (e.g. file uploads where
    # text extraction hasn't finished yet) before reading their text.
    import asyncio as _asyncio
    _PROCESSING_POLL_INTERVAL = 3  # seconds
    _PROCESSING_TIMEOUT = 90  # seconds
    _waited = 0
    while _waited < _PROCESSING_TIMEOUT:
        still_processing = await SmartDocument.find(
            {"uuid": {"$in": document_uuids}, "processing": True},
        ).count()
        if still_processing == 0:
            break
        await _asyncio.sleep(_PROCESSING_POLL_INTERVAL)
        _waited += _PROCESSING_POLL_INTERVAL

    # Pre-load document texts and file paths
    import os
    from app.config import Settings
    upload_dir = Settings().upload_dir

    doc_texts: list[str] = []
    doc_file_paths: list[str] = []
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if doc and doc.raw_text:
            doc_texts.append(doc.raw_text)
        else:
            # Placeholder to keep indices aligned with doc_file_paths
            doc_texts.append("")
        if doc and doc.path:
            doc_file_paths.append(os.path.join(upload_dir, doc.path))
        else:
            doc_file_paths.append("")

    if not any(doc_texts) and not any(doc_file_paths):
        return []

    # Combined context: merge all documents into a single text for extraction
    if combined_context and len(doc_texts) > 1:
        merged = "\n\n---\n\n".join(t for t in doc_texts if t)
        doc_texts = [merged]
        doc_file_paths = []  # image mode not supported for combined

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

    # Fetch field metadata for enum/optional hints
    field_metadata = await get_extraction_field_metadata(search_set_uuid)

    engine = ExtractionEngine(system_config_doc=sys_config_doc)

    # Run in thread to avoid blocking the event loop
    result = await asyncio.to_thread(
        engine.extract,
        extract_keys=keys,
        model=model,
        doc_texts=doc_texts,
        extraction_config_override=combined_override or None,
        field_metadata=field_metadata,
        doc_file_paths=doc_file_paths,
    )
    return result
