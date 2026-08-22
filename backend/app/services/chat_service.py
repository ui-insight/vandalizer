"""Chat service  - streaming chat with full document context."""

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator, Optional

from pydantic_ai.agent import Agent
from pydantic_ai.messages import (
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    UserPromptPart,
)

from app.models.activity import ActivityEvent, ActivityStatus
from app.models.chat import ChatConversation, ChatRole
from app.models.document import SmartDocument
from app.models.system_config import SystemConfig
from app.services import document_service
from app.services.config_service import get_llm_model_by_name, get_user_model_name
from app.services.context_budget import (
    DocumentSegment,
    estimate_input_tokens,
    plan_and_compact_context,
)
from app.services.model_routing import (
    RoutingDecision,
    choose_document_model,
    suggest_document_model,
)
from app.services.page_locator import locator_for_meta
from app.services.llm_service import (
    build_project_kb_empty_prompt,
    create_chat_agent,
    DOCUMENT_CHAT_SYSTEM_PROMPT,
    FIRST_SESSION_SYSTEM_PROMPT,
    HELP_CHAT_SYSTEM_PROMPT,
    KB_CHAT_SYSTEM_PROMPT,
    NO_DOCUMENT_SYSTEM_PROMPT,
    VANDALIZER_CONTEXT,
)

logger = logging.getLogger(__name__)


_THINK_OPEN_RE = re.compile(r"<think(?:ing)?>")
_THINK_CLOSE_RE = re.compile(r"</think(?:ing)?>")
_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>\n?")
# Longest possible opening / closing tag
_MAX_OPEN = len("<thinking>")   # 10
_MAX_CLOSE = len("</thinking>")  # 11


class _ThinkTagParser:
    """Detect ``<think>``/``<thinking>`` blocks in streaming text.

    At most ``_MAX_OPEN - 1`` or ``_MAX_CLOSE - 1`` characters are held back
    between calls to handle tags split across chunks.
    """

    def __init__(self) -> None:
        self.in_think = False
        self.pending = ""

    def feed(self, text: str) -> list[tuple[str, str]]:
        """Return list of (kind, content) pairs — kind is 'text' or 'thinking'."""
        self.pending += text
        results: list[tuple[str, str]] = []

        while self.pending:
            if not self.in_think:
                m = _THINK_OPEN_RE.search(self.pending)
                if m:
                    if m.start() > 0:
                        results.append(("text", self.pending[: m.start()]))
                    self.pending = self.pending[m.end() :]
                    self.in_think = True
                else:
                    safe = self._safe_emit(self.pending, _MAX_OPEN)
                    if safe > 0:
                        results.append(("text", self.pending[:safe]))
                        self.pending = self.pending[safe:]
                    break
            else:
                m = _THINK_CLOSE_RE.search(self.pending)
                if m:
                    if m.start() > 0:
                        results.append(("thinking", self.pending[: m.start()]))
                    self.pending = self.pending[m.end() :]
                    if self.pending.startswith("\n"):
                        self.pending = self.pending[1:]
                    self.in_think = False
                else:
                    safe = self._safe_emit(self.pending, _MAX_CLOSE)
                    if safe > 0:
                        results.append(("thinking", self.pending[:safe]))
                        self.pending = self.pending[safe:]
                    break

        return results

    def flush(self) -> list[tuple[str, str]]:
        if not self.pending:
            return []
        kind = "thinking" if self.in_think else "text"
        result = [(kind, self.pending)]
        self.pending = ""
        return result

    @staticmethod
    def _safe_emit(text: str, max_tag_len: int) -> int:
        """How many leading chars of *text* can be emitted?

        Hold back at most ``max_tag_len - 1`` characters that could be
        the start of an opening or closing tag (anything beginning with ``<``).
        """
        # Find the last '<' in the holdback zone
        holdback = min(max_tag_len - 1, len(text))
        last_lt = text.rfind("<", len(text) - holdback)
        if last_lt == -1:
            return len(text)
        return last_lt


def annotate_pages(text: str, markers: list[dict] | None) -> str:
    """Insert ``[p. N]`` boundaries into document text using its page markers.

    Page structure is computed at ingest and stored on the document
    (``SmartDocument.text_markers``, one ``{"char_offset", "kind": "page",
    "value": n}`` per page). Extraction sources and KB chat already resolve it;
    document chat previously sent ``raw_text`` flat, so the model had no way to
    attribute a fact to a page even though the data was sitting right there.

    Returns *text* unchanged when there is no usable page structure — non-PDF
    formats, and PDFs ingested before markers were persisted. Callers get a
    plain document rather than an error. See #603.
    """
    if not text or not markers:
        return text

    positions: list[tuple[int, int, bool]] = []
    for m in markers:
        if not isinstance(m, dict) or m.get("kind") != "page":
            continue  # XLSX markers describe sheets, not pages
        page = m.get("value")
        offset = m.get("char_offset")
        if not isinstance(page, int) or not isinstance(offset, bool | int):
            continue
        if isinstance(offset, bool) or not 0 <= offset <= len(text):
            # raw_text can be re-saved shorter than when markers were computed.
            continue
        positions.append((offset, page, bool(m.get("approximate"))))

    if not positions:
        return text

    positions.sort()
    out: list[str] = []
    cursor = 0
    for offset, page, approximate in positions:
        out.append(text[cursor:offset])
        # OCR'd pages are evenly-spaced estimates, so the boundary is a guess.
        # The tilde keeps the model from quoting an estimate as a fact.
        out.append(f"[p. ~{page}]\n" if approximate else f"[p. {page}]\n")
        cursor = offset
    out.append(text[cursor:])
    return "".join(out)


def page_note_for(markers: list[dict] | None, *, annotated: bool) -> str:
    """The instruction that tells the model how to cite pages in this document.

    Returns "" when the document got no page markers — promising citations the
    model has no way to make is worse than saying nothing (non-PDF formats, or
    PDFs ingested before page markers existed).

    The two notes are deliberately parallel in force. An earlier version made
    the measured-page note conditional ("cite when you quote or reference a
    specific passage") while the interpolated one was a directive, so the
    document whose page numbers were *trustworthy* carried the weaker
    instruction. Measured against a live 30B: the scanned document was cited,
    the digital one on one question in three.

    The interpolated note rules out asserting exactness by name. Telling a
    model to hedge left room for it to hedge *and* claim a passage was
    "explicitly stated" on a page, which is what it did — five times out of
    five at temperature 0, on a document whose page markers are 100%
    interpolated.
    """
    if not annotated or not _has_page_markers(markers):
        return ""
    if _has_approximate_pages(markers):
        # Boundaries were interpolated from character offsets, so an
        # exact-sounding citation is invented precision.
        return (
            "\n_`[p. ~N]` marks the *estimated* start of page N — this document "
            "was scanned, so page positions are approximate. Always give pages "
            "as approximate, e.g. \"around p. 4\". Never state a page as exact "
            "and never say a passage is \"explicitly\" or \"clearly\" on a given "
            "page._\n"
        )
    return (
        "\n_`[p. N]` marks the start of page N. Cite the page for every fact you "
        "take from this document, e.g. \"p. 3\"._\n"
    )


def _has_page_markers(markers: list[dict] | None) -> bool:
    return any(
        isinstance(m, dict) and m.get("kind") == "page" for m in (markers or [])
    )


def _has_approximate_pages(markers: list[dict] | None) -> bool:
    """True when any usable page marker came from interpolation, not measurement."""
    return any(
        isinstance(m, dict) and m.get("kind") == "page" and m.get("approximate")
        for m in markers or []
    )


