"""Agentic chat tool functions.

Each tool is registered on the agentic chat agent via ``@agent.tool`` and
receives ``RunContext[AgenticChatDeps]`` for user-scoped authorization.

Tools are exported as the ``TOOLS`` list for bulk registration.
"""

import asyncio
import logging
import re
from typing import Optional

from pydantic_ai.tools import RunContext

from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.folder import SmartFolder
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.quality_alert import QualityAlert
from app.models.search_set import SearchSet, SearchSetItem
from app.models.validation_run import ValidationRun
from app.models.verification_session import VerificationField, VerificationSession
from app.models.workflow import Workflow, WorkflowStep
from app.services.chat_deps import AgenticChatDeps
from app.services.document_manager import get_document_manager

logger = logging.getLogger(__name__)

MAX_RESULTS = 20


def _score_to_tier(score: float | None) -> str | None:
    """Map a numeric quality score to a tier label."""
    if score is None:
        return None
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


# ---------------------------------------------------------------------------
# Phase 1 — Read-only tools
# ---------------------------------------------------------------------------


# Filler words that add noise to search queries like "what's in the X document"
_QUERY_STOPWORDS = frozenset({
    "a", "an", "the", "in", "on", "of", "is", "are", "was", "were", "be", "to",
    "for", "with", "about", "and", "or", "but", "my", "your",
    "what", "whats", "what's", "whos", "who's", "where", "when", "which", "how",
    "show", "find", "search", "get", "tell", "me", "please",
    "document", "documents", "file", "files", "doc", "docs", "guide", "sheet",
    # File extensions — dropped so "foo.pdf" tokenizes to ["foo"] instead of
    # forcing a lookahead on "pdf" that matches every PDF in the workspace.
    "pdf", "docx", "xlsx", "xls", "html", "htm", "txt", "csv", "jpg", "jpeg",
    "png", "gif", "ppt", "pptx",
})


def _tokenize_query(query: str) -> list[str]:
    """Normalize and tokenize a search query.

    - Lowercases
    - Replaces separators (_ - . /) with spaces so "elven garden guide"
      can match titles like "Elven_Garden_Guide.pdf"
    - Drops filler words so "what's in my elven garden guide" reduces to
      ["elven", "garden"]
    - Preserves quoted phrases as single tokens (e.g. ``"thirty meter telescope"``)
    """
    if not query:
        return []
    # Extract quoted phrases first so they survive tokenization
    quoted = re.findall(r'"([^"]+)"', query)
    remainder = re.sub(r'"[^"]+"', " ", query)
    # Replace separators with spaces and lowercase
    remainder = re.sub(r"[_\-./\\,;:!?()\[\]{}]+", " ", remainder.lower())
    raw_tokens = [t for t in remainder.split() if t]
    content_tokens = [t for t in raw_tokens if t not in _QUERY_STOPWORDS]
    # Reinsert quoted phrases (as-is, lowered) at the front
    tokens = [q.lower().strip() for q in quoted if q.strip()] + content_tokens
    # If stopword stripping killed everything (e.g. query was only "the guide"),
    # fall back to the raw tokens so we still search *something*.
    return tokens or raw_tokens


def _words_to_regex(query: str) -> str:
    r"""Build a regex that requires every tokenized word in *query* to appear (any order).

    ``"what's in my elven garden guide"`` tokenizes to ``["elven", "garden"]``
    and produces ``(?=[\s\S]*elven)(?=[\s\S]*garden)``.

    Uses ``[\s\S]`` instead of ``.`` so the lookahead crosses newline boundaries
    (MongoDB regex does not enable dotall by default).
    """
    tokens = _tokenize_query(query)
    if not tokens:
        return ""
    if len(tokens) == 1:
        return re.escape(tokens[0])
    return "".join(rf"(?=[\s\S]*{re.escape(t)})" for t in tokens)


def _build_owner_filter(deps: "AgenticChatDeps") -> dict:
    """Build the owner-scope filter for user + all accessible teams.

    Mirrors the logic in ``routers/documents.py`` so chat tools see the same
    documents the file browser does. Previously the tool only scoped by a
    single team_id *or* user_id, silently hiding personal docs whenever the
    user had a current_team set.
    """
    ta = deps.team_access
    conditions: list[dict] = [{"user_id": deps.user_id}]
    if ta and ta.team_uuids:
        conditions.append({"team_id": {"$in": list(ta.team_uuids)}})
    if ta and ta.team_object_ids:
        conditions.append({"team_id": {"$in": list(ta.team_object_ids)}})
    return {"$or": conditions}


