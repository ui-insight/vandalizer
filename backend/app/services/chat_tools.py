"""Agentic chat tool functions.

Each tool is registered on the agentic chat agent via ``@agent.tool`` and
receives ``RunContext[AgenticChatDeps]`` for user-scoped authorization.

Tools are exported as the ``TOOLS`` list for bulk registration.
"""

import asyncio
import datetime
import difflib
import hashlib
import json
import logging
import re
from typing import Optional

from pydantic import BaseModel
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
from app.services.certification_versions.runtime import course_operation
from app.services.certification_versions.tool_results import (
    CheckResult, CompletionResult, LessonResult, ModuleResult, ProgressResult,
    ProvisionResult, ReflectionResult, certification_result,
)
from app.services.page_locator import annotate_chunk_pages, cited_pages

logger = logging.getLogger(__name__)

MAX_RESULTS = 20


def _resolve_doc_uuids(
    context: RunContext[AgenticChatDeps],
    document_uuids: list[str] | None,
) -> list[str]:
    """Resolve the document UUIDs a tool should act on.

    When the model passes none — e.g. the user said "run it on this" about a
    PDF that's already open in the chat — fall back to the documents currently
    selected in the conversation (``deps.context_document_uuids``) instead of
    forcing the model to re-type a UUID it can see. Returns a de-duplicated
    list preserving order.
    """
    uuids = list(document_uuids or [])
    if not uuids:
        uuids = list(getattr(context.deps, "context_document_uuids", None) or [])
    seen: set[str] = set()
    deduped: list[str] = []
    for u in uuids:
        if u and u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


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


async def _extraction_set_staleness(
    ss: "SearchSet",
    latest_run,
    current_keys: Optional[set[str]] = None,
) -> tuple[bool, list[str]]:
    """Whether *ss* has drifted from the config its latest validation measured.

    Workflows already get a ``plan_stale`` check; extraction sets got nothing —
    edit a template's fields or settings after validating and the quality badge
    kept asserting a score for a configuration that no longer exists. Compares
    the current effective extraction config hash and the current field set
    against what the run recorded. Exception-safe: staleness detection failing
    must never break quality reporting, so any error reports "not stale".
    """
    reasons: list[str] = []
    if latest_run is None:
        return False, reasons
    try:
        from app.services.quality_service import compute_config_hash
        from app.services.search_set_service import effective_extraction_config

        if latest_run.config_hash:
            current_hash = compute_config_hash(effective_extraction_config(ss) or {})
            if current_hash != latest_run.config_hash:
                reasons.append("extraction settings changed since the last validation run")

        validated_fields: set[str] = set()
        for tc in (latest_run.result_snapshot or {}).get("test_cases", []) or []:
            for fr in tc.get("fields", []) or []:
                name = fr.get("field_name") if isinstance(fr, dict) else None
                if name:
                    validated_fields.add(name)
        if validated_fields:
            if current_keys is None:
                items = await ss.get_extraction_items()
                current_keys = {i.searchphrase for i in items if i.searchphrase}
            if current_keys != validated_fields:
                added = sorted(current_keys - validated_fields)
                removed = sorted(validated_fields - current_keys)
                detail = []
                if added:
                    detail.append(f"added: {', '.join(added[:5])}")
                if removed:
                    detail.append(f"removed: {', '.join(removed[:5])}")
                reasons.append(
                    "fields changed since the last validation run"
                    + (f" ({'; '.join(detail)})" if detail else "")
                )
    except Exception as e:
        logger.warning("Extraction-set staleness check failed for %s: %s", ss.uuid, e)
    return bool(reasons), reasons


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


def _err(message: str, hint: Optional[str] = None) -> dict:
    """Tool-error envelope with an optional corrective hint.

    Soft by design (uplift plan Phase 5): pydantic-ai's ModelRetry becomes
    run-FATAL once a tool exceeds its retry budget, so errors return as
    normal results the model can read and adapt to — the loop never dies on a
    stubborn call. ``hint`` names the exact next call to make ("call
    list_folders, retry with a returned uuid"), because the model corrects
    far better from a concrete instruction than from a bare not-found.
    """
    if hint:
        return {"error": message, "hint": hint}
    return {"error": message}


def _doc_text_unavailable_err(doc: "SmartDocument") -> dict:
    """Honest error for a document whose text is unavailable.

    Distinguishes a permanent ingest failure (``task_status == "error"``) from
    a document still processing — telling the user to "try again once
    processing completes" for a document that permanently failed sends them
    into a retry loop that can never succeed.
    """
    label = doc.title or doc.uuid
    if getattr(doc, "task_status", None) == "error":
        detail = getattr(doc, "error_message", None) or "text extraction failed"
        return _err(
            f'Text extraction FAILED for "{label}" ({detail}). This is a '
            "permanent processing failure — retrying will not help.",
            hint=(
                "Tell the user this document could not be read and suggest "
                "re-uploading it (or checking the OCR configuration if it is "
                "a scanned PDF). Do not say it is still processing."
            ),
        )
    return _err(
        f'"{label}" has no extracted text yet — it is still processing.',
        hint="Try again in a moment once processing completes.",
    )


# Approve-button labels on the chat approval card. Mirrors ``actionLabel`` in
# frontend/src/components/chat/ToolCallDisplay.tsx so the assistant can name
# the button the user actually sees.
_APPROVE_BUTTON_LABELS = {
    "create_workflow": "Create workflow",
    "create_automation": "Create automation",
    "create_extraction_from_document": "Create extraction",
    "run_workflow": "Run workflow",
    "run_validation": "Run validation",
}


def approve_button_label(tool_name: str) -> str:
    """The approve button's label on the approval card for ``tool_name``."""
    return _APPROVE_BUTTON_LABELS.get(tool_name, f"Approve {tool_name.replace('_', ' ')}")


def _armed_stash(
    context: "RunContext[AgenticChatDeps]", tool_name: str, key: dict
) -> Optional[dict]:
    """The ``stash`` a preview of this exact action saved with its arming, if any.

    Lets a write tool execute exactly what its approval card showed instead of
    recomputing a non-deterministic proposal after the user approved.
    """
    conv = getattr(context.deps, "conversation", None)
    fp = _confirm_fingerprint(tool_name, key)
    for entry in list(getattr(conv, "pending_confirmations", None) or []) if conv else []:
        if isinstance(entry, dict) and entry.get("fp") == fp:
            stash = entry.get("stash")
            return stash if isinstance(stash, dict) else None
    return None


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
    stash: Optional[dict] = None,
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

    ``stash`` is saved with the arming entry; read it back on the confirm call
    with ``_armed_stash`` to execute exactly what the preview showed.
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
        entry = {"fp": fp, "turn": marker, "tool": tool_name}
        if stash is not None:
            entry["stash"] = stash
        new_pending.append(entry)
        # Cap to bound growth on long conversations; keep the most recent.
        conv.pending_confirmations = new_pending[-25:]
        try:
            await conv.save()
        except Exception:
            logger.warning("Failed to arm pending confirmation for %s", tool_name)

    out = dict(preview)
    out["needs_confirmation"] = True
    # Make it impossible for the model to read this result as a completed
    # action. Without these the model routinely narrates success ("the PDFs
    # are now indexed") on the preview turn even though nothing was written,
    # leaving the user thinking the write happened when it did not.
    out["status"] = "awaiting_user_confirmation"
    label = approve_button_label(tool_name)
    out["assistant_instruction"] = (
        f"This action has NOT been performed. '{tool_name}' is only staged and "
        f'is waiting for the user to approve it with the "{label}" button on '
        "the approval card (or by replying yes). Do NOT tell the user it is "
        "done, added, saved, created, indexed, or running. The approval card "
        f'with its "{label}" and "Cancel action" buttons is shown to the user '
        "automatically, so do NOT call this tool again this turn and do NOT "
        "ask a separate yes/no question in your reply — just briefly state "
        f'what you have prepared. If you name the button, call it "{label}"; '
        'there is no "Confirm" button.'
    )
    return out


class _TitleRow(BaseModel):
    uuid: str
    title: Optional[str] = None


# Titles scanned for "did you mean" when a search finds nothing. Newest first,
# so a large workspace may miss an old file — a near miss is still far better
# than the bare "not found" this replaces.
_SUGGESTION_POOL = 1000
_SUGGESTION_CUTOFF = 0.75


def _closest_titles(query: str, rows: list[_TitleRow], limit: int = 3) -> list[dict]:
    """Rank document titles by closeness to a query that matched nothing.

    A title scores the better of (a) whole-string similarity of the
    normalized names and (b) the share of query tokens that appear in, or
    nearly match a word of, the title — so a typo in one word of a long
    filename and a typo in a short query both surface.
    """
    tokens = _tokenize_query(query)
    q_norm = " ".join(tokens)
    if not q_norm:
        return []
    scored: list[tuple[float, _TitleRow]] = []
    for row in rows:
        title_tokens = _tokenize_query(row.title or "")
        if not title_tokens:
            continue
        t_norm = " ".join(title_tokens)
        whole = difflib.SequenceMatcher(None, q_norm, t_norm).ratio()
        near = sum(
            1 for t in tokens
            if t in t_norm or difflib.get_close_matches(t, title_tokens, n=1, cutoff=0.75)
        )
        score = max(whole, near / len(tokens))
        if score >= _SUGGESTION_CUTOFF:
            scored.append((score, row))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [{"uuid": r.uuid, "title": r.title} for _, r in scored[:limit]]