def build_document_segments(
    documents: list,
) -> tuple[list[DocumentSegment], list[str], list[str], list[str]]:
    """Turn selected documents into trimmable context segments.

    One segment per document so the budget planner can trim each independently.
    Returns ``(segments, skipped_no_text, errored, low_quality)`` — the last
    three are titles the caller warns the user about. ``skipped_no_text`` and
    ``errored`` never reach the model; ``low_quality`` documents do, but their
    text layer is garbled, so the answer is unreliable (see #609).
    """
    segments: list[DocumentSegment] = []
    skipped_no_text: list[str] = []
    errored: list[str] = []
    low_quality: list[str] = []

    for doc in documents:
        if doc.raw_text:
            markers = getattr(doc, "text_markers", None)
            body = annotate_pages(doc.raw_text, markers)
            page_note = page_note_for(markers, annotated=body != doc.raw_text)
            segments.append(DocumentSegment(
                label=f"doc:{doc.title or doc.uuid}",
                text=f"\n\n## Document: {doc.title}\n{page_note}{body}",
            ))
            if document_service.is_extraction_low_quality(doc):
                low_quality.append(doc.title or doc.uuid)
        elif doc.task_status == "error":
            errored.append(doc.title or doc.uuid)
        else:
            skipped_no_text.append(doc.title or doc.uuid)

    return segments, skipped_no_text, errored, low_quality


def _classify_stream_error(exc: BaseException) -> tuple[str, str]:
    """Classify a chat stream error into (severity, user_message).

    severity is "warning" for transient/external/user-input issues that aren't
    actionable bugs — these stay out of Sentry's error stream. "error" is the
    fallback for unexpected exceptions.
    """
    text = str(exc)
    lower = text.lower()

    # Trial account out of token budget — expected lifecycle event, not a bug.
    from app.exceptions import TrialBudgetExceededError

    if isinstance(exc, TrialBudgetExceededError):
        return "warning", exc.message

    # Upstream LLM context window exceeded — user-input issue, not a bug.
    if "exceeds model's maximum context length" in lower or "context length" in lower:
        return "warning", (
            "This conversation is too large for the selected model. "
            "Remove some documents or switch to a larger model."
        )

    # Configured model isn't served by the upstream LLM gateway.
    if "model_not_found" in lower or "does not exist" in lower:
        return "warning", (
            "The selected model is not available right now. "
            "Pick a different model in Settings and try again."
        )

    # Upstream gateway / connectivity / retry exhaustion — transient.
    transient_markers = (
        "peer closed connection",
        "incomplete chunked read",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
        "connection error",
        "streaming attempts failed",
        "remoteprotocolerror",
    )
    if any(m in lower for m in transient_markers):
        return "warning", (
            "The model service was unreachable. Please try again in a moment."
        )

    return "error", text


def _extract_event_content(event) -> tuple[str | None, bool]:
    """Extract content from a pydantic-ai stream event.

    Returns (content, is_api_thinking).  content is None for unrecognised events.
    """
    if isinstance(event, PartStartEvent):
        if isinstance(event.part, TextPart):
            return event.part.content or "", False
        if isinstance(event.part, ThinkingPart):
            return event.part.content or "", True
    elif isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            return event.delta.content_delta or "", False
        if isinstance(event.delta, ThinkingPartDelta):
            return event.delta.content_delta or "", True
    return None, False


def select_chat_system_prompt(
    *,
    kb_sources: list[dict],
    have_context: bool,
    kb_uuid: Optional[str],
    is_first_session: bool,
    include_onboarding_context: bool,
    manifest_block: str = "",
) -> str:
    """Pick the system prompt for a chat turn from its context state.

    Extracted from ``chat_stream`` so each branch is unit-testable: the choice
    is pure, while the generator around it is not.

    Ordered most-grounded first. Every branch returns a prompt that tells the
    model what it does and does not have — none may return ``None``, because
    ``create_chat_agent`` turns a falsey prompt into
    ``DEFAULT_CHAT_SYSTEM_PROMPT``, which carries no grounding rule at all and
    lets the model answer document-specific questions from invention.
    """
    if kb_sources:
        # The manifest rides on the system prompt (re-sent every turn) so the
        # model can distinguish "exists here but wasn't retrieved" from "not
        # in this project" on follow-ups too.
        return KB_CHAT_SYSTEM_PROMPT + manifest_block
    if have_context:
        return DOCUMENT_CHAT_SYSTEM_PROMPT
    if kb_uuid:
        # A project/KB chat was requested but retrieval returned nothing (empty KB,
        # docs not indexed yet, or no match). Tell it the KB was empty for this
        # query while still allowing general-knowledge answers.
        return build_project_kb_empty_prompt(manifest_block)
    if is_first_session:
        # First-session onboarding: conversational value discovery.
        # Do NOT inject VANDALIZER_CONTEXT here — it's a technical how-to dump
        # that causes the LLM to skip the conversation and spit out directions.
        # The FIRST_SESSION_SYSTEM_PROMPT already has everything it needs.
        return FIRST_SESSION_SYSTEM_PROMPT
    if include_onboarding_context:
        return HELP_CHAT_SYSTEM_PROMPT
    # Nothing attached at all — no documents, no attachments, no KB, no
    # onboarding. The model must be told so explicitly rather than left with
    # the generic prompt, which would let it answer "what is the total in this
    # proposal?" as though a proposal were present.
    return NO_DOCUMENT_SYSTEM_PROMPT


def _suggest_model_for_overflow(
    compacted,
    model_name: str,
    model_config: Optional[dict],
    sys_config_doc: dict,
    input_tokens: int,
) -> Optional[dict]:
    """A larger model to offer, or None when nothing needs offering.

    Only when the request actually overflowed — a suggestion on a request that
    fit would be noise, and the dialog it feeds only opens on overflow.

    ``input_tokens`` must be the size of the request *before* compaction. The
    question being asked is "could another model have held what the user
    actually sent?", and the compacted total cannot answer it: compaction is
    defined as making the request fit, so ``compacted.plan.total_input_tokens``
    is always within the current model's budget. Passing it made
    :func:`suggest_document_model` return None every time and the dialog's
    fourth option could never appear.
    """
    if not compacted.actions:
        return None
    suggestion = suggest_document_model(
        current_name=model_name,
        current_config=model_config,
        models=(sys_config_doc or {}).get("available_models") or [],
        input_tokens=input_tokens,
    )
    if not suggestion:
        return None
    return {
        "name": suggestion.get("name", ""),
        "tag": suggestion.get("tag", ""),
        "context_window": suggestion.get("context_window", 0),
    }