async def search_documents(
    context: RunContext[AgenticChatDeps],
    query: str,
    search_content: bool = False,
) -> list[dict]:
    """Search the user's documents by title (fast) or full content (slow).

    Args:
        context: The call context.
        query: A text query to match against document titles (or content if
               search_content=True). Multi-word queries match each word
               independently (any order). Common filler words ("the",
               "what's in", "document") and file extensions (".pdf", ".docx")
               are stripped.
        search_content: If True, also regex-match the document's extracted
               text. Off by default because content search is a full
               collection scan (no text index) and can time out on large
               workspaces. Only set this when a title search returns nothing
               and the user is describing content rather than a filename.
    """
    owner_filter = _build_owner_filter(context.deps)
    base_filters: dict = {"$and": [owner_filter, {"soft_deleted": {"$ne": True}}]}

    if query:
        pattern = _words_to_regex(query)
        if pattern:
            title_regex = {"title": {"$regex": pattern, "$options": "i"}}
            if search_content:
                text_filter = {
                    "$or": [
                        title_regex,
                        {"raw_text": {"$regex": pattern, "$options": "i"}},
                    ],
                }
            else:
                text_filter = title_regex
            filters = {"$and": [*base_filters["$and"], text_filter]}
        else:
            filters = base_filters
    else:
        filters = base_filters

    docs = await SmartDocument.find(filters).sort("-created_at").limit(MAX_RESULTS).to_list()
    return [
        {
            "uuid": d.uuid,
            "title": d.title,
            "extension": d.extension,
            "pages": d.num_pages,
            "classification": d.classification,
            "folder": d.folder,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


async def list_documents(
    context: RunContext[AgenticChatDeps],
    folder_uuid: Optional[str] = None,
) -> dict:
    """List documents and folders in a directory. Defaults to the root folder.

    Args:
        context: The call context.
        folder_uuid: UUID of the folder to list. Omit or pass null for the root.
    """
    owner_filter = _build_owner_filter(context.deps)
    doc_conditions: list[dict] = [owner_filter, {"soft_deleted": {"$ne": True}}]
    folder_conditions: list[dict] = [owner_filter]

    if folder_uuid:
        doc_conditions.append({"folder": folder_uuid})
        folder_conditions.append({"parent_id": folder_uuid})
    else:
        doc_conditions.append({"folder": {"$in": [None, "", "0"]}})
        folder_conditions.append({"parent_id": {"$in": [None, ""]}})

    doc_filters = {"$and": doc_conditions}
    folder_filters = {"$and": folder_conditions}

    folders = await SmartFolder.find(folder_filters).sort("title").limit(50).to_list()
    docs = await SmartDocument.find(doc_filters).sort("-created_at").limit(MAX_RESULTS).to_list()

    return {
        "folders": [
            {"uuid": f.uuid, "title": f.title}
            for f in folders
        ],
        "documents": [
            {
                "uuid": d.uuid,
                "title": d.title,
                "extension": d.extension,
                "pages": d.num_pages,
            }
            for d in docs
        ],
    }


async def search_knowledge_base(
    context: RunContext[AgenticChatDeps],
    query: str,
    kb_uuid: Optional[str] = None,
) -> list[dict]:
    """Search a knowledge base for relevant content chunks using semantic search.

    Args:
        context: The call context.
        query: The search query.
        kb_uuid: UUID of the knowledge base to search. Uses the active KB if omitted.
    """
    uuid = kb_uuid or context.deps.active_kb_uuid
    if not uuid:
        return [{"error": "No knowledge base specified. Use list_knowledge_bases to find one."}]

    # Verify the KB exists and user has access
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == uuid)
    if not kb:
        return [{"error": f"Knowledge base '{uuid}' not found."}]

    team_id = context.deps.team_id
    user_id = context.deps.user_id
    if not kb.verified and not kb.shared_with_team:
        if kb.user_id != user_id:
            return [{"error": "You do not have access to this knowledge base."}]
    if kb.shared_with_team and kb.team_id and team_id:
        if kb.team_id != team_id:
            return [{"error": "You do not have access to this knowledge base."}]

    if kb.status and kb.status != "ready":
        return [{"error": f"Knowledge base \"{kb.title}\" is currently {kb.status}. Try again in a few minutes once indexing completes."}]

    dm = get_document_manager()
    results = await asyncio.to_thread(dm.query_kb, uuid, query, 8)

    # Record behavioral memory — best-effort, never blocks the tool.
    from app.services import user_memory_service
    await user_memory_service.record_kb_query(user_id, team_id, uuid, kb.title or uuid)

    # Batch-lookup KnowledgeBaseSource records to enrich results with
    # source_type, document_uuid, and url so the frontend can link back
    # to the original document or website.
    source_ids = list(
        {r.get("metadata", {}).get("source_id") for r in results}
        - {None, ""}
    )
    source_map: dict[str, KnowledgeBaseSource] = {}
    if source_ids:
        sources = await KnowledgeBaseSource.find(
            {"uuid": {"$in": source_ids}}
        ).to_list()
        source_map = {s.uuid: s for s in sources}

    enriched: list[dict] = []
    for r in results:
        meta = r.get("metadata", {})
        sid = meta.get("source_id", "")
        entry: dict = {
            "content": r.get("content", ""),
            "source_name": meta.get("source_name", "unknown"),
        }
        src = source_map.get(sid)
        if src:
            entry["source_type"] = src.source_type
            if src.source_type == "document" and src.document_uuid:
                entry["document_uuid"] = src.document_uuid
            elif src.source_type == "url" and src.url:
                entry["url"] = src.url
        enriched.append(entry)

    return enriched


async def list_knowledge_bases(
    context: RunContext[AgenticChatDeps],
) -> list[dict]:
    """List knowledge bases available to the user (personal, team-shared, and verified).

    Args:
        context: The call context.
    """
    team_id = context.deps.team_id
    user_id = context.deps.user_id

    # Personal + team shared + verified
    filters = {
        "$or": [
            {"user_id": user_id},
            {"verified": True},
        ]
    }
    if team_id:
        filters["$or"].append({"team_id": team_id, "shared_with_team": True})

    kbs = await KnowledgeBase.find(filters).sort("-updated_at").limit(MAX_RESULTS).to_list()
    return [
        {
            "uuid": kb.uuid,
            "title": kb.title,
            "description": kb.description,
            "status": kb.status,
            "total_sources": kb.total_sources,
            "total_chunks": kb.total_chunks,
            "verified": kb.verified,
            "shared_with_team": kb.shared_with_team,
        }
        for kb in kbs
    ]


async def list_extraction_sets(
    context: RunContext[AgenticChatDeps],
    search: Optional[str] = None,
) -> list[dict]:
    """List extraction templates available to the user.

    Args:
        context: The call context.
        search: Optional text to filter extraction templates by title.
    """
    team_id = context.deps.team_id
    user_id = context.deps.user_id

    filters: dict = {
        "$or": [
            {"user_id": user_id},
            {"verified": True},
        ]
    }
    if team_id:
        filters["$or"].append({"team_id": team_id})
    if search:
        filters["title"] = {"$regex": re.escape(search), "$options": "i"}

    sets = await SearchSet.find(filters).sort("-created_at").limit(MAX_RESULTS).to_list()

    results = []
    for ss in sets:
        field_count = len(ss.item_order) if ss.item_order else 0
        results.append({
            "uuid": ss.uuid,
            "title": ss.title,
            "verified": ss.verified or False,
            "field_count": field_count,
            "domain": ss.domain,
        })
    return results


async def list_workflows(
    context: RunContext[AgenticChatDeps],
    search: Optional[str] = None,
) -> list[dict]:
    """List workflows available to the user.

    Args:
        context: The call context.
        search: Optional text to filter workflows by name.
    """
    team_id = context.deps.team_id
    user_id = context.deps.user_id

    filters: dict = {
        "$or": [
            {"user_id": user_id},
            {"verified": True},
        ]
    }
    if team_id:
        filters["$or"].append({"team_id": team_id})
    if search:
        filters["name"] = {"$regex": re.escape(search), "$options": "i"}

    workflows = await Workflow.find(filters).sort("-updated_at").limit(MAX_RESULTS).to_list()
    return [
        {
            "id": str(w.id),
            "name": w.name,
            "description": w.description,
            "verified": w.verified or False,
            "step_count": len(w.steps) if w.steps else 0,
        }
        for w in workflows
    ]


async def get_quality_info(
    context: RunContext[AgenticChatDeps],
    item_kind: str,
    item_uuid: str,
) -> dict:
    """Get quality, validation, and verification metadata for an extraction set, workflow, or knowledge base.

    Args:
        context: The call context.
        item_kind: The type of item — one of 'search_set', 'workflow', or 'knowledge_base'.
        item_uuid: The UUID or ID of the item.
    """
    # Latest validation run
    latest_run = await ValidationRun.find(
        ValidationRun.item_kind == item_kind,
        ValidationRun.item_id == item_uuid,
    ).sort("-created_at").first_or_none()

    # Active (unacknowledged) quality alerts
    alerts = await QualityAlert.find(
        QualityAlert.item_kind == item_kind,
        QualityAlert.item_id == item_uuid,
        QualityAlert.acknowledged != True,
    ).sort("-created_at").limit(5).to_list()

    result: dict = {
        "item_kind": item_kind,
        "item_uuid": item_uuid,
    }

    if latest_run:
        result["score"] = latest_run.score
        result["accuracy"] = latest_run.accuracy
        result["consistency"] = latest_run.consistency
        result["grade"] = latest_run.grade
        result["num_test_cases"] = latest_run.num_test_cases
        result["num_runs"] = latest_run.num_runs
        result["last_validated_at"] = latest_run.created_at.isoformat() if latest_run.created_at else None
        if latest_run.score_breakdown:
            result["score_breakdown"] = latest_run.score_breakdown
    else:
        result["score"] = None
        result["last_validated_at"] = None
        result["note"] = "No validation runs found for this item."

    alert_list = [
        {
            "type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ] if alerts else []

    result["active_alerts"] = alert_list

    # Emit quality sidecar — streaming layer strips this and sends to frontend
    if latest_run and latest_run.score is not None:
        result["quality"] = {
            "score": latest_run.score,
            "tier": _score_to_tier(latest_run.score),
            "grade": latest_run.grade,
            "last_validated_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
            "num_test_cases": latest_run.num_test_cases,
            "num_runs": latest_run.num_runs,
            "active_alerts": alert_list,
        }

    return result


async def search_library(
    context: RunContext[AgenticChatDeps],
    query: str,
    kind: Optional[str] = None,
) -> list[dict]:
    """Search the library for extraction sets, workflows, or knowledge bases by name or tags.

    Args:
        context: The call context.
        query: The search query.
        kind: Optional filter — one of 'workflow', 'search_set', or 'knowledge_base'.
    """
    from app.services.library_service import search_libraries

    results = await search_libraries(
        user=context.deps.user,
        query=query,
        team_id=context.deps.team_id,
        kind=kind,
    )
    return results[:MAX_RESULTS]


# ---------------------------------------------------------------------------
# Phase 2 — Extraction tools
# ---------------------------------------------------------------------------


async def get_document_text(
    context: RunContext[AgenticChatDeps],
    document_uuid: str,
) -> dict:
    """Get the full text content of a document. Useful for reading before extracting.

    Args:
        context: The call context.
        document_uuid: UUID of the document to read.
    """
    doc = await SmartDocument.find_one(SmartDocument.uuid == document_uuid)
    if not doc:
        return {"error": f"Document '{document_uuid}' not found."}

    # Authorization: must belong to user's team or the user directly
    team_id = context.deps.team_id
    if team_id:
        if doc.team_id != team_id and doc.user_id != context.deps.user_id:
            return {"error": "You do not have access to this document."}
    else:
        if doc.user_id != context.deps.user_id:
            return {"error": "You do not have access to this document."}

    text = doc.raw_text or ""
    # Truncate to avoid overwhelming the LLM context
    max_chars = 30000
    truncated = len(text) > max_chars
    return {
        "uuid": doc.uuid,
        "title": doc.title,
        "extension": doc.extension,
        "pages": doc.num_pages,
        "text": text[:max_chars],
        "truncated": truncated,
        "total_chars": len(text),
    }


async def run_extraction(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
    document_uuids: list[str],
) -> dict:
    """Run an extraction template against one or more documents. Returns extracted entities with quality metadata.

    Maximum 10 documents per call. Results are capped at 50 entities.
    If you need to process more documents, call this tool multiple times.

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template to run.
        document_uuids: List of document UUIDs to extract from (max 10).
    """
    from app.services.extraction_engine import ExtractionEngine

    # Load the search set
    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return {"error": f"Extraction set '{extraction_set_uuid}' not found."}

    # Authorization: must be accessible to user
    team_id = context.deps.team_id
    user_id = context.deps.user_id
    if not ss.verified and ss.user_id != user_id:
        if not (team_id and ss.team_id == team_id):
            return {"error": "You do not have access to this extraction set."}

    # Load extraction items (fields)
    items = await ss.get_extraction_items()
    if not items:
        return {"error": "Extraction set has no fields defined."}

    keys = [item.searchphrase for item in items if item.searchphrase]
    if not keys:
        return {"error": "Extraction set has no valid field keys."}

    # Build field metadata
    field_metadata = [
        {
            "key": item.searchphrase,
            "is_optional": item.is_optional,
            "enum_values": item.enum_values,
        }
        for item in items
        if item.searchphrase
    ]

    # Authorize and load document texts
    doc_texts: list[str] = []
    doc_names: list[str] = []
    for doc_uuid in document_uuids[:10]:  # Cap at 10 documents
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if not doc:
            continue
        # Authorization check
        if team_id:
            if doc.team_id != team_id and doc.user_id != user_id:
                continue
        else:
            if doc.user_id != user_id:
                continue
        if doc.raw_text:
            doc_texts.append(doc.raw_text)
            doc_names.append(doc.title or doc_uuid)

    if not doc_texts:
        return {"error": "No accessible documents with text content found."}

    # Run extraction synchronously in a thread
    sys_cfg = context.deps.system_config_doc

    def _run():
        engine = ExtractionEngine(system_config_doc=sys_cfg, domain=ss.domain)
        results = engine.extract(
            extract_keys=keys,
            doc_texts=doc_texts,
            extraction_config_override=ss.extraction_config or None,
            field_metadata=field_metadata,
        )
        return results, engine.tokens_in, engine.tokens_out

    try:
        results, tokens_in, tokens_out = await asyncio.wait_for(
            asyncio.to_thread(_run), timeout=120,
        )
    except asyncio.TimeoutError:
        return {"error": "Extraction timed out after 2 minutes. Try with fewer documents or a smaller extraction set."}

    # Record behavioral memory — best-effort, never blocks the tool.
    from app.services import user_memory_service
    await user_memory_service.record_extraction(
        user_id, team_id, extraction_set_uuid, ss.title or extraction_set_uuid
    )

    # Attach quality metadata as sidecar if validation data exists
    latest_run = await ValidationRun.find(
        ValidationRun.item_kind == "search_set",
        ValidationRun.item_id == extraction_set_uuid,
    ).sort("-created_at").first_or_none()

    docs_requested = len(document_uuids)
    docs_skipped = docs_requested - len(doc_names)

    response: dict = {
        "extraction_set": ss.title,
        "fields": keys,
        "documents": doc_names,
        "entities": results[:50],  # Cap output size
        "entity_count": len(results),
        "token_usage": {"input": tokens_in, "output": tokens_out},
    }
    if docs_skipped > 0:
        response["note"] = f"{docs_skipped} of {docs_requested} document(s) were skipped (not found or not accessible)."
    if len(results) > 50:
        response["note"] = response.get("note", "") + f" Results truncated to 50 of {len(results)} entities."

    # Quality sidecar — streaming layer strips "quality" key before LLM sees it
    if latest_run and latest_run.score is not None:
        # Check for active alerts on this extraction set
        alerts = await QualityAlert.find(
            QualityAlert.item_kind == "search_set",
            QualityAlert.item_id == extraction_set_uuid,
            QualityAlert.acknowledged != True,
        ).sort("-created_at").limit(3).to_list()

        response["quality"] = {
            "score": latest_run.score,
            "tier": _score_to_tier(latest_run.score),
            "grade": latest_run.grade,
            "accuracy": latest_run.accuracy,
            "consistency": latest_run.consistency,
            "last_validated_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
            "num_test_cases": latest_run.num_test_cases,
            "num_runs": latest_run.num_runs,
            "active_alerts": [
                {"type": a.alert_type, "severity": a.severity, "message": a.message}
                for a in alerts
            ],
        }

    return response


# ---------------------------------------------------------------------------
# Phase 3 — Knowledge base write tools
# ---------------------------------------------------------------------------


async def create_knowledge_base(
    context: RunContext[AgenticChatDeps],
    title: str,
    description: str = "",
    confirmed: bool = False,
) -> dict:
    """Create a new knowledge base for the user.

    Call first with confirmed=false to preview. Then call again with confirmed=true after the user approves.

    Args:
        context: The call context.
        title: Title for the new knowledge base.
        description: Optional description.
        confirmed: Must be true to actually create. If false, returns a preview for user confirmation.
    """
    if not confirmed:
        return {
            "action": "create_knowledge_base",
            "preview": f"Create a new knowledge base titled \"{title}\"" + (f" — {description}" if description else ""),
            "needs_confirmation": True,
        }

    from app.services.knowledge_service import create_knowledge_base as kb_create

    kb = await kb_create(
        title=title,
        user_id=context.deps.user_id,
        team_id=context.deps.team_id,
        description=description or None,
    )
    return {
        "uuid": kb.uuid,
        "title": kb.title,
        "description": kb.description,
        "status": kb.status,
        "message": f"Knowledge base '{kb.title}' created successfully.",
    }


async def add_documents_to_kb(
    context: RunContext[AgenticChatDeps],
    kb_uuid: str,
    document_uuids: list[str],
    confirmed: bool = False,
) -> dict:
    """Add documents to an existing knowledge base. Documents are chunked and indexed for semantic search.

    Call first with confirmed=false to preview. Then call again with confirmed=true after the user approves.

    Args:
        context: The call context.
        kb_uuid: UUID of the knowledge base.
        document_uuids: List of document UUIDs to add.
        confirmed: Must be true to actually add. If false, returns a preview for user confirmation.
    """
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        return {"error": f"Knowledge base '{kb_uuid}' not found."}

    # Authorization
    user = context.deps.user
    if kb.user_id != user.user_id and not kb.shared_with_team:
        if not (context.deps.team_id and kb.team_id == context.deps.team_id):
            return {"error": "You do not have access to this knowledge base."}

    if not confirmed:
        return {
            "action": "add_documents_to_kb",
            "preview": f"Add {len(document_uuids)} document(s) to knowledge base \"{kb.title}\"",
            "needs_confirmation": True,
        }

    from app.services.knowledge_service import add_documents as kb_add_docs

    added = await kb_add_docs(kb, document_uuids[:20], user)
    return {
        "kb_uuid": kb_uuid,
        "kb_title": kb.title,
        "documents_added": added,
        "documents_requested": len(document_uuids),
        "message": f"Added {added} document(s) to '{kb.title}'. Indexing may take a moment.",
    }


async def add_url_to_kb(
    context: RunContext[AgenticChatDeps],
    kb_uuid: str,
    url: str,
    crawl: bool = False,
    confirmed: bool = False,
) -> dict:
    """Add a URL source to a knowledge base. Optionally crawl linked pages.

    Call first with confirmed=false to preview. Then call again with confirmed=true after the user approves.

    Args:
        context: The call context.
        kb_uuid: UUID of the knowledge base.
        url: The URL to add.
        crawl: If true, follow links on the page and index them too (max 5 pages).
        confirmed: Must be true to actually add. If false, returns a preview for user confirmation.
    """
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        return {"error": f"Knowledge base '{kb_uuid}' not found."}

    user = context.deps.user
    if kb.user_id != user.user_id and not kb.shared_with_team:
        if not (context.deps.team_id and kb.team_id == context.deps.team_id):
            return {"error": "You do not have access to this knowledge base."}

    if not confirmed:
        action = f"Add URL \"{url}\" to knowledge base \"{kb.title}\""
        if crawl:
            action += " (with link crawling, up to 5 pages)"
        return {
            "action": "add_url_to_kb",
            "preview": action,
            "needs_confirmation": True,
        }

    from app.services.knowledge_service import add_urls as kb_add_urls

    added = await kb_add_urls(
        kb, [url],
        crawl_enabled=crawl,
        max_crawl_pages=5 if crawl else 1,
    )
    return {
        "kb_uuid": kb_uuid,
        "kb_title": kb.title,
        "urls_added": added,
        "crawl_enabled": crawl,
        "message": f"Added URL to '{kb.title}'. Ingestion will process in the background.",
    }


# ---------------------------------------------------------------------------
# Phase 4 — Workflow orchestration tools
# ---------------------------------------------------------------------------


async def run_workflow(
    context: RunContext[AgenticChatDeps],
    workflow_id: str,
    document_uuids: list[str],
    confirmed: bool = False,
) -> dict:
    """Start a workflow execution against documents. Returns a session ID for status polling.

    Call first with confirmed=false to preview. Then call again with confirmed=true after the user approves.
    Workflows run asynchronously in the background. Use get_workflow_status to check progress.

    Args:
        context: The call context.
        workflow_id: The ID of the workflow to execute.
        document_uuids: List of document UUIDs to process.
        confirmed: Must be true to actually run. If false, returns a preview for user confirmation.
    """
    # Look up workflow and verify access
    wf = await Workflow.get(workflow_id)
    if not wf:
        return {"error": f"Workflow '{workflow_id}' not found."}

    team_id = context.deps.team_id
    user_id = context.deps.user_id
    if not wf.verified and getattr(wf, "user_id", None) != user_id:
        if not (team_id and getattr(wf, "team_id", None) == team_id):
            return {"error": "You do not have access to this workflow."}

    if not confirmed:
        return {
            "action": "run_workflow",
            "preview": f"Run workflow \"{wf.name}\" on {len(document_uuids)} document(s)",
            "needs_confirmation": True,
        }

    from app.services import workflow_service

    try:
        session_id = await workflow_service.run_workflow(
            workflow_id=workflow_id,
            document_uuids=document_uuids[:10],
            user_id=context.deps.user_id,
            model=context.deps.model_name or None,
            user=context.deps.user,
        )
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("Workflow launch failed: %s", e)
        return {"error": f"Failed to start workflow: {e}"}

    # Record behavioral memory — best-effort, never blocks the tool.
    from app.services import user_memory_service
    await user_memory_service.record_workflow(
        user_id, team_id, workflow_id, wf.name or workflow_id
    )

    return {
        "session_id": session_id,
        "status": "running",
        "message": "Workflow started. Use get_workflow_status with the session_id to check progress.",
    }


async def get_workflow_status(
    context: RunContext[AgenticChatDeps],
    session_id: str,
) -> dict:
    """Check the status of a running or completed workflow execution.

    Args:
        context: The call context.
        session_id: The session ID returned by run_workflow.
    """
    from app.services import workflow_service

    status = await workflow_service.get_workflow_status(
        session_id, user=context.deps.user,
    )
    if not status:
        return {"error": f"Workflow session '{session_id}' not found."}

    result: dict = {
        "status": status["status"],
        "steps_completed": status["num_steps_completed"],
        "steps_total": status["num_steps_total"],
        "current_step": status.get("current_step_name"),
    }

    if status["status"] == "completed" and status.get("final_output"):
        final = status["final_output"]
        # Return the output but cap size
        if isinstance(final, dict) and "output" in final:
            output = final["output"]
            if isinstance(output, str) and len(output) > 5000:
                output = output[:5000] + "\n\n[Output truncated...]"
            result["output"] = output
        else:
            result["output"] = final
    elif status["status"] == "failed":
        result["error_detail"] = status.get("current_step_detail")
    elif status["status"] == "paused":
        result["approval_request_id"] = status.get("approval_request_id")
        result["message"] = "Workflow is paused waiting for approval."

    if status.get("current_step_preview"):
        result["preview"] = status["current_step_preview"]

    return result


# ---------------------------------------------------------------------------
# Phase 5 — Validation & guided verification tools
# ---------------------------------------------------------------------------


async def list_test_cases(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
) -> dict:
    """List existing test cases (ground truth) for an extraction set.

    Use this to understand validation coverage before proposing new test cases
    — e.g., if the set already has 5 test cases, suggest one with different
    characteristics instead of a near-duplicate.

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template.
    """
    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return {"error": f"Extraction set '{extraction_set_uuid}' not found."}

    team_id = context.deps.team_id
    user_id = context.deps.user_id
    if not ss.verified and ss.user_id != user_id:
        if not (team_id and ss.team_id == team_id):
            return {"error": "You do not have access to this extraction set."}

    test_cases = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == extraction_set_uuid
    ).sort("-created_at").limit(MAX_RESULTS).to_list()

    return {
        "extraction_set": ss.title,
        "count": len(test_cases),
        "test_cases": [
            {
                "uuid": tc.uuid,
                "label": tc.label,
                "source_type": tc.source_type,
                "document_uuid": tc.document_uuid,
                "field_count": len(tc.expected_values or {}),
                "created_at": tc.created_at.isoformat() if tc.created_at else None,
            }
            for tc in test_cases
        ],
    }


async def propose_test_case(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
    document_uuid: str,
    label: Optional[str] = None,
) -> dict:
    """Propose a new test case by extracting values and opening a guided verification session.

    This runs the extraction once and creates a VerificationSession — it does
    NOT persist a test case yet. The frontend opens the document in the viewer
    with each extracted value highlighted so the user can approve or correct
    each one in context. Only after the user finalizes the session does an
    ExtractionTestCase get created with user-verified ground truth.

    Prefer this over assuming an extraction is correct. Use this whenever the
    user says things like "looks right", "save this as a test case", "use this
    for validation", or when you notice a good candidate document for
    validation (well-structured, representative, known-good).

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template.
        document_uuid: UUID of the document to extract from.
        label: Optional human-readable label for the test case. Defaults to the document title.
    """
    from app.services.extraction_engine import ExtractionEngine

    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return {"error": f"Extraction set '{extraction_set_uuid}' not found."}

    user_id = context.deps.user_id
    team_id = context.deps.team_id
    if not ss.verified and ss.user_id != user_id:
        if not (team_id and ss.team_id == team_id):
            return {"error": "You do not have access to this extraction set."}

    doc = await SmartDocument.find_one(SmartDocument.uuid == document_uuid)
    if not doc:
        return {"error": f"Document '{document_uuid}' not found."}
    if team_id:
        if doc.team_id != team_id and doc.user_id != user_id:
            return {"error": "You do not have access to this document."}
    else:
        if doc.user_id != user_id:
            return {"error": "You do not have access to this document."}
    if not doc.raw_text:
        return {"error": "Document has no extracted text yet."}

    items = await ss.get_extraction_items()
    keys = [item.searchphrase for item in items if item.searchphrase]
    if not keys:
        return {"error": "Extraction set has no fields defined."}

    field_metadata = [
        {"key": i.searchphrase, "is_optional": i.is_optional, "enum_values": i.enum_values}
        for i in items
        if i.searchphrase
    ]

    sys_cfg = context.deps.system_config_doc

    def _run():
        engine = ExtractionEngine(system_config_doc=sys_cfg, domain=ss.domain)
        return engine.extract(
            extract_keys=keys,
            doc_texts=[doc.raw_text],
            extraction_config_override=ss.extraction_config or None,
            field_metadata=field_metadata,
        )

    try:
        results = await asyncio.wait_for(asyncio.to_thread(_run), timeout=120)
    except asyncio.TimeoutError:
        return {"error": "Extraction timed out. Try a smaller extraction set."}

    flat: dict = {}
    if results and isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                flat.update(item)

    fields = [
        VerificationField(
            key=k,
            extracted=str(flat.get(k)) if flat.get(k) is not None else "",
            status="pending",
        )
        for k in keys
    ]

    session = VerificationSession(
        search_set_uuid=extraction_set_uuid,
        document_uuid=document_uuid,
        document_title=doc.title or document_uuid,
        label=label or (doc.title or document_uuid),
        fields=fields,
        user_id=user_id,
        team_id=team_id,
    )
    await session.insert()

    return {
        "verification_session_id": session.uuid,
        "extraction_set": ss.title,
        "extraction_set_uuid": extraction_set_uuid,
        "document_uuid": document_uuid,
        "document_title": doc.title or document_uuid,
        "label": session.label,
        "status": "pending_verification",
        "fields": [
            {"key": f.key, "extracted": f.extracted, "status": f.status}
            for f in fields
        ],
        "field_count": len(fields),
        "message": (
            f"Opened a verification session for '{doc.title}'. "
            "Review each extracted value in the document viewer and approve or correct it. "
            "The test case will be saved only after you finish verifying."
        ),
    }


async def create_extraction_from_document(
    context: RunContext[AgenticChatDeps],
    document_uuids: list[str],
    title: Optional[str] = None,
    domain: Optional[str] = None,
    confirmed: bool = False,
) -> dict:
    """Create a new extraction set by analyzing one or more documents.

    Uses the LLM to read the document(s) and propose field names worth
    extracting (e.g. "PI name", "award amount", "period of performance").
    A new SearchSet is created with those fields, and its UUID is returned.

    Use this when the user asks things like "build an extraction from this
    grant notice", "make a template out of this RFP", or "what fields should
    we pull from this?". After creating, it's natural to follow up with
    ``propose_test_case`` using the same document — the user-verified values
    become the first test case and seed validation from day one.

    Call first with confirmed=false to preview. Then call again with
    confirmed=true after the user approves — field discovery uses an LLM
    call and mutates workspace state.

    Args:
        context: The call context.
        document_uuids: Document(s) to analyze. The first document's title
            seeds the default extraction set title when no title is provided.
            Max 5 documents per call.
        title: Optional name for the new extraction set.
        domain: Optional domain hint — one of 'nsf', 'nih', 'dod', 'doe'.
            Activates domain-specific extraction prompts.
        confirmed: Must be true to create. If false, returns a preview.
    """
    user_id = context.deps.user_id
    team_id = context.deps.team_id

    doc_uuids = document_uuids[:5]
    if not doc_uuids:
        return {"error": "At least one document_uuid is required."}

    # Authorize and collect document titles for the preview / default title
    docs: list[SmartDocument] = []
    for doc_uuid in doc_uuids:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if not doc:
            continue
        if team_id:
            if doc.team_id != team_id and doc.user_id != user_id:
                continue
        else:
            if doc.user_id != user_id:
                continue
        docs.append(doc)

    if not docs:
        return {"error": "No accessible documents found."}

    if any(not d.raw_text for d in docs):
        # At least one doc is missing text — filter them out; reject if none remain
        docs = [d for d in docs if d.raw_text]
        if not docs:
            return {"error": "Documents have no extracted text yet. Try again once processing completes."}

    default_title = title or f"Extraction from {docs[0].title or doc_uuids[0]}"

    if not confirmed:
        doc_names = ", ".join(f'"{d.title}"' for d in docs[:3])
        if len(docs) > 3:
            doc_names += f" + {len(docs) - 3} more"
        return {
            "action": "create_extraction_from_document",
            "preview": (
                f'Create a new extraction set "{default_title}" by analyzing {doc_names}. '
                "The LLM will propose field names worth extracting."
            ),
            "needs_confirmation": True,
            "document_count": len(docs),
            "default_title": default_title,
        }

    from app.services import search_set_service as svc

    ss = await svc.create_search_set(
        title=default_title,
        user_id=user_id,
        set_type="extraction",
        team_id=team_id,
    )
    if domain:
        ss.domain = domain
        await ss.save()

    try:
        discovered_fields, suggested_title = await svc.build_from_documents(
            search_set_uuid=ss.uuid,
            document_uuids=[d.uuid for d in docs],
            user_id=user_id,
            model=context.deps.model_name or None,
        )
    except RuntimeError as e:
        # Tear down the empty set if field discovery fails
        await ss.delete()
        return {"error": f"Field discovery failed: {e}"}

    # When the caller didn't pass an explicit title, prefer the LLM's
    # content-aware suggestion over the generic "Extraction from <doc>" fallback.
    if not title and suggested_title:
        ss.title = suggested_title
        await ss.save()

    try:
        from app.services.library_service import add_item, get_or_create_personal_library

        lib = await get_or_create_personal_library(user_id)
        await add_item(str(lib.id), context.deps.user, str(ss.id), "search_set")
    except Exception:
        pass

    if not discovered_fields:
        return {
            "extraction_set_uuid": ss.uuid,
            "title": ss.title,
            "fields": [],
            "document_uuids": [d.uuid for d in docs],
            "message": (
                "Created an empty extraction set — the LLM didn't find clear "
                "fields in the document. You can add fields manually."
            ),
        }

    return {
        "extraction_set_uuid": ss.uuid,
        "title": ss.title,
        "fields": discovered_fields,
        "field_count": len(discovered_fields),
        "document_uuids": [d.uuid for d in docs],
        "document_titles": [d.title or d.uuid for d in docs],
        "message": (
            f'Created "{ss.title}" with {len(discovered_fields)} proposed field(s). '
            "You can now run extraction on other documents, or propose this same "
            "document as the first test case to lock in ground truth."
        ),
    }


async def run_validation(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
    num_runs: int = 3,
    test_case_uuids: Optional[list[str]] = None,
    confirmed: bool = False,
) -> dict:
    """Run validation on an extraction set's test cases. Measures accuracy and consistency.

    Runs extraction N times on each test case and compares against user-verified
    expected values. Returns a unified 0-100 score plus per-field accuracy and
    consistency. Persists a ValidationRun record and updates the extraction set's
    quality tier.

    Call first with confirmed=false to preview. Then call again with confirmed=true
    after the user approves — validation uses LLM calls and can take 30–90s depending
    on test case count and num_runs.

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template to validate.
        num_runs: How many times to run extraction per test case (3+ recommended for consistency measurement). Default 3.
        test_case_uuids: Optional — validate only these test cases. If omitted, validates all.
        confirmed: Must be true to execute. If false, returns a preview.
    """
    from app.services import extraction_validation_service as val_svc

    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return {"error": f"Extraction set '{extraction_set_uuid}' not found."}

    user_id = context.deps.user_id
    team_id = context.deps.team_id
    if not ss.verified and ss.user_id != user_id:
        if not (team_id and ss.team_id == team_id):
            return {"error": "You do not have access to this extraction set."}

    tc_count = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == extraction_set_uuid
    ).count()
    effective_count = len(test_case_uuids) if test_case_uuids else tc_count
    if effective_count == 0:
        return {
            "error": "No test cases found for this extraction set. Use propose_test_case first to add ground truth.",
        }

    if not confirmed:
        return {
            "action": "run_validation",
            "preview": (
                f"Validate \"{ss.title}\" with {effective_count} test case(s), "
                f"running extraction {num_runs} time(s) each."
            ),
            "needs_confirmation": True,
            "num_test_cases": effective_count,
            "num_runs": num_runs,
        }

    try:
        result = await val_svc.run_validation(
            search_set_uuid=extraction_set_uuid,
            user_id=user_id,
            test_case_uuids=test_case_uuids,
            num_runs=num_runs,
            model=context.deps.model_name or None,
        )
    except ValueError as e:
        return {"error": str(e)}

    # Fetch the ValidationRun we just persisted so we can surface the score.
    latest = await ValidationRun.find(
        ValidationRun.item_kind == "search_set",
        ValidationRun.item_id == extraction_set_uuid,
    ).sort("-created_at").first_or_none()

    score = latest.score if latest else None
    response: dict = {
        "extraction_set": ss.title,
        "extraction_set_uuid": extraction_set_uuid,
        "num_test_cases": effective_count,
        "num_runs": num_runs,
        "accuracy": result.get("aggregate_accuracy"),
        "consistency": result.get("aggregate_consistency"),
        "score": score,
        "tier": _score_to_tier(score),
        "challenging_fields": [
            {
                "field": cf.get("field") or cf.get("key"),
                "accuracy": cf.get("accuracy"),
                "consistency": cf.get("consistency"),
            }
            for cf in (result.get("challenging_fields") or [])[:8]
        ],
    }

    if latest and latest.score_breakdown:
        response["score_breakdown"] = latest.score_breakdown

    # Quality sidecar for the badge UI
    if score is not None:
        response["quality"] = {
            "score": score,
            "tier": _score_to_tier(score),
            "accuracy": latest.accuracy if latest else None,
            "consistency": latest.consistency if latest else None,
            "num_test_cases": effective_count,
            "num_runs": num_runs,
            "last_validated_at": (
                latest.created_at.isoformat() if latest and latest.created_at else None
            ),
        }

    return response


# ---------------------------------------------------------------------------
# Tool registry — imported by llm_service.create_agentic_chat_agent()
# ---------------------------------------------------------------------------

TOOLS = [
    # Phase 1 — Read-only
    search_documents,
    list_documents,
    search_knowledge_base,
    list_knowledge_bases,
    list_extraction_sets,
    list_workflows,
    get_quality_info,
    search_library,
    # Phase 2 — Extraction
    get_document_text,
    run_extraction,
    # Phase 3 — KB write
    create_knowledge_base,
    add_documents_to_kb,
    add_url_to_kb,
    # Phase 4 — Workflow orchestration
    run_workflow,
    get_workflow_status,
    # Phase 5 — Validation & guided verification
    list_test_cases,
    propose_test_case,
    run_validation,
    create_extraction_from_document,
]
