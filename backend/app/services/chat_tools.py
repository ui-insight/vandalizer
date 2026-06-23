"""Agentic chat tool functions.

Each tool is registered on the agentic chat agent via ``@agent.tool`` and
receives ``RunContext[AgenticChatDeps]`` for user-scoped authorization.

Tools are exported as the ``TOOLS`` list for bulk registration.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import re
from typing import Optional

from pydantic_ai.tools import RunContext

from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.folder import SmartFolder
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.quality_alert import QualityAlert
from app.models.search_set import SearchSet
from app.models.validation_run import ValidationRun
from app.models.verification_session import VerificationField, VerificationSession
from app.models.workflow import Workflow
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


def _kb_access_ok(kb: "KnowledgeBase", user_id: str, team_id: Optional[str]) -> bool:
    """Whether ``(user_id, team_id)`` may access *kb*.

    ``shared_with_team`` is NOT a global grant — it only opens the KB to members
    of ``kb.team_id``. Earlier guards treated a truthy ``shared_with_team`` as a
    blanket bypass (``... and not kb.shared_with_team``), so any authenticated
    user — including one on a different team or with no current team — could read
    or write a team-shared KB by UUID (cross-tenant leak). This mirrors the
    correct predicate already used in ``_get_optimizable_item``.

    Verified (org-curated) KBs are intentionally NOT granted here: read paths
    that allow them check ``kb.verified`` explicitly, and write paths must never
    let a non-owner mutate a verified KB.
    """
    if kb.user_id == user_id:
        return True
    if kb.shared_with_team and team_id and kb.team_id == team_id:
        return True
    return False


def _confirm_fingerprint(tool_name: str, key: dict) -> str:
    """Stable fingerprint of a write action, used to match preview→confirm."""
    raw = tool_name + "|" + json.dumps(key, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def _confirm_gate(
    context: "RunContext[AgenticChatDeps]",
    *,
    tool_name: str,
    key: dict,
    confirmed: bool,
    preview: dict,
) -> Optional[dict]:
    """Server-side enforcement of the write-tool preview→confirm handshake.

    Returns ``None`` when the action is genuinely approved and the caller may
    execute; otherwise returns the ``preview`` dict (with
    ``needs_confirmation=True``) and the caller must return it unchanged.

    A write tool may only execute when (a) the identical action was previewed
    on an EARLIER user turn and (b) the model re-issues it with
    ``confirmed=true``. The agent loops server-side within a single turn, so a
    ``confirmed=true`` argument it produces on its own — e.g. because a
    prompt-injected document or KB snippet told it to — never satisfies the
    gate: there is no prior-turn arming, so it is downgraded to a preview that a
    human must approve by sending another message. Fails closed: any error or
    missing conversation yields a preview, never execution.

    ``turn_marker`` is ``len(conversation.messages)`` at turn start, which
    strictly increases each turn, so "armed on an earlier turn" is
    ``entry.turn < turn_marker``.
    """
    deps = context.deps
    conv = getattr(deps, "conversation", None)
    marker = int(getattr(deps, "turn_marker", 0) or 0)
    fp = _confirm_fingerprint(tool_name, key)

    armed = list(getattr(conv, "pending_confirmations", None) or []) if conv else []
    match = next(
        (p for p in armed if isinstance(p, dict) and p.get("fp") == fp), None
    )

    # Execute only when a prior-turn preview armed this exact action.
    if confirmed and match is not None and int(match.get("turn", marker)) < marker:
        if conv is not None:
            conv.pending_confirmations = [
                p for p in armed
                if not (isinstance(p, dict) and p.get("fp") == fp)
            ]
            try:
                await conv.save()
            except Exception:
                logger.warning("Failed to clear pending confirmation for %s", tool_name)
        return None

    # Otherwise (re)arm the confirmation for a future turn and return the
    # preview. confirmed=true with no prior-turn arming is downgraded here —
    # this is the injection defense.
    if conv is not None:
        new_pending = [
            p for p in armed
            if not (isinstance(p, dict) and p.get("fp") == fp)
        ]
        new_pending.append({"fp": fp, "turn": marker, "tool": tool_name})
        # Cap to bound growth on long conversations; keep the most recent.
        conv.pending_confirmations = new_pending[-25:]
        try:
            await conv.save()
        except Exception:
            logger.warning("Failed to arm pending confirmation for %s", tool_name)

    out = dict(preview)
    out["needs_confirmation"] = True
    return out


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


async def list_folders(
    context: RunContext[AgenticChatDeps],
) -> list[dict]:
    """List every folder the user can access, flattened across the whole tree.

    Unlike list_documents (which shows one level at a time), this returns all
    accessible folders — personal and team — in a single call. Use it to resolve
    a folder name to its UUID before calling save_to_folder, e.g. the user says
    "save it to my Grants folder" and you need the destination folder_uuid.

    Args:
        context: The call context.
    """
    owner_filter = _build_owner_filter(context.deps)
    folders = await SmartFolder.find(owner_filter).sort("title").limit(200).to_list()
    return [
        {
            "uuid": f.uuid,
            "title": f.title,
            "parent_id": f.parent_id,
            "team_id": f.team_id,
        }
        for f in folders
    ]


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
    # Verified KBs are readable org-wide; otherwise require ownership or a
    # team-shared KB whose team matches the caller (see _kb_access_ok).
    if not (kb.verified or _kb_access_ok(kb, user_id, team_id)):
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
    citations: list[dict] = []
    for r in results:
        meta = r.get("metadata", {})
        sid = meta.get("source_id", "")
        page = meta.get("page")
        sheet = meta.get("sheet")
        entry: dict = {
            "content": r.get("content", ""),
            "source_name": meta.get("source_name", "unknown"),
        }
        if isinstance(page, int):
            entry["page"] = page
        if isinstance(sheet, str) and sheet:
            entry["sheet"] = sheet
        src = source_map.get(sid)
        if src:
            entry["source_type"] = src.source_type
            if src.source_type == "document" and src.document_uuid:
                entry["document_uuid"] = src.document_uuid
            elif src.source_type == "url" and src.url:
                entry["url"] = src.url
            if src.source_reference:
                entry["source_reference"] = src.source_reference
        enriched.append(entry)

        citations.append({
            "document_id": sid or None,
            "document_title": meta.get("source_name", "Unknown"),
            "page": page if isinstance(page, int) else None,
            "sheet": sheet if isinstance(sheet, str) else None,
            "chunk_id": r.get("chunk_id"),
            "score": r.get("score"),
            "content_preview": (r.get("content") or "")[:240],
            "source_reference": src.source_reference if src and src.source_reference else None,
            "url": src.url if src and src.source_type == "url" and src.url else None,
        })

    # Citation sidecar: the streaming layer pops this by tool_call_id, emits a
    # 'sources' chunk, and persists the citations on the assistant message.
    if citations and context.tool_call_id:
        context.deps.citation_annotations[context.tool_call_id] = citations

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
        QualityAlert.acknowledged != True,  # noqa: E712
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

    # Latest autovalidate (optimizer) run, if the item has ever been optimized.
    # A completed, unapplied, not-tied run is a pending recommendation the
    # agent should surface ("a tuned config scored X vs your current Y").
    optimization_summary: dict | None = None
    try:
        from app.services.optimization_summary import latest_optimization_summary

        opt = await latest_optimization_summary(item_kind, item_uuid)
        if opt:
            pending = (
                opt["status"] == "completed"
                and not opt.get("applied_at")
                and not opt.get("tied_with_baseline")
            )
            optimization_summary = {
                "status": opt["status"],
                "run_uuid": opt["run_uuid"],
                "optimized_score": opt.get("score"),
                "baseline_score": opt.get("baseline_score"),
                "tied_with_baseline": opt.get("tied_with_baseline", False),
                "applied_at": opt.get("applied_at"),
                "completed_at": opt.get("completed_at"),
                "pending_recommendation": pending,
            }
            result["optimization"] = optimization_summary
    except Exception as e:
        logger.warning("Optimization lookup failed for %s/%s: %s", item_kind, item_uuid, e)

    # Workflows: surface validation-plan staleness so the agent can offer the
    # one-click regenerate instead of validating against a drifted plan.
    plan_stale = None
    if item_kind == "workflow":
        try:
            from app.services import workflow_service

            plan_info = await workflow_service.get_validation_plan(item_uuid, context.deps.user)
            plan_stale = plan_info.get("plan_stale", False)
            result["validation_plan_stale"] = plan_stale
            if plan_stale:
                result["validation_plan_stale_reasons"] = plan_info.get("stale_reasons", [])
                result["note_plan_stale"] = (
                    "The validation plan no longer matches the workflow definition. "
                    "Offer to regenerate it (regenerate_validation_plan) before "
                    "trusting or re-running validation."
                )
        except ValueError:
            pass  # not found / no access — quality info above still stands
        except Exception as e:
            logger.warning("Plan staleness lookup failed for workflow %s: %s", item_uuid, e)

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
            "optimization": optimization_summary,
            "plan_stale": plan_stale,
        }

    return result


async def get_app_help(
    context: RunContext[AgenticChatDeps],
    topic: str,
) -> dict:
    """Look up help content about Vandalizer itself — features, UI navigation, concepts.

    Use this when the user asks what Vandalizer is, how to do something in the
    UI, what a feature means, or why Vandalizer is different from generic AI
    chat. Examples: "what is a knowledge base", "how do I create a workflow",
    "what does the quality score mean", "how do I invite teammates",
    "what makes this different from ChatGPT".

    Do NOT call this for questions about the user's own documents, workflows,
    or data — use the search/list tools for those.

    Args:
        context: The call context.
        topic: A short phrase describing what the user wants to know about
            (e.g. "knowledge bases", "validation", "team folders").
    """
    from app.services.help_content import find_topics, list_topic_index

    matches = find_topics(topic, limit=3)
    if not matches:
        return {
            "matched": False,
            "query": topic,
            "available_topics": list_topic_index(),
            "note": (
                "No help topic matched. The list above shows every topic "
                "available — pick one and call again with its title or id."
            ),
        }

    # White-label: help bodies say "Vandalizer"; branded deployments swap in
    # the configured org name (same convention as email and prompt branding).
    org = (context.deps.system_config_doc or {}).get("org_name") or ""

    def _brand(text: str) -> str:
        if not org or org == "Vandalizer":
            return text
        return text.replace("Vandalizer", org)

    primary = matches[0]
    result = {
        "matched": True,
        "topic": {
            "id": primary["id"],
            "title": _brand(primary["title"]),
            "body": _brand(primary["body"]),
        },
    }
    if len(matches) > 1:
        result["related_topics"] = [
            {"id": m["id"], "title": _brand(m["title"])} for m in matches[1:]
        ]
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


# Caps for fetch_url. Raw bytes cap protects memory; text cap protects the
# LLM context window. Both are deliberately smaller than the KB ingestion
# path's 500KB cap because chat answers don't need the full document — the
# LLM is summarizing, not indexing.
_FETCH_URL_TIMEOUT_S = 20.0
_FETCH_URL_MAX_BYTES = 2_000_000  # 2 MB raw HTML
_FETCH_URL_MAX_CHARS = 25_000     # ~25k chars of extracted text to the LLM


async def fetch_url(
    context: RunContext[AgenticChatDeps],
    url: str,
) -> dict:
    """Fetch a public web page and return its readable text so you can answer questions about it.

    Use this when the user pastes a URL into chat, asks you to read/summarize/check
    a specific page, or references "this article" / "that link". Auto-fire when
    the user's message contains an http(s) URL they clearly want you to look at.

    Does NOT work for pages behind login (SharePoint, Google Docs, Confluence,
    etc.) — those return login HTML, not the real content. If a result looks
    like a login page, tell the user and suggest uploading an export or using
    M365 intake instead.

    Does NOT fetch arbitrary file types (PDFs, ZIPs). For those, the user
    should upload to Files instead — uploaded docs get OCR'd and indexed.

    Args:
        context: The call context.
        url: The full URL to fetch (must start with http:// or https://).
    """
    import httpx

    from app.services.knowledge_service import (
        _extract_text_from_html,
        _extract_title_from_html,
    )
    from app.utils.url_validation import safe_get, validate_outbound_url

    try:
        validate_outbound_url(url)
    except ValueError as e:
        return {
            "error": f"URL rejected: {e}",
            "url": url,
        }

    try:
        # follow_redirects=False + safe_get re-validates every hop, so a public
        # page can't 302 us into an internal/metadata address (SSRF).
        async with httpx.AsyncClient(
            timeout=_FETCH_URL_TIMEOUT_S,
            follow_redirects=False,
            headers={"User-Agent": "Vandalizer-Chat/1.0 (+research-admin agent)"},
        ) as client:
            resp = await safe_get(client, url)
            resp.raise_for_status()
    except ValueError as e:
        return {
            "error": f"URL rejected: {e}",
            "url": url,
        }
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        return {
            "error": f"Page returned HTTP {status}.",
            "url": url,
            "status_code": status,
        }
    except httpx.TimeoutException:
        return {
            "error": f"Timed out after {int(_FETCH_URL_TIMEOUT_S)}s. The page may be slow or unreachable.",
            "url": url,
        }
    except Exception as e:  # network errors, DNS, TLS, etc.
        return {
            "error": f"Could not fetch URL: {e}",
            "url": url,
        }

    content_type = (resp.headers.get("content-type") or "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        return {
            "error": (
                f"URL returned non-HTML content ({content_type}). "
                "For PDFs and other documents, ask the user to upload via Files instead."
            ),
            "url": url,
            "content_type": content_type,
        }

    raw_html = resp.text[:_FETCH_URL_MAX_BYTES]
    text = _extract_text_from_html(raw_html)

    if not text.strip():
        return {
            "error": "Fetched the page but could not extract readable text. May be JavaScript-only or empty.",
            "url": str(resp.url),
        }

    truncated = len(text) > _FETCH_URL_MAX_CHARS
    title = _extract_title_from_html(raw_html, str(resp.url))

    return {
        "url": str(resp.url),  # final URL after redirects
        "title": title,
        "text": text[:_FETCH_URL_MAX_CHARS],
        "total_chars": len(text),
        "truncated": truncated,
        "fetched_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
    }


async def web_search(
    context: RunContext[AgenticChatDeps],
    query: str,
    max_results: int = 5,
) -> dict:
    """Search the public web and return ranked results (title, URL, snippet).

    Prefer the user's own workspace first — use search_documents and
    search_knowledge_base before this. Reach for web_search only when the answer
    isn't in the user's documents or knowledge bases, or when the question needs
    current, external, or public information: latest policy/version numbers,
    sponsor or agency websites, regulations, or general facts the workspace
    doesn't contain. When you use a result, cite the source URL.

    Unlike fetch_url (which reads one page you already have the link to), this
    discovers pages from a query. Follow up with fetch_url on a returned URL when
    you need the full page text rather than just the snippet.

    Returns an error note if web search isn't configured for this deployment —
    in that case, answer from the workspace or your general knowledge and tell
    the user web search isn't enabled.

    Args:
        context: The call context.
        query: A natural-language search query.
        max_results: How many results to return (1-10, default 5).
    """
    from app.services import web_search_service

    result = await web_search_service.web_search(
        query=query,
        sys_config_doc=context.deps.system_config_doc,
        max_results=max_results,
    )

    if result.get("configured") is False:
        return {
            "error": result.get("error", "Web search is not configured."),
            "note": (
                "Web search isn't enabled for this deployment. Answer from the "
                "user's workspace or your general knowledge instead, and let them "
                "know web search isn't configured."
            ),
        }
    if result.get("error") and not result.get("results"):
        return {"error": result["error"], "results": []}

    results = result.get("results", [])

    # Citation sidecar — mirror search_knowledge_base so web results render as
    # source chips. The streaming layer pops this by tool_call_id and emits a
    # 'sources' chunk (see chat_service.py).
    if results and context.tool_call_id:
        citations = [
            {
                "document_id": None,
                "document_title": r.get("title") or r.get("url", "Web result"),
                "page": None,
                "sheet": None,
                "chunk_id": None,
                "score": None,
                "content_preview": (r.get("snippet") or "")[:240],
                "source_reference": None,
                "url": r.get("url"),
            }
            for r in results
            if r.get("url")
        ]
        if citations:
            context.deps.citation_annotations[context.tool_call_id] = citations

    response: dict = {"query": result.get("query", query), "results": results}
    if result.get("answer"):
        response["answer"] = result["answer"]
    return response


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

    return await _execute_extraction(context, ss, document_uuids)


async def _execute_extraction(
    context: RunContext[AgenticChatDeps],
    ss,
    document_uuids: list[str],
) -> dict:
    """Run an already-authorized extraction set against documents.

    Shared by ``run_extraction`` (after it authorizes the set) and
    ``run_pin_on_project`` (where the project pin is the authorization
    boundary). Each document is still authorized against the caller. Returns
    the same response shape as ``run_extraction``, including the quality
    sidecar. Caps at 10 documents and 50 entities.
    """
    from app.services.extraction_engine import ExtractionEngine

    team_id = context.deps.team_id
    user_id = context.deps.user_id
    extraction_set_uuid = ss.uuid

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

    # Persist a SEARCH_SET_RUN activity event so cert validators + analytics can
    # see that this extraction was actually run (matches what the REST route
    # does for classical runs). Best-effort — never blocks the tool.
    try:
        from app.models.activity import ActivityEvent, ActivityType, ActivityStatus
        now = datetime.datetime.now(datetime.timezone.utc)
        await ActivityEvent(
            type=ActivityType.SEARCH_SET_RUN.value,
            title=f"Extraction: {ss.title or extraction_set_uuid}",
            status=ActivityStatus.COMPLETED.value,
            user_id=user_id,
            team_id=team_id,
            search_set_uuid=extraction_set_uuid,
            started_at=now,
            finished_at=now,
            last_updated_at=now,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            total_tokens=tokens_in + tokens_out,
            documents_touched=len(doc_names),
            tags=["chat"],
        ).insert()
    except Exception:
        logger.exception("Failed to log SEARCH_SET_RUN activity for %s", extraction_set_uuid)

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
            QualityAlert.acknowledged != True,  # noqa: E712
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


async def check_compliance(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
    document_uuids: list[str],
) -> dict:
    """Check documents against an extraction set's cross-field compliance rules.

    Use this for "does this proposal/contract follow our rules?" questions. It
    runs the extraction template against each document to pull the field values,
    then evaluates the set's cross-field rules — sum checks (parts add up to a
    total), required-when conditions, date ordering (start before end), numeric
    ranges, and cross-references — and reports every rule that passes or fails,
    with a plain-language reason for each violation.

    Read-only: nothing is saved. Maximum 10 documents per call. If the
    extraction set has no rules defined, say so and offer to set them up in the
    extraction's Cross-field Rules section (chat can't author rules yet).

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template whose rules to apply.
        document_uuids: Document UUIDs to check (max 10).
    """
    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return {"error": f"Extraction set '{extraction_set_uuid}' not found."}

    # Authorization mirrors run_extraction.
    team_id = context.deps.team_id
    user_id = context.deps.user_id
    if not ss.verified and ss.user_id != user_id:
        if not (team_id and ss.team_id == team_id):
            return {"error": "You do not have access to this extraction set."}

    rules = ss.normalized_cross_field_rules()
    active_rules = [
        r for r in rules
        if not (r.get("enabled") is False or r.get("auto_disabled"))
    ]
    if not active_rules:
        return {
            "extraction_set": ss.title,
            "rules_checked": 0,
            "message": (
                f"\"{ss.title}\" has no active compliance rules defined, so there "
                "is nothing to check against. Compliance rules (sum checks, "
                "required-when conditions, date order, ranges) live in the "
                "extraction set's Cross-field Rules section in the UI. Set them up "
                "there, then I can check documents against them."
            ),
        }

    # Run the extraction to get field values, then validate each document.
    extraction = await _execute_extraction(context, ss, document_uuids)
    if "error" in extraction:
        return extraction

    from app.services.cross_field_validation import (
        CrossFieldValidator,
        summarize_results,
    )

    validator = CrossFieldValidator()
    entities = extraction.get("entities") or []
    doc_names = extraction.get("documents") or []

    per_document: list[dict] = []
    total_fail = 0
    for idx, entity in enumerate(entities):
        data = entity if isinstance(entity, dict) else {}
        results = validator.validate(data, active_rules)
        summary = summarize_results(results)
        total_fail += summary.get("fail", 0)
        violations = [
            {
                "rule_type": (r.get("rule") or {}).get("type"),
                "message": r.get("message"),
            }
            for r in results
            if r.get("status") == "fail"
        ]
        per_document.append({
            "document": doc_names[idx] if idx < len(doc_names) else f"document {idx + 1}",
            "compliant": summary.get("fail", 0) == 0,
            "checks_passed": summary.get("pass", 0),
            "checks_failed": summary.get("fail", 0),
            "checks_unparseable": summary.get("unparseable", 0),
            "violations": violations,
        })

    response: dict = {
        "extraction_set": ss.title,
        "rules_checked": len(active_rules),
        "documents_checked": len(per_document),
        "all_compliant": total_fail == 0,
        "total_violations": total_fail,
        "results": per_document,
    }
    # Carry the extraction's quality sidecar through (streaming layer strips it
    # before the LLM sees it and renders a badge) so compliance answers also
    # surface how trustworthy the underlying extraction is.
    if extraction.get("quality"):
        response["quality"] = extraction["quality"]
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
    gate = await _confirm_gate(
        context,
        tool_name="create_knowledge_base",
        key={"title": title, "description": description},
        preview={
            "action": "create_knowledge_base",
            "preview": f"Create a new knowledge base titled \"{title}\"" + (f" — {description}" if description else ""),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

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

    # Authorization — owner or a team-shared KB matching the caller's team.
    user = context.deps.user
    if not _kb_access_ok(kb, user.user_id, context.deps.team_id):
        return {"error": "You do not have access to this knowledge base."}

    gate = await _confirm_gate(
        context,
        tool_name="add_documents_to_kb",
        key={"kb_uuid": kb_uuid, "docs": sorted(document_uuids)},
        preview={
            "action": "add_documents_to_kb",
            "preview": f"Add {len(document_uuids)} document(s) to knowledge base \"{kb.title}\"",
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

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
    if not _kb_access_ok(kb, user.user_id, context.deps.team_id):
        return {"error": "You do not have access to this knowledge base."}

    action = f"Add URL \"{url}\" to knowledge base \"{kb.title}\""
    if crawl:
        action += " (with link crawling, up to 5 pages)"
    gate = await _confirm_gate(
        context,
        tool_name="add_url_to_kb",
        key={"kb_uuid": kb_uuid, "url": url, "crawl": crawl},
        preview={
            "action": "add_url_to_kb",
            "preview": action,
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

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
    document_uuids: list[str] | None = None,
    text_input: str = "",
    confirmed: bool = False,
) -> dict:
    """Start a workflow execution. Returns a session ID for status polling.

    A workflow runs on documents, on **typed text** (for text-input workflows),
    or on nothing (for no-input workflows). Call first with confirmed=false to
    preview, then again with confirmed=true after the user approves. Workflows
    run asynchronously in the background — use get_workflow_status for progress.

    Args:
        context: The call context.
        workflow_id: The ID of the workflow to execute.
        document_uuids: Document UUIDs to process. Omit for text-input or
            no-input workflows.
        text_input: For a text-input workflow, the text the user wants it to run
            on (e.g. a bed name, a pasted snippet). It becomes the workflow's
            input; any documents pinned to the workflow are included too.
        confirmed: Must be true to actually run. If false, returns a preview.
    """
    document_uuids = list(document_uuids or [])
    text = (text_input or "").strip()

    # Look up workflow and verify access
    wf = await Workflow.get(workflow_id)
    if not wf:
        return {"error": f"Workflow '{workflow_id}' not found."}

    team_id = context.deps.team_id
    user_id = context.deps.user_id
    if not wf.verified and getattr(wf, "user_id", None) != user_id:
        if not (team_id and getattr(wf, "team_id", None) == team_id):
            return {"error": "You do not have access to this workflow."}

    input_cfg = getattr(wf, "input_config", None) or {}
    trigger_type = input_cfg.get("trigger_type") or "documents"
    has_fixed = bool(input_cfg.get("fixed_documents"))

    # Make sure the run will have something to chew on. "no_input" workflows run
    # empty by design; everything else needs docs, typed text, or documents
    # pinned to the workflow (those are merged in at execution time).
    if trigger_type != "no_input" and not document_uuids and not text and not has_fixed:
        if trigger_type == "text_input":
            return {"error": f"Workflow \"{wf.name}\" runs on text input — give me the text to run it on (for example, the bed name or the details to process)."}
        return {"error": f"Give me at least one document to run \"{wf.name}\" on."}

    run_label = (
        "typed input" if text and not document_uuids
        else f"typed input + {len(document_uuids)} document(s)" if text
        else f"{len(document_uuids)} document(s)" if document_uuids
        else "its pinned inputs"
    )
    gate = await _confirm_gate(
        context,
        tool_name="run_workflow",
        key={"workflow_id": workflow_id, "docs": sorted(document_uuids), "text": text[:200]},
        preview={
            "action": "run_workflow",
            "preview": f"Run workflow \"{wf.name}\" on {run_label}",
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    # Turn typed text into a transient document the workflow reads — the same
    # path the visual runner uses. Done only after confirmation so an unconfirmed
    # preview never leaves an orphaned temp document behind.
    run_docs = list(document_uuids)
    if text:
        from app.services import workflow_service
        try:
            temp_uuids = await workflow_service.create_temp_documents_from_text(
                [{"text": text, "label": "Chat text input"}], user_id,
            )
            run_docs.extend(temp_uuids)
        except Exception as e:
            logger.error("Failed to create temp document for workflow %s: %s", workflow_id, e)
            return {"error": "Couldn't prepare the text input for this run — try again."}

    return await _execute_workflow(context, wf, run_docs)


async def _execute_workflow(
    context: RunContext[AgenticChatDeps],
    wf,
    document_uuids: list[str],
) -> dict:
    """Dispatch an already-authorized workflow against documents.

    Shared by ``run_workflow`` (after auth + confirmation) and
    ``run_pin_on_project``. Caps at 10 documents (the workflow_service limit).
    Returns a session_id for polling via get_workflow_status.
    """
    from app.services import workflow_service

    workflow_id = str(wf.id)
    team_id = context.deps.team_id
    user_id = context.deps.user_id

    # Create a chat-tagged activity event so the completion hook can increment
    # chat_workflow_count only when the workflow actually finishes.
    activity_id = None
    try:
        from app.models.activity import ActivityEvent, ActivityType, ActivityStatus
        now = datetime.datetime.now(datetime.timezone.utc)
        ev = ActivityEvent(
            type=ActivityType.WORKFLOW_RUN.value,
            title=f"Workflow: {wf.name or workflow_id}",
            status=ActivityStatus.RUNNING.value,
            user_id=user_id,
            team_id=team_id,
            started_at=now,
            last_updated_at=now,
            documents_touched=len(document_uuids),
            tags=["chat"],
        )
        await ev.insert()
        activity_id = str(ev.id)
    except Exception:
        logger.exception("Failed to create chat-tagged activity for workflow %s", workflow_id)

    try:
        session_id = await workflow_service.run_workflow(
            workflow_id=workflow_id,
            document_uuids=document_uuids[:10],
            user_id=context.deps.user_id,
            model=context.deps.model_name or None,
            user=context.deps.user,
            activity_id=activity_id,
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

    # first_chat_workflow_at is set at dispatch time so we know *when a user
    # first tried*, even if that run later failed. The power-user counter is
    # incremented on completion via the activity tag (see workflow_tasks.py).
    try:
        from app.models.user import User as _User
        u = await _User.find_one(_User.user_id == user_id)
        if u and u.first_chat_workflow_at is None:
            u.first_chat_workflow_at = datetime.datetime.now(datetime.timezone.utc)
            await u.save()
    except Exception:
        logger.exception("Failed to stamp first_chat_workflow_at for %s", user_id)

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


async def _can_decide_approval(approval, user) -> bool:
    """Whether *user* may approve/reject *approval*.

    Mirrors ``routers/reviews.py::_can_decide_approval``: an assigned reviewer,
    or anyone with manage access to the workflow.
    """
    if user.user_id in (approval.assigned_to_user_ids or []):
        return True
    from app.services import access_control

    workflow = await access_control.get_authorized_workflow(
        str(approval.workflow_id), user, manage=True,
    )
    return workflow is not None


async def approve_workflow_step(
    context: RunContext[AgenticChatDeps],
    approval_request_id: str,
    comments: str = "",
    confirmed: bool = False,
) -> dict:
    """Approve a workflow that is paused awaiting human review, resuming it.

    A workflow pauses at an approval gate; get_workflow_status returns an
    ``approval_request_id`` for it. Pass that id here. Call first with
    confirmed=false to preview, then confirmed=true after the user approves.
    Only an assigned reviewer or a workflow manager can approve.

    Args:
        context: The call context.
        approval_request_id: The approval request UUID from get_workflow_status.
        comments: Optional reviewer note recorded with the decision.
        confirmed: Must be true to actually approve. If false, returns a preview.
    """
    from app.models.approval import (
        ApprovalRequest,
        STATUS_APPROVED,
        STATUS_PENDING,
    )

    approval = await ApprovalRequest.find_one(
        ApprovalRequest.uuid == approval_request_id
    )
    if not approval:
        return {"error": f"Approval request '{approval_request_id}' not found."}
    if approval.status != STATUS_PENDING:
        return {
            "error": (
                f"This review can't be approved — its status is "
                f"'{approval.status}', not pending."
            )
        }
    if not await _can_decide_approval(approval, context.deps.user):
        return {
            "error": (
                "You're not authorized to approve this step. Only an assigned "
                "reviewer or a workflow manager can."
            )
        }

    gate = await _confirm_gate(
        context,
        tool_name="approve_workflow_step",
        key={"approval": approval_request_id},
        preview={
            "action": "approve_workflow_step",
            "preview": (
                f"Approve the paused step \"{approval.step_name}\" of workflow "
                f"\"{approval.workflow_name or 'workflow'}\" and resume it"
            ),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    now = datetime.datetime.now(datetime.timezone.utc)
    approval.status = STATUS_APPROVED
    approval.reviewer_user_id = context.deps.user_id
    approval.reviewer_comments = comments or ""
    approval.decision_at = now
    await approval.save()

    try:
        from app.celery_app import celery

        celery.send_task(
            "tasks.workflow.resume_after_approval",
            kwargs={"approval_uuid": approval_request_id},
            queue="workflows",
        )
    except Exception as e:
        logger.error("Failed to dispatch workflow resume after approval: %s", e)
        return {
            "error": (
                "The step was marked approved but the workflow couldn't be "
                "resumed automatically. Try again from the Reviews screen."
            )
        }

    return {
        "status": "approved",
        "step": approval.step_name,
        "message": "Approved. The workflow is resuming from where it paused.",
    }


async def reject_workflow_step(
    context: RunContext[AgenticChatDeps],
    approval_request_id: str,
    comments: str = "",
    confirmed: bool = False,
) -> dict:
    """Reject a workflow that is paused awaiting human review, failing it.

    Get the ``approval_request_id`` from get_workflow_status. Call first with
    confirmed=false to preview, then confirmed=true after the user approves.
    Only an assigned reviewer or a workflow manager can reject. Rejecting marks
    the workflow run as failed — it does not resume.

    Args:
        context: The call context.
        approval_request_id: The approval request UUID from get_workflow_status.
        comments: Optional reason recorded with the rejection.
        confirmed: Must be true to actually reject. If false, returns a preview.
    """
    from app.models.approval import (
        ApprovalRequest,
        STATUS_PENDING,
        STATUS_REJECTED,
    )

    approval = await ApprovalRequest.find_one(
        ApprovalRequest.uuid == approval_request_id
    )
    if not approval:
        return {"error": f"Approval request '{approval_request_id}' not found."}
    if approval.status != STATUS_PENDING:
        return {
            "error": (
                f"This review can't be rejected — its status is "
                f"'{approval.status}', not pending."
            )
        }
    if not await _can_decide_approval(approval, context.deps.user):
        return {
            "error": (
                "You're not authorized to reject this step. Only an assigned "
                "reviewer or a workflow manager can."
            )
        }

    gate = await _confirm_gate(
        context,
        tool_name="reject_workflow_step",
        key={"approval": approval_request_id},
        preview={
            "action": "reject_workflow_step",
            "preview": (
                f"Reject the paused step \"{approval.step_name}\" of workflow "
                f"\"{approval.workflow_name or 'workflow'}\" — this fails the run"
            ),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    now = datetime.datetime.now(datetime.timezone.utc)
    approval.status = STATUS_REJECTED
    approval.reviewer_user_id = context.deps.user_id
    approval.reviewer_comments = comments or ""
    approval.decision_at = now
    await approval.save()

    # Mark the workflow run failed, mirroring routers/reviews.py::reject_review.
    try:
        from app.models.workflow import WorkflowResult

        result = await WorkflowResult.get(approval.workflow_result_id)
        if result:
            result.status = "failed"
            result.current_step_detail = (
                f"Rejected by reviewer: {comments}" if comments
                else "Rejected by reviewer"
            )
            await result.save()
    except Exception:
        logger.exception(
            "Failed to mark workflow result failed after rejection of %s",
            approval_request_id,
        )

    return {
        "status": "rejected",
        "step": approval.step_name,
        "message": "Rejected. The workflow run is marked failed and will not resume.",
    }


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
    pin_to_active_project: bool = True,
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
        pin_to_active_project: When a project is open and the user can manage
            it, pin the new extraction to that project (default true).
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

    # If the user is inside a project they can manage, the new extraction is
    # auto-pinned there so it shows up alongside the project's other tools.
    from app.services import project_service

    active_project = await _resolve_active_project(context) if pin_to_active_project else None
    if active_project and not await project_service.can_manage_project(
        active_project, context.deps.user
    ):
        active_project = None  # viewer — don't pin

    doc_names = ", ".join(f'"{d.title}"' for d in docs[:3])
    if len(docs) > 3:
        doc_names += f" + {len(docs) - 3} more"
    preview_text = (
        f'Create a new extraction set "{default_title}" by analyzing {doc_names}. '
        "The LLM will propose field names worth extracting."
    )
    if active_project:
        preview_text += f' It will also be pinned to project "{active_project.title}".'
    gate = await _confirm_gate(
        context,
        tool_name="create_extraction_from_document",
        key={"docs": sorted(d.uuid for d in docs), "title": default_title},
        preview={
            "action": "create_extraction_from_document",
            "preview": preview_text,
            "needs_confirmation": True,
            "document_count": len(docs),
            "default_title": default_title,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

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

    # Auto-pin to the active project (best-effort — never blocks creation).
    pinned_to_project = None
    if active_project:
        try:
            await project_service.add_pin(
                active_project, "extraction", ss.uuid, context.deps.user
            )
            pinned_to_project = active_project.title
        except Exception:
            logger.exception("Auto-pin of new extraction to project failed")

    if not discovered_fields:
        return {
            "extraction_set_uuid": ss.uuid,
            "title": ss.title,
            "fields": [],
            "document_uuids": [d.uuid for d in docs],
            "pinned_to_project": pinned_to_project,
            "message": (
                "Created an empty extraction set — the LLM didn't find clear "
                "fields in the document. You can add fields manually."
            ),
        }

    pin_note = (
        f' It\'s pinned to project "{pinned_to_project}".' if pinned_to_project else ""
    )
    return {
        "extraction_set_uuid": ss.uuid,
        "title": ss.title,
        "fields": discovered_fields,
        "field_count": len(discovered_fields),
        "document_uuids": [d.uuid for d in docs],
        "document_titles": [d.title or d.uuid for d in docs],
        "pinned_to_project": pinned_to_project,
        "message": (
            f'Created "{ss.title}" with {len(discovered_fields)} proposed field(s).'
            f"{pin_note} You can now run extraction on other documents, or propose "
            "this same document as the first test case to lock in ground truth."
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

    gate = await _confirm_gate(
        context,
        tool_name="run_validation",
        key={
            "extraction_set_uuid": extraction_set_uuid,
            "num_runs": num_runs,
            "test_case_uuids": sorted(test_case_uuids) if test_case_uuids else None,
        },
        preview={
            "action": "run_validation",
            "preview": (
                f"Validate \"{ss.title}\" with {effective_count} test case(s), "
                f"running extraction {num_runs} time(s) each."
            ),
            "needs_confirmation": True,
            "num_test_cases": effective_count,
            "num_runs": num_runs,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

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
# Phase 6 — Autovalidate (optimizer) tools
# ---------------------------------------------------------------------------

# Default optimizer token budget when the user doesn't name one. ~500k tokens
# is the "typically $1–$5" tier the autovalidate marketing copy promises.
DEFAULT_OPTIMIZATION_TOKEN_BUDGET = 500_000

_OPTIMIZE_KIND_ALIASES = {
    "kb": "knowledge_base",
    "knowledge_base": "knowledge_base",
    "extraction": "search_set",
    "search_set": "search_set",
    "workflow": "workflow",
}


async def _get_optimizable_item(context: RunContext[AgenticChatDeps], item_kind: str, item_uuid: str):
    """Resolve + manage-level authorize the parent item of an optimization.

    Returns (item, title, error_dict_or_None). Manage level = owner or same
    team — verified-only visibility is NOT enough to retune someone's config.
    """
    user_id = context.deps.user_id
    team_id = context.deps.team_id

    if item_kind == "knowledge_base":
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == item_uuid)
        if not kb:
            return None, None, {"error": f"Knowledge base '{item_uuid}' not found."}
        if kb.user_id != user_id and not (
            kb.shared_with_team and team_id and kb.team_id == team_id
        ):
            return None, None, {"error": "You need manage access to this knowledge base to optimize it."}
        return kb, kb.title, None

    if item_kind == "search_set":
        ss = await SearchSet.find_one(SearchSet.uuid == item_uuid)
        if not ss:
            return None, None, {"error": f"Extraction set '{item_uuid}' not found."}
        if ss.user_id != user_id and not (team_id and ss.team_id == team_id):
            return None, None, {"error": "You need manage access to this extraction set to optimize it."}
        return ss, ss.title, None

    if item_kind == "workflow":
        wf = await Workflow.get(item_uuid)
        if not wf:
            return None, None, {"error": f"Workflow '{item_uuid}' not found."}
        if getattr(wf, "user_id", None) != user_id and not (
            team_id and getattr(wf, "team_id", None) == team_id
        ):
            return None, None, {"error": "You need manage access to this workflow to optimize it."}
        return wf, wf.name, None

    return None, None, {
        "error": f"Unknown item_kind '{item_kind}'. Use 'knowledge_base', 'search_set', or 'workflow'."
    }


async def list_optimization_recommendations(
    context: RunContext[AgenticChatDeps],
) -> dict:
    """List pending autovalidate (optimizer) recommendations across KBs, extraction sets, and workflows.

    Vandalizer's quality monitor automatically tunes items in shadow mode when
    it detects quality drift. Completed shadow runs with a winning config that
    beats the current one are "pending recommendations" — the user can review
    and apply them. Use this when the user asks "any optimization suggestions?",
    "what can be improved?", or after surfacing a quality alert.

    Args:
        context: The call context.
    """
    from app.services.optimization_summary import shadow_inbox

    inbox = await shadow_inbox()
    # Trim chatty fields the LLM doesn't need; apply_preview alone can be huge.
    items = [
        {k: v for k, v in item.items() if k not in ("apply_preview", "trigger_detail")}
        for item in inbox["items"]
    ]
    return {
        "items": items,
        "counts": inbox["counts"],
        "lookback_days": inbox["lookback_days"],
        "note": (
            "Items with status=completed, no applied_at, and tied_with_baseline=false "
            "are pending recommendations. Offer apply_optimization for those."
        ),
    }


async def get_optimization_run(
    context: RunContext[AgenticChatDeps],
    item_kind: str,
    run_uuid: str,
) -> dict:
    """Get status and results of an autovalidate (optimizer) run.

    Use after start_optimization to poll progress, or to inspect a completed
    run before offering to apply it.

    Args:
        context: The call context.
        item_kind: One of 'knowledge_base', 'search_set', or 'workflow' (aliases 'kb' / 'extraction' accepted).
        run_uuid: UUID of the optimization run.
    """
    from app.services.optimization_summary import get_run_by_uuid, summarize_run

    kind = _OPTIMIZE_KIND_ALIASES.get(item_kind)
    if not kind:
        return {"error": f"Unknown item_kind '{item_kind}'."}
    surface = {"knowledge_base": "kb", "search_set": "extraction", "workflow": "workflow"}[kind]

    run = await get_run_by_uuid(surface, run_uuid)
    if not run:
        return {"error": f"Optimization run '{run_uuid}' not found."}

    item_id = getattr(run, "kb_uuid", None) or getattr(run, "search_set_uuid", None) or getattr(run, "workflow_id", None)
    _, _, err = await _get_optimizable_item(context, kind, item_id)
    if err:
        return err

    summary = summarize_run(run) or {}
    summary.pop("apply_preview", None)
    summary.update({
        "phase": getattr(run, "phase", None),
        "progress_message": getattr(run, "progress_message", None),
        "tokens_used": getattr(run, "tokens_used", None),
        "estimated_cost_usd": getattr(run, "estimated_cost_usd", None),
        "winner_selection_reason": getattr(run, "winner_selection_reason", None),
        "stopped_reason": getattr(run, "stopped_reason", None),
        "error_message": getattr(run, "error_message", None),
    })
    if summary.get("status") == "completed" and not summary.get("applied_at"):
        if summary.get("tied_with_baseline"):
            summary["note"] = (
                "The best trial is statistically tied with the current config — "
                "applying would not meaningfully change quality."
            )
        else:
            summary["note"] = "Completed and unapplied — offer apply_optimization."
    return summary


async def start_optimization(
    context: RunContext[AgenticChatDeps],
    item_kind: str,
    item_uuid: str,
    token_budget: int = DEFAULT_OPTIMIZATION_TOKEN_BUDGET,
    confirmed: bool = False,
) -> dict:
    """Start an autovalidate (optimizer) run that finds a better config for a KB, extraction set, or workflow.

    Autovalidate sweeps candidate configurations against the item's test set
    and reports the best one — nothing changes until the user applies it.
    Runs cost real LLM tokens (the budget) and take 5–30 minutes.

    Call first with confirmed=false to preview. Then call again with confirmed=true after the user approves.

    Args:
        context: The call context.
        item_kind: One of 'knowledge_base', 'search_set', or 'workflow' (aliases 'kb' / 'extraction' accepted).
        item_uuid: UUID of the item to optimize (workflow id for workflows).
        token_budget: Max LLM tokens the run may spend. Default 500k (roughly $1–$5 depending on model).
        confirmed: Must be true to actually start. If false, returns a preview for user confirmation.
    """
    from app.services.optimization_actions import (
        OptimizationActionError,
        start_extraction_optimization,
        start_kb_optimization,
        start_workflow_optimization,
    )

    kind = _OPTIMIZE_KIND_ALIASES.get(item_kind)
    if not kind:
        return {"error": f"Unknown item_kind '{item_kind}'."}

    item, title, err = await _get_optimizable_item(context, kind, item_uuid)
    if err:
        return err

    duration = {
        "knowledge_base": "10–20 minutes",
        "search_set": "5–15 minutes",
        "workflow": "15–30 minutes",
    }[kind]
    gate = await _confirm_gate(
        context,
        tool_name="start_optimization",
        key={"item_kind": kind, "item_uuid": item_uuid, "token_budget": token_budget},
        preview={
            "action": "start_optimization",
            "preview": (
                f"Run autovalidate on \"{title}\" with a budget of "
                f"{token_budget:,} tokens (typically takes {duration}). "
                "Nothing changes until the winning config is applied."
            ),
            "needs_confirmation": True,
            "token_budget": token_budget,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    user_id = context.deps.user_id
    try:
        if kind == "knowledge_base":
            run = await start_kb_optimization(item, user_id, token_budget)
        elif kind == "search_set":
            run = await start_extraction_optimization(item, user_id, token_budget)
        else:
            run = await start_workflow_optimization(str(item.id), user_id, token_budget)
    except OptimizationActionError as e:
        return {"error": e.message, "code": e.code, **e.detail}

    return {
        "run_uuid": run.uuid,
        "status": "queued",
        "item": title,
        "message": (
            f"Autovalidate started for '{title}'. It runs in the background — "
            "check progress with get_optimization_run."
        ),
    }


async def apply_optimization(
    context: RunContext[AgenticChatDeps],
    item_kind: str,
    run_uuid: str,
    confirmed: bool = False,
) -> dict:
    """Apply a completed optimization run's winning config to its KB, extraction set, or workflow.

    Call first with confirmed=false to preview the change (scores, deltas).
    Then call again with confirmed=true after the user approves. The previous
    config is snapshotted so the apply can be reverted from the UI.

    Args:
        context: The call context.
        item_kind: One of 'knowledge_base', 'search_set', or 'workflow' (aliases 'kb' / 'extraction' accepted).
        run_uuid: UUID of the completed optimization run to apply.
        confirmed: Must be true to actually apply. If false, returns a preview for user confirmation.
    """
    from app.services.optimization_actions import (
        OptimizationActionError,
        apply_extraction_optimization,
        apply_kb_optimization,
        apply_workflow_optimization,
    )
    from app.services.optimization_summary import get_run_by_uuid

    kind = _OPTIMIZE_KIND_ALIASES.get(item_kind)
    if not kind:
        return {"error": f"Unknown item_kind '{item_kind}'."}
    surface = {"knowledge_base": "kb", "search_set": "extraction", "workflow": "workflow"}[kind]

    run = await get_run_by_uuid(surface, run_uuid)
    if not run:
        return {"error": f"Optimization run '{run_uuid}' not found."}

    item_id = getattr(run, "kb_uuid", None) or getattr(run, "search_set_uuid", None) or getattr(run, "workflow_id", None)
    item, title, err = await _get_optimizable_item(context, kind, item_id)
    if err:
        return err

    if run.status != "completed":
        return {"error": f"Cannot apply — run status is '{run.status}', expected 'completed'."}

    optimized = getattr(run, "optimized_score", None)
    baseline = getattr(run, "baseline_default_score", None)
    delta = ""
    if optimized is not None and baseline is not None:
        delta = f" (score {baseline:.2f} → {optimized:.2f})"
    preview_text = f"Apply the winning autovalidate config to \"{title}\"{delta}."
    if getattr(run, "tied_with_baseline", False):
        preview_text += (
            " Note: the winner is statistically tied with the current config — "
            "applying may not improve quality."
        )
    rollup = (getattr(run, "apply_preview", None) or {})
    preview_result: dict = {
        "action": "apply_optimization",
        "preview": preview_text,
        "needs_confirmation": True,
    }
    if rollup:
        preview_result["expected_changes"] = {
            k: rollup.get(k)
            for k in ("total", "will_change", "improvements", "regressions", "significant_regressions", "net_delta")
            if k in rollup
        }
    gate = await _confirm_gate(
        context,
        tool_name="apply_optimization",
        key={"item_kind": kind, "run_uuid": run_uuid},
        preview=preview_result,
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    user_id = context.deps.user_id
    try:
        if kind == "knowledge_base":
            outcome = await apply_kb_optimization(item, run, user_id)
        elif kind == "search_set":
            outcome = await apply_extraction_optimization(item, run, user_id)
        else:
            outcome = await apply_workflow_optimization(item, run, user_id)
    except OptimizationActionError as e:
        return {"error": e.message, "code": e.code, **e.detail}

    return {
        "ok": True,
        "item": title,
        "message": f"Applied the optimized config to '{title}'. It can be reverted from the item's autovalidate panel.",
        "applied_config": outcome.get("applied_config"),
    }


async def regenerate_validation_plan(
    context: RunContext[AgenticChatDeps],
    workflow_id: str,
    confirmed: bool = False,
) -> dict:
    """Regenerate a workflow's validation plan when it has gone stale.

    Use when get_quality_info reports validation_plan_stale=true — the saved
    checks no longer match the workflow definition, so validation grades are
    unreliable until the plan is regenerated.

    Call first with confirmed=false to preview. Then call again with confirmed=true after the user approves.

    Args:
        context: The call context.
        workflow_id: The ID of the workflow whose plan should be regenerated.
        confirmed: Must be true to actually regenerate. If false, returns a preview for user confirmation.
    """
    from app.services import workflow_service

    item, title, err = await _get_optimizable_item(context, "workflow", workflow_id)
    if err:
        return err

    gate = await _confirm_gate(
        context,
        tool_name="regenerate_validation_plan",
        key={"workflow_id": workflow_id},
        preview={
            "action": "regenerate_validation_plan",
            "preview": (
                f"Regenerate the validation plan for \"{title}\" from its current "
                "definition. The old checks are replaced."
            ),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    try:
        checks = await workflow_service.generate_validation_plan(workflow_id, user=context.deps.user)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "ok": True,
        "workflow": title,
        "num_checks": len(checks) if isinstance(checks, list) else None,
        "message": f"Regenerated the validation plan for '{title}'. Validation runs now grade against the current definition.",
    }


# ---------------------------------------------------------------------------
# Phase 7 — Output artifacts (write generated content back to the workspace)
# ---------------------------------------------------------------------------

# Markdown and plain text are the only formats the agent authors directly — both
# round-trip cleanly through raw_text, so the saved doc is immediately
# chat-searchable, KB-ingestable, and usable as extraction/workflow input.
_SAVE_EXTENSIONS = {"md", "txt"}
MAX_SAVE_CHARS = 1_000_000


async def save_to_folder(
    context: RunContext[AgenticChatDeps],
    title: str,
    content: str,
    folder_uuid: Optional[str] = None,
    extension: str = "md",
    confirmed: bool = False,
) -> dict:
    """Save generated text content as a document in the user's folder tree.

    This is how chat output becomes a durable, reusable artifact instead of
    living only in the transcript. The saved file is a real SmartDocument: it
    appears in the Files tab, can be downloaded, and — once indexing finishes —
    is searchable in chat, addable to a knowledge base, and usable as input to
    extractions and workflows.

    Use when the user says "save this", "save that to my folder", "write this up
    as a document", "export the results", or after you've synthesized something
    worth keeping (a summary, a memo, a comparison table, a drafted section).
    For structured extraction or workflow results, render them as a Markdown
    table in ``content`` before saving.

    Call first with confirmed=false to preview the destination. Then call again
    with confirmed=true after the user approves — this writes a file and mutates
    workspace state.

    Args:
        context: The call context.
        title: Human-readable document title (also seeds the filename).
        content: The full text to save. Markdown is preferred; it renders in the
            viewer and round-trips as searchable text.
        folder_uuid: Destination folder UUID. Omit or pass null to save to the
            user's root folder. Use list_folders to resolve a folder by name.
        extension: File type — "md" (default) or "txt".
        confirmed: Must be true to actually save. If false, returns a preview
            for user confirmation.
    """
    import uuid as uuid_mod

    from werkzeug.utils import secure_filename

    user = context.deps.user
    user_id = context.deps.user_id

    ext = (extension or "md").lower().lstrip(".")
    if ext not in _SAVE_EXTENSIONS:
        return {"error": f"Unsupported extension '{ext}'. Use 'md' or 'txt'."}

    clean_title = (title or "").strip()
    if not clean_title:
        return {"error": "A title is required."}
    if not (content or "").strip():
        return {"error": "Cannot save empty content."}
    if len(content) > MAX_SAVE_CHARS:
        return {
            "error": f"Content is too large to save ({len(content):,} chars; limit {MAX_SAVE_CHARS:,})."
        }

    # Resolve + authorize the destination. Root ("0"/None) is the user's personal
    # space and is always writable; team_id is inherited only from a real folder,
    # so a personal save never lands under a team uuid (team_id dual-identity trap).
    target_folder = "0"
    team_id: Optional[str] = None
    folder_name = "your root folder"
    if folder_uuid and folder_uuid not in ("0", ""):
        from app.services import access_control

        folder = await access_control.get_authorized_folder(
            folder_uuid, user, team_access=context.deps.team_access,
        )
        if not folder:
            return {"error": "Folder not found or you don't have access to it."}
        target_folder = folder.uuid
        team_id = folder.team_id
        folder_name = f'"{folder.title}"'

    display_title = (
        clean_title if clean_title.lower().endswith(f".{ext}") else f"{clean_title}.{ext}"
    )

    gate = await _confirm_gate(
        context,
        tool_name="save_to_folder",
        key={"title": display_title, "folder": target_folder, "ext": ext},
        preview={
            "action": "save_to_folder",
            "preview": f'Save "{display_title}" ({len(content):,} chars) to {folder_name}.',
            "needs_confirmation": True,
            "destination_folder": target_folder,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    # Guard against an empty filename from a title of only punctuation/spaces.
    if not secure_filename(clean_title):
        return {"error": "Title contains no usable characters for a filename."}

    uid = uuid_mod.uuid4().hex.upper()
    # On-disk name is uuid-based to avoid collisions; the friendly name lives in title.
    relative_path = f"{user_id}/{uid}.{ext}"

    from app.services.storage import get_storage

    storage = get_storage()
    try:
        await storage.write(relative_path, content.encode("utf-8"))
    except Exception as e:
        logger.exception("save_to_folder: failed to write %s", relative_path)
        return {"error": f"Failed to write the file: {e}"}

    doc = SmartDocument(
        title=display_title,
        processing=False,
        valid=True,
        raw_text=content,
        path=relative_path,
        downloadpath=relative_path,
        extension=ext,
        uuid=uid,
        user_id=user_id,
        team_id=team_id,
        folder=target_folder,
        token_count=len(content) // 4,
    )
    await doc.insert()

    # Index for retrieval so the saved doc is immediately chat-searchable and
    # KB-ingestable. We already have the text, so skip the extraction round-trip.
    # Best-effort — the document is usable as text even if indexing lags.
    try:
        from app.celery_app import celery_app

        celery_app.send_task(
            "tasks.document.semantic_ingestion",
            kwargs={"raw_text": content, "document_uuid": uid, "user_id": user_id},
            queue="documents",
        )
    except Exception:
        logger.exception("save_to_folder: failed to dispatch ingestion for %s", uid)

    return {
        "document_uuid": uid,
        "title": display_title,
        "folder": target_folder,
        "extension": ext,
        "char_count": len(content),
        "message": (
            f'Saved "{display_title}" to {folder_name}. It\'s in your Files tab now and '
            "will be searchable in chat once indexing finishes — you can also add it to a "
            "knowledge base or run an extraction on it."
        ),
    }


# ---------------------------------------------------------------------------
# Phase 8 — Project tools (active only when a project is open in chat)
# ---------------------------------------------------------------------------


async def _resolve_active_project(context: RunContext[AgenticChatDeps]):
    """The authorized active project, or None when no project is open.

    Resolves ``deps.active_project_uuid`` (set when the user chats inside a
    project) through the same authorization as the project routes.
    """
    project_uuid = getattr(context.deps, "active_project_uuid", None)
    if not project_uuid:
        return None
    from app.services import project_service

    return await project_service.get_authorized_project(project_uuid, context.deps.user)


async def list_project_documents(context: RunContext[AgenticChatDeps]) -> dict:
    """List the documents inside the active project's folder subtree.

    Use when the user refers to "this project's files" or "what's in the
    project", or when you need the project's document set. Only works when a
    project is open. Returns up to 50 documents with uuid + title.

    Args:
        context: The call context.
    """
    project = await _resolve_active_project(context)
    if not project:
        return {"error": "No project is open. Open a project to use this tool."}

    from app.services import project_service

    doc_uuids = await project_service.get_project_document_uuids(project)
    docs: list[dict] = []
    for doc_uuid in doc_uuids[:50]:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if doc:
            docs.append({"uuid": doc.uuid, "title": doc.title or doc_uuid})

    return {
        "project": project.title,
        "document_count": len(doc_uuids),
        "documents": docs,
        "note": (
            f"Showing {len(docs)} of {len(doc_uuids)} documents."
            if len(doc_uuids) > len(docs)
            else None
        ),
    }


async def run_pin_on_project(
    context: RunContext[AgenticChatDeps],
    pin_type: str,
    target_id: str,
    confirmed: bool = False,
) -> dict:
    """Run a project-pinned workflow or extraction on ALL the project's documents.

    Resolves the project's document set automatically — you do not need to list
    documents first. ``pin_type`` must be "workflow" or "extraction" and must
    match a capability pinned to the project (see the Active project section).
    Automation pins cannot be run from chat.

    Call first with confirmed=false to preview, then confirmed=true after the
    user approves.

    Args:
        context: The call context.
        pin_type: "workflow" or "extraction".
        target_id: The pinned item's target_id (from the Active project section).
        confirmed: Must be true to actually run; false returns a preview.
    """
    project = await _resolve_active_project(context)
    if not project:
        return {"error": "No project is open. Open a project to use this tool."}

    if pin_type not in ("workflow", "extraction"):
        return {
            "error": (
                "Only 'workflow' and 'extraction' pins can be run from chat. "
                f"'{pin_type}' is not runnable here."
            )
        }

    from app.services import project_service

    # Running is a manage action — keep it to owners/editors. Viewers can chat
    # with the project but not trigger work on it.
    if not await project_service.can_manage_project(project, context.deps.user):
        return {"error": "You need edit access to this project to run its tools."}

    # The pin must exist on this project — that's the authorization boundary for
    # the referenced workflow/extraction (the user reaches it via the project).
    pins = await project_service.list_pins(project)
    match = next(
        (p for p in pins if p["pin_type"] == pin_type and p["target_id"] == target_id),
        None,
    )
    if not match:
        return {"error": f"That {pin_type} is not pinned to this project."}

    doc_uuids = await project_service.get_project_document_uuids(project)
    if not doc_uuids:
        return {"error": "This project has no documents to run on yet."}

    gate = await _confirm_gate(
        context,
        tool_name="run_pin_on_project",
        key={"project": project.uuid, "pin_type": pin_type, "target_id": target_id},
        preview={
            "action": "run_pin_on_project",
            "preview": (
                f'Run {pin_type} "{match["name"]}" on {len(doc_uuids)} '
                f'document(s) in project "{project.title}"'
            ),
            "needs_confirmation": True,
            "document_count": len(doc_uuids),
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    if pin_type == "extraction":
        ss = await SearchSet.find_one(SearchSet.uuid == target_id)
        if not ss:
            return {"error": "The pinned extraction no longer exists."}
        result = await _execute_extraction(context, ss, doc_uuids)
    else:  # workflow
        wf = await Workflow.get(target_id)
        if not wf:
            return {"error": "The pinned workflow no longer exists."}
        result = await _execute_workflow(context, wf, doc_uuids)
        if len(doc_uuids) > 10 and "error" not in result:
            result["note"] = (
                "Ran on the first 10 of "
                f"{len(doc_uuids)} project documents (workflow run limit)."
            )

    if isinstance(result, dict) and "error" not in result:
        result["project"] = project.title
    return result


async def pin_to_project(
    context: RunContext[AgenticChatDeps],
    pin_type: str,
    target_id: str,
    confirmed: bool = False,
) -> dict:
    """Pin an existing workflow/extraction/automation/knowledge_base to the project.

    A pin is a reference for quick access — it never moves or copies the
    artifact. Call first with confirmed=false to preview.

    Args:
        context: The call context.
        pin_type: One of "workflow", "extraction", "automation", "knowledge_base".
        target_id: The artifact's id (workflow/automation ObjectId, or uuid).
        confirmed: Must be true to actually pin; false returns a preview.
    """
    from app.models.project import PIN_TYPES
    from app.services import project_service

    project = await _resolve_active_project(context)
    if not project:
        return {"error": "No project is open. Open a project to use this tool."}
    if pin_type not in PIN_TYPES:
        return {"error": f"Invalid pin type. Must be one of: {', '.join(PIN_TYPES)}."}
    if not await project_service.can_manage_project(project, context.deps.user):
        return {"error": "You need edit access to this project to pin items."}

    gate = await _confirm_gate(
        context,
        tool_name="pin_to_project",
        key={"project": project.uuid, "pin_type": pin_type, "target_id": target_id},
        preview={
            "action": "pin_to_project",
            "preview": f'Pin {pin_type} {target_id} to project "{project.title}"',
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    try:
        await project_service.add_pin(project, pin_type, target_id, context.deps.user)
    except ValueError as e:
        return {"error": str(e)}
    return {
        "ok": True,
        "project": project.title,
        "pin_type": pin_type,
        "target_id": target_id,
        "message": f'Pinned {pin_type} to "{project.title}".',
    }


async def unpin_from_project(
    context: RunContext[AgenticChatDeps],
    pin_type: str,
    target_id: str,
    confirmed: bool = False,
) -> dict:
    """Remove a pinned workflow/extraction/automation/knowledge_base from the project.

    The artifact itself is untouched — only the project reference is removed.
    Call first with confirmed=false to preview.

    Args:
        context: The call context.
        pin_type: One of "workflow", "extraction", "automation", "knowledge_base".
        target_id: The pinned item's target_id.
        confirmed: Must be true to actually unpin; false returns a preview.
    """
    from app.services import project_service

    project = await _resolve_active_project(context)
    if not project:
        return {"error": "No project is open. Open a project to use this tool."}
    if not await project_service.can_manage_project(project, context.deps.user):
        return {"error": "You need edit access to this project to unpin items."}

    gate = await _confirm_gate(
        context,
        tool_name="unpin_from_project",
        key={"project": project.uuid, "pin_type": pin_type, "target_id": target_id},
        preview={
            "action": "unpin_from_project",
            "preview": f'Remove {pin_type} {target_id} from project "{project.title}"',
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    try:
        await project_service.remove_pin(project, pin_type, target_id, context.deps.user)
    except ValueError as e:
        return {"error": str(e)}
    return {
        "ok": True,
        "project": project.title,
        "message": f'Removed {pin_type} from "{project.title}".',
    }


async def set_project_status(
    context: RunContext[AgenticChatDeps],
    state: str,
    confirmed: bool = False,
) -> dict:
    """Set the active project's lifecycle status.

    Use when the user wants to move the project through its lifecycle (e.g.
    "mark this submitted", "archive the project"). Call first with
    confirmed=false to preview.

    Args:
        context: The call context.
        state: One of draft, active, submitted, awarded, closeout, archived.
        confirmed: Must be true to actually change; false returns a preview.
    """
    from app.models.project import PROJECT_STATES
    from app.services import project_service

    project = await _resolve_active_project(context)
    if not project:
        return {"error": "No project is open. Open a project to use this tool."}
    if state not in PROJECT_STATES:
        return {
            "error": f"Invalid status. Must be one of: {', '.join(PROJECT_STATES)}."
        }
    # update_project is an ungated setter, so the manage check must live here.
    if not await project_service.can_manage_project(project, context.deps.user):
        return {"error": "You need edit access to change this project's status."}

    gate = await _confirm_gate(
        context,
        tool_name="set_project_status",
        key={"project": project.uuid, "state": state},
        preview={
            "action": "set_project_status",
            "preview": (
                f'Set project "{project.title}" status to {state} '
                f"(currently {project.state})"
            ),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    await project_service.update_project(project, state=state)
    return {
        "ok": True,
        "project": project.title,
        "state": state,
        "message": f'Project "{project.title}" is now {state}.',
    }


async def create_project(
    context: RunContext[AgenticChatDeps],
    title: str,
    description: Optional[str] = None,
    confirmed: bool = False,
) -> dict:
    """Create a project — a goal-scoped workspace for one unit of work (e.g. a grant).

    A project is the right answer when the user wants to "drop files in as they
    arrive and chat across the whole set." Every file added to the project is
    automatically indexed into the project's implicit knowledge base, so
    project-wide chat works with NO separate knowledge-base building. The project
    also carries a lifecycle status and can have extraction/workflow capabilities
    pinned to it.

    Recommend this over create_knowledge_base whenever the user describes an
    ongoing effort they'll feed documents into over time and want to question as
    a whole (a grant, a proposal package, a compliance review). A bare knowledge
    base is better only when they want a standalone reference corpus with no
    folder, lifecycle, or pinned capabilities.

    Call first with confirmed=false to preview. Then call again with confirmed=true
    after the user approves — this creates a folder plus a knowledge base and
    mutates workspace state.

    Args:
        context: The call context.
        title: Name for the project (e.g. the grant or effort name).
        description: Optional short description of the project's goal.
        confirmed: Must be true to actually create. If false, returns a preview.
    """
    from app.services import project_service

    clean_title = (title or "").strip()
    if not clean_title:
        return {"error": "A project title is required."}
    clean_desc = (description or "").strip()

    gate = await _confirm_gate(
        context,
        tool_name="create_project",
        key={"title": clean_title, "description": clean_desc},
        preview={
            "action": "create_project",
            "preview": (
                f'Create a project "{clean_title}". Files you add to it are '
                "auto-indexed, so you can chat across the whole project with no "
                "knowledge-base setup."
            ),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    project = await project_service.create_project(
        title=clean_title,
        description=clean_desc or None,
        user=context.deps.user,
    )
    return {
        "project_uuid": project.uuid,
        "title": project.title,
        "root_folder_uuid": project.root_folder_uuid,
        "kb_uuid": project.kb_uuid,
        "state": project.state,
        "message": (
            f'Created the project "{project.title}". Add files to it as they come in — '
            "each one is automatically indexed into the project's knowledge base, so you "
            "can chat across the entire project without building a separate KB. Open the "
            "project to start adding documents."
        ),
    }


# ---------------------------------------------------------------------------
# Phase 9 — Automations
# ---------------------------------------------------------------------------


async def create_automation(
    context: RunContext[AgenticChatDeps],
    name: str,
    action_type: str,
    action_id: str,
    trigger_type: str = "folder_watch",
    folder_uuid: str = "",
    cron_expression: str = "",
    description: str = "",
    confirmed: bool = False,
) -> dict:
    """Create an automation that runs a workflow or extraction automatically.

    Two trigger types are supported from chat:
      - "folder_watch": fires whenever a document is added to a folder (needs folder_uuid)
      - "schedule": fires on a cron schedule (needs cron_expression, e.g. "0 9 * * 1")

    The action is an EXISTING workflow or extraction (action_type + action_id);
    chat can't author those, so find or create them first (list_workflows /
    list_extraction_sets). Call with confirmed=false to preview, then
    confirmed=true after the user approves. The automation is created DISABLED —
    tell the user to enable it on the Automations screen once it looks right.

    Args:
        context: The call context.
        name: A name for the automation.
        action_type: "workflow" or "extraction" — what runs when the trigger fires.
        action_id: ID of the workflow (object id) or extraction (uuid) to run.
        trigger_type: "folder_watch" (default) or "schedule".
        folder_uuid: Required for folder_watch — the folder to watch.
        cron_expression: Required for schedule — a cron expression like "0 9 * * 1".
        description: Optional description.
        confirmed: Must be true to actually create. If false, returns a preview.
    """
    from app.services import access_control

    user = context.deps.user

    # Validate the trigger and build its config.
    if trigger_type not in ("folder_watch", "schedule"):
        return {
            "error": "trigger_type must be 'folder_watch' or 'schedule'.",
        }
    trigger_config: dict = {}
    trigger_desc = ""
    if trigger_type == "folder_watch":
        if not folder_uuid:
            return {"error": "folder_watch needs a folder_uuid to watch."}
        folder = await access_control.get_authorized_folder(
            folder_uuid, user, team_access=context.deps.team_access,
        )
        if not folder:
            return {"error": "Folder not found or you don't have access to it."}
        trigger_config = {"folder_id": folder.uuid}
        trigger_desc = f'when a document is added to "{folder.title}"'
    else:  # schedule
        if not (cron_expression or "").strip():
            return {
                "error": "schedule needs a cron_expression (e.g. '0 9 * * 1').",
            }
        trigger_config = {"cron_expression": cron_expression.strip()}
        trigger_desc = f"on schedule ({cron_expression.strip()})"

    # Validate the action target and resolve a friendly name.
    if action_type not in ("workflow", "extraction"):
        return {"error": "action_type must be 'workflow' or 'extraction'."}
    if action_type == "workflow":
        wf = await access_control.get_authorized_workflow(
            action_id, user, team_access=context.deps.team_access,
        )
        if not wf:
            return {"error": "Workflow not found or you don't have access to it."}
        action_name = wf.name or action_id
    else:
        ss = await access_control.get_authorized_search_set(action_id, user)
        if not ss:
            return {"error": "Extraction not found or you don't have access to it."}
        action_name = ss.title or action_id

    gate = await _confirm_gate(
        context,
        tool_name="create_automation",
        key={
            "name": name,
            "trigger_type": trigger_type,
            "trigger_config": trigger_config,
            "action_type": action_type,
            "action_id": action_id,
        },
        preview={
            "action": "create_automation",
            "preview": (
                f'Create automation "{name}": run {action_type} "{action_name}" '
                f"{trigger_desc}. (Created disabled — you enable it after review.)"
            ),
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    from app.services import automation_service

    team_id = str(user.current_team) if user.current_team else None
    auto = await automation_service.create_automation(
        name=name,
        user_id=context.deps.user_id,
        description=description or None,
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        action_type=action_type,
        action_id=action_id,
        team_id=team_id,
        shared_with_team=False,
    )
    return {
        "id": str(auto.id),
        "name": auto.name,
        "enabled": auto.enabled,
        "message": (
            f'Automation "{auto.name}" created (disabled). It will run the '
            f'{action_type} "{action_name}" {trigger_desc}. Enable it on the '
            "Automations screen when you're ready."
        ),
    }


# ---------------------------------------------------------------------------
# Phase 10 — Workflow authoring
# ---------------------------------------------------------------------------


# Friendly step "type" (what the user/agent describes) → backend task name +
# whether the step consumes the workflow's input documents. Keeping this map
# small and RA-oriented means the agent doesn't need to know internal node names
# like "ResearchNode" or "KnowledgeBaseQuery".
_WORKFLOW_STEP_TYPES = {
    "extraction": ("Extraction", True),
    "extract": ("Extraction", True),
    "prompt": ("Prompt", True),
    "summarize": ("Prompt", True),
    "custom": ("Prompt", True),
    "format": ("Formatter", True),
    "research": ("ResearchNode", True),
    "knowledge_base_query": ("KnowledgeBaseQuery", False),
    "kb_query": ("KnowledgeBaseQuery", False),
    "website": ("AddWebsite", False),
    "approval": ("Approval", False),
}


async def _build_workflow_step_data(
    context: "RunContext[AgenticChatDeps]",
    step: dict,
    step_type: str,
    model: str | None,
) -> tuple[Optional[dict], Optional[str]]:
    """Translate one friendly step spec into a (task_data, error) pair.

    Returns ``(data, None)`` on success or ``(None, error_message)`` on a
    validation problem (unknown type, missing/inaccessible reference, etc.).
    """
    instruction = (
        step.get("prompt")
        or step.get("question")
        or step.get("instructions")
        or step.get("format_template")
        or ""
    ).strip()

    if step_type in ("extraction", "extract"):
        set_uuid = step.get("extraction_set_uuid") or step.get("search_set_uuid")
        if set_uuid:
            from app.services import access_control

            ss = await access_control.get_authorized_search_set(set_uuid, context.deps.user)
            if not ss:
                return None, f"extraction set '{set_uuid}' not found or not accessible"
            return {"search_set_uuid": set_uuid}, None
        fields = step.get("extractions") or step.get("fields")
        if not fields or not isinstance(fields, list):
            return None, "an extraction step needs 'extraction_set_uuid' or a non-empty 'extractions' list"
        return {"extractions": [str(f) for f in fields]}, None

    if step_type in ("prompt", "summarize", "custom"):
        prompt = instruction
        if not prompt and step_type == "summarize":
            prompt = "Summarize the input clearly and concisely."
        if not prompt:
            return None, "a prompt step needs a 'prompt' describing what to do"
        return {"prompt": prompt, "model": model}, None

    if step_type == "format":
        if not instruction:
            return None, "a format step needs a 'format_template' (or 'prompt') describing the output shape"
        return {"format_template": instruction, "model": model}, None

    if step_type == "research":
        if not instruction:
            return None, "a research step needs a 'question' to investigate"
        return {"question": instruction, "model": model}, None

    if step_type in ("knowledge_base_query", "kb_query"):
        kb_uuid = step.get("kb_uuid")
        query = step.get("query") or instruction
        if not kb_uuid:
            return None, "a knowledge_base_query step needs a 'kb_uuid'"
        if not query:
            return None, "a knowledge_base_query step needs a 'query'"
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
        if not kb or not (kb.verified or _kb_access_ok(kb, context.deps.user_id, context.deps.team_id)):
            return None, f"knowledge base '{kb_uuid}' not found or not accessible"
        mode = step.get("mode") if step.get("mode") in ("passages", "answer") else "answer"
        return {"kb_uuid": kb_uuid, "query": query, "mode": mode, "model": model}, None

    if step_type == "website":
        url = step.get("url") or instruction
        if not url:
            return None, "a website step needs a 'url'"
        return {"url": url}, None

    if step_type == "approval":
        return {
            "review_instructions": instruction or "Review the output before the workflow continues.",
            "assignee_role": "workflow_owner",
        }, None

    return None, f"unknown step type '{step_type}'"


async def create_workflow(
    context: RunContext[AgenticChatDeps],
    name: str,
    steps: list[dict],
    description: str = "",
    input_mode: str = "documents",
    fixed_document_uuids: list[str] | None = None,
    confirmed: bool = False,
) -> dict:
    """Build a multi-step workflow from a plain-language description of the steps.

    Use this when the user wants to *create* a reusable workflow by talking it
    through ("build me a workflow that extracts the budget, checks it against
    policy, then drafts a summary"). Steps run in order — each step's output
    feeds the next. The workflow is created UNVERIFIED and ready to run; tell the
    user they can fine-tune it in the visual workflow editor and validate it
    before relying on it.

    Each entry in ``steps`` is a dict with:
      - "name": short label for the step (e.g. "Extract budget fields")
      - "type": one of:
          "extraction"  — pull structured fields. Needs "extractions" (a list of
                          field names) OR "extraction_set_uuid" (an existing set).
          "prompt"      — run an instruction over the input. Needs "prompt".
          "summarize"   — summarize the input. "prompt" optional.
          "format"      — reshape the input into a template. Needs "format_template".
          "research"    — investigate a question (multi-pass). Needs "question".
          "knowledge_base_query" — query a KB. Needs "kb_uuid" and "query".
          "website"     — fetch a page. Needs "url".
          "approval"    — pause for human review. "instructions" optional.
      - "is_output": optional bool — mark this step's result as a deliverable.

    Steps are wired linearly: the first content step reads the workflow's input;
    later steps read the previous step's output.

    ``input_mode`` sets how the workflow is fed when run:
      - "documents" (default) — runs on documents/folders the user picks.
      - "text_input" — the user types text at run time (e.g. a bed name, a
        pasted snippet); that text becomes the input the first step reads. Use
        this when the user says they want to "type" or "input" something each
        run. Requires at least one content step to read the text.
      - "no_input" — runs with no input (e.g. a research/website step that
        supplies its own data).
    ``fixed_document_uuids`` pins documents that are ALWAYS included on every run
    (handy with text_input — e.g. pin the source PDF so the typed bed name is
    matched against it).

    Call first with confirmed=false to preview the plan, then confirmed=true
    after the user approves.

    Args:
        context: The call context.
        name: Name for the new workflow.
        steps: Ordered list of step specs (see above). At least one required.
        description: Optional description of what the workflow does.
        input_mode: "documents" (default), "text_input", or "no_input".
        fixed_document_uuids: Optional UUIDs always included alongside the input.
        confirmed: Must be true to actually create. If false, returns a preview.
    """
    if not name or not name.strip():
        return {"error": "A workflow name is required."}
    if not steps or not isinstance(steps, list):
        return {"error": "A workflow needs at least one step."}
    if len(steps) > 25:
        return {"error": "That's a lot of steps — keep workflows to 25 or fewer. Split big jobs into multiple workflows."}

    input_mode = (input_mode or "documents").strip().lower()
    if input_mode not in ("documents", "text_input", "no_input"):
        return {"error": "input_mode must be 'documents', 'text_input', or 'no_input'."}

    model = context.deps.model_name or None

    # Validate every step up front so the preview reflects a buildable plan and
    # we never half-create a workflow because step 4 was malformed.
    plan: list[dict] = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            return {"error": f"Step {idx + 1} is malformed (expected an object)."}
        raw_type = str(step.get("type") or "").strip().lower()
        if raw_type not in _WORKFLOW_STEP_TYPES:
            return {
                "error": (
                    f"Step {idx + 1} has an unknown type '{step.get('type')}'. "
                    f"Valid types: {', '.join(sorted(set(_WORKFLOW_STEP_TYPES)))}."
                )
            }
        task_name, doc_consuming = _WORKFLOW_STEP_TYPES[raw_type]
        data, err = await _build_workflow_step_data(context, step, raw_type, model)
        if err:
            return {"error": f"Step {idx + 1} ({step.get('name') or raw_type}): {err}."}
        step_label = str(step.get("name") or f"Step {idx + 1}").strip()
        plan.append({
            "label": step_label,
            "type": raw_type,
            "task_name": task_name,
            "data": data,
            "doc_consuming": doc_consuming,
            "is_output": bool(step.get("is_output")),
        })

    # A text-input workflow must have a step that actually reads the typed text;
    # otherwise the input silently goes nowhere.
    if input_mode == "text_input" and not any(p["doc_consuming"] for p in plan):
        return {"error": "A text-input workflow needs at least one step that reads the input (extraction, prompt, summarize, format, or research). Add one so the typed text is actually used."}

    mode_suffix = {"text_input": " [text input]", "no_input": " [no input]"}.get(input_mode, "")
    preview_lines = "; ".join(f"{i + 1}. {p['label']} ({p['type']})" for i, p in enumerate(plan))
    gate = await _confirm_gate(
        context,
        tool_name="create_workflow",
        key={"name": name, "mode": input_mode, "steps": [{"t": p["type"], "n": p["label"]} for p in plan]},
        preview={
            "action": "create_workflow",
            "preview": f"Create workflow \"{name}\"{mode_suffix} with {len(plan)} step(s): {preview_lines}",
            "needs_confirmation": True,
        },
        confirmed=confirmed,
    )
    if gate is not None:
        return gate

    from app.services import workflow_service

    user = context.deps.user
    team_id = context.deps.team_id

    # If the author didn't mark any deliverable, mark the last step as output so
    # the run produces a downloadable result.
    if not any(p["is_output"] for p in plan):
        plan[-1]["is_output"] = True

    wf = await workflow_service.create_workflow(
        name.strip(), context.deps.user_id, description.strip() or None, team_id=team_id,
    )
    workflow_id = str(wf.id)

    try:
        first_doc_step_wired = False
        for p in plan:
            data = dict(p["data"])
            # Linear wiring: the first document-consuming step reads the run's
            # documents; every later step reads the previous step's output.
            if p["doc_consuming"]:
                if not first_doc_step_wired:
                    data["input_sources"] = ["workflow_documents"]
                    first_doc_step_wired = True
                else:
                    data["input_sources"] = ["step_input"]

            step_res = await workflow_service.add_step(
                workflow_id, p["label"], user=user, data={}, is_output=p["is_output"],
            )
            if not step_res or not step_res.get("id"):
                raise RuntimeError(f"failed to create step '{p['label']}'")
            task_res = await workflow_service.add_task(
                step_res["id"], p["task_name"], user=user, data=data,
            )
            if not task_res:
                raise RuntimeError(f"failed to configure step '{p['label']}'")
    except Exception as e:
        logger.error("create_workflow failed mid-build for %s: %s", workflow_id, e)
        # Roll back the half-built workflow so the user isn't left with a broken shell.
        try:
            await workflow_service.delete_workflow(workflow_id, user)
        except Exception:
            logger.exception("Failed to clean up partial workflow %s", workflow_id)
        return {"error": "Something went wrong building the workflow. Nothing was saved — try again."}

    # Persist the input trigger so the workflow knows how it's fed: documents
    # (default), typed text at run time, or nothing. Mirrors the editor's shape
    # ({trigger_type, fixed_documents:[{uuid,title}]}) so both paths agree, and
    # the execution task auto-merges fixed_documents on every run.
    input_config: dict = {}
    if input_mode in ("text_input", "no_input"):
        input_config["trigger_type"] = input_mode
    if fixed_document_uuids:
        fixed: list[dict] = []
        for u in fixed_document_uuids:
            d = await SmartDocument.find_one(SmartDocument.uuid == u)
            if d:
                fixed.append({"uuid": u, "title": d.title or "Document"})
        if fixed:
            input_config["fixed_documents"] = fixed
    if input_config:
        try:
            wf.input_config = input_config
            await wf.save()
        except Exception:
            logger.exception("Failed to persist input_config for workflow %s", workflow_id)

    mode_note = {
        "text_input": " It takes typed text input each run — tell me what to type and I'll run it.",
        "no_input": " It runs with no input.",
    }.get(input_mode, "")
    return {
        "workflow_id": workflow_id,
        "name": wf.name,
        "steps_created": len(plan),
        "input_mode": input_mode,
        "verified": False,
        "message": (
            f"Created workflow \"{wf.name}\" with {len(plan)} steps.{mode_note} You can "
            "fine-tune the steps or validate it in the workflow editor. Want to run it now "
            "or open it to review?"
        ),
    }


# ---------------------------------------------------------------------------
# Tool registry — imported by llm_service.create_agentic_chat_agent()
# ---------------------------------------------------------------------------

TOOLS = [
    # Phase 1 — Read-only
    search_documents,
    list_documents,
    list_folders,
    search_knowledge_base,
    list_knowledge_bases,
    list_extraction_sets,
    list_workflows,
    get_quality_info,
    search_library,
    get_app_help,
    # Phase 2 — Extraction
    fetch_url,
    web_search,
    get_document_text,
    run_extraction,
    check_compliance,
    # Phase 3 — KB write
    create_knowledge_base,
    add_documents_to_kb,
    add_url_to_kb,
    # Phase 4 — Workflow orchestration
    run_workflow,
    get_workflow_status,
    approve_workflow_step,
    reject_workflow_step,
    # Phase 5 — Validation & guided verification
    list_test_cases,
    propose_test_case,
    run_validation,
    create_extraction_from_document,
    # Phase 6 — Autovalidate (optimizer)
    list_optimization_recommendations,
    get_optimization_run,
    start_optimization,
    apply_optimization,
    regenerate_validation_plan,
    # Phase 7 — Output artifacts
    save_to_folder,
    # Phase 8 — Projects. create_project works anytime; the rest need a project open.
    create_project,
    list_project_documents,
    run_pin_on_project,
    pin_to_project,
    unpin_from_project,
    set_project_status,
    # Phase 9 — Automations
    create_automation,
    # Phase 10 — Workflow authoring
    create_workflow,
]