async def search_documents(
    context: RunContext[AgenticChatDeps],
    query: str,
    search_content: bool = False,
) -> list[dict] | dict:
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

    Returns a list of matching documents. When a non-empty query matches
    nothing, returns ``{"documents": [], "did_you_mean": [...]}`` with the
    closest titles instead.
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
    if docs or not query:
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

    # Every query token must appear in the title, so one mistyped character
    # ("nih-ro1" for "nih-r01") finds nothing. A bare [] left the model
    # telling the user the file didn't exist, and later turns trusted that
    # verdict even after the user typed the name correctly.
    rows = await SmartDocument.find(base_filters).sort("-created_at").limit(
        _SUGGESTION_POOL,
    ).project(_TitleRow).to_list()
    suggestions = _closest_titles(query, rows)
    if suggestions:
        instruction = (
            f"No document title matches '{query}' exactly. Ask the user whether "
            "they meant one of did_you_mean (name it), and use its uuid once "
            "they confirm. Do not say the file does not exist."
        )
    else:
        instruction = (
            f"No document title matches '{query}' and nothing is close. Say so "
            "and ask the user to check the name or upload the file."
        )
    return {
        "documents": [],
        "did_you_mean": suggestions,
        "assistant_instruction": instruction
        + " This result covers only this query: if the user names a file "
        "again, search for it again.",
    }


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

    # Go through the shared tuned retrieval pipeline — the same seam the
    # classic KB chat path and the validation harness use — so the KB's
    # Autovalidate-tuned knobs (k, min_similarity floor, query rewriting,
    # rerank) apply on the agentic path too. A raw top-k vector query here
    # would silently skip the relevance floor the platform advertises.
    from app.services.kb_validation_service import (
        _ensure_system_config_loaded,
        retrieve_kb_chunks,
    )

    try:
        await _ensure_system_config_loaded()
        results, rag_cfg, _ = await retrieve_kb_chunks(
            uuid, query, context.deps.model_name, per_step_timeout=6.0,
        )
        results = results[: rag_cfg.k]
    except Exception as e:
        # Distinguish infrastructure failure from an empty corpus: a Chroma /
        # embedding outage must never be presented as "the KB had nothing".
        logger.warning("KB retrieval failed for kb %s: %s", uuid, e)
        return [_err(
            f"Knowledge base search FAILED for \"{kb.title}\" — the retrieval "
            "backend returned an error. The knowledge base was NOT searched.",
            hint=(
                "Tell the user the search itself failed (not that the KB had "
                "no matching content) and suggest retrying in a moment. Do not "
                "answer the question from general knowledge as if it were "
                "grounded in this knowledge base."
            ),
        )]

    if not results:
        return [{
            "no_results": True,
            "note": (
                f"No content in knowledge base \"{kb.title}\" matched this "
                "query above its relevance threshold. Tell the user the "
                "knowledge base had no matching content for this question. If "
                "you answer from general knowledge instead, clearly label the "
                "answer as NOT coming from their documents."
            ),
        }]

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

    # The openable SmartDocument behind each source, resolved for this reader.
    # A source's raw document_uuid can name a soft-deleted file or another
    # member's personal-space file; opening either 404s in the viewer as
    # "Source unavailable" (support ticket). Both the passage cards and the
    # citation chips link only through this map, so a source the reader can't
    # open stays preview-only rather than offering a button that 404s.
    from app.services.knowledge_service import resolve_openable_documents

    openable = await resolve_openable_documents(source_ids, user_id=user_id)

    enriched: list[dict] = []
    citations: list[dict] = []
    any_approximate = False
    any_spanning = False
    for r in results:
        meta = r.get("metadata", {})
        sid = meta.get("source_id", "")
        sheet = meta.get("sheet")
        content = r.get("content", "") or ""

        # The two things `page_locator` exists to prevent, both of which this
        # path had reintroduced by reading `metadata["page"]` directly:
        #
        #  * an interpolated OCR page stated as exact — the page count spread
        #    evenly over text the OCR endpoint returned with no page structure,
        #    which on a 400-page package with a 40-page budget table is off by
        #    an unbounded amount;
        #  * a chunk that crosses a page break cited by the page it *starts*
        #    on rather than the page the answering passage is actually on.
        cited = cited_pages(meta, content, query)
        page, page_end = cited["page"], cited["page_end"]
        approximate = bool(cited["page_approximate"])
        any_approximate = any_approximate or (page is not None and approximate)

        # `[p. N]` markers at each internal page break, so the model can see
        # where the page changes instead of inferring it.
        annotated = annotate_chunk_pages(content, meta)
        any_spanning = any_spanning or annotated != content

        entry: dict = {
            # Annotated for the model, so it can see where the page turns.
            "content": annotated,
            "source_name": meta.get("source_name", "unknown"),
        }
        if annotated != content:
            # Unannotated, for anything that has to match this text against the
            # document itself. The UI derives its click-to-highlight phrase
            # from the passage, and an injected "[p. 3]" marker appears nowhere
            # in the document — a chunk whose page break falls inside its first
            # 60 characters would open the viewer on a highlight that can never
            # match. Only set when the two differ.
            entry["content_verbatim"] = content
        if isinstance(page, int):
            entry["page"] = page
            if isinstance(page_end, int) and page_end > page:
                entry["page_end"] = page_end
            if approximate:
                entry["page_approximate"] = True
        if isinstance(sheet, str) and sheet:
            entry["sheet"] = sheet
        src = source_map.get(sid)
        if src:
            entry["source_type"] = src.source_type
            if src.source_type == "document" and openable.get(sid):
                entry["document_uuid"] = openable[sid]
            elif src.source_type == "url" and src.url:
                entry["url"] = src.url
            if src.source_reference:
                entry["source_reference"] = src.source_reference
        enriched.append(entry)

        citations.append({
            "document_id": sid or None,
            "document_title": meta.get("source_name", "Unknown"),
            "page": page if isinstance(page, int) else None,
            "page_end": page_end if isinstance(page_end, int) else None,
            # The chip renderer already hedges on this key; it was simply never
            # being sent, so every estimated page rendered as measured.
            "page_approximate": approximate,
            "sheet": sheet if isinstance(sheet, str) else None,
            "chunk_id": r.get("chunk_id"),
            "score": r.get("score"),
            "content_preview": content[:240],
            "source_reference": src.source_reference if src and src.source_reference else None,
            "url": src.url if src and src.source_type == "url" and src.url else None,
        })

    # Without document_uuid the chip has no "Open at p. N", and the preview's
    # "Open the source" would have only the KB source id, which is not a file.
    for c in citations:
        doc_uuid = openable.get(c.get("document_id") or "")
        if doc_uuid:
            c["document_uuid"] = doc_uuid

    # Citation sidecar: the streaming layer pops this by tool_call_id, emits a
    # 'sources' chunk, and persists the citations on the assistant message.
    if citations and context.tool_call_id:
        context.deps.citation_annotations[context.tool_call_id] = citations

    # The same labels the classic path gives the model, for the same measured
    # reason: a tilde nobody explained gets normalised away and the estimate is
    # restated as fact. Prepended so it is read before the passages it governs.
    notes: list[str] = []
    if any_approximate:
        notes.append(
            "A page marked page_approximate is an ESTIMATE — that source was "
            "scanned, so page positions were interpolated rather than read. "
            "Give such pages as approximate, e.g. \"around p. 4\". Never state "
            "one as exact and never say a passage is \"explicitly\" or "
            "\"clearly\" on it."
        )
    if any_spanning:
        notes.append(
            "A passage that runs across pages carries [p. N] where the next "
            "page begins. Cite the page the passage you are using falls under, "
            "not the page the passage starts on."
        )
    if notes:
        # On every entry rather than as a leading pseudo-passage. The array is
        # rendered by the UI as passages — a note dict prepended to it inflates
        # "Found N relevant passages" by one, takes a slot in the 3-passage
        # preview as a blank "Source ·" row, and leads the copied text with an
        # empty [Source] block. Keeping the array homogeneous costs a little
        # repetition in the model's view and keeps both consumers correct.
        guidance = " ".join(notes)
        for entry in enriched:
            entry["citation_note"] = guidance

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

    # Latest validation score per set: the tier is the primary sort key so the
    # most trusted templates surface first (QUALITY_SIGNALS_EXPLAINED.md).
    # Tier/score in a listing is deliberately model-visible — like
    # get_quality_info, it helps the agent recommend trusted templates; the
    # anti-inflation strip only applies to per-result badges.
    scores: dict[str, float] = {}
    uuids = [ss.uuid for ss in sets]
    if uuids:
        runs = await ValidationRun.find({
            "item_kind": "search_set",
            "item_id": {"$in": uuids},
        }).sort("-created_at").to_list()
        for run in runs:
            if run.score is not None and run.item_id not in scores:
                scores[run.item_id] = run.score

    results = []
    for ss in sets:
        field_count = len(ss.item_order) if ss.item_order else 0
        entry = {
            "uuid": ss.uuid,
            "title": ss.title,
            "verified": ss.verified or False,
            "field_count": field_count,
            "domain": ss.domain,
        }
        score = scores.get(ss.uuid)
        if score is not None:
            entry["quality_score"] = score
            entry["quality_tier"] = _score_to_tier(score)
        results.append(entry)
    # Scored sets first (best score leading), unscored keep recency order.
    results.sort(key=lambda r: (r.get("quality_score") is None, -(r.get("quality_score") or 0.0)))
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
        result["model"] = latest_run.model
        result["last_validated_at"] = latest_run.created_at.isoformat() if latest_run.created_at else None
        if latest_run.score_breakdown:
            result["score_breakdown"] = latest_run.score_breakdown

        # Per-model comparison over this item's measured history — answers
        # "which model does best on THIS template" without leaving chat.
        # Runs that recorded no model (older history) group as unattributed.
        # Best-effort like the other enrichment lookups below: a failure here
        # must not take down the main quality answer.
        try:
            model_scores: dict = {}
            all_runs = await ValidationRun.find(
                ValidationRun.item_kind == item_kind,
                ValidationRun.item_id == item_uuid,
            ).to_list()
            for r in all_runs:
                if getattr(r, "source", None) == "demo_seed":
                    continue
                entry = model_scores.setdefault(r.model, {"scores": [], "count": 0})
                entry["scores"].append(r.score)
                entry["count"] += 1
            model_comparison = [
                {
                    "model": m or "(unattributed)",
                    "avg_score": round(sum(e["scores"]) / len(e["scores"]), 1),
                    "run_count": e["count"],
                }
                for m, e in model_scores.items()
                if e["scores"]
            ]
            model_comparison.sort(key=lambda x: -x["avg_score"])
            if len(model_comparison) > 1 or (
                model_comparison and model_comparison[0]["model"] != "(unattributed)"
            ):
                result["model_comparison"] = model_comparison
        except Exception as e:
            logger.warning(
                "Model comparison lookup failed for %s/%s: %s", item_kind, item_uuid, e,
            )
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

    # Extraction sets: surface config/field drift since the last validation —
    # the score describes the configuration that was measured, and a template
    # edited afterwards is wearing an unearned badge.
    validation_stale = None
    if item_kind == "search_set" and latest_run:
        try:
            ss = await SearchSet.find_one(SearchSet.uuid == item_uuid)
            if ss:
                validation_stale, stale_reasons = await _extraction_set_staleness(ss, latest_run)
                result["validation_stale"] = validation_stale
                if validation_stale:
                    result["validation_stale_reasons"] = stale_reasons
                    result["note_validation_stale"] = (
                        "This extraction set changed after its last validation run "
                        f"({'; '.join(stale_reasons)}). The quality score describes "
                        "the previous configuration — recommend re-validating "
                        "(run_validation) before relying on the score."
                    )
        except Exception as e:
            logger.warning("Staleness lookup failed for search_set %s: %s", item_uuid, e)

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
            "stale": validation_stale if item_kind == "search_set" else plan_stale,
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
    from app.services.access_control import _team_role
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
    topic = {
        "id": primary["id"],
        "title": _brand(primary["title"]),
        "body": _brand(primary["body"]),
    }
    if primary.get("requires"):
        topic["requires"] = primary["requires"]
    user = context.deps.user
    team_role = _team_role(context.deps.team_id, context.deps.team_access)
    result = {
        "matched": True,
        "topic": topic,
        # The steps in a topic can be gated by role. This is who is asking, so
        # the answer can say "ask your admin" instead of describing controls
        # the user will never see.
        "viewer_access": {
            "is_system_admin": bool(user.is_admin),
            "current_team_role": team_role or "none",
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
            resp = await safe_get(client, url, validate=validate_outbound_url)
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


_DOCUMENT_READ_MAX_CHARS = 30000


def read_document_range(
    raw: str,
    markers: list[dict] | None,
    *,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    start_char: Optional[int] = None,
    max_chars: int = _DOCUMENT_READ_MAX_CHARS,
) -> dict:
    """One bounded read of a document's text, by page where it has pages (#1007).

    A read used to be the first 30,000 characters and nothing else, so a
    100-page solicitation could not be read past roughly page 25 from chat.
    Now a read covers the requested pages (all of them by default) and stops
    at a page boundary when it hits the cap, and the result says exactly which
    pages it holds and where to continue. Documents without page markers are
    read by character offset with the same continuation fields.

    Returns the read (``text``, ``pages_returned``, ``next_page`` or
    ``next_start_char``, ``complete``) or ``{"error", "hint"}``.
    """
    from app.services.chat_service import _page_positions, annotate_pages

    raw = raw or ""
    positions = _page_positions(markers, len(raw))

    if not positions:
        if start_page is not None or end_page is not None:
            return _err(
                "This document has no page markers, so it can't be read by page.",
                hint="Read it by position instead: start_char=0, then the next_start_char each read returns.",
            )
        begin = start_char or 0
        if begin < 0 or (raw and begin >= len(raw)):
            return _err(
                f"start_char {begin} is outside this document ({len(raw)} characters).",
                hint="Use start_char=0, or the next_start_char a previous read returned.",
            )
        stop = min(len(raw), begin + max_chars)
        return {
            "text": raw[begin:stop],
            "start_char": begin,
            "end_char": stop,
            "next_start_char": stop if stop < len(raw) else None,
            "total_chars": len(raw),
            "complete": begin == 0 and stop == len(raw),
        }

    if start_char is not None:
        return _err(
            "This document has page markers; read it by page.",
            hint="Use start_page and end_page (the pages to read).",
        )
    pages = [p for _offset, p, _approx in positions]
    first, last = pages[0], pages[-1]
    want_start = first if start_page is None else start_page
    want_end = last if end_page is None else end_page
    if not first <= want_start <= last:
        return _err(
            f"Page {want_start} is outside this document (pages {first}–{last}).",
            hint=f"Ask for a page between {first} and {last}.",
        )
    if want_end < want_start:
        return _err(
            f"end_page {want_end} is before start_page {want_start}.",
            hint="Give the first page to read as start_page and the last as end_page.",
        )
    want_end = min(want_end, last)

    begin = next(o for o, p, _a in positions if p >= want_start)
    stop = next((o for o, p, _a in positions if p > want_end), len(raw))
    mid_page_stop = None
    if stop - begin > max_chars:
        # Whole pages when they fit; a single page longer than the cap is cut
        # mid-page, and the read says where to pick up.
        boundary = max((o for o, _p, _a in positions if begin < o <= begin + max_chars), default=None)
        if boundary is not None:
            stop = boundary
        else:
            stop = mid_page_stop = begin + max_chars

    in_read = [(o, p, a) for o, p, a in positions if begin <= o < stop]
    text = annotate_pages(
        raw[begin:stop],
        [{"kind": "page", "value": p, "char_offset": o - begin, "approximate": a} for o, p, a in in_read],
    )
    read_first, read_last = in_read[0][1], in_read[-1][1]
    next_page = None
    if mid_page_stop is None:
        next_page = next((p for o, p, _a in positions if o >= stop), None)
        if next_page is not None and next_page > want_end:
            next_page = None if end_page is not None else next_page
    result = {
        "text": text,
        "page_count": last,
        "start_page": read_first,
        "end_page": read_last,
        "pages_returned": f"{read_first}–{read_last}" if read_first != read_last else str(read_first),
        "next_page": next_page,
        "total_chars": len(raw),
        "complete": begin == 0 and stop == len(raw),
    }
    if mid_page_stop is not None:
        result["page_cut_mid"] = True
        result["next_start_char"] = mid_page_stop
    return result


async def get_document_text(
    context: RunContext[AgenticChatDeps],
    document_uuid: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    start_char: Optional[int] = None,
) -> dict:
    """Read a document's text, a page range at a time. Useful for reading before extracting.

    One call returns at most about 30,000 characters (roughly 20-25 pages),
    ending at a page boundary. With no range it starts at page 1. The result
    says which pages it holds (``pages_returned``) and, when there is more,
    ``next_page``: call again with ``start_page=next_page`` to keep reading.
    For a long solicitation or award, read the pages that matter (budget,
    eligibility, required attachments, terms) before answering, and never
    describe pages you have not read.

    Args:
        context: The call context.
        document_uuid: UUID of the document to read.
        start_page: First page to read (1-based). Omit to start at page 1.
        end_page: Last page to read. Omit to read as far as one call allows.
        start_char: For documents without page numbers only: character offset
            to start from (use ``next_start_char`` from the previous read).
    """
    doc = await SmartDocument.find_one(SmartDocument.uuid == document_uuid)
    if not doc:
        return _err(
            f"Document '{document_uuid}' not found.",
            hint=(
                "Find the right document with search_documents (by title) or "
                "list_documents, then retry with the exact uuid returned."
            ),
        )

    # Authorization: must belong to user's team or the user directly
    team_id = context.deps.team_id
    if team_id:
        if doc.team_id != team_id and doc.user_id != context.deps.user_id:
            return {"error": "You do not have access to this document."}
    else:
        if doc.user_id != context.deps.user_id:
            return {"error": "You do not have access to this document."}

    # Same page treatment as the attach path: [p. N] boundaries from the
    # stored markers so an answer built on this tool has a page-citable
    # substrate, and a note on how to cite (with the approximate-page hedge
    # preserved). Local import — chat_service imports this module.
    from app.services.chat_service import page_note_for

    raw = doc.raw_text or ""
    markers = getattr(doc, "text_markers", None)
    read = read_document_range(
        raw, markers, start_page=start_page, end_page=end_page, start_char=start_char,
    )
    if "error" in read:
        return read
    result = {
        "uuid": doc.uuid,
        "title": doc.title,
        "extension": doc.extension,
        "pages": doc.num_pages,
        **read,
        "truncated": not read["complete"],
    }
    citation_note = page_note_for(markers, annotated="page_count" in read)
    if citation_note:
        result["page_citation_note"] = citation_note.strip()
    if not read["complete"]:
        if "page_count" in read:
            where = f"pp. {read['pages_returned']} of {read['page_count']}"
            more = (
                f" To keep reading, call get_document_text again with start_page={read['next_page']}."
                if read.get("next_page") else
                f" The rest of page {read['end_page']} starts at start_char={read['next_start_char']}."
                if read.get("next_start_char") else ""
            )
        else:
            where = f"characters {read['start_char']}–{read['end_char']} of {read['total_chars']}"
            more = (
                f" To keep reading, call again with start_char={read['next_start_char']}."
                if read.get("next_start_char") else ""
            )
        result["note"] = (
            f"This read covers {where}, not the whole document.{more} Say which "
            "pages your answer is based on, and do not present conclusions as "
            "covering pages you have not read."
        )
    return result


async def run_extraction(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
    document_uuids: list[str],
) -> dict:
    """Run an extraction template against one or more documents. Returns extracted entities with quality metadata.

    Maximum 10 documents per call. Results are capped at 50 entities.
    If you need to process more documents, call this tool multiple times.

    <example>
    User: "Pull the budget fields out of this proposal."
    → run_extraction with the budget template.
    <reasoning>Direct field extraction: one template's fields, once. No saved
    multi-step process, no rule judgment, no accuracy measurement.</reasoning>
    </example>
    <example>
    User: "Is this proposal compliant with our budget rules?"
    → check_compliance, NOT run_extraction.
    <reasoning>They asked for a pass/fail judgment against rules; extraction
    alone would dump fields and leave the judging to prose.</reasoning>
    </example>

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template to run.
        document_uuids: List of document UUIDs to extract from (max 10).
    """
    # Default to the documents open in the chat when the model omits them.
    document_uuids = _resolve_doc_uuids(context, document_uuids)
    if not document_uuids:
        return {"error": "Give me at least one document to extract from."}

    # Load the search set
    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return _err(
            f"Extraction set '{extraction_set_uuid}' not found.",
            hint=(
                "Call list_extraction_sets or search_library to find the "
                "template, then retry with the uuid it returns."
            ),
        )

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
    doc_metadata: list[dict] = []
    docs_unreadable: list[str] = []
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
            doc_metadata.append({
                "uuid": doc_uuid,
                "title": doc.title or doc_uuid,
                "text_markers": doc.text_markers or [],
            })
        else:
            # Accessible but has no text — a failed or unfinished ingest, not
            # an authorization miss. Reported separately below so the model
            # can't summarize a partially-failed run as complete.
            status = getattr(doc, "task_status", None)
            label = doc.title or doc_uuid
            if status == "error":
                docs_unreadable.append(f"{label} (text extraction FAILED)")
            else:
                docs_unreadable.append(f"{label} (still processing)")

    if not doc_texts:
        return _err(
            "No accessible documents with text content found.",
            hint=(
                "The documents may still be processing or belong to another "
                "team. Use search_documents to locate them, and check the "
                "document status before retrying."
            ),
        )

    # Run extraction synchronously in a thread
    sys_cfg = context.deps.system_config_doc

    def _run():
        engine = ExtractionEngine(system_config_doc=sys_cfg, domain=ss.domain)
        results = engine.extract(
            extract_keys=keys,
            doc_texts=doc_texts,
            extraction_config_override=ss.extraction_config or None,
            field_metadata=field_metadata,
            # Per-field source tracking, same as the interactive run-sync
            # endpoint — chat-dispatched runs must not ship untraced values.
            capture_sources=True,
            doc_metadata=doc_metadata,
        )
        return results, engine.tokens_in, engine.tokens_out

    from app.services.extraction_engine import ExtractionError

    try:
        results, tokens_in, tokens_out = await asyncio.wait_for(
            asyncio.to_thread(_run), timeout=120,
        )
    except asyncio.TimeoutError:
        return {"error": "Extraction timed out after 2 minutes. Try with fewer documents or a smaller extraction set."}
    except ExtractionError as e:
        # The engine raises on provider/parse failure (never returns silent
        # empties); translate to the tool-error envelope so the agent loop
        # survives and the model reports a FAILED run — not an empty one.
        return _err(
            f"Extraction FAILED — the model call did not complete: {e}",
            hint=(
                "This was an infrastructure/model failure, not an empty "
                "document. Tell the user the run failed and suggest retrying; "
                "do not describe any field as 'not found'."
            ),
        )

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
    docs_skipped = docs_requested - len(doc_names) - len(docs_unreadable)

    # Split the per-field source sidecar out of each entity (same shape as the
    # interactive run-sync endpoint): `sources` stays index-aligned with
    # `entities`. Quotes are previewed, not full — the page + verified flag is
    # the trust signal; the full passage is one click away in the editor.
    from app.services.extraction_sources import SOURCE_KEY

    entities = results[:50]  # Cap output size
    sources: list[dict] = []
    fields_verified = 0
    fields_unsourced = 0
    for entity in entities:
        entity_sources: dict = {}
        raw_sidecar = entity.pop(SOURCE_KEY, None) if isinstance(entity, dict) else None
        if isinstance(entity, dict):
            for field_key, value in entity.items():
                src = (raw_sidecar or {}).get(field_key)
                if isinstance(src, dict) and src.get("quote"):
                    entity_sources[field_key] = {
                        "quote": (src.get("quote") or "")[:200],
                        "page": src.get("page"),
                        "page_approximate": src.get("page_approximate", False),
                        "document_uuid": src.get("document_uuid"),
                        "document_title": src.get("document_title"),
                        "verified": bool(src.get("verified")),
                    }
                # Only extracted values need a source; a null/absent value
                # has nothing to trace.
                if value in (None, ""):
                    continue
                if isinstance(src, dict) and src.get("verified"):
                    fields_verified += 1
                else:
                    fields_unsourced += 1
        sources.append(entity_sources)

    response: dict = {
        "extraction_set": ss.title,
        "fields": keys,
        "documents": doc_names,
        "entities": entities,
        "entity_count": len(results),
        "sources": sources,
        "source_coverage": {
            "fields_with_verified_source": fields_verified,
            "fields_without_verified_source": fields_unsourced,
        },
        "token_usage": {"input": tokens_in, "output": tokens_out},
    }
    if fields_unsourced:
        response["source_note"] = (
            f"{fields_unsourced} extracted value(s) have no verified source "
            "passage. Treat those values as unconfirmed — when you present "
            "them, say they could not be traced to the document."
        )
    notes: list[str] = []
    if docs_unreadable:
        notes.append(
            f"{len(docs_unreadable)} document(s) were NOT extracted because "
            f"their text is unavailable: {'; '.join(docs_unreadable)}. Do not "
            "present this run as covering those documents."
        )
    if docs_skipped > 0:
        notes.append(f"{docs_skipped} of {docs_requested} document(s) were skipped (not found or not accessible).")
    if len(results) > 50:
        notes.append(f"Results truncated to 50 of {len(results)} entities.")
    if notes:
        response["note"] = " ".join(notes)

    # Quality sidecar — streaming layer strips "quality" key before LLM sees it
    if latest_run and latest_run.score is not None:
        # Check for active alerts on this extraction set
        alerts = await QualityAlert.find(
            QualityAlert.item_kind == "search_set",
            QualityAlert.item_id == extraction_set_uuid,
            QualityAlert.acknowledged != True,  # noqa: E712
        ).sort("-created_at").limit(3).to_list()

        # A badge for a configuration that no longer exists is worse than no
        # badge — check whether the set drifted since this run was measured.
        stale, stale_reasons = await _extraction_set_staleness(
            ss, latest_run, current_keys=set(keys),
        )
        if stale:
            # Model-visible (not stripped): the agent must caveat the score.
            response["validation_stale"] = True
            response["note_validation_stale"] = (
                "The extraction set changed after its last validation run "
                f"({'; '.join(stale_reasons)}). Its quality score describes "
                "the previous configuration — present it as outdated and "
                "recommend re-validating."
            )

        response["quality"] = {
            "score": latest_run.score,
            "tier": _score_to_tier(latest_run.score),
            "grade": latest_run.grade,
            "accuracy": latest_run.accuracy,
            "consistency": latest_run.consistency,
            "last_validated_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
            "num_test_cases": latest_run.num_test_cases,
            "num_runs": latest_run.num_runs,
            "stale": stale,
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

    <example>
    User: "Do the numbers add up in this subaward budget?"
    → check_compliance
    <reasoning>Sum checks are cross-field rules — this tool extracts, then
    evaluates each rule and reports pass/fail with reasons.</reasoning>
    </example>
    <example>
    User: "Validate the budget template."
    → run_validation, NOT check_compliance.
    <reasoning>"Validate" plus a TEMPLATE means measuring the template's
    accuracy against verified test cases, not judging one document.</reasoning>
    </example>

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template whose rules to apply.
        document_uuids: Document UUIDs to check (max 10).
    """
    # Default to the documents open in the chat when the model omits them.
    document_uuids = _resolve_doc_uuids(context, document_uuids)
    if not document_uuids:
        return {"error": "Give me at least one document to check."}

    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return _err(
            f"Extraction set '{extraction_set_uuid}' not found.",
            hint=(
                "Call list_extraction_sets or search_library to find the "
                "template, then retry with the uuid it returns."
            ),
        )

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
        return _err(
            f"Knowledge base '{kb_uuid}' not found.",
            hint=(
                "Call list_knowledge_bases and retry with one of the "
                "returned kb uuids."
            ),
        )

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
        return _err(
            f"Knowledge base '{kb_uuid}' not found.",
            hint=(
                "Call list_knowledge_bases and retry with one of the "
                "returned kb uuids."
            ),
        )

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

    <example>
    User: "Run the proposal-intake workflow on these three files."
    → run_workflow (preview → confirm), then get_workflow_status.
    <reasoning>An existing saved workflow, named by the user.</reasoning>
    </example>
    <example>
    User: "Every proposal, I extract the budget then check it against policy —
    can you do that here?"
    → create_workflow, NOT run_workflow.
    <reasoning>They described a repeatable multi-step process that doesn't
    exist yet; build it (preview → confirm), then offer to run it.</reasoning>
    </example>

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
    # Fall back to the documents already open in the chat when the model omits
    # them ("run the workflow on it"). Text-input workflows pass text instead,
    # so only default when no text was given.
    document_uuids = _resolve_doc_uuids(context, document_uuids) if not (text_input or "").strip() else list(document_uuids or [])
    text = (text_input or "").strip()

    # Look up workflow and verify access
    wf = await Workflow.get(workflow_id)
    if not wf:
        return _err(
            f"Workflow '{workflow_id}' not found.",
            hint=(
                "Call list_workflows or search_library to find the workflow, "
                "then retry with the uuid it returns."
            ),
        )

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


async def _workflow_quality_sidecar(workflow_id: str, user) -> Optional[dict]:
    """Quality sidecar for a completed workflow run, from the workflow's own
    latest ValidationRun — QUALITY_SIGNALS_EXPLAINED.md promises signals on
    workflow results. Same contract as run_extraction's sidecar: the streaming
    layer strips the "quality" key before the model sees it.
    """
    latest = await ValidationRun.find(
        ValidationRun.item_kind == "workflow",
        ValidationRun.item_id == workflow_id,
    ).sort("-created_at").first_or_none()
    if not latest or latest.score is None:
        return None
    alerts = await QualityAlert.find(
        QualityAlert.item_kind == "workflow",
        QualityAlert.item_id == workflow_id,
        QualityAlert.acknowledged != True,  # noqa: E712
    ).sort("-created_at").limit(3).to_list()
    sidecar: dict = {
        "score": latest.score,
        "tier": _score_to_tier(latest.score),
        "grade": latest.grade,
        "accuracy": latest.accuracy,
        "consistency": latest.consistency,
        "last_validated_at": latest.created_at.isoformat() if latest.created_at else None,
        "num_test_cases": latest.num_test_cases,
        "num_runs": latest.num_runs,
        "active_alerts": [
            {"type": a.alert_type, "severity": a.severity, "message": a.message}
            for a in alerts
        ],
    }
    try:
        from app.services import workflow_service

        plan_info = await workflow_service.get_validation_plan(workflow_id, user)
        sidecar["plan_stale"] = bool(plan_info.get("plan_stale", False))
    except Exception:
        # A score without the staleness flag is still a real score.
        pass
    return sidecar


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
        return _err(
            f"Workflow session '{session_id}' not found.",
            hint=(
                "The session_id must come from a run_workflow result in this "
                "conversation — check the earlier result, or run the workflow "
                "again."
            ),
        )

    done, total = status["num_steps_completed"], status["num_steps_total"]
    result: dict = {
        "status": status["status"],
        "steps_completed": done,
        "steps_total": total,
        "progress": f"{done} of {total} steps completed",
        "current_step": status.get("current_step_name"),
    }

    if status["status"] == "completed" and status.get("workflow_id"):
        try:
            quality = await _workflow_quality_sidecar(
                status["workflow_id"], context.deps.user,
            )
            if quality:
                result["quality"] = quality
        except Exception:
            logger.exception("Workflow quality sidecar failed for %s", session_id)

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
    elif status["status"] in _AWAITING_APPROVAL_STATUSES:
        step = status.get("current_step_name") or "approval"
        result["awaiting_approval"] = True
        result["approval_request_id"] = status.get("approval_request_id")
        result["message"] = (
            f'The run is NOT running: it is stopped at the "{step}" step, '
            "waiting for a person to approve or reject it, and will not "
            "continue until someone does. Tell the user approval is needed. "
            "If they ask you to approve or reject it, call approve_workflow_step "
            f'or reject_workflow_step with session_id="{session_id}". Never ask '
            "the user for an approval ID — they can't see one."
        )
    elif status["status"] not in ("completed", "canceled", "error"):
        result["message"] = (
            f"Still running ({done} of {total} steps completed). You can't "
            "notify the user when it finishes — never promise to. Tell them "
            "the run card in this chat updates live, or to ask again."
        )

    if status.get("current_step_preview"):
        result["preview"] = status["current_step_preview"]

    return result


# A run parked at an approval gate. The engine writes "pending_approval";
# "paused" is kept for runs recorded before that name.
_AWAITING_APPROVAL_STATUSES = ("pending_approval", "paused")


async def _find_pending_approval(
    context: RunContext[AgenticChatDeps], approval_request_id: str, session_id: str,
):
    """The ApprovalRequest to decide, by its id or by the waiting run's session.

    Returns ``(approval, None)`` or ``(None, error_dict)``. The user never sees
    an approval id in the app, so the run's session_id (from run_workflow) is
    the usual way in.
    """
    from app.models.approval import ApprovalRequest

    if not approval_request_id and session_id:
        from app.services import workflow_service

        status = await workflow_service.get_workflow_status(
            session_id, user=context.deps.user,
        )
        if not status:
            return None, _err(
                f"Workflow session '{session_id}' not found.",
                hint="Use the session_id from this conversation's run_workflow result.",
            )
        if status["status"] not in _AWAITING_APPROVAL_STATUSES or not status.get("approval_request_id"):
            return None, {
                "error": (
                    f"This run isn't waiting for approval — its status is "
                    f"'{status['status']}'."
                )
            }
        approval_request_id = status["approval_request_id"]
    if not approval_request_id:
        return None, _err(
            "Name the run to decide.",
            hint=(
                "Pass session_id from this conversation's run_workflow result. "
                "Don't ask the user for an approval ID."
            ),
        )
    approval = await ApprovalRequest.find_one(
        ApprovalRequest.uuid == approval_request_id
    )
    if not approval:
        return None, _err(
            f"Approval request '{approval_request_id}' not found.",
            hint=(
                "Retry with session_id set to the run's session_id from "
                "run_workflow instead of an approval id."
            ),
        )
    return approval, None


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
    approval_request_id: str = "",
    comments: str = "",
    confirmed: bool = False,
    session_id: str = "",
) -> dict:
    """Approve a workflow run that is waiting at an approval step, resuming it.

    Use this when the user says "approve it" about a run waiting for approval.
    Pass the run's ``session_id`` from run_workflow — the tool finds the
    pending approval itself. (An ``approval_request_id`` from
    get_workflow_status also works.) Never ask the user for an approval ID;
    the app doesn't show one. Call first with confirmed=false to preview,
    then confirmed=true after the user approves. Only an assigned reviewer or
    a workflow manager can approve.

    Args:
        context: The call context.
        approval_request_id: Optional approval request UUID from get_workflow_status.
        comments: Optional reviewer note recorded with the decision.
        confirmed: Must be true to actually approve. If false, returns a preview.
        session_id: The waiting run's session_id from run_workflow.
    """
    from app.models.approval import STATUS_APPROVED, STATUS_PENDING

    approval, error = await _find_pending_approval(context, approval_request_id, session_id)
    if error:
        return error
    approval_request_id = approval.uuid
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
    from app.services.approval_service import update_pending_approval
    if not await update_pending_approval(approval, {
        "status": STATUS_APPROVED, "reviewer_user_id": context.deps.user_id,
        "reviewer_comments": comments or "", "decision_at": now,
    }):
        return {"error": "Review changed, was already decided, or its deadline passed. Reopen the review before continuing."}

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
                "resumed automatically. Open Reviews to inspect the recorded decision and ask the workflow owner to check the failed dispatch."
            )
        }

    return {
        "status": "approved",
        "step": approval.step_name,
        "message": "Approved. The workflow is resuming from where it paused.",
    }


async def reject_workflow_step(
    context: RunContext[AgenticChatDeps],
    approval_request_id: str = "",
    comments: str = "",
    confirmed: bool = False,
    session_id: str = "",
) -> dict:
    """Reject a workflow run that is waiting at an approval step, failing it.

    Pass the run's ``session_id`` from run_workflow (or an
    ``approval_request_id`` from get_workflow_status); never ask the user for
    an approval ID. Call first with
    confirmed=false to preview, then confirmed=true after the user approves.
    Only an assigned reviewer or a workflow manager can reject. Rejecting marks
    the workflow run as failed — it does not resume.

    Args:
        context: The call context.
        approval_request_id: Optional approval request UUID from get_workflow_status.
        comments: Optional reason recorded with the rejection.
        confirmed: Must be true to actually reject. If false, returns a preview.
        session_id: The waiting run's session_id from run_workflow.
    """
    from app.models.approval import STATUS_PENDING, STATUS_REJECTED

    approval, error = await _find_pending_approval(context, approval_request_id, session_id)
    if error:
        return error
    approval_request_id = approval.uuid
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
    from app.services.approval_service import update_pending_approval
    if not await update_pending_approval(approval, {
        "status": STATUS_REJECTED, "reviewer_user_id": context.deps.user_id,
        "reviewer_comments": comments or "", "decision_at": now,
    }):
        return {"error": "Review changed, was already decided, or its deadline passed. Reopen the review before continuing."}

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
        return _err(
            f"Extraction set '{extraction_set_uuid}' not found.",
            hint=(
                "Call list_extraction_sets or search_library to find the "
                "template, then retry with the uuid it returns."
            ),
        )

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
        return _err(
            f"Extraction set '{extraction_set_uuid}' not found.",
            hint=(
                "Call list_extraction_sets or search_library to find the "
                "template, then retry with the uuid it returns."
            ),
        )

    user_id = context.deps.user_id
    team_id = context.deps.team_id
    if not ss.verified and ss.user_id != user_id:
        if not (team_id and ss.team_id == team_id):
            return {"error": "You do not have access to this extraction set."}

    doc = await SmartDocument.find_one(SmartDocument.uuid == document_uuid)
    if not doc:
        return _err(
            f"Document '{document_uuid}' not found.",
            hint=(
                "Find the right document with search_documents (by title) or "
                "list_documents, then retry with the exact uuid returned."
            ),
        )
    if team_id:
        if doc.team_id != team_id and doc.user_id != user_id:
            return {"error": "You do not have access to this document."}
    else:
        if doc.user_id != user_id:
            return {"error": "You do not have access to this document."}
    if not doc.raw_text:
        return _doc_text_unavailable_err(doc)

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
    doc_metadata = [{
        "uuid": document_uuid,
        "title": doc.title or document_uuid,
        "text_markers": doc.text_markers or [],
    }]

    def _run():
        engine = ExtractionEngine(system_config_doc=sys_cfg, domain=ss.domain)
        return engine.extract(
            extract_keys=keys,
            doc_texts=[doc.raw_text],
            extraction_config_override=ss.extraction_config or None,
            field_metadata=field_metadata,
            # These values seed the human-verification flow that produces
            # ground-truth test cases — of all places, they must be traced.
            capture_sources=True,
            doc_metadata=doc_metadata,
        )

    from app.services.extraction_engine import ExtractionError

    try:
        results = await asyncio.wait_for(asyncio.to_thread(_run), timeout=120)
    except asyncio.TimeoutError:
        return {"error": "Extraction timed out. Try a smaller extraction set."}
    except ExtractionError as e:
        return _err(
            f"Extraction FAILED — the model call did not complete: {e}",
            hint=(
                "Do not open a verification session from a failed run. Tell "
                "the user the extraction failed and suggest retrying."
            ),
        )

    from app.services.extraction_sources import SOURCE_KEY

    flat: dict = {}
    flat_sources: dict = {}
    if results and isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                sidecar = item.pop(SOURCE_KEY, None)
                if isinstance(sidecar, dict):
                    flat_sources.update(sidecar)
                flat.update(item)

    def _field_for(k: str) -> VerificationField:
        src = flat_sources.get(k)
        src = src if isinstance(src, dict) else {}
        page = src.get("page")
        return VerificationField(
            key=k,
            extracted=str(flat.get(k)) if flat.get(k) is not None else "",
            status="pending",
            source_quote=(src.get("quote") or None),
            source_page=page if isinstance(page, int) else None,
            source_page_approximate=bool(src.get("page_approximate")),
            source_verified=bool(src.get("verified")) if src.get("quote") else None,
        )

    fields = [_field_for(k) for k in keys]

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
            {
                "key": f.key,
                "extracted": f.extracted,
                "status": f.status,
                "source_page": f.source_page,
                "source_verified": f.source_verified,
            }
            for f in fields
        ],
        "field_count": len(fields),
        "unverified_source_count": sum(
            1 for f in fields if f.extracted and not f.source_verified
        ),
        "message": (
            f"Opened a verification session for '{doc.title}'. "
            "Review each extracted value in the document viewer and approve or correct it. "
            "The test case will be saved only after you finish verifying. "
            "Values without a verified source passage could not be traced to "
            "the document — point those out as needing the closest review."
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

    Call first with confirmed=false to preview: the preview runs field
    discovery and shows the exact name and fields that will be created. Then
    call again with the SAME arguments and confirmed=true after the user
    approves — that creates exactly what the preview showed.

    Args:
        context: The call context.
        document_uuids: Document(s) to analyze. Max 5 documents per call.
        title: Optional name for the new extraction set. When omitted, the
            name is suggested from the documents' content during the preview.
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
        return _err(
            "No accessible documents found.",
            hint=(
                "Use search_documents or list_documents to find documents "
                "you can access, then retry with those uuids."
            ),
        )

    # Split out docs with no text and say WHY (permanent failure vs still
    # processing) — silently dropping them lets the model present an analysis
    # of 3 documents as covering 5.
    unreadable = [d for d in docs if not d.raw_text]
    docs = [d for d in docs if d.raw_text]
    if not docs:
        if len(unreadable) == 1:
            return _doc_text_unavailable_err(unreadable[0])
        failed = [d.title or d.uuid for d in unreadable if getattr(d, "task_status", None) == "error"]
        if failed:
            return _err(
                "None of the documents are readable. Text extraction FAILED "
                f"permanently for: {', '.join(failed)}. The rest are still processing.",
                hint=(
                    "Failed documents will not recover by retrying — suggest "
                    "re-uploading them. Retry later only for the ones still processing."
                ),
            )
        return {"error": "Documents have no extracted text yet. Try again once processing completes."}
    unreadable_note: Optional[str] = None
    if unreadable:
        parts = [
            f'"{d.title or d.uuid}" ({"text extraction FAILED" if getattr(d, "task_status", None) == "error" else "still processing"})'
            for d in unreadable
        ]
        unreadable_note = (
            f"{len(unreadable)} document(s) will NOT be analyzed: "
            f"{', '.join(parts)}. Tell the user which documents are excluded."
        )

    from app.services import search_set_service as svc

    # Discover the fields and the content-aware name BEFORE the approval card,
    # so the card shows the name and fields that will actually be created. The
    # proposal is stashed with the arming and reused on approval — re-running
    # discovery afterwards is non-deterministic and could create a set under a
    # name the user never saw.
    # If the user is inside a project they can manage, the new extraction is
    # auto-pinned there so it shows up alongside the project's other tools.
    # Resolved before the gate and part of its key: the project was otherwise
    # looked up again on the approval turn, so a project opened after the card
    # was shown got the pin though the card never named it (support ticket). A
    # different project now re-arms with a card that names it.
    from app.services import project_service

    active_project = await _resolve_active_project(context) if pin_to_active_project else None
    if active_project and not await project_service.can_manage_project(
        active_project, context.deps.user
    ):
        active_project = None  # viewer — don't pin

    gate_key = {
        "docs": sorted(d.uuid for d in docs),
        "title": title,
        "project": active_project.uuid if active_project else None,
    }
    proposal = _armed_stash(context, "create_extraction_from_document", gate_key)
    if proposal is None:
        try:
            fields, suggested_title = await svc.suggest_fields_from_documents(
                [d.uuid for d in docs], user_id, context.deps.model_name or None,
            )
        except RuntimeError as e:
            return {"error": f"Field discovery failed: {e}"}
        proposal = {
            "title": title or suggested_title or f"Extraction from {docs[0].title or doc_uuids[0]}",
            "fields": list(fields),
        }
    default_title = proposal["title"]
    proposed_fields: list[str] = list(proposal.get("fields") or [])

    doc_names = ", ".join(f'"{d.title}"' for d in docs[:3])
    if len(docs) > 3:
        doc_names += f" + {len(docs) - 3} more"
    if proposed_fields:
        shown = ", ".join(f'"{f}"' for f in proposed_fields[:5])
        if len(proposed_fields) > 5:
            shown += f" + {len(proposed_fields) - 5} more"
        fields_text = f"with {len(proposed_fields)} proposed field(s): {shown}."
    else:
        fields_text = "with no fields — no clear fields were found; you can add them manually."
    preview_text = f'Create a new extraction set "{default_title}" from {doc_names} {fields_text}'
    if active_project:
        preview_text += f' It will also be pinned to project "{active_project.title}".'
    if unreadable_note:
        preview_text += f" Note: {unreadable_note}"
    preview_payload = {
        "action": "create_extraction_from_document",
        "preview": preview_text,
        "needs_confirmation": True,
        "document_count": len(docs),
        "default_title": default_title,
        "proposed_fields": proposed_fields,
        "field_count": len(proposed_fields),
    }
    if unreadable_note:
        preview_payload["excluded_documents_note"] = unreadable_note
    gate = await _confirm_gate(
        context,
        tool_name="create_extraction_from_document",
        key=gate_key,
        preview=preview_payload,
        confirmed=confirmed,
        stash=proposal,
    )
    if gate is not None:
        return gate

    ss = await svc.create_search_set(
        title=default_title,
        user_id=user_id,
        set_type="extraction",
        team_id=team_id,
    )
    if domain:
        ss.domain = domain
        await ss.save()

    discovered_fields = await svc.add_fields(ss.uuid, proposed_fields, user_id)

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
    result = {
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
    if unreadable_note:
        result["excluded_documents_note"] = unreadable_note
    return result


async def run_validation(
    context: RunContext[AgenticChatDeps],
    extraction_set_uuid: str,
    num_runs: int = 3,
    test_case_uuids: Optional[list[str]] = None,
    model: Optional[str] = None,
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

    <example>
    User: "How accurate is the NSF budget template?"
    → run_validation (if test cases exist; otherwise propose_test_case first).
    <reasoning>Accuracy of a TEMPLATE is measured against verified test cases —
    exactly what validation does.</reasoning>
    </example>
    <example>
    User: "How well does the local Llama model do on this template?"
    → run_validation with model set to that model's configured name.
    <reasoning>An explicit model request runs the validation under that model
    and labels the run with it — afterwards get_quality_info's
    model_comparison can answer which model does best here.</reasoning>
    </example>
    <example>
    User: "Check whether this contract meets our requirements."
    → check_compliance, NOT run_validation.
    <reasoning>Judging one DOCUMENT against rules is compliance; validation
    measures the template itself and needs ground-truth test cases.</reasoning>
    </example>

    Args:
        context: The call context.
        extraction_set_uuid: UUID of the extraction template to validate.
        num_runs: How many times to run extraction per test case (3+ recommended for consistency measurement). Default 3.
        test_case_uuids: Optional — validate only these test cases. If omitted, validates all.
        model: Optional — validate under this specific configured model (name or tag). Only pass when the user asked to measure a particular model; otherwise the template's own configuration decides.
        confirmed: Must be true to execute. If false, returns a preview.
    """
    from app.services import extraction_validation_service as val_svc

    ss = await SearchSet.find_one(SearchSet.uuid == extraction_set_uuid)
    if not ss:
        return _err(
            f"Extraction set '{extraction_set_uuid}' not found.",
            hint=(
                "Call list_extraction_sets or search_library to find the "
                "template, then retry with the uuid it returns."
            ),
        )

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

    # Resolve an explicitly requested model against the configured list before
    # burning any LLM calls — an unknown name would otherwise fail mid-run.
    requested_model: Optional[str] = None
    if model:
        from app.models.system_config import SystemConfig
        sys_cfg = await SystemConfig.get_config()
        available = (sys_cfg.available_models if sys_cfg else None) or []
        match = next(
            (m for m in available if m.get("name") == model or m.get("tag") == model),
            None,
        )
        if not match:
            names = [m.get("name") for m in available if m.get("name")]
            return _err(
                f"Model '{model}' is not configured on this deployment.",
                hint=f"Configured models: {', '.join(names) or 'none'}. Retry with one of these names.",
            )
        requested_model = match.get("name")

    model_note = f' under model "{requested_model}"' if requested_model else ""
    gate = await _confirm_gate(
        context,
        tool_name="run_validation",
        key={
            "extraction_set_uuid": extraction_set_uuid,
            "num_runs": num_runs,
            "test_case_uuids": sorted(test_case_uuids) if test_case_uuids else None,
            "model": requested_model,
        },
        preview={
            "action": "run_validation",
            "preview": (
                f"Validate \"{ss.title}\" with {effective_count} test case(s), "
                f"running extraction {num_runs} time(s) each{model_note}."
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
        # Only an explicit user request is passed as the model: the service
        # treats a passed model as a forced override of the template's own
        # configuration (including an optimizer-applied model), so the chat
        # session's model must not be smuggled in as one.
        result = await val_svc.run_validation(
            search_set_uuid=extraction_set_uuid,
            user_id=user_id,
            test_case_uuids=test_case_uuids,
            num_runs=num_runs,
            model=requested_model,
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
        # What was asked for, and what the run was actually labeled with —
        # None model means the template's own configuration decided.
        "model_requested": requested_model,
        "model": latest.model if latest else requested_model,
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
        return _err(
            f"Optimization run '{run_uuid}' not found.",
            hint=(
                "Call list_optimization_recommendations, or use the run uuid "
                "returned by start_optimization, then retry."
            ),
        )

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
        return _err(
            f"Optimization run '{run_uuid}' not found.",
            hint=(
                "Call list_optimization_recommendations, or use the run uuid "
                "returned by start_optimization, then retry."
            ),
        )

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
_SAVE_EXTENSIONS = {"md", "txt", "docx", "xlsx"}
_MAX_SAVE_SOURCES = 50
MAX_SAVE_CHARS = 1_000_000


async def _checked_save_sources(sources: list[dict], context) -> list[dict]:
    """Sources for a saved file, each quote checked against its document (#1008).

    A quote is only marked found when it appears in the named document's text,
    and only documents this user can open are read.
    """
    from app.services.export_provenance import check_quote

    rows: list[dict] = []
    texts: dict[str, Optional[str]] = {}
    for src in sources:
        if not isinstance(src, dict):
            continue
        doc_uuid = str(src.get("document_uuid") or "")
        if doc_uuid and doc_uuid not in texts:
            doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
            readable = doc is not None and (
                doc.user_id == context.deps.user_id
                or (context.deps.team_id and doc.team_id == context.deps.team_id)
            )
            texts[doc_uuid] = (doc.raw_text or "") if readable else None
        page = src.get("page")
        rows.append({
            "item": str(src.get("item") or ""),
            "document": str(src.get("document_title") or ""),
            "page": f"p. {page}" if isinstance(page, int) else str(page or ""),
            "quote": str(src.get("quote") or "").strip(),
            "status": check_quote(str(src.get("quote") or ""), texts.get(doc_uuid)) if doc_uuid else "not checked",
        })
    return rows


def _render_saved_file(ext: str, title: str, content: str, source_rows: list[dict]) -> bytes:
    """The bytes save_to_folder writes for *ext*, with a Sources section when given."""
    import io

    from app.services.export_provenance import SOURCE_HEADERS, append_sources_to_docx, sources_markdown

    if ext in ("md", "txt"):
        sources = sources_markdown(source_rows)
        return (f"{content.rstrip()}\n\n{sources}" if sources else content).encode("utf-8")
    if ext == "docx":
        from app.services.docx_service import markdown_to_docx

        buf = io.BytesIO()
        markdown_to_docx(content).save(buf)
        return append_sources_to_docx(buf.getvalue(), source_rows)
    # xlsx: the first Markdown table in content, plus a Sources sheet.
    from openpyxl import Workbook
    from openpyxl.styles import Font

    from app.services.docx_service import _split_md_table_row

    rows: list[list[str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = _split_md_table_row(stripped)
            if all(set(c.strip()) <= set("-: ") for c in cells):
                continue  # the |---|---| separator
            rows.append(cells)
        elif rows:
            break
    wb = Workbook()
    sheet = wb.active
    sheet.title = (re.sub(r"[\\/*?:\[\]]", " ", title.rsplit(".", 1)[0]).strip() or "Table")[:31]
    for row in rows:
        sheet.append(row)
    if rows:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
    if source_rows:
        src_sheet = wb.create_sheet("Sources")
        src_sheet.append(SOURCE_HEADERS)
        for cell in src_sheet[1]:
            cell.font = Font(bold=True)
        for r in source_rows:
            src_sheet.append([r["item"], r["document"], r["page"], r["quote"], r["status"]])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


async def save_to_folder(
    context: RunContext[AgenticChatDeps],
    title: str,
    content: str,
    folder_uuid: Optional[str] = None,
    extension: str = "md",
    sources: Optional[list[dict]] = None,
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

    When the user wants something to hand to someone (a memo to a PI, a
    checklist, a budget table for routing), save it as "docx" (a Word
    document) or, for a table, "xlsx" (a spreadsheet of the first Markdown
    table in ``content``), not as pasted Markdown. Pass the evidence it rests
    on in ``sources``: each quote is checked against the document it names and
    saved with the file as a Sources section (Word) or a Sources sheet
    (spreadsheet), so the reader can check it.

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
        extension: File type — "md" (default), "txt", "docx" (Word) or
            "xlsx" (spreadsheet; ``content`` must contain a Markdown table).
        sources: Optional evidence, up to 50 items, each
            ``{"document_uuid", "document_title", "page", "quote", "item"}``:
            the document and page a claim comes from and the exact quoted
            passage. ``item`` names what it supports (a field or a claim).
        confirmed: Must be true to actually save. If false, returns a preview
            for user confirmation.
    """
    import uuid as uuid_mod

    from werkzeug.utils import secure_filename

    user = context.deps.user
    user_id = context.deps.user_id

    ext = (extension or "md").lower().lstrip(".")
    if ext not in _SAVE_EXTENSIONS:
        return {"error": f"Unsupported extension '{ext}'. Use 'md', 'txt', 'docx' or 'xlsx'."}
    if sources is not None and (not isinstance(sources, list) or len(sources) > _MAX_SAVE_SOURCES):
        return {"error": f"sources must be a list of at most {_MAX_SAVE_SOURCES} items."}
    if ext == "xlsx":
        from app.services.docx_service import _split_md_table_row

        if not any(
            line.strip().startswith("|") and len(_split_md_table_row(line)) > 1
            for line in (content or "").splitlines()
        ):
            return _err(
                "A spreadsheet needs a Markdown table in content.",
                hint="Put the rows in a Markdown table (| Field | Value |), or save as docx instead.",
            )

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
            folder_uuid, user, team_access=context.deps.team_access, contribute=True,
        )
        if not folder:
            return _err(
                "Folder not found or you don't have access to it.",
                hint=(
                    "Call list_folders and retry with one of the returned "
                    "folder uuids."
                ),
            )
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

    try:
        source_rows = await _checked_save_sources(sources or [], context)
        payload = _render_saved_file(ext, display_title, content, source_rows)
    except Exception as e:
        logger.exception("save_to_folder: failed to build %s", relative_path)
        return {"error": f"Failed to build the {ext} file: {e}"}

    storage = get_storage()
    try:
        await storage.write(relative_path, payload)
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
        "sources": [{k: r[k] for k in ("item", "document", "page", "status")} for r in source_rows],
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
            return _err(
                "Folder not found or you don't have access to it.",
                hint=(
                    "Call list_folders and retry with one of the returned "
                    "folder uuids."
                ),
            )
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

    # Register the workflow in the user's personal library so it shows up in the
    # Library tab — mirrors what the modal "New workflow" flow does, and what
    # create_extraction_from_document already does for search sets. Without this
    # a chat-built workflow exists but never appears in the Library.
    try:
        from app.services.library_service import add_item, get_or_create_personal_library

        lib = await get_or_create_personal_library(context.deps.user_id)
        await add_item(str(lib.id), user, workflow_id, "workflow")
    except Exception:
        logger.exception("Failed to add workflow %s to personal library", workflow_id)

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
# Bulk document analysis via subagents (uplift plan Phase 9)
# ---------------------------------------------------------------------------

_ANALYZE_MAX_DOCS = 20


async def analyze_documents(
    context: RunContext[AgenticChatDeps],
    instruction: str,
    document_uuids: list[str],
) -> dict:
    """Analyze several documents in parallel WITHOUT loading their full text here. Returns one concise analysis per document.

    Each document is handed to its own read-only sub-analysis with your
    instruction; you receive back only the per-document digests (a few
    hundred words each). Use this for 3 or more documents — summaries,
    comparisons, per-document extractions in prose, screening a folder.
    For 1–2 documents, use get_document_text directly instead.

    Brief the sub-analysis like a colleague who just walked in: it sees ONLY
    one document and your instruction — no conversation history, no other
    documents. Include everything it needs: what to find, what to ignore,
    and the exact output shape you want (e.g. "list sponsor, total budget,
    and period of performance as three labeled lines").

    <example>
    User: "Summarize each of these 8 proposals and flag any with cost share."
    → analyze_documents(instruction="Summarize this proposal in ~5 bullets:
    sponsor, total request, period, aims. End with 'COST SHARE: yes/no' based
    on whether it commits cost sharing.", document_uuids=[…8 uuids…])
    <reasoning>8 full proposals would blow the conversation's context; the
    fan-out returns 8 digests, and the instruction carries the output shape
    since the sub-analysis can't see the user's ask.</reasoning>
    </example>
    <example>
    User: "What's the indirect rate in this budget?"
    → get_document_text, NOT analyze_documents.
    <reasoning>One document, one lookup — read it directly.</reasoning>
    </example>

    Args:
        context: The call context.
        instruction: Complete, self-contained analysis instruction, including
            the desired output shape.
        document_uuids: Documents to analyze (2–20; prefer get_document_text
            for a single document).
    """
    chat_cfg = (context.deps.system_config_doc or {}).get("chat_config") or {}
    if not chat_cfg.get("subagents_enabled", True):
        return _err(
            "Bulk analysis is disabled on this deployment.",
            hint="Read documents individually with get_document_text instead.",
        )

    instruction = (instruction or "").strip()
    if not instruction:
        return _err(
            "instruction is required.",
            hint=(
                "Write a self-contained instruction including the output "
                "shape — the sub-analysis sees only one document and this text."
            ),
        )

    document_uuids = _resolve_doc_uuids(context, document_uuids)
    if not document_uuids:
        return _err(
            "Give me at least one document to analyze.",
            hint="Find documents with search_documents or list_documents first.",
        )
    if len(document_uuids) > _ANALYZE_MAX_DOCS:
        return _err(
            f"Too many documents ({len(document_uuids)} > {_ANALYZE_MAX_DOCS}).",
            hint="Split the set into batches and call analyze_documents per batch.",
        )

    # Resolve + authorize up front; report unusable documents instead of
    # silently skipping them.
    team_id = context.deps.team_id
    user_id = context.deps.user_id
    ready: list[dict] = []
    skipped: list[dict] = []
    for doc_uuid in dict.fromkeys(document_uuids):  # de-dupe, keep order
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if not doc:
            skipped.append({"uuid": doc_uuid, "reason": "not found"})
            continue
        if team_id:
            allowed = doc.team_id == team_id or doc.user_id == user_id
        else:
            allowed = doc.user_id == user_id
        if not allowed:
            skipped.append({"uuid": doc_uuid, "reason": "no access"})
            continue
        if not (doc.raw_text or "").strip():
            skipped.append({
                "uuid": doc_uuid,
                "reason": (
                    "text extraction FAILED (permanent — re-upload needed)"
                    if getattr(doc, "task_status", None) == "error"
                    else "no text yet (still processing)"
                ),
            })
            continue
        ready.append({
            "uuid": doc.uuid,
            "title": doc.title or doc.uuid,
            "raw_text": doc.raw_text,
        })

    if not ready:
        return _err(
            "None of the requested documents are readable.",
            hint=(
                "Check the skipped reasons: documents may still be "
                "processing, or belong to another team."
            ),
        )

    from app.services.chat_subagents import fan_out_analyses

    results = await fan_out_analyses(
        documents=ready,
        instruction=instruction,
        model_name=context.deps.model_name,
        sys_config_doc=context.deps.system_config_doc,
    )
    failed = [r for r in results if "error" in r]
    return {
        "instruction": instruction,
        "analyzed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
        "skipped": skipped or None,
    }


# ---------------------------------------------------------------------------
# Plan / progress tracking (uplift plan Phase 8)
# ---------------------------------------------------------------------------

_PLAN_STATUSES = ("pending", "in_progress", "completed")
_PLAN_MAX_TASKS = 20


async def update_plan(
    context: RunContext[AgenticChatDeps],
    tasks: list[dict],
) -> dict:
    """Update the visible task checklist for multi-step work. Call with the FULL list every time.

    The user sees this as a live pinned checklist, so keeping it current is
    how they know what you're doing and what's left. Use it proactively when
    a request takes 3 or more distinct steps (batch extractions, build-then-
    validate flows, multi-document comparisons, workflow setup). Skip it for
    single, trivial actions — one search or one extraction needs no plan;
    just do it.

    Rules (strict):
    - Send the COMPLETE list each call, not a delta.
    - Exactly ONE task must be in_progress at a time — not less, not more —
      until everything is completed.
    - Mark a task completed IMMEDIATELY after finishing it; never batch
      completions.
    - NEVER mark a task completed if its tool call failed or was cancelled —
      keep it in_progress and surface the blocker to the user.
    - Every task needs both forms: content (imperative: "Run extraction on
      FY24 proposals") and active_form (present continuous: "Running
      extraction on FY24 proposals").

    <example>
    User: "Extract budgets from these 6 proposals, check them against the
    F&A rules, and save a summary to my Awards folder."
    → update_plan with three tasks, then work through them, updating after
    each completes.
    <reasoning>Three distinct operations the user will wait through —
    visible progress beats a silent multi-minute spinner.</reasoning>
    </example>
    <example>
    User: "What's the PI name on this proposal?"
    → Just run the extraction/lookup. No update_plan.
    <reasoning>Single trivial step; a checklist would be ceremony.</reasoning>
    </example>

    Args:
        context: The call context.
        tasks: Full task list. Each task: {"content": str (imperative),
            "active_form": str (present continuous),
            "status": "pending" | "in_progress" | "completed"}.
    """
    if not isinstance(tasks, list) or not tasks:
        return _err(
            "tasks must be a non-empty list.",
            hint="Send the full checklist: [{content, active_form, status}, …].",
        )
    if len(tasks) > _PLAN_MAX_TASKS:
        return _err(
            f"Too many tasks ({len(tasks)} > {_PLAN_MAX_TASKS}).",
            hint="Collapse related steps — the checklist is for the user, not a log.",
        )

    normalized: list[dict] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            return _err(f"Task {i} is not an object.")
        content = str(task.get("content", "")).strip()
        active_form = str(task.get("active_form", "")).strip()
        status = str(task.get("status", "")).strip()
        if not content or not active_form:
            return _err(
                f"Task {i} is missing content or active_form.",
                hint=(
                    "Both forms are required: content is imperative ('Run "
                    "extraction'), active_form is present continuous "
                    "('Running extraction')."
                ),
            )
        if status not in _PLAN_STATUSES:
            return _err(
                f"Task {i} has invalid status {status!r}.",
                hint="Status must be pending, in_progress, or completed.",
            )
        normalized.append(
            {"content": content, "active_form": active_form, "status": status}
        )

    in_progress = sum(1 for t in normalized if t["status"] == "in_progress")
    completed = sum(1 for t in normalized if t["status"] == "completed")
    all_done = completed == len(normalized)
    if not all_done and in_progress != 1:
        return _err(
            f"Exactly one task must be in_progress (got {in_progress}).",
            hint=(
                "Mark the task you are working on RIGHT NOW as in_progress "
                "and everything not yet started as pending. Zero in_progress "
                "is only valid when every task is completed."
            ),
        )

    context.deps.plan_state = normalized
    return {
        "ok": True,
        "task_count": len(normalized),
        "completed": completed,
        "all_done": all_done,
    }


# ---------------------------------------------------------------------------
# Phase 11 — Certification program (Vandal Workflow Architect)
#
# These wrap certification_service — the SAME service the certification panel
# calls — so progress, XP, and module completion earned in chat show up in the
# panel (and vice versa). Grading always runs the deterministic validators;
# the model narrates results, it never decides pass/fail.
# ---------------------------------------------------------------------------


@course_operation(tool=True)
@certification_result(ProgressResult)
async def get_certification_progress(
    context: RunContext[AgenticChatDeps],
) -> dict:
    """Get the user's Vandal Workflow Architect certification progress.

    Returns overall XP, level, per-module completion/stars, and the
    next incomplete module. Call this when the user says "start certification",
    "continue certification", asks how far along they are, or asks about XP,
    levels, or badges. Progress is shared with the Certification panel for
    the selected enrollment. Only its applicable assessed requirements earn
    credit; reading, drafting and practice do not become completion by chat.

    Args:
        context: The call context.
    """
    from app.services import certification_service as cert_svc

    prog = await cert_svc.get_progress_dict(context.deps.user_id)
    modules = []
    next_module_id = None
    for mid in cert_svc.course_module_order():
        data = prog["modules"].get(mid, {})
        completed = data.get("completed", False)
        if type(completed) is not bool:
            raise TypeError('Stored certification completion must be a boolean')
        if not completed and next_module_id is None:
            next_module_id = mid
        modules.append({
            "module_id": mid,
            "title": cert_svc.course_module_titles().get(mid, mid),
            "xp": cert_svc.course_module_xp()[mid],
            "completed": completed,
            "stars": data.get("stars", 0),
        })
    completed_count = sum(1 for m in modules if m["completed"])
    operation = cert_svc.current_operation()
    from app.services.certification_versions.progression_policy import public_progression_policy
    policy = public_progression_policy(operation.package) if operation else None
    return {
        **cert_svc.course_identity(),
        "total_xp": prog["total_xp"],
        "level": prog["level"],
        "certified": prog["certified"],
        "modules_completed": completed_count,
        "modules_total": len(modules),
        "next_module_id": next_module_id,
        "modules": modules,
        **({'progression_policy': policy} if policy is not None else {}),
        **({"learning_position": prog.get("learning_position"), "position_revision": prog.get("position_revision", 0), "pending_completions": prog.get("pending_completions", [])} if prog.get("enrollment_id") else {}),
    }


@course_operation(tool=True)
@certification_result(ModuleResult)
async def get_certification_module(
    context: RunContext[AgenticChatDeps],
    module_id: str,
) -> dict:
    """Get one certification module's exercise: overview, instructions, criteria.

    Use the returned assessment_mode and required_outcomes, never a module
    name, to choose its assessment path. Teach relevant lessons and respect
    the learner's saved position. Selected-outcome courses require the
    learner's saved evidence and decisions in the Certification panel; chat
    can explain and help author work but cannot choose or submit those
    assessment decisions for the learner. Legacy requirements remain pinned.
    The instructions field contains learner-visible steps. Follow separate
    agent_guidance for assistant-specific coaching and evidence boundaries.

    Args:
        context: The call context.
        module_id: One of the certification module ids (see
            get_certification_progress for the full ordered list).
    """
    from app.services import certification_service as cert_svc

    if module_id not in cert_svc.course_module_xp():
        return _err(
            f"Unknown module '{module_id}'.",
            hint=f"Valid module ids: {', '.join(cert_svc.course_module_order())}",
        )
    exercise = cert_svc.get_exercise(module_id) or {}
    lessons = cert_svc.get_lessons(module_id) or {}
    prog = await cert_svc.get_progress_dict(context.deps.user_id)
    data = prog["modules"].get(module_id, {})
    completed = data.get("completed", False)
    if type(completed) is not bool:
        raise TypeError('Stored certification completion must be a boolean')
    assessment = lessons.get("assessment") or {}
    assessment_keys = list(cert_svc.ASSESSMENT_KEYS.get(module_id, ()))
    assessment_questions = assessment.get("questions", [])
    assessment_mode = "legacy_reflection" if assessment_keys else "legacy_practical"
    required_outcomes = []
    selected_completion = False
    operation = cert_svc.current_operation()
    if operation and 'outcomes.json' in operation.package.manifest.artifacts:
        from app.services.certification_versions.outcomes import package_outcomes
        from app.services.certification_versions.grading import selected_outcome_completion_available
        contract = package_outcomes(operation.package)
        required = next(module for module in contract.modules if module.module_id == module_id)
        assessment_mode = "selected_saved_outcomes"
        assessment_keys, assessment_questions = [], []
        required_outcomes = [{'outcome_id': outcome.id, 'statement': outcome.statement,
                              'method': outcome.method} for outcome in required.outcomes]
        selected_completion = selected_outcome_completion_available(operation.package)
    return {
        **cert_svc.course_identity(),
        "module_id": module_id,
        "title": cert_svc.course_module_titles().get(module_id, module_id),
        "xp": cert_svc.course_module_xp()[module_id],
        "completed": completed,
        "stars": data.get("stars", 0),
        "overview": exercise.get("overview", ""),
        # New-course cards show the learner's procedure, not assistant directives.
        # Original courses retain their established chat-native wording.
        "instructions": (exercise.get("instructions", []) if assessment_mode == "selected_saved_outcomes"
                         else exercise.get("chat_instructions") or exercise.get("instructions", [])),
        "agent_guidance": exercise.get("chat_instructions", []) if assessment_mode == "selected_saved_outcomes" else [],
        "lesson_titles": [les["title"] for les in lessons.get("lessons", [])],
        "expected_fields": exercise.get("expected_fields", []),
        "star_criteria": exercise.get("star_criteria", {}),
        "sample_documents": exercise.get("documents", []),
        "provisioned_docs": data.get("provisioned_docs", []),
        # Old reflection keys must never redirect a competency enrollment
        # into the legacy participation route, even in a mixed package.
        "assessment_mode": assessment_mode,
        "required_outcomes": required_outcomes,
        "selected_outcome_completion": selected_completion,
        "assessment_keys": assessment_keys,
        "assessment_questions": assessment_questions,
    }


@course_operation(tool=True)
@certification_result(LessonResult)
async def get_certification_lesson(
    context: RunContext[AgenticChatDeps],
    module_id: str,
    lesson_number: int | None = None,
    lesson_id: str | None = None,
    enrollment_id: str | None = None,
) -> dict:
    """Get one lesson of a certification module — the same content the panel teaches.

    Each module's challenge assumes the user has been taught its lessons, so
    walk through them one at a time before the exercise or self-assessment.
    The lesson content renders as a card the user reads directly — don't
    repeat it verbatim. Knowledge checks render as interactive practice in the
    card; invite the learner to try them and ask for help if needed. Do not
    duplicate the question or claim to have seen their local answer. Practice
    checks do not award module credit.

    Args:
        context: The call context.
        module_id: The certification module the lesson belongs to.
        lesson_number: 1-based lesson number (lesson_titles in
            get_certification_module lists them in order).
        lesson_id: Stable identity from a saved position; use instead of lesson_number when resuming.
        enrollment_id: Enrollment returned by progress; pins the requested teaching.
    """
    from app.services import certification_service as cert_svc

    if module_id not in cert_svc.course_module_xp():
        return _err(
            f"Unknown module '{module_id}'.",
            hint=f"Valid module ids: {', '.join(cert_svc.course_module_order())}",
        )
    lessons = (cert_svc.get_lessons(module_id) or {}).get("lessons", [])
    if not lessons:
        return _err(f"Module '{module_id}' has no lessons.")
    if lesson_id is not None:
        matching = next((index for index, row in enumerate(lessons, 1) if row.get('id') == lesson_id), None)
        if matching is None or (lesson_number is not None and lesson_number != matching):
            return _err('The lesson identity does not match this course position. Reload progress before continuing.')
        lesson_number = matching
    if not isinstance(lesson_number, int) or not 1 <= lesson_number <= len(lessons):
        return _err(
            f"lesson_number must be 1..{len(lessons)} for '{module_id}'.",
        )
    lesson = lessons[lesson_number - 1]
    return {
        **cert_svc.course_identity(),
        "module_id": module_id,
        "module_title": cert_svc.course_module_titles().get(module_id, module_id),
        "lesson_number": lesson_number,
        "lesson_count": len(lessons),
        "lesson_id": lesson.get("id"),
        "lesson_revision": lesson.get("revision"),
        "title": lesson["title"],
        "objective": lesson.get("objective", ""),
        "variant": lesson.get("variant", "concept"),
        "content": lesson["content"],
        "knowledge_check": lesson.get("knowledge_check"),
        "diagram": lesson.get("diagram"),
        "is_last": lesson_number == len(lessons),
    }


@course_operation(write=True, tool=True)
async def save_certification_position(
    context: RunContext[AgenticChatDeps],
    module_id: str,
    lesson_id: str,
    expected_revision: int,
    enrollment_id: str,
) -> dict:
    """Save the lesson being viewed for resume in chat or the learning panel.

    This stores navigation only; it never awards credit or records an answer.
    Use the lesson_id returned by the lesson tool and enrollment_id plus
    position_revision from progress. If another session changed the position,
    reload and explain the conflict rather than overwriting it automatically.

    Args:
        context: The call context.
        module_id: Module of the lesson being viewed.
        lesson_id: Exact stable identity returned by get_certification_lesson.
        expected_revision: Most recently read or saved position_revision.
        enrollment_id: Exact enrollment returned by get_certification_progress.
    """
    from app.services import certification_service as cert_svc
    if type(expected_revision) is not int or expected_revision < 0:
        return _err('expected_revision must be a nonnegative integer from saved progress.')
    return await cert_svc.save_learning_position(context.deps.user_id, module_id, lesson_id, expected_revision)


@course_operation(write=True, tool=True)
@certification_result(ProvisionResult)
async def provision_certification_lab(
    context: RunContext[AgenticChatDeps],
    module_id: str,
    enrollment_id: str | None = None,
) -> dict:
    """Set up a module's sample documents in the user's Certification Lab folder.

    Uploads the module's practice PDFs into a "Certification Lab" folder in the
    user's workspace (created if needed; existing owned copies are reused).
    Follow the pinned module instructions for setup. Selected-outcome courses
    use their panel's assessment preparation controls and learner decisions.
    This only supplies documents; it does not approve scope, run an assessment
    or earn credit. Modules without assigned documents return an empty list.

    Args:
        context: The call context.
        module_id: The certification module to provision documents for.
        enrollment_id: Enrollment returned by get_certification_progress; use it to pin this action to the learner's chosen course.
    """
    from app.config import Settings
    from app.services import certification_service as cert_svc

    if module_id not in cert_svc.course_module_xp():
        return _err(
            f"Unknown module '{module_id}'.",
            hint=f"Valid module ids: {', '.join(cert_svc.course_module_order())}",
        )
    result = await cert_svc.provision_module_documents(
        context.deps.user, module_id, Settings(),
    )
    if "error" in result:
        return _err(result["error"])
    provisioned = result["provisioned_docs"]
    exercise = cert_svc.get_exercise(module_id) or {}
    folder_name = result.get('folder_name', cert_svc.CERT_FOLDER_TITLE)
    return {
        **cert_svc.course_identity(),
        "module_id": module_id,
        "provisioned_docs": provisioned,
        "document_names": exercise.get("documents", []),
        "folder": folder_name,
        "message": (
            f"{len(provisioned)} sample document(s) are in the "
            f'"{folder_name}" folder (Files tab).'
            if provisioned
            else "This module has no sample documents — nothing to provision."
        ),
    }


@course_operation(tool=True)
@certification_result(CheckResult)
async def check_certification_module(
    context: RunContext[AgenticChatDeps],
    module_id: str,
    enrollment_id: str | None = None,
) -> dict:
    """Read a supported legacy module's pinned validation result.

    Use only after get_certification_module identifies a legacy assessment
    mode. This read-only check does not complete a module. Relay saved checks
    faithfully and distinguish unavailable grading from a learner failure.
    A passing legacy check permits offering complete_certification_module.
    For selected_saved_outcomes, direct the learner to Open module assessment:
    this tool cannot select saved evidence or replace that assessment path.

    Args:
        context: The call context.
        module_id: The certification module to check.
        enrollment_id: Enrollment returned by get_certification_progress, when available.
    """
    from app.services import certification_service as cert_svc

    if module_id not in cert_svc.course_module_xp():
        return _err(
            f"Unknown module '{module_id}'.",
            hint=f"Valid module ids: {', '.join(cert_svc.course_module_order())}",
        )
    result = await cert_svc.validate_module(context.deps.user_id, module_id)
    return {
        **cert_svc.course_identity(),
        "module_id": module_id,
        "title": cert_svc.course_module_titles().get(module_id, module_id),
        "passed": result["passed"],
        "stars": result["stars"],
        "checks": result["checks"],
    }


@course_operation(write=True, tool=True)
@certification_result(CompletionResult)
async def complete_certification_module(
    context: RunContext[AgenticChatDeps],
    module_id: str,
    enrollment_id: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Complete a supported legacy module under its pinned rubric and XP rules.

    Re-runs the module's validator first — if it doesn't pass, nothing is
    awarded and the failing checks are returned. On success, returns XP
    earned, stars, new total/level, and whether the user just became fully
    certified. Use only for a returned legacy assessment mode, after a passing
    check and the learner's request. Base XP is awarded once; star upgrades
    follow that course's rules. After uncertainty inspect the original result
    before retrying with the same request identity. For selected_saved_outcomes,
    use the panel: this tool cannot select receipts or bypass required evidence.
    Live calls automatically retain a reference from their conversation turn
    and tool-call identity when request_id is omitted.

    Args:
        context: The call context.
        module_id: The certification module to complete.
        enrollment_id: Enrollment returned by get_certification_progress; required for a versioned course.
        request_id: Optional 32-character lowercase hexadecimal retry identity. Reuse it after an uncertain response; use a new identity for a new assessed submission.
    """
    from app.services import certification_service as cert_svc

    if module_id not in cert_svc.course_module_xp():
        return _err(
            f"Unknown module '{module_id}'.",
            hint=f"Valid module ids: {', '.join(cert_svc.course_module_order())}",
        )
    if request_id is None:
        conversation = getattr(context.deps, 'conversation', None)
        conversation_id = getattr(conversation, 'uuid', None)
        call_id = getattr(context, 'tool_call_id', None)
        marker = getattr(context.deps, 'turn_marker', None)
        if isinstance(conversation_id, str) and conversation_id and isinstance(call_id, str) and call_id and type(marker) is int and marker >= 0:
            # Transport retries of this live tool call retain their original
            # completion identity without asking the model to invent one.
            request_id = hashlib.sha256(json.dumps(['certification-completion', context.deps.user_id,
                conversation_id, marker, call_id, module_id, enrollment_id], separators=(',', ':')).encode()).hexdigest()[:32]
    result = await cert_svc.complete_module(context.deps.user_id, module_id, request_id=request_id)
    if "error" in result:
        return {
            **cert_svc.course_identity(),
            "error": result["error"],
            "module_id": module_id,
            "validation": result.get("validation"),
            **({'attempt_id': result['attempt_id']} if result.get('attempt_id') else {}),
            **({'failure_kind': result['failure_kind']} if result.get('failure_kind') else {}),
        }
    result["title"] = cert_svc.course_module_titles().get(module_id, module_id)
    return result


@course_operation(write=True, tool=True)
@certification_result(ReflectionResult)
async def submit_certification_assessment(
    context: RunContext[AgenticChatDeps],
    module_id: str,
    answers: dict,
    enrollment_id: str | None = None,
) -> dict:
    """Store the learner's supplied answers for a legacy_reflection module.

    Use only when get_certification_module returns assessment_mode
    legacy_reflection and its assessment_keys/questions. A module title never
    determines this route. Ask its questions one at a time, retaining the
    supplied options when present, and submit only the learner's own answers.
    Never invent or pad answers. Saving is not completion. Courses with
    selected_saved_outcomes reject this route; use Open module assessment
    for the learner's decisions and saved evidence instead.

    Args:
        context: The call context.
        module_id: A module returned with the legacy_reflection assessment mode.
        answers: The user's answers, keyed by the module's assessment_keys.
        enrollment_id: Enrollment returned by get_certification_progress; required for a versioned course.
    """
    from app.services import certification_service as cert_svc

    required = cert_svc.ASSESSMENT_KEYS.get(module_id)
    if not required:
        return _err(
            f"Module '{module_id}' has no self-assessment.",
            hint=(
                "Read get_certification_module for this course's assessment_mode. "
                "Selected-outcome courses use Open module assessment in the Certification panel."
            ),
        )
    if not isinstance(answers, dict):
        return _err("answers must be an object keyed by the module's assessment_keys.")
    cleaned = {k: str(v).strip() for k, v in answers.items() if str(v or "").strip()}
    missing = [k for k in required if not cleaned.get(k)]
    if missing:
        return _err(
            f"Missing answer(s) for: {', '.join(missing)}.",
            hint="Ask the user these questions and resubmit with every key answered.",
        )
    await cert_svc.store_assessment(
        context.deps.user_id, module_id, {k: cleaned[k] for k in required},
    )
    return {
        **cert_svc.course_identity(),
        "stored": True,
        "module_id": module_id,
        "message": (
            "Answers saved. Run check_certification_module then "
            "complete_certification_module to bank the XP."
        ),
    }


# ---------------------------------------------------------------------------
# Tool registry — imported by llm_service.create_agentic_chat_agent()
# ---------------------------------------------------------------------------

TOOLS = [
    # Phase 0 — Plan/progress tracking (sequential: mutates deps.plan_state)
    update_plan,
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
    analyze_documents,
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
    # Phase 11 — Certification program
    get_certification_progress,
    get_certification_module,
    get_certification_lesson,
    save_certification_position,
    provision_certification_lab,
    check_certification_module,
    complete_certification_module,
    submit_certification_assessment,
]


# Tools whose old results may be cleared from replayed history when the
# conversation nears its context budget (micro-compaction — see
# ChatConversation.to_model_messages and the uplift plan Phase 3). Only
# read-type tools whose results are safely re-obtainable by calling the tool
# again. NEVER add gated write tools here: their preview results must replay
# verbatim for the confirm-gate handshake, and a cleared preview could let the
# model mis-describe what the user approved. Status/decision tools
# (get_workflow_status, get_optimization_run) stay out too — their results are
# small and anchor in-flight processes.
COMPACTABLE_TOOLS: frozenset[str] = frozenset({
    "search_documents",
    "list_documents",
    "list_folders",
    "search_knowledge_base",
    "list_knowledge_bases",
    "list_extraction_sets",
    "list_workflows",
    "get_quality_info",
    "search_library",
    "get_app_help",
    "fetch_url",
    "web_search",
    "get_document_text",
    "analyze_documents",
    "run_extraction",
    "check_compliance",
    "list_test_cases",
    "list_optimization_recommendations",
    "list_project_documents",
    "get_certification_progress",
    "get_certification_module",
    "get_certification_lesson",
    "check_certification_module",
})


# Tools that may execute CONCURRENTLY when the model issues several calls in
# one response (uplift plan Phase 7). Fail-closed: anything not listed here is
# registered sequential — every gated write tool serializes so two mutations
# (or a mutation and a read of its target) never race, and the confirm-gate's
# pending_confirmations bookkeeping is never written from two calls at once.
# The read set is COMPACTABLE_TOOLS (read-only, re-runnable) plus the two
# read-only status tools that were excluded from compaction for staleness
# reasons, not safety ones.
PARALLEL_SAFE_TOOLS: frozenset[str] = COMPACTABLE_TOOLS | frozenset({
    "get_workflow_status",
    "get_optimization_run",
})