async def chat_stream(
    message: str,
    document_uuids: list[str],
    conversation_uuid: str,
    user_id: str,
    activity_id: Optional[str] = None,
    settings=None,
    model_override: Optional[str] = None,
    kb_uuid: Optional[str] = None,
    include_onboarding_context: bool = False,
    is_first_session: bool = False,
) -> AsyncGenerator[str, None]:
    """Async generator yielding newline-delimited JSON chunks for streaming chat."""

    # Resolve model — prefer per-request override, fall back to user config
    if model_override:
        from app.services.config_service import resolve_model_name
        model_name = await resolve_model_name(model_override)
    else:
        model_name = await get_user_model_name(user_id)

    # Fetch system config so agent creation can read per-model settings (api_key, endpoint, etc.)
    cfg = await SystemConfig.get_config()
    sys_config_doc = cfg.model_dump() if cfg else {}

    # Load conversation
    conversation = await ChatConversation.find_one(
        ChatConversation.uuid == conversation_uuid,
        ChatConversation.user_id == user_id,
    )
    if not conversation:
        yield json.dumps({"kind": "error", "content": "Conversation not found"}) + "\n"
        return

    # Load documents
    documents: list[SmartDocument] = []
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(
            SmartDocument.uuid == doc_uuid,
        )
        if doc:
            documents.append(doc)

    # Build attachment segments (each can be independently trimmed by the budget planner)
    attachment_segments: list[DocumentSegment] = []
    url_attachments = await conversation.get_url_attachments()
    for att in url_attachments:
        if att.content:
            # Content is already clean extracted text (web_fetcher runs
            # trafilatura).  Cap at 80K chars (~20K tokens) — enough for a
            # multi-page policy or article; the budget planner trims further
            # when prompt space is tight.
            attachment_segments.append(DocumentSegment(
                label=f"web:{att.title or att.url}",
                text=(
                    f"\n\n## Web Content: {att.title}\nSource: {att.url}\n\n"
                    f"{att.content[:80000]}\n"
                ),
            ))

    file_attachments = await conversation.get_file_attachments()
    logger.info(
        "Chat file attachments: count=%d with_content=%d",
        len(file_attachments),
        sum(1 for a in file_attachments if a.content),
    )
    for att in file_attachments:
        if att.content:
            attachment_segments.append(DocumentSegment(
                label=f"file:{att.filename}",
                text=f"\n\n## Document: {att.filename}\n\n{att.content[:10000]}\n",
            ))

    # If the conversation was created during first-session onboarding, honour
    # that flag even when the frontend doesn't pass it (e.g. after a remount).
    if not is_first_session and conversation.is_first_session:
        is_first_session = True

    # Load message history, excluding the user message we just saved (chat.py
    # saves the bare message before calling chat_stream).  We re-send it as
    # the enriched prompt below so the model only sees the version that
    # includes document / KB / attachment context.
    previous_messages: list[ModelMessage] = await conversation.to_model_messages()
    if previous_messages:
        previous_messages = previous_messages[:-1]

    # Document segments — one entry per SmartDocument so each can be trimmed
    # independently by the budget planner.
    doc_segments, skipped_no_text, errored_docs, low_quality_docs = (
        build_document_segments(documents)
    )

    # Warn the caller about any selected document that the model won't see
    # because text extraction hasn't finished, errored out, or the doc is gone.
    missing_uuids = [u for u in document_uuids if u not in {d.uuid for d in documents}]
    if errored_docs:
        joined = ", ".join(errored_docs[:5]) + ("…" if len(errored_docs) > 5 else "")
        yield json.dumps({
            "kind": "context_notice",
            "content": (
                f"{len(errored_docs)} selected document(s) failed text extraction "
                f"and can't be used here: {joined}. Open the document and use "
                "\"Retry extraction\" to try again."
            ),
            "action": "documents_extraction_failed",
            "tokens_dropped": 0,
        }) + "\n"
    if skipped_no_text or missing_uuids:
        names = list(skipped_no_text) + missing_uuids
        joined = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        yield json.dumps({
            "kind": "context_notice",
            "content": (
                f"{len(names)} selected document(s) had no extracted text yet "
                f"and were not sent to the model: {joined}. "
                "Wait for processing to finish, then re-send."
            ),
            "action": "documents_not_ready",
            "tokens_dropped": 0,
        }) + "\n"
    if low_quality_docs:
        # A garbled text layer (broken font encoding) still yields plenty of
        # "text", and models answer over it with fluent, confidently wrong
        # summaries — the user gets no signal unless we give one.
        joined = ", ".join(low_quality_docs[:5]) + ("…" if len(low_quality_docs) > 5 else "")
        yield json.dumps({
            "kind": "context_notice",
            "content": (
                f"Text extracted poorly from {len(low_quality_docs)} selected "
                f"document(s): {joined}. Most of the stored text is unreadable, "
                "so answers about these documents are likely to be unreliable "
                "or wrong. Try \"Retry extraction\" on the document, or "
                "re-upload it (e.g. as a scanned/printed copy) so OCR can "
                "produce clean text."
            ),
            "action": "documents_low_quality",
            "tokens_dropped": 0,
        }) + "\n"

    total_text_len = sum(len(s.text) for s in doc_segments)
    if document_uuids:
        logger.info(
            "Chat doc context: requested=%d found=%d with_text=%d text_len=%d skipped_no_text=%d",
            len(document_uuids),
            len(documents),
            sum(1 for d in documents if d.raw_text),
            total_text_len,
            len(skipped_no_text),
        )

    # KB context: query ChromaDB for relevant chunks and add as a segment.
    kb_sources: list[dict] = []
    kb_manifest: list[dict] = []
    if kb_uuid:
        try:
            from app.services.knowledge_service import get_kb_manifest
            kb_manifest = await get_kb_manifest(kb_uuid)
        except Exception as e:
            logger.warning("KB manifest fetch failed for kb_uuid=%s: %s", kb_uuid, e)
        try:
            kb_segment, kb_sources = await _build_kb_segment(
                kb_uuid, message, model_name, manifest=kb_manifest,
                history=previous_messages, user_id=user_id,
            )
            if kb_segment:
                doc_segments.insert(0, kb_segment)
        except Exception as e:
            logger.error("KB context retrieval failed for kb_uuid=%s: %s", kb_uuid, e)
            kb_sources = []

    # Select system prompt based on whether we have document context.
    # KB chat needs a stricter prompt: snippets are partial excerpts, so the model
    # must cite by filename, distinguish grounded answers from general knowledge,
    # and admit when the retrieved set doesn't actually contain the answer.
    have_context = bool(doc_segments or attachment_segments)
    system_prompt: Optional[str] = select_chat_system_prompt(
        kb_sources=kb_sources,
        have_context=have_context,
        kb_uuid=kb_uuid,
        is_first_session=is_first_session,
        include_onboarding_context=include_onboarding_context,
        manifest_block=_build_manifest_block(kb_manifest),
    )
    if system_prompt == HELP_CHAT_SYSTEM_PROMPT:
        # Inject Vandalizer help context only when explicitly requested
        # (triggered by the placeholder pills in the chat UI).
        doc_segments.append(DocumentSegment(
            label="onboarding",
            text=(
                "--- BEGIN ONBOARDING CONTEXT ---\n"
                f"{VANDALIZER_CONTEXT}\n"
                "--- END ONBOARDING CONTEXT ---"
            ),
        ))

    # Resolve the model's context window and compact oversize components.
    model_config = await get_llm_model_by_name(model_name)

    # A whole document is the unit people actually work in — a grant proposal
    # arrives as one file and gets read as one. When it doesn't fit, trimming
    # answers from part of it. If the deployment nominated a bigger model, use
    # it rather than silently dropping the middle. See services/model_routing.
    # Measured before any trimming: both routing and the dialog's suggestion
    # ask "could another model have held what the user actually sent?", and the
    # post-compaction total cannot answer that — it always fits by definition.
    # `model_config` carries this model's token safety margin, so the estimate
    # is an upper bound rather than an optimistic one. Routing decides off this
    # number: an estimate that reads low makes the router see headroom that is
    # not there and decline to move a request that does not fit.
    requested_input_tokens = estimate_input_tokens(
        model_name=model_name,
        system_prompt=system_prompt or "",
        user_message=message,
        history=previous_messages,
        documents=doc_segments,
        attachments=attachment_segments,
        model_config=model_config,
    )

    routing = RoutingDecision(model_name, False, "")
    candidate_name = (sys_config_doc or {}).get("long_document_model") or ""
    if candidate_name and (doc_segments or attachment_segments):
        candidate_config = await get_llm_model_by_name(candidate_name)
        routing = choose_document_model(
            current_name=model_name,
            current_config=model_config,
            candidate_name=candidate_name,
            candidate_config=candidate_config,
            input_tokens=requested_input_tokens,
        )
        if routing.switched:
            logger.info(
                "Routing to %s: request does not fit %s", candidate_name, model_name
            )
            model_name, model_config = routing.model_name, candidate_config

    compacted = plan_and_compact_context(
        model_name=model_name,
        model_config=model_config,
        system_prompt=system_prompt or "",
        user_message=message,
        history=previous_messages,
        documents=doc_segments,
        attachments=attachment_segments,
    )

    # Tell the client what we planned (and whether we had to compact).
    yield json.dumps({
        "kind": "context_budget",
        "content": "",
        "plan": compacted.plan.to_dict(),
        # Offered to the user when their request didn't fit, so the context
        # dialog can propose keeping the whole document instead of dropping
        # part of it. Computed server-side under the same privacy rule as
        # automatic routing — picking a model from the list in the browser
        # would walk around that gate.
        "suggested_model": _suggest_model_for_overflow(
            compacted, model_name, model_config, sys_config_doc,
            requested_input_tokens,
        ),
    }) + "\n"
    # Switching the model without saying so is the same failure as trimming a
    # document without saying so — the answer looks identical either way.
    if routing.reason:
        yield json.dumps({
            "kind": "context_notice",
            "content": routing.reason,
            "action": "model_routed" if routing.switched else "model_not_routed",
            "tokens_dropped": 0,
        }) + "\n"
    for action in compacted.actions:
        yield json.dumps({
            "kind": "context_notice",
            "content": action.detail,
            "action": action.kind,
            "tokens_dropped": action.tokens_dropped,
        }) + "\n"

    # Emit KB sources before the LLM streams its answer so the UI can render
    # citation chips alongside (or just before) the response.
    if kb_sources:
        yield json.dumps({
            "kind": "sources",
            "content": "",
            "sources": kb_sources,
        }) + "\n"

    if compacted.fatal:
        logger.warning(
            "Chat context over budget for model=%s: plan=%s actions=%s",
            model_name, compacted.plan.to_dict(),
            [a.to_dict() for a in compacted.actions],
        )
        # Identify which attached documents are individually too large for the
        # model — those are the ones the user should convert to a Knowledge
        # Base. If none qualify, the prompt is just generically too big and we
        # fall back to the plain error.
        from app.services.context_budget import find_oversize_documents
        oversize = find_oversize_documents(
            documents=[
                {"uuid": d.uuid, "title": d.title, "token_count": d.token_count}
                for d in documents
            ],
            model_name=model_name,
            model_config=model_config,
        )
        if oversize:
            titles = ", ".join(o.title for o in oversize[:3])
            if len(oversize) > 3:
                titles += f", and {len(oversize) - 3} more"
            content = (
                f"{titles} is too large to read inline with the selected model. "
                "Convert it to a Knowledge Base and chat will search it instead."
            )
            yield json.dumps({
                "kind": "error",
                "code": "context_over_budget_convertible",
                "content": content,
                "suggested_action": "convert_to_kb",
                "oversize_documents": [o.to_dict() for o in oversize],
            }) + "\n"
        else:
            yield json.dumps({
                "kind": "error",
                "code": "context_over_budget",
                "content": (
                    "This request is too large for the selected model "
                    f"(~{compacted.plan.total_input_tokens} tokens vs "
                    f"{compacted.plan.input_budget} token input budget). "
                    "Remove some documents or switch to a larger model."
                ),
            }) + "\n"
        await _save_failed_assistant_turn(
            conversation,
            "_(no response — request exceeded the model's context budget)_",
            activity_id,
            "context over budget",
        )
        return

    previous_messages = compacted.history

    # Rebuild the final prompt from compacted segments.
    if have_context or include_onboarding_context:
        context_pieces: list[str] = [s.text for s in compacted.documents]
        context_pieces.extend(s.text for s in compacted.attachments)
        context_block = "\n\n".join(context_pieces)
        if include_onboarding_context and not have_context:
            # Preserve the original onboarding wording when that's the only context.
            prompt = f"{context_block}\n\nUser question: {message}"
        else:
            prompt = (
                f"{message}\n\n"
                "--- BEGIN REFERENCE DOCUMENTS (provided for context only) ---\n"
                f"{context_block}\n"
                "--- END REFERENCE DOCUMENTS ---"
            )
    else:
        prompt = message

    agent = create_chat_agent(model_name, system_prompt=system_prompt, system_config_doc=sys_config_doc)

    # Stream the response
    full_response: list[str] = []
    full_thinking: list[str] = []
    thinking_started_at: float | None = None
    thinking_duration: float | None = None
    thinking_done_emitted = False

    # Meter every token this chat consumes (see app/services/metering.py). Manual
    # enter/exit avoids re-indenting the large streaming body; __aexit__ in the
    # finally flushes whatever was accrued, even on cancellation mid-stream.
    from app.services.metering import metered_async
    _meter = metered_async(
        "chat",
        user_id=user_id,
        team_id=getattr(conversation, "team_id", None),
        activity_id=activity_id,
    )
    _meter_entered = False
    try:
        # Entered inside the try so a trial-budget rejection at scope entry
        # surfaces through the stream's error path instead of aborting the SSE.
        await _meter.__aenter__()
        _meter_entered = True
        think_parser = _ThinkTagParser()

        async with agent.iter(
            prompt, message_history=previous_messages
        ) as agent_run:
            async for node in agent_run:
                if Agent.is_model_request_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:
                            content, is_api_thinking = _extract_event_content(event)
                            if content is None:
                                continue

                            if is_api_thinking:
                                # Native API-level thinking (e.g. Claude extended thinking)
                                full_thinking.append(content)
                                if thinking_started_at is None:
                                    thinking_started_at = time.monotonic()
                                yield json.dumps({"kind": "thinking", "content": content}) + "\n"
                            else:
                                # Text — parse for embedded <think> tags
                                for kind, text in think_parser.feed(content):
                                    if kind == "thinking":
                                        full_thinking.append(text)
                                        if thinking_started_at is None:
                                            thinking_started_at = time.monotonic()
                                        yield json.dumps({"kind": "thinking", "content": text}) + "\n"
                                    else:
                                        if thinking_started_at and not thinking_done_emitted:
                                            thinking_duration = round(
                                                time.monotonic() - thinking_started_at, 1
                                            )
                                            thinking_done_emitted = True
                                            yield json.dumps({
                                                "kind": "thinking_done",
                                                "content": "",
                                                "duration": thinking_duration,
                                            }) + "\n"
                                        full_response.append(text)
                                        yield json.dumps({"kind": "text", "content": text}) + "\n"

                    # Flush any remaining buffered content from the parser
                    for kind, text in think_parser.flush():
                        if kind == "thinking":
                            full_thinking.append(text)
                            yield json.dumps({"kind": "thinking", "content": text}) + "\n"
                        else:
                            full_response.append(text)
                            yield json.dumps({"kind": "text", "content": text}) + "\n"

            if agent_run.result:
                usage = agent_run.result.usage()
                # Safety-net: strip any residual think tags the parser missed
                assistant_message = _THINK_BLOCK_RE.sub("", "".join(full_response)).strip()
                thinking_text = "".join(full_thinking) or None
                await _finalize(
                    conversation, assistant_message, documents,
                    usage, activity_id, user_id,
                    thinking=thinking_text,
                    thinking_duration=thinking_duration,
                    citations=kb_sources or None,
                )

                # Stream token usage so the frontend can display context utilization
                input_toks = usage.input_tokens if usage else 0
                output_toks = usage.output_tokens if usage else 0

                # Fallback: estimate tokens when provider doesn't report usage
                if not input_toks:
                    history_chars = sum(
                        len(str(part))
                        for m in previous_messages
                        for part in m.parts
                    )
                    char_count = history_chars + len(prompt) + len(assistant_message)
                    input_toks = max(char_count // 4, 1)
                    output_toks = output_toks or max(len(assistant_message) // 4, 1)

                yield json.dumps({
                    "kind": "usage",
                    "content": "",
                    "request_tokens": input_toks,
                    "response_tokens": output_toks,
                    "total_tokens": input_toks + output_toks,
                }) + "\n"

    except asyncio.CancelledError:
        # Client disconnected mid-stream. Persist any partial response so the
        # user message isn't orphaned (would leave consecutive user turns in
        # history, which pydantic-ai rejects on the next request).
        try:
            await asyncio.shield(_save_failed_assistant_turn(
                conversation,
                _build_interrupted_body(full_response, "connection closed before completion"),
                activity_id,
                "client disconnected",
                thinking="".join(full_thinking) or None,
                thinking_duration=thinking_duration,
            ))
        except Exception as save_err:
            logger.error("Failed to persist interrupted chat on cancel: %s", save_err)
        raise

    except Exception as e:
        severity, user_message = _classify_stream_error(e)
        if severity == "warning":
            logger.warning("Chat stream error: %s", e)
        else:
            logger.error("Chat stream error: %s", e)
        yield json.dumps({"kind": "error", "content": user_message}) + "\n"
        try:
            await _save_failed_assistant_turn(
                conversation,
                _build_interrupted_body(full_response, user_message[:200]),
                activity_id,
                str(e),
                thinking="".join(full_thinking) or None,
                thinking_duration=thinking_duration,
            )
        except Exception as save_err:
            logger.error("Failed to persist interrupted chat: %s", save_err)
    finally:
        if _meter_entered:
            await _meter.__aexit__(None, None, None)



_ANAPHORA_RE = re.compile(
    r"\b(it|its|that|this|these|those|they|them|their|he|she|his|her|hers)\b",
    re.IGNORECASE,
)
_FOLLOWUP_STARTERS = ("what about", "how about", "and ", "also ", "why", "same for")


def _looks_anaphoric(message: str) -> bool:
    """Heuristic: does this message likely depend on conversation context for
    retrieval? Errs toward True — a needless condense only costs one bounded
    LLM call, while retrieving on a bare "what about year 2?" loses grounding.
    """
    msg = " ".join((message or "").strip().lower().split())
    if not msg:
        return False
    if len(msg) < 100:
        return True
    if _ANAPHORA_RE.search(msg):
        return True
    return msg.startswith(_FOLLOWUP_STARTERS)


def _recent_turns(
    history: list[ModelMessage], max_turns: int = 6,
) -> list[tuple[str, str]]:
    """Flatten pydantic-ai message history into (role, text) pairs for the
    condense prompt. System parts are skipped; persisted user turns are the
    bare messages (chat.py saves them before enrichment)."""
    turns: list[tuple[str, str]] = []
    for m in history:
        for part in getattr(m, "parts", []):
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                turns.append(("user", part.content))
            elif isinstance(part, TextPart) and part.content:
                turns.append(("assistant", part.content))
    return turns[-max_turns:]


_MANIFEST_MAX_ENTRIES = 60
_MANIFEST_MAX_CHARS = 3000


def _build_manifest_block(manifest: list[dict]) -> str:
    """Render the project's document list as a system-prompt section.

    Appended to the system prompt (re-sent every turn) so the model always
    knows what the project contains — the retrieved snippets alone can't tell
    it whether an unretrieved document exists.
    """
    if not manifest:
        return ""
    lines: list[str] = []
    total_chars = 0
    shown = 0
    for entry in manifest[:_MANIFEST_MAX_ENTRIES]:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        status = entry.get("status")
        line = f"- {name}" + (" (still indexing)" if status and status != "ready" else "")
        if total_chars + len(line) > _MANIFEST_MAX_CHARS:
            break
        lines.append(line)
        total_chars += len(line)
        shown += 1
    if not lines:
        return ""
    more = len(manifest) - shown
    more_note = f"\n…and {more} more document(s) not listed here." if more > 0 else ""
    return (
        "\n\n## Project Document Manifest\n"
        f"This project contains {len(manifest)} document(s):\n"
        + "\n".join(lines)
        + more_note
        + "\n\nManifest rules:\n"
        "- If the user asks about a document listed above but none of the retrieved "
        "snippets come from it, say the document is in this project but nothing from "
        "it was retrieved for this question — suggest asking about it by name or "
        "rephrasing. Never claim a listed document lacks content, or that a fact "
        "\"isn't in the project\", just because no snippet from it was retrieved.\n"
        "- If the user asks about a document NOT listed above, say it isn't part of "
        "this project.\n"
        "- A document marked \"(still indexing)\" can't be searched yet — say so if "
        "the user asks about it.\n"
    )


def _select_diverse_chunks(
    results: list[dict], k: int, max_per_source: int,
) -> list[dict]:
    """Pick up to ``k`` chunks in relevance order, capping any single source at
    ``max_per_source`` so one long narrative document can't fill every slot.

    A second pass backfills from the overflow so a single-source KB (or one
    genuinely dominant document) still fills all ``k`` slots.
    """
    selected: list[dict] = []
    overflow: list[dict] = []
    counts: dict = {}
    for r in results:
        meta = r.get("metadata") or {}
        src = meta.get("source_id") or meta.get("source_name")
        if counts.get(src, 0) < max_per_source:
            selected.append(r)
            counts[src] = counts.get(src, 0) + 1
        else:
            overflow.append(r)
        if len(selected) >= k:
            break
    if len(selected) < k:
        selected.extend(overflow[: k - len(selected)])
    return selected[:k]


def _match_named_sources(message: str, manifest: list[dict]) -> list[str]:
    """Return the manifest names the user's message mentions explicitly.

    Normalized substring match: case-insensitive, extension-insensitive.
    Names shorter than 5 characters with fewer than 2 tokens are skipped so a
    file called "a.txt" doesn't match every message containing "a".
    """
    msg = " ".join((message or "").lower().split())
    matched: list[str] = []
    for entry in manifest:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        stem = name.rsplit(".", 1)[0] if "." in name else name
        stem_norm = " ".join(stem.lower().replace("_", " ").replace("-", " ").split())
        if len(stem_norm) < 5 and len(stem_norm.split()) < 2:
            continue
        if name.lower() in msg or (stem_norm and stem_norm in msg):
            matched.append(name)
    return matched


def _compose_kb_results(
    general: list[dict],
    named: list[dict],
    k: int,
    pinned: Optional[list[dict]] = None,
) -> list[dict]:
    """Merge pinned + named-document hits with the general pool into the top-k.

    ``pinned`` chunks (an explicit section/identifier lookup the user typed,
    e.g. "§ 200.1") get first claim on slots — the user named exactly what they
    want. Named-document chunks are guaranteed the next share so a file asked
    about by name isn't crowded out. The rest is filled from the general
    semantic pool with a per-source diversity cap. Any slots the general pool
    can't fill are backfilled from leftover pinned/named hits, so a query that
    *only* names a section (nothing clears the semantic floor) still returns
    the section's chunks instead of abstaining.
    """
    half = max(1, -(-k // 2))  # ceil(k/2)
    max_per_source = max(2, half)
    pinned = pinned or []
    final: list[dict] = []
    seen: set = set()

    def take(items: list[dict], limit: int) -> None:
        for r in items:
            if limit <= 0 or len(final) >= k:
                break
            cid = r.get("chunk_id")
            if cid is not None and cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            final.append(r)
            limit -= 1

    # 1. Section/identifier hits the user asked for by name — highest priority,
    #    but capped at half so they can't starve co-asked questions.
    take(pinned, half)
    # 2. Named-source hits — half of whatever slots remain.
    take(named, max(1, -(-(k - len(final)) // 2)))
    # 3. General semantic pool with per-source diversity.
    remaining = [r for r in general if r.get("chunk_id") not in seen]
    for r in _select_diverse_chunks(remaining, k - len(final), max_per_source):
        cid = r.get("chunk_id")
        if cid is not None and cid in seen:
            continue
        if cid is not None:
            seen.add(cid)
        final.append(r)
    # 4. Backfill unused slots from leftover pinned/named (section-only query).
    if len(final) < k:
        take([r for r in pinned + named if r.get("chunk_id") not in seen],
             k - len(final))
    return final[:k]


# A CFR-style section citation: an optional § / "section" / "sec." lead-in
# followed by a "part.section" number (e.g. "200.1", "200.512"). The lead-in is
# optional so a bare "200.1" is still caught, but we require the dotted form so
# plain years or dollar amounts ("2024", "200") don't trip it.
_SECTION_REF_RE = re.compile(
    r"(?:§+\s*|\bsections?\s+|\bsec\.?\s+)?(\d{1,4}\.\d+[a-z]?)",
    re.IGNORECASE,
)

# An identifier-shaped token: an upper-case alphanumeric run joined by hyphens
# and carrying at least one digit — role and award identifiers ("CSU-PI-001",
# "NSF-2024-117"), OMB numbers, contract numbers. Both the hyphen and the digit
# are required so ordinary capitalised words ("NSF", "CHIPS") and hyphenated
# prose ("cost-sharing", "NSF-funded") never pin.
_IDENTIFIER_REF_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")

# A phrase the user put in double quotes — an explicit "find me this string".
# Apostrophes are deliberately excluded so ordinary contractions can't pair up
# into a bogus quoted span.
_QUOTED_PHRASE_RE = re.compile("[\"“]([^\"“”\n]{3,60})[\"”]")

# The noun phrase a definitional question is asking about: the words directly
# after a "what/which is/are" frame. "What are the three field sites?" -> "field
# sites". Only this frame fires, and only when two content words survive the
# lead-in strip, so ordinary prose and open-ended requests pin nothing.
_ASKED_PHRASE_RE = re.compile(
    r"\bwh(?:at|ich)\s+(?:is|are|was|were)\b([^?.,;:!\n]{0,60})",
    re.IGNORECASE,
)

# Articles, demonstratives, possessives and counts that lead a questioned noun
# phrase without narrowing it — stripped so "the three field sites" pins on
# "field sites".
_PHRASE_LEAD_WORDS = frozenset({
    "a", "an", "the", "this", "that", "these", "those", "its", "their", "our",
    "my", "your", "his", "her", "all", "any", "some", "each", "every", "both",
    "other", "main", "key",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten",
})

# Function words a noun phrase does not run through. "the name of the vendor"
# is not asking for the string "name of the" — it is asking about the vendor —
# so the phrase ends at the first of these. Without this the channel pins
# prepositional fragments, which on a small knowledge base are common enough to
# fill the lane with every chunk that happens to say "name of the".
_PHRASE_STOP_WORDS = frozenset({
    "of", "in", "on", "for", "to", "from", "with", "by", "at", "as", "and",
    "or", "but", "between", "about", "into", "over", "under", "per", "via",
    "that", "which", "who", "whom", "whose", "if", "when", "than", "then",
    "there", "here", "it", "we", "you", "i", "they", "he", "she",
})

# At most this many *inferred* terms pin per turn: the lane only has ceil(k/2)
# slots, so fanning out further just costs lexical lookups nothing can use.
# Section numbers don't count against it — "compare 200.1, 200.2, 200.3, 200.4
# and 200.5" is five deliberate citations, and dropping the fifth would regress
# a feature that predates this lane.
_MAX_PIN_TERMS = 4

# A term found in more chunks than this isn't pointing anywhere in particular —
# it's boilerplate, like the project number stamped in every running header —
# and pinning an arbitrary handful of its hits would spend slots the semantic
# pool needs. Section numbers the user cited explicitly are exempt: those are a
# deliberate lookup, however often the corpus repeats them.
#
# Note what this does *not* protect: a flat count can only fire on a collection
# big enough to reach it, so on a small knowledge base every term survives it.
# That is why the phrase channel above has to be narrow on its own terms rather
# than leaning on this.
_MAX_PIN_TERM_HITS = 24


def _extract_pin_terms(message: str) -> list[str]:
    """Pull the literal strings worth a lexical lookup out of the message.

    Three shapes, in priority order:

    * CFR-style section numbers — "§ 200.1", "section 200.1", a bare "200.1";
    * identifier-shaped tokens — "CSU-PI-001", "NSF-2024-117";
    * a short phrase the user quoted, or the noun phrase a "what is/are …"
      question asks about.

    All three name something the embedding barely represents: a bi-encoder
    scores an identifier or a rare bigram as near-noise, so the chunk that
    literally contains it can rank far below chunks that merely echo the
    question's vocabulary. Deduped, order-preserving, and capped at
    ``_MAX_PIN_TERMS`` for everything but section citations.

    A *phrase* that merely wraps a term already collected is dropped: "what is
    the CSU-PI-001 role?" yields the identifier, not the identifier plus
    "CSU-PI-001 role", which would spend two of the four slots and four lexical
    lookups on one concept. Single tokens are exempt from that check — one
    citation is routinely a text prefix of another ("200.1" of "200.10",
    "AA-1" of "AA-11"), and both are separate lookups the user asked for.
    """
    seen: set = set()
    terms: list[str] = []

    def add(term: str, *, cited: bool = False) -> None:
        if not term or term in seen:
            return
        if " " in term and any(t in term for t in terms):
            return
        if not cited and sum(1 for t in terms if not _is_section(t)) >= _MAX_PIN_TERMS:
            return
        seen.add(term)
        terms.append(term)

    message = message or ""
    for m in _SECTION_REF_RE.finditer(message):
        add(m.group(1), cited=True)
    for m in _IDENTIFIER_REF_RE.finditer(message):
        token = m.group(0)
        if any(c.isdigit() for c in token):
            add(token)
    for m in _QUOTED_PHRASE_RE.finditer(message):
        add(" ".join(m.group(1).split()))
    for m in _ASKED_PHRASE_RE.finditer(message):
        add(_questioned_phrase(m.group(1)))
    return terms


def _is_section(term: str) -> bool:
    """True for a dotted ``part.section`` citation the user typed verbatim."""
    return bool(_SECTION_REF_RE.fullmatch(term))


def _questioned_phrase(tail: str) -> str:
    """Reduce the tail of a "what is/are …" question to its noun phrase.

    Strips leading articles, possessives and counts, then keeps words up to the
    first function word — a noun phrase that runs through "of" or "for" is not
    one, and "name of the" is a fragment of English rather than a string worth
    looking for. Returns "" unless at least two words with some substance
    survive, so "what are you?" and "what is this about?" pin nothing.
    """
    words = tail.split()
    while words and words[0].lower().strip("'’") in _PHRASE_LEAD_WORDS:
        words.pop(0)
    kept: list[str] = []
    for word in words[:3]:
        if word.lower().strip(".,;:'’") in _PHRASE_STOP_WORDS:
            break
        kept.append(word)
    if len(kept) < 2 or not any(len(w) >= 4 for w in kept):
        return ""
    return " ".join(kept)


def _rank_pinned_chunks(chunks: list[dict], pattern: re.Pattern) -> list[dict]:
    """Order lexical hits by how central the pinned term is to each chunk.

    ``get_kb_chunks_containing`` returns ChromaDB storage order, which is
    arbitrary. When a term hits more chunks than the pin lane has slots, that
    ordering decides whether the chunk the user actually asked about reaches
    the context at all — so rank by how many times the chunk names the term,
    then by how early the first mention falls. A chunk that names it in its
    heading is about it; one that names it once on the last line only mentions
    it. Ties keep storage order (``sorted`` is stable).
    """
    def key(item: dict) -> tuple:
        starts = [m.start() for m in pattern.finditer(item.get("content") or "")]
        return (-len(starts), starts[0] if starts else len(item.get("content") or ""))

    return sorted(chunks, key=key)


async def _retrieve_pinned_chunks(
    kb_uuid: str, terms: list[str], limit_per_ref: int = 6,
) -> list[dict]:
    """Lexically fetch chunks that literally contain each pin term.

    A candidate pool comes from ChromaDB's substring filter (which would also
    match "200.10" for "200.1"), then a word-boundary regex keeps only exact
    matches so "§ 200.1" doesn't drag in "§ 200.10". Runs off the embedding
    index entirely — the point is to rescue identifier and phrase lookups that
    vector search can't see.

    ``$contains`` is case-sensitive, so a multi-word phrase is also looked up
    in the capitalisations a heading or a title would actually use.
    """
    from app.services.document_manager import get_document_manager

    dm = get_document_manager()
    out: list[dict] = []
    seen: set = set()
    for term in terms:
        is_section = _is_section(term)
        is_phrase = " " in term
        flags = re.IGNORECASE if is_phrase else 0
        exact = re.compile(rf"(?<!\d){re.escape(term)}(?!\d)", flags)
        variants = [term]
        if is_phrase:
            variants += [term.lower(), term.lower().capitalize(), term.title()]
        candidates: list[dict] = []
        pooled: set = set()
        for variant in dict.fromkeys(variants):
            for r in await asyncio.to_thread(
                dm.get_kb_chunks_containing, kb_uuid, variant,
                _MAX_PIN_TERM_HITS + 1,
            ):
                cid = r.get("chunk_id")
                if cid is not None and cid in pooled:
                    continue
                if cid is not None:
                    pooled.add(cid)
                candidates.append(r)
        if not is_section and len(candidates) > _MAX_PIN_TERM_HITS:
            continue
        kept = 0
        for r in _rank_pinned_chunks(candidates, exact):
            if kept >= limit_per_ref:
                break
            if not exact.search(r.get("content") or ""):
                continue
            cid = r.get("chunk_id")
            if cid is not None and cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            out.append(r)
            kept += 1
    return out


def _split_questions(message: str) -> list[str]:
    """Split a message into standalone questions when it asks several at once.

    Returns the individual ``?``-terminated questions only when there are at
    least two — otherwise an empty list, so the single-question path is
    untouched. Multiple questions in one turn otherwise share a single blended
    embedding and one top-k budget, so a secondary question can retrieve zero
    supporting chunks and go unanswered even though its answer is in the KB.
    """
    segments = re.split(r"(?<=\?)\s+", (message or "").strip())
    questions = [s.strip() for s in segments if s.strip().endswith("?")]
    return questions if len(questions) >= 2 else []


def _round_robin_merge(pools: list[list[dict]]) -> list[dict]:
    """Interleave per-question result pools so each question is fairly ranked.

    Taking each pool's #1 before any pool's #2 means the downstream top-k trim
    can't spend the whole budget on the first (or loudest) question — every
    question contributes before any question gets a second chunk. Deduped by
    chunk_id.
    """
    import itertools

    merged: list[dict] = []
    seen: set = set()
    for tier in itertools.zip_longest(*pools):
        for r in tier:
            if r is None:
                continue
            cid = r.get("chunk_id")
            if cid is not None and cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            merged.append(r)
    return merged


async def _build_kb_segment(
    kb_uuid: str,
    message: str,
    model_name: str,
    manifest: Optional[list[dict]] = None,
    history: Optional[list[ModelMessage]] = None,
    user_id: Optional[str] = None,
) -> tuple[Optional[DocumentSegment], list[dict]]:
    """Retrieve KB context for one chat turn.

    Returns ``(segment, kb_sources)``; the segment is None when nothing clears
    the KB's tuned relevance floor, so the caller falls through to the empty-KB
    prompt and the model abstains instead of answering from junk.
    """
    from app.services.kb_validation_service import (
        _ensure_system_config_loaded,
        condense_retrieval_query,
        retrieve_kb_chunks,
    )

    # The retrieval pipeline's optional LLM steps (rewrite/rerank) build their
    # agents from the ContextVar'd SystemConfig snapshot.
    await _ensure_system_config_loaded()

    # Retrieval is per-turn and sees only the current message, so a follow-up
    # like "what about year 2?" retrieves nothing useful even though the model
    # "remembers" the topic. Condense anaphoric messages into a standalone
    # search query using recent turns; the raw message still drives the answer
    # prompt and rerank scoring.
    retrieval_query: Optional[str] = None
    if history and _looks_anaphoric(message):
        recent = _recent_turns(history)
        if recent:
            retrieval_query, _ = await condense_retrieval_query(
                message, recent, model_name,
            )

    # Honour the KB's tuned retrieval knobs (k, min_similarity, query
    # rewriting, rerank). cfg.model / prompt_variant / answer_temperature
    # deliberately do NOT apply here — they tune the headless RAG answer
    # generator, while chat keeps its own agent, prompt, and settings.
    # Over-fetch 3× so the diversity pass below has a pool to select from.
    #
    # Multi-question turns: when the user asks several questions at once, one
    # blended embedding and one top-k budget let a secondary question retrieve
    # nothing. Retrieve per sub-question and round-robin the pools so each is
    # fairly represented before the top-k trim. Skipped for anaphoric turns
    # (single condensed intent) and single-question turns (unchanged path).
    sub_questions = _split_questions(message) if retrieval_query is None else []
    if sub_questions:
        pools = await asyncio.gather(*[
            retrieve_kb_chunks(
                kb_uuid, q, model_name, per_step_timeout=6.0,
                overfetch_multiplier=3,
            )
            for q in sub_questions
        ])
        kb_results = _round_robin_merge([p[0] for p in pools])
        rag_cfg = pools[0][1]
    else:
        kb_results, rag_cfg, _ = await retrieve_kb_chunks(
            kb_uuid, message, model_name, per_step_timeout=6.0,
            overfetch_multiplier=3,
            retrieval_query=retrieval_query,
        )

    # Literal-string targeting: a bare identifier like "§ 200.1" or
    # "CSU-PI-001", and a rare phrase like "field sites", carry almost no
    # semantic signal, so vector search misses the very chunk that contains
    # them — and near-identical documents that differ only by an identifier are
    # not separable at all. Fetch those chunks lexically and pin them into the
    # final slots.
    pinned_results: list[dict] = []
    pin_terms = _extract_pin_terms(message)
    if pin_terms:
        pinned_results = await _retrieve_pinned_chunks(kb_uuid, pin_terms)

    # Named-document targeting: when the message mentions a project file by
    # name, run a second search restricted to that source and guarantee it a
    # share of the final slots — short documents (timelines, letters) are
    # otherwise routinely out-ranked by long narrative documents.
    named_results: list[dict] = []
    matched_names = _match_named_sources(message, manifest or [])
    if matched_names:
        named_results, _, _ = await retrieve_kb_chunks(
            kb_uuid, message, model_name,
            config=rag_cfg.with_overrides(rerank="off", query_rewriting=False),
            source_filter=matched_names,
            per_step_timeout=6.0,
            retrieval_query=retrieval_query,
        )

    kb_results = _compose_kb_results(
        kb_results, named_results, rag_cfg.k, pinned=pinned_results,
    )
    if not kb_results:
        logger.warning("KB query returned no results for kb_uuid=%s", kb_uuid)
        return None, []

    kb_sources: list[dict] = []
    snippet_blocks: list[str] = []
    any_approximate = False
    for r in kb_results:
        meta = r.get("metadata") or {}
        src = meta.get("source_name", "Unknown")
        page = meta.get("page")
        sheet = meta.get("sheet")
        approximate = bool(meta.get("page_approximate"))
        locator = locator_for_meta(meta)
        label = f"{src} ({locator})" if locator else src
        any_approximate = any_approximate or approximate
        snippet_blocks.append(f"\n**Source: {label}**\n{r['content']}\n")
        kb_sources.append({
            "document_id": meta.get("source_id"),
            "document_title": src,
            "page": page if isinstance(page, int) else None,
            "page_approximate": approximate,
            "sheet": sheet if isinstance(sheet, str) else None,
            "chunk_id": r.get("chunk_id"),
            "score": r.get("score"),
            "similarity": r.get("similarity"),
            "content_preview": (r.get("content") or "")[:240],
        })
    kb_text = (
        "\n\n## Retrieved Knowledge Base Snippets\n"
        "_The following are partial excerpts from a larger corpus, ranked "
        "by similarity to the user's question. They may be incomplete, "
        "off-topic, or miss the best answer. Cite by filename only when a "
        "snippet actually supports your claim._\n"
    )
    if any_approximate:
        # A tilde the model has not had explained to it does not survive: it
        # gets normalised away and the estimate is restated as fact. Measured
        # five times out of five at temperature 0 on a fully interpolated
        # document, which is why page_note_for rules out exactness by name for
        # document chat. The same labels reach the model here.
        kb_text += (
            "_A page written as `p. ~N` is an *estimate* — that source was "
            "scanned, so page positions were interpolated rather than read. "
            "Give such pages as approximate, e.g. \"around p. 4\". Never state "
            "one as exact and never say a passage is \"explicitly\" or "
            "\"clearly\" on it._\n"
        )
    kb_text += "".join(snippet_blocks)

    # Attach the openable SmartDocument behind each cited source, so the UI can
    # offer "open the document at the cited page" and not just a text preview —
    # the page numbers are a retrieval heuristic, so verifying them in the
    # document itself is exactly what a reader needs to do. URL sources,
    # deleted documents, and documents this reader cannot view resolve to
    # nothing and stay preview-only.
    from app.services.knowledge_service import resolve_openable_documents

    openable = await resolve_openable_documents(
        [s["document_id"] for s in kb_sources if s.get("document_id")],
        user_id=user_id,
    )
    for src_dict in kb_sources:
        doc_uuid = openable.get(src_dict.get("document_id") or "")
        if doc_uuid:
            src_dict["document_uuid"] = doc_uuid

    return DocumentSegment(label="kb", text=kb_text), kb_sources


def _build_interrupted_body(full_response: list[str], reason: str) -> str:
    """Compose an assistant-turn body from any partial stream content + a reason."""
    partial = _THINK_BLOCK_RE.sub("", "".join(full_response)).strip()
    if partial:
        return f"{partial}\n\n_(response interrupted — {reason})_"
    return f"_(no response — {reason})_"


async def _save_failed_assistant_turn(
    conversation: ChatConversation,
    body: str,
    activity_id: Optional[str],
    reason: str,
    thinking: Optional[str] = None,
    thinking_duration: Optional[float] = None,
) -> None:
    """Persist a placeholder assistant turn after a failure or cancellation.

    Why: chat.py saves the user message before streaming; if the LLM call
    fails or is cancelled, the conversation would otherwise be left with an
    orphan user turn. pydantic-ai's message_history rejects consecutive user
    turns, so the *next* request would error or silently drop messages.
    """
    await conversation.add_message(
        ChatRole.ASSISTANT,
        body,
        thinking=thinking,
        thinking_duration=thinking_duration,
    )
    if not activity_id:
        return
    ev = await ActivityEvent.get(activity_id)
    if not ev:
        return
    ev.status = ActivityStatus.FAILED.value
    ev.error = reason[:2000]
    from datetime import datetime, timezone
    ev.finished_at = datetime.now(timezone.utc)
    ev.last_updated_at = datetime.now(timezone.utc)
    reloaded = await ChatConversation.get(conversation.id)
    ev.message_count = len(reloaded.messages) if reloaded else 0
    await ev.save()


async def _finalize(
    conversation: ChatConversation,
    assistant_message: str,
    documents: list[SmartDocument],
    usage,
    activity_id: Optional[str],
    user_id: str,
    thinking: Optional[str] = None,
    thinking_duration: Optional[float] = None,
    citations: Optional[list[dict]] = None,
) -> None:
    """Save assistant message and update activity metrics."""
    await conversation.add_message(
        ChatRole.ASSISTANT,
        assistant_message,
        thinking=thinking,
        thinking_duration=thinking_duration,
        citations=citations,
    )

    if activity_id:
        ev = await ActivityEvent.get(activity_id)
        if ev:
            # Reload conversation to get updated message count
            conversation = await ChatConversation.get(conversation.id)
            ev.message_count = len(conversation.messages) if conversation else 0
            ev.status = ActivityStatus.COMPLETED.value
            if usage:
                ev.tokens_input = usage.input_tokens or 0
                ev.tokens_output = usage.output_tokens or 0
                ev.total_tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)
            ev.documents_touched = len(documents)
            from datetime import datetime, timezone
            ev.finished_at = datetime.now(timezone.utc)
            ev.last_updated_at = datetime.now(timezone.utc)
            await ev.save()

            # Generate an AI title after the first exchange
            if ev.message_count <= 2:
                try:
                    from app.tasks.activity_tasks import generate_activity_description_task
                    generate_activity_description_task.delay(
                        str(ev.id), ev.type, [d.uuid for d in documents]
                    )
                except Exception as _e:
                    logger.warning("Could not queue activity title generation: %s", _e)
