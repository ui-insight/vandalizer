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
from app.models.folder import SmartFolder
from app.models.knowledge import KnowledgeBase
from app.models.quality_alert import QualityAlert
from app.models.search_set import SearchSet, SearchSetItem
from app.models.validation_run import ValidationRun
from app.models.workflow import Workflow, WorkflowStep
from app.services.chat_deps import AgenticChatDeps
from app.services.document_manager import DocumentManager

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


async def search_documents(
    context: RunContext[AgenticChatDeps],
    query: str,
) -> list[dict]:
    """Search the user's documents by title. Returns matching documents with metadata.

    Args:
        context: The call context.
        query: A text query to match against document titles.
    """
    team_id = context.deps.team_id
    filters: dict = {"soft_deleted": {"$ne": True}}
    if team_id:
        filters["team_id"] = team_id
    else:
        filters["user_id"] = context.deps.user_id
    if query:
        filters["title"] = {"$regex": re.escape(query), "$options": "i"}

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
    team_id = context.deps.team_id
    doc_filters: dict = {"soft_deleted": {"$ne": True}}
    folder_filters: dict = {}

    if team_id:
        doc_filters["team_id"] = team_id
        folder_filters["team_id"] = team_id
    else:
        doc_filters["user_id"] = context.deps.user_id
        folder_filters["user_id"] = context.deps.user_id

    if folder_uuid:
        doc_filters["folder"] = folder_uuid
        folder_filters["parent_id"] = folder_uuid
    else:
        doc_filters["folder"] = {"$in": [None, "", "0"]}
        folder_filters["parent_id"] = {"$in": [None, ""]}

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

    dm = DocumentManager()
    results = await asyncio.to_thread(dm.query_kb, uuid, query, 8)
    return [
        {
            "content": r.get("content", ""),
            "source_name": r.get("metadata", {}).get("source_name", "unknown"),
        }
        for r in results
    ]


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
    """List extraction sets (formatters) available to the user.

    Args:
        context: The call context.
        search: Optional text to filter extraction sets by title.
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
    """Run an extraction set against one or more documents. Returns extracted entities with quality metadata.

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction set (search set) to run.
        document_uuids: List of document UUIDs to extract from.
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

    results, tokens_in, tokens_out = await asyncio.to_thread(_run)

    # Attach quality metadata as sidecar if validation data exists
    latest_run = await ValidationRun.find(
        ValidationRun.item_kind == "search_set",
        ValidationRun.item_id == extraction_set_uuid,
    ).sort("-created_at").first_or_none()

    response: dict = {
        "extraction_set": ss.title,
        "fields": keys,
        "documents": doc_names,
        "entities": results[:50],  # Cap output size
        "entity_count": len(results),
        "token_usage": {"input": tokens_in, "output": tokens_out},
    }

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
    if not confirmed:
        # Look up workflow name for the preview
        wf = await Workflow.get(workflow_id)
        wf_name = wf.name if wf else workflow_id
        return {
            "action": "run_workflow",
            "preview": f"Run workflow \"{wf_name}\" on {len(document_uuids)} document(s)",
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
]
