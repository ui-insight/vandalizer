"""Chat service  - streaming chat with full document context."""

import asyncio
import datetime
import json
import logging
import re
import time
from typing import AsyncGenerator, Optional

from pydantic_ai.agent import Agent
from pydantic_ai.usage import UsageLimitExceeded, UsageLimits
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
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
from app.models.user import User
from app.services.access_control import TeamAccessContext
from app.services.config_service import get_llm_model_by_name, get_user_model_name
from app.services.context_budget import (
    DocumentSegment,
    plan_and_compact_context,
)
from app.services.llm_service import (
    AGENTIC_CHAT_SYSTEM_PROMPT,
    build_project_kb_empty_reminder,
    create_agentic_chat_agent,
    create_chat_agent,
    DEFAULT_CHAT_SYSTEM_PROMPT,
    DOCUMENT_CHAT_RULES,
    FIRST_SESSION_SYSTEM_PROMPT,
    HELP_CHAT_RULES,
    KB_CHAT_RULES,
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


def _classify_stream_error(exc: BaseException) -> tuple[str, str]:
    """Classify a chat stream error into (severity, user_message).

    severity is "warning" for transient/external/user-input issues that aren't
    actionable bugs — these stay out of Sentry's error stream. "error" is the
    fallback for unexpected exceptions.
    """
    text = str(exc)
    lower = text.lower()

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

    # Unexpected failure. Never surface the raw exception to the user — it leaks
    # stack-trace-shaped text that breaks the assistant's voice. The caller logs
    # the original exception for debugging.
    return "error", (
        "Something went wrong while generating that response. Please try again — "
        "if it keeps happening, let your administrator know."
    )


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


def _brand_org_text(text: str, org: str | None) -> str:
    """White-label chat-visible copy: swap the default product name for the
    deployment's org name (same convention as email branding).

    Also neutralizes the built-in "University of Idaho" home institution, which
    is true for the default Vandalizer build but wrong (and off-brand) on a
    white-labeled deployment. The identity/onboarding prompts are the only
    places that phrasing appears, so collapsing the two fixed patterns keeps the
    grammar clean without a brittle blanket strip.
    """
    if not org or org == "Vandalizer":
        return text
    text = text.replace("Vandalizer", org)
    text = text.replace(
        "research administration at the University of Idaho",
        "research administration",
    )
    text = text.replace(
        "built at the University of Idaho for research administration",
        "built for research administration",
    )
    return text


def _wrap_system_reminder(text: str) -> str:
    """Wrap a volatile context block for injection into the user prompt.

    Volatile per-turn context (workspace inventory, open documents, project
    state, mode rules) rides inside <system-reminder> tags on the CURRENT
    user message instead of the system prompt, so the instructions — and with
    them the provider prompt cache — stay byte-stable across turns. The static
    prompts teach the model these tags are system context, not user text
    (llm_service.SYSTEM_REMINDER_SECTION).
    """
    return f"<system-reminder>\n{text.strip()}\n</system-reminder>"


# Prompt-cache observability (uplift plan Phase 1.5). Per-conversation
# baseline of cache-read tokens per model request, so an unexpected drop —
# >5% AND >=2000 tokens, the thresholds Claude Code's cache-break detector
# uses — is logged. Warning-level only (a cost signal, not a failure — see
# the Sentry noise convention). Process-local and best-effort: multi-worker
# deployments each track their own baseline, and a miss just costs a log line.
_CACHE_READ_BASELINE: dict[str, int] = {}
_CACHE_BASELINE_MAX = 1024


def _note_cache_usage(conversation_uuid: str, usage, model_name: str) -> tuple[int, int]:
    """Record per-turn cache token usage; warn on an unexpected cache break.

    Returns ``(cache_read_tokens, cache_write_tokens)`` run totals for the
    usage chunk. The regression comparison is normalized per model request:
    a turn with N tool-loop requests reads the cached prefix N times, so raw
    run totals would false-positive on the next low-tool-count turn.
    """
    cache_read = int(getattr(usage, "cache_read_tokens", 0) or 0)
    cache_write = int(getattr(usage, "cache_write_tokens", 0) or 0)
    requests = max(int(getattr(usage, "requests", 1) or 1), 1)
    per_request_read = cache_read // requests

    prev = _CACHE_READ_BASELINE.get(conversation_uuid)
    if (
        prev is not None
        and prev - per_request_read >= 2000
        and prev - per_request_read > prev * 0.05
    ):
        logger.warning(
            "Prompt cache regression: conversation=%s model=%s per-request "
            "cache_read dropped %d -> %d (run totals: read=%d write=%d requests=%d)",
            conversation_uuid, model_name, prev, per_request_read,
            cache_read, cache_write, requests,
        )
    if (
        conversation_uuid not in _CACHE_READ_BASELINE
        and len(_CACHE_READ_BASELINE) >= _CACHE_BASELINE_MAX
    ):
        _CACHE_READ_BASELINE.pop(next(iter(_CACHE_READ_BASELINE)))
    _CACHE_READ_BASELINE[conversation_uuid] = per_request_read
    return cache_read, cache_write


def _brand_org_json_chunk(chunk: str, org: str | None) -> str:
    """Brand a serialized stream chunk. The replacement is JSON-escaped so an
    org name containing quotes can't corrupt the chunk."""
    if not org or org == "Vandalizer":
        return chunk
    import json as _json
    return chunk.replace("Vandalizer", _json.dumps(org)[1:-1])


async def _run_scripted_demo(
    onboarding_context,
    conversation: ChatConversation,
    user,
    user_id: str,
    activity_id: Optional[str],
    sys_config_doc: dict,
) -> AsyncGenerator[str, None]:
    """Deterministic onboarding demo — scripted tool calls, template narration.

    Runs the same tools the LLM agent would, but in a fixed sequence so the
    demo is identical every time.  Yields the same chunk format as the agent
    streaming path so the frontend renders tool status lines, extraction
    tables, quality badges, and interleaved text identically.
    """
    import asyncio
    import uuid

    from app.models.activity import ActivityEvent, ActivityStatus
    from app.models.search_set import SearchSet
    from app.models.validation_run import ValidationRun

    ctx = onboarding_context
    team_id = str(user.current_team) if user.current_team else None
    full_text_parts: list[str] = []
    all_tool_calls: list[dict] = []
    all_tool_results: list[dict] = []
    demo_segments: list[dict] = []

    def _text(content: str):
        full_text_parts.append(content)
        demo_segments.append({"kind": "text", "content": content})
        return json.dumps({"kind": "text", "content": content}) + "\n"

    def _tool_call(name: str, call_id: str, args: dict):
        data = {"tool_name": name, "tool_call_id": call_id, "args": args}
        all_tool_calls.append(data)
        demo_segments.append({"kind": "tool_call", "call": data})
        return json.dumps({"kind": "tool_call", **data}) + "\n"

    def _tool_result(name: str, call_id: str, content, quality=None):
        data = {"tool_name": name, "tool_call_id": call_id, "content": content, "quality": quality}
        all_tool_results.append(data)
        demo_segments.append({"kind": "tool_result", "result": data})
        return json.dumps({"kind": "tool_result", **data}) + "\n"

    try:
        # -- Step 1: Introduction ------------------------------------------------
        yield _text(
            "Watch me do something most AI tools can't.\n\n"
            "I'm going to pull structured data out of a real NSF grant proposal — "
            "and tell you, up front, *how accurate it is*. Not a hope. A **measured "
            "number**, from real test cases.\n\n"
            "Whether your week is grants, IRB, contracts, or something else, "
            "the pattern is the same: drop in the doc, run a validated template, "
            "trust the number. Here's what that looks like.\n\n"
        )

        # -- Step 2: Search library ----------------------------------------------
        call_id_1 = str(uuid.uuid4())[:12]
        yield _tool_call("search_library", call_id_1, {"query": "NSF", "kind": "search_set"})
        await asyncio.sleep(0.05)  # real flush so the spinner reaches the client before slow work blocks the loop

        from app.services.library_service import search_libraries
        lib_results = await search_libraries(user, query="NSF", team_id=team_id, kind="search_set")

        yield _tool_result("search_library", call_id_1, lib_results[:20])

        # Find the specific template info for narration
        template_name = ctx.extraction_set_title or "NSF Grant Proposal"
        # Look up validation data for narration
        ss = await SearchSet.find_one(SearchSet.uuid == ctx.extraction_set_uuid)
        latest_run = await ValidationRun.find(
            ValidationRun.item_kind == "search_set",
            ValidationRun.item_id == ctx.extraction_set_uuid,
        ).sort("-created_at").first_or_none()

        if latest_run and latest_run.accuracy is not None:
            acc_pct = round(latest_run.accuracy * 100)
            yield _text(
                f'Found **"{template_name}"** — a verified template that\'s been '
                f"validated at **{acc_pct}% accuracy** across "
                f"{latest_run.num_test_cases} test cases "
                f"and {latest_run.num_runs} validation runs. "
                "That means you know how reliable the results are before you even start.\n\n"
                "Now watch — I'll run it against the sample proposal…\n\n"
            )
        else:
            yield _text(
                f'Found **"{template_name}"** — a verified extraction template. '
                "Let me run it against the sample proposal…\n\n"
            )

        # -- Step 3: Run extraction -----------------------------------------------
        call_id_2 = str(uuid.uuid4())[:12]
        yield _tool_call("run_extraction", call_id_2, {
            "extraction_set_uuid": ctx.extraction_set_uuid,
            "document_uuids": [ctx.sample_doc_uuid],
        })
        await asyncio.sleep(0.05)  # real flush so the spinner reaches the client before slow work blocks the loop before LLM extraction runs

        # Execute the actual extraction
        from app.services.extraction_engine import ExtractionEngine

        items = await ss.get_extraction_items() if ss else []
        keys = [item.searchphrase for item in items if item.searchphrase]
        field_metadata = [
            {"key": item.searchphrase, "is_optional": item.is_optional, "enum_values": item.enum_values}
            for item in items if item.searchphrase
        ]

        doc = await SmartDocument.find_one(SmartDocument.uuid == ctx.sample_doc_uuid)
        doc_text = doc.raw_text if doc else ""
        doc_title = doc.title if doc else "Sample Document"

        extraction_result: dict = {"error": "Extraction failed"}
        quality_sidecar = None

        if doc_text and keys:
            def _extract():
                engine = ExtractionEngine(system_config_doc=sys_config_doc, domain=ss.domain if ss else None)
                results = engine.extract(
                    extract_keys=keys,
                    doc_texts=[doc_text],
                    extraction_config_override=ss.extraction_config if ss else None,
                    field_metadata=field_metadata,
                )
                return results

            try:
                entities = await asyncio.wait_for(
                    asyncio.to_thread(_extract), timeout=120,
                )
            except asyncio.TimeoutError:
                logger.warning("Scripted demo extraction timed out")
                entities = []

            extraction_result = {
                "extraction_set": template_name,
                "fields": keys,
                "documents": [doc_title],
                "entities": entities[:50],
                "entity_count": len(entities),
            }

            if latest_run and latest_run.score is not None:
                score = latest_run.score
                tier = "excellent" if score >= 90 else "good" if score >= 75 else "fair" if score >= 50 else "poor"
                quality_sidecar = {
                    "score": score,
                    "tier": tier,
                    "grade": latest_run.grade,
                    "accuracy": latest_run.accuracy,
                    "consistency": latest_run.consistency,
                    "last_validated_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
                    "num_test_cases": latest_run.num_test_cases,
                    "num_runs": latest_run.num_runs,
                    "active_alerts": [],
                }

        yield _tool_result("run_extraction", call_id_2, extraction_result, quality=quality_sidecar)

        entity_count = extraction_result.get("entity_count", 0)
        field_count = len(keys) if keys else 0

        if latest_run and latest_run.accuracy is not None:
            acc_pct = round(latest_run.accuracy * 100)
            yield _text(
                f"That pulled out **{field_count} structured fields** in seconds. "
                f"Because this template was validated at **{acc_pct}% accuracy**, "
                "you can trust these results for reporting, budgeting, and compliance — "
                "not just hope the LLM got it right.\n\n"
            )
        else:
            yield _text(
                f"Extracted **{entity_count} entities** with **{field_count} fields** each. "
            )

        # -- Step 4: Knowledge base (if available) --------------------------------
        if ctx.kb_uuid:
            call_id_3 = str(uuid.uuid4())[:12]
            yield _text(
                "Let me cross-reference the budget against the NSF PAPPG policy guide…\n\n"
            )
            yield _tool_call("search_knowledge_base", call_id_3, {
                "query": "NSF budget indirect costs MTDC equipment exclusion",
                "kb_uuid": ctx.kb_uuid,
            })
            await asyncio.sleep(0.05)  # real flush so the spinner reaches the client before slow work blocks the loop

            from app.services.document_manager import get_document_manager
            dm = get_document_manager()
            kb_results = await asyncio.to_thread(
                dm.query_kb, ctx.kb_uuid, "NSF budget indirect costs MTDC equipment exclusion", 8,
            )
            kb_content = [
                {"content": r.get("content", ""), "source_name": r.get("metadata", {}).get("source_name", "unknown")}
                for r in kb_results
            ]
            yield _tool_result("search_knowledge_base", call_id_3, kb_content)

            if kb_results:
                yield _text(
                    "The PAPPG confirms that **equipment over $5,000 is excluded from the "
                    "MTDC base** for indirect cost calculations — which lines up with the "
                    "$61,100 equipment line in the extracted budget. "
                    "This kind of automated cross-reference catches policy issues before they "
                    "become audit findings.\n\n"
                )
            else:
                yield _text(
                    "The knowledge base query didn't return strong matches this time, "
                    "but with more reference content loaded, Vandalizer can cross-reference "
                    "any extracted data against policy documents automatically.\n\n"
                )

        # -- Step 5: Hand off ------------------------------------------------------
        yield _text(
            "That's the pattern: **validated extraction** you can measure and trust"
        )
        if ctx.kb_uuid:
            yield _text(
                ", plus **policy cross-reference** that catches compliance issues automatically"
            )
        yield _text(
            ".\n\n"
            "**Now do it with one of yours.** Drop in a grant, IRB protocol, "
            "contract, or any document you actually work with — I'll find the "
            "right template and run it.\n\n"
            "[ACTION:upload-docs]Try it on one of yours[/ACTION]\n\n"
            "Want the bigger picture on why validated workflows matter for "
            "research admin? [ACTION:start-cert]Start the Certification Program[/ACTION]\n\n"
            "Or just ask me anything — I know this tool and your documents.\n"
        )

        # -- Finalize: save to conversation & activity ----------------------------
        # Brand persisted copy the same way the streamed chunks are branded so
        # history reloads match what the user saw live.
        _org = (sys_config_doc or {}).get("org_name") or ""
        assistant_message = _brand_org_text("".join(full_text_parts), _org)
        if _org and _org != "Vandalizer":
            demo_segments = [
                {**seg, "content": _brand_org_text(seg["content"], _org)}
                if seg.get("kind") == "text" else seg
                for seg in demo_segments
            ]
        await _finalize(
            conversation, assistant_message, [doc] if doc else [],
            None, activity_id, user_id,
            tool_calls=all_tool_calls or None,
            tool_results=all_tool_results or None,
            segments=demo_segments or None,
        )

    except Exception as e:
        logger.error("Scripted demo error: %s", e, exc_info=True)
        yield json.dumps({"kind": "error", "content": f"Demo error: {e}"}) + "\n"
        if activity_id:
            ev = await ActivityEvent.get(activity_id)
            if ev:
                ev.status = ActivityStatus.FAILED.value
                ev.error = str(e)[:2000]
                await ev.save()


def _hold_message_for_unreadable_docs(
    *,
    document_uuids: list[str],
    doc_segments: list,
    kb_sources: list,
    attachment_segments: list,
    skipped_no_text: list[str],
    errored_docs: list[str],
) -> Optional[str]:
    """Honest holding reply when attached docs aren't readable yet.

    Returns a message to stream (and persist) instead of running the agent when
    the user explicitly attached documents but none yielded readable text —
    either extraction is still in flight (``skipped_no_text``) or it failed
    (``errored_docs``) — and there's no other grounding (KB snippets, pasted
    attachments). Returns ``None`` when the agent should run normally.
    """
    if not (
        document_uuids
        and not doc_segments
        and not kb_sources
        and not attachment_segments
        and (skipped_no_text or errored_docs)
    ):
        return None
    if skipped_no_text:
        names = ", ".join(skipped_no_text[:3]) + ("…" if len(skipped_no_text) > 3 else "")
        many = len(skipped_no_text) != 1
        return (
            f"I can't read {names} yet — {'they are' if many else 'it is'} still being "
            f"processed (text extraction/OCR). I'll analyze {'them' if many else 'it'} as "
            "soon as that finishes — ask again in a moment."
        )
    names = ", ".join(errored_docs[:3]) + ("…" if len(errored_docs) > 3 else "")
    many = len(errored_docs) != 1
    return (
        f"I couldn't read {names} — text extraction failed, so there's nothing for me "
        f"to work from. Open {'each document' if many else 'the document'} and use "
        '"Retry extraction", then ask again.'
    )


async def chat_stream(
    message: str,
    document_uuids: list[str],
    conversation_uuid: str,
    user_id: str,
    activity_id: Optional[str] = None,
    settings=None,
    model_override: Optional[str] = None,
    kb_uuid: Optional[str] = None,
    project_uuid: Optional[str] = None,
    include_onboarding_context: bool = False,
    is_first_session: bool = False,
    run_demo: bool = False,
    user: Optional[User] = None,
    team_access: Optional[TeamAccessContext] = None,
    onboarding_context=None,
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

    # ---------------------------------------------------------------------------
    # Scripted demo: deterministic tool calls + template narration.
    # Bypasses the LLM agent entirely so the demo is 100% reliable.
    # ---------------------------------------------------------------------------
    if run_demo and onboarding_context and onboarding_context.extraction_set_uuid:
        _demo_org = (sys_config_doc or {}).get("org_name") or ""
        async for chunk in _run_scripted_demo(
            onboarding_context=onboarding_context,
            conversation=conversation,
            user=user,
            user_id=user_id,
            activity_id=activity_id,
            sys_config_doc=sys_config_doc,
        ):
            yield _brand_org_json_chunk(chunk, _demo_org)
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
    doc_segments: list[DocumentSegment] = []
    skipped_no_text: list[str] = []
    errored_docs: list[str] = []
    for doc in documents:
        if doc.raw_text:
            doc_segments.append(DocumentSegment(
                label=f"doc:{doc.title or doc.uuid}",
                text=f"\n\n## Document: {doc.title}\n{doc.raw_text}",
            ))
        elif doc.task_status == "error":
            errored_docs.append(doc.title or doc.uuid)
        else:
            skipped_no_text.append(doc.title or doc.uuid)

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
                history=previous_messages,
            )
            if kb_segment:
                doc_segments.insert(0, kb_segment)
        except Exception as e:
            logger.error("KB context retrieval failed for kb_uuid=%s: %s", kb_uuid, e)
            kb_sources = []

    # Hold instead of hallucinate. The user attached document(s) but none are
    # readable — text extraction hasn't finished or it failed — and there's no
    # other grounding (KB snippets, pasted attachments). Running the agent here
    # is exactly how we got a confident answer about a file the model never
    # read. Return an honest holding turn instead. The frontend also auto-holds
    # the send, but the backend is the source of truth on `raw_text` and must
    # never fabricate when context is empty. The documents_not_ready /
    # documents_extraction_failed notices were already emitted above.
    hold_text = _hold_message_for_unreadable_docs(
        document_uuids=document_uuids,
        doc_segments=doc_segments,
        kb_sources=kb_sources,
        attachment_segments=attachment_segments,
        skipped_no_text=skipped_no_text,
        errored_docs=errored_docs,
    )
    if hold_text is not None:
        yield json.dumps({"kind": "text", "content": hold_text}) + "\n"
        await _finalize(conversation, hold_text, [], None, activity_id, user_id)
        return

    # Build workspace inventory for all non-demo, non-help paths.
    # run_demo returns early (scripted demo path); help path uses its own context.
    team_id = str(user.current_team) if user and user.current_team else None
    inventory = ""
    if user and not run_demo and not include_onboarding_context and not is_first_session:
        try:
            inventory = await _build_workspace_inventory(user_id, team_id)
        except Exception as e:
            logger.warning("Workspace inventory failed: %s", e)

    # Static instruction base + volatile <system-reminder> blocks.
    #
    # The instruction base must be byte-stable across every turn of a
    # conversation so the provider prompt cache can hit (Phase 1 of
    # .claude/agentic-chat-harness-uplift-plan.md). Everything that varies per
    # turn — workspace inventory, KB manifest, open documents, project state,
    # and mode-specific rules — is injected as <system-reminder> blocks on the
    # CURRENT user prompt instead. History replays raw user text
    # (ChatMessage.to_model_messages), so stale reminders never accumulate.
    #
    # Note: run_demo is handled via scripted demo and returns early above, so
    # it never reaches this block.
    have_context = bool(doc_segments or attachment_segments)
    reminder_blocks: list[str] = []
    kb_empty_mode = False

    # Mode rules — same precedence as the pre-Phase-1 per-turn prompt swap:
    # KB retrieval hit > attached documents > empty-KB project > first-session
    # > onboarding help.
    if kb_sources:
        # KB chat needs the strictest rules: snippets are partial excerpts, so
        # the model must cite by filename, distinguish grounded answers from
        # general knowledge, and admit when the retrieved set doesn't actually
        # contain the answer. The manifest rides along every turn so the model
        # can distinguish "exists here but wasn't retrieved" from "not in this
        # project" on follow-ups too.
        reminder_blocks.append(KB_CHAT_RULES + _build_manifest_block(kb_manifest))
    elif have_context:
        reminder_blocks.append(DOCUMENT_CHAT_RULES)
    elif kb_uuid:
        # A project/KB chat was requested but retrieval returned nothing (empty
        # KB, docs not indexed yet, or no match). Do NOT skip the rules block —
        # that lets the model freely hallucinate document contents. Tell it the
        # KB was empty for this query while still allowing general-knowledge
        # answers.
        kb_empty_mode = True
        reminder_blocks.append(
            build_project_kb_empty_reminder(_build_manifest_block(kb_manifest))
        )
    elif is_first_session:
        # First-session onboarding: conversational value discovery, handled by
        # the FIRST_SESSION_SYSTEM_PROMPT instruction base below. Do NOT inject
        # VANDALIZER_CONTEXT here — it's a technical how-to dump that causes
        # the LLM to skip the conversation and spit out directions.
        pass
    elif include_onboarding_context:
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
        reminder_blocks.append(HELP_CHAT_RULES)

    # Workspace inventory (already "" for first-session/help/demo paths).
    # Excluded in empty-KB mode for parity with the pre-Phase-1 behavior: that
    # mode is a hard "don't invent project contents" stance and the inventory's
    # capability nudges dilute it.
    if inventory and not kb_empty_mode:
        reminder_blocks.append(inventory)

    # Expose open documents to the agent so tools like run_extraction can
    # reference them by UUID without a blind search_documents call. Without
    # this, the model has to search by filename — which is both fragile and
    # expensive on large workspaces (see chat_tools.search_documents).
    open_docs_block = _build_open_documents_block(
        documents, file_attachments, url_attachments
    )
    if open_docs_block:
        reminder_blocks.append(open_docs_block)

    # Tell the agent it's inside a project, and what that project contains
    # (pinned workflows/extractions with their ids, file/KB counts). This is
    # what makes the project tools usable — without it the agent doesn't know a
    # project is active or which target_ids to run. Existing tools are
    # unaffected; the block explicitly tells the agent not to narrow them.
    if project_uuid and user:
        try:
            project_block = await _build_project_context(project_uuid, user)
        except Exception as e:  # never let project context break a turn
            logger.warning("Project context build failed: %s", e)
            project_block = ""
        if project_block:
            reminder_blocks.append(project_block)

    # Instruction base. First-session keeps its own conversation-stable base
    # (the whole conversation is a distinct behavioral mode); everything else
    # uses ONE base per agent type so the cached prefix never shifts when the
    # user attaches a doc or a KB lookup hits/misses mid-conversation.
    if is_first_session and not (kb_sources or have_context or kb_uuid):
        instruction_base = FIRST_SESSION_SYSTEM_PROMPT
    elif user and team_access:
        instruction_base = AGENTIC_CHAT_SYSTEM_PROMPT
    else:
        instruction_base = DEFAULT_CHAT_SYSTEM_PROMPT

    # Branding is deployment-stable, so branded instructions stay byte-stable.
    _org_name = (sys_config_doc or {}).get("org_name") or ""
    instructions_text = _brand_org_text(instruction_base, _org_name)
    reminder_bundle = "\n\n".join(
        _wrap_system_reminder(b) for b in reminder_blocks if b and b.strip()
    )
    if reminder_bundle:
        reminder_bundle = _brand_org_text(reminder_bundle, _org_name)

    # Resolve the model's context window and compact oversize components.
    # The reminder bundle is counted with the system prompt: it isn't part of
    # the instructions, but it's per-turn overhead the budget must reserve.
    model_config = await get_llm_model_by_name(model_name)
    compacted = plan_and_compact_context(
        model_name=model_name,
        model_config=model_config,
        system_prompt=(
            instructions_text + ("\n\n" + reminder_bundle if reminder_bundle else "")
        ),
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

    # Volatile context rides on the current user prompt (see the reminder-
    # block comment above). Reminders lead, the user's actual ask stays last
    # for recency. History replay uses the raw stored message, so these blocks
    # exist only on the live turn.
    if reminder_bundle:
        prompt = f"{reminder_bundle}\n\n{prompt}"

    # Select agent — agentic (with tools) when user context is available.
    # Agents are cached by model; the stable instruction base is passed via
    # ``instructions`` at iter() time, and all volatile context (workspace
    # inventory, mode rules, etc.) already rides on `prompt` as reminders.
    deps = None
    if user and team_access:
        from app.services.chat_deps import AgenticChatDeps

        # Only inject the onboarding sample doc during the scripted demo.
        # Outside the demo, force-injecting it leaks a phantom NSF proposal
        # into normal agent tool calls.
        effective_doc_uuids = list(document_uuids)
        if run_demo and onboarding_context and onboarding_context.sample_doc_uuid:
            if onboarding_context.sample_doc_uuid not in effective_doc_uuids:
                effective_doc_uuids.append(onboarding_context.sample_doc_uuid)

        deps = AgenticChatDeps(
            user=user,
            user_id=user_id,
            team_id=str(user.current_team) if user.current_team else None,
            team_access=team_access,
            organization_id=getattr(user, "organization_id", None),
            system_config_doc=sys_config_doc,
            model_name=model_name,
            context_document_uuids=effective_doc_uuids,
            active_kb_uuid=kb_uuid,
            active_project_uuid=project_uuid,
            conversation=conversation,
            # Monotonic per-turn marker: the current user message is already
            # persisted (router add_message) before chat_stream runs, so this
            # strictly increases each turn. Write tools require a preview armed
            # on an earlier turn (smaller marker) before they execute.
            turn_marker=len(conversation.messages),
        )
        agent = create_agentic_chat_agent(
            model_name, system_config_doc=sys_config_doc,
        )
    else:
        # Bake the branded base directly: create_chat_agent builds a fresh
        # Agent per call (no cache to poison), and run-level instructions
        # APPEND to construction-level ones in pydantic-ai — passing the base
        # at iter() time on top of the baked default would duplicate it and
        # leak the unbranded copy on white-labeled deployments.
        agent = create_chat_agent(
            model_name, system_prompt=instructions_text,
            system_config_doc=sys_config_doc,
        )

    # Stream the response
    full_response: list[str] = []
    full_thinking: list[str] = []
    thinking_started_at: float | None = None
    thinking_duration: float | None = None
    thinking_done_emitted = False
    streamed_tool_calls: list[dict] = []
    streamed_tool_results: list[dict] = []
    streamed_segments: list[dict] = []
    # Citations accumulated this turn: pre-agent KB context (classic path)
    # plus any search_knowledge_base tool calls (agentic path).
    streamed_citations: list[dict] = list(kb_sources)

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
    await _meter.__aenter__()
    try:
        think_parser = _ThinkTagParser()

        iter_kwargs: dict = {
            "message_history": previous_messages,
            "usage_limits": UsageLimits(request_limit=25, tool_calls_limit=15),
        }
        if deps is not None:
            iter_kwargs["deps"] = deps
            # Byte-stable per conversation (branded static base — see the
            # instruction-base selection above). All volatile context already
            # rides in the <system-reminder> blocks on `prompt`. Only the
            # agentic agent takes run-level instructions: it is cached per
            # model with nothing baked in, whereas the non-agentic agent gets
            # the same text baked at construction (run-level instructions
            # APPEND to baked ones — passing both would duplicate the base).
            iter_kwargs["instructions"] = instructions_text

        async with agent.iter(prompt, **iter_kwargs) as agent_run:
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
                                        # Build segment — merge consecutive text
                                        if streamed_segments and streamed_segments[-1].get("kind") == "text":
                                            streamed_segments[-1]["content"] += text
                                        else:
                                            streamed_segments.append({"kind": "text", "content": text})
                                        yield json.dumps({"kind": "text", "content": text}) + "\n"

                    # Flush any remaining buffered content from the parser
                    for kind, text in think_parser.flush():
                        if kind == "thinking":
                            full_thinking.append(text)
                            yield json.dumps({"kind": "thinking", "content": text}) + "\n"
                        else:
                            full_response.append(text)
                            if streamed_segments and streamed_segments[-1].get("kind") == "text":
                                streamed_segments[-1]["content"] += text
                            else:
                                streamed_segments.append({"kind": "text", "content": text})
                            yield json.dumps({"kind": "text", "content": text}) + "\n"

                elif Agent.is_call_tools_node(node):
                    # Stream tool call / result events to the frontend
                    async with node.stream(agent_run.ctx) as tool_stream:
                        async for event in tool_stream:
                            if isinstance(event, FunctionToolCallEvent):
                                try:
                                    args = event.part.args_as_dict()
                                except Exception:
                                    args = {}
                                call_data = {
                                    "tool_name": event.part.tool_name,
                                    "tool_call_id": event.part.tool_call_id,
                                    "args": args,
                                }
                                streamed_tool_calls.append(call_data)
                                streamed_segments.append({"kind": "tool_call", "call": call_data})
                                yield json.dumps({"kind": "tool_call", **call_data}) + "\n"
                            elif isinstance(event, FunctionToolResultEvent):
                                # Extract quality sidecar from tool result.
                                # Tools embed a "quality" key in their return dict;
                                # we strip it here so it goes to the frontend but
                                # NOT back into the LLM context.
                                quality = None
                                result_content = event.result.content
                                if isinstance(result_content, dict) and "quality" in result_content:
                                    quality = result_content.pop("quality")
                                # Also check the deps annotations dict (future-proof)
                                if quality is None and deps and event.tool_call_id in deps.quality_annotations:
                                    quality = deps.quality_annotations.pop(event.tool_call_id)
                                if not isinstance(result_content, (str, dict, list)):
                                    result_content = str(result_content)
                                result_data = {
                                    "tool_name": event.result.tool_name,
                                    "tool_call_id": event.result.tool_call_id,
                                    "content": result_content,
                                    "quality": quality,
                                }
                                streamed_tool_results.append(result_data)
                                streamed_segments.append({"kind": "tool_result", "result": result_data})
                                yield json.dumps({"kind": "tool_result", **result_data}) + "\n"

                                # Citation sidecar (search_knowledge_base): emit a
                                # 'sources' chunk so the frontend renders citation
                                # chips for agent-driven KB lookups, same as the
                                # classic pre-agent KB path.
                                if deps and event.tool_call_id in deps.citation_annotations:
                                    tool_citations = deps.citation_annotations.pop(event.tool_call_id)
                                    streamed_citations.extend(tool_citations)
                                    yield json.dumps({
                                        "kind": "sources",
                                        "content": "",
                                        "sources": tool_citations,
                                    }) + "\n"

            if agent_run.result:
                usage = agent_run.result.usage()
                # Safety-net: strip any residual think tags the parser missed
                assistant_message = _THINK_BLOCK_RE.sub("", "".join(full_response)).strip()
                thinking_text = "".join(full_thinking) or None

                # Clean think tags from text segments before persisting
                cleaned_segments: list[dict] = []
                for seg in streamed_segments:
                    if seg.get("kind") == "text":
                        cleaned = _THINK_BLOCK_RE.sub("", seg["content"]).strip()
                        if cleaned:
                            cleaned_segments.append({"kind": "text", "content": cleaned})
                    else:
                        cleaned_segments.append(seg)

                await _finalize(
                    conversation, assistant_message, documents,
                    usage, activity_id, user_id,
                    thinking=thinking_text,
                    thinking_duration=thinking_duration,
                    tool_calls=streamed_tool_calls or None,
                    tool_results=streamed_tool_results or None,
                    segments=cleaned_segments or None,
                    citations=streamed_citations or None,
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

                cache_read_toks, cache_write_toks = _note_cache_usage(
                    conversation.uuid, usage, model_name,
                ) if usage else (0, 0)

                yield json.dumps({
                    "kind": "usage",
                    "content": "",
                    "request_tokens": input_toks,
                    "response_tokens": output_toks,
                    "total_tokens": input_toks + output_toks,
                    "cache_read_tokens": cache_read_toks,
                    "cache_write_tokens": cache_write_toks,
                }) + "\n"

    except UsageLimitExceeded:
        logger.warning("Chat usage limit reached for user %s", user_id)
        yield json.dumps({"kind": "error", "content": "This response used too many tool calls. Try breaking your request into smaller steps."}) + "\n"
        if activity_id:
            ev = await ActivityEvent.get(activity_id)
            if ev:
                ev.status = ActivityStatus.COMPLETED.value
                await ev.save()
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
    """Render the project's document list as a context section.

    Rides in the KB <system-reminder> block on every turn's user prompt so the
    model always knows what the project contains — the retrieved snippets
    alone can't tell it whether an unretrieved document exists.
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
    general: list[dict], named: list[dict], k: int,
) -> list[dict]:
    """Merge named-document hits with the general pool into the final top-k.

    Named-document chunks are guaranteed up to ceil(k/2) slots (the document
    the user asked about by name must not be crowded out), the rest are filled
    from the general pool with a per-source diversity cap.
    """
    max_per_source = max(2, -(-k // 2))  # ceil(k/2)
    if not named:
        return _select_diverse_chunks(general, k, max_per_source)

    quota = -(-k // 2)
    final = named[:quota]
    seen = {r.get("chunk_id") for r in final}
    remaining = [r for r in general if r.get("chunk_id") not in seen]
    final.extend(
        _select_diverse_chunks(remaining, k - len(final), max_per_source)
    )
    return final[:k]


async def _build_kb_segment(
    kb_uuid: str,
    message: str,
    model_name: str,
    manifest: Optional[list[dict]] = None,
    history: Optional[list[ModelMessage]] = None,
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
    kb_results, rag_cfg, _ = await retrieve_kb_chunks(
        kb_uuid, message, model_name, per_step_timeout=6.0,
        overfetch_multiplier=3,
        retrieval_query=retrieval_query,
    )

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

    kb_results = _compose_kb_results(kb_results, named_results, rag_cfg.k)
    if not kb_results:
        logger.warning("KB query returned no results for kb_uuid=%s", kb_uuid)
        return None, []

    kb_sources: list[dict] = []
    kb_text = (
        "\n\n## Retrieved Knowledge Base Snippets\n"
        "_The following are partial excerpts from a larger corpus, ranked "
        "by similarity to the user's question. They may be incomplete, "
        "off-topic, or miss the best answer. Cite by filename only when a "
        "snippet actually supports your claim._\n"
    )
    for r in kb_results:
        meta = r.get("metadata") or {}
        src = meta.get("source_name", "Unknown")
        page = meta.get("page")
        sheet = meta.get("sheet")
        label = src
        if isinstance(page, int):
            label = f"{src} (p. {page})"
        elif isinstance(sheet, str) and sheet:
            label = f"{src} ({sheet})"
        kb_text += f"\n**Source: {label}**\n{r['content']}\n"
        kb_sources.append({
            "document_id": meta.get("source_id"),
            "document_title": src,
            "page": page if isinstance(page, int) else None,
            "sheet": sheet if isinstance(sheet, str) else None,
            "chunk_id": r.get("chunk_id"),
            "score": r.get("score"),
            "similarity": r.get("similarity"),
            "content_preview": (r.get("content") or "")[:240],
        })
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


def _get_full_text(documents: list[SmartDocument]) -> str:
    """Combine document texts for direct-prompt chat."""
    parts = []
    for doc in documents:
        if doc.raw_text:
            parts.append(f"\n\n## Document: {doc.title}\n{doc.raw_text}")
    return "".join(parts)


def _build_open_documents_block(
    documents: list[SmartDocument],
    file_attachments: list | None = None,
    url_attachments: list | None = None,
) -> str:
    """Format everything currently attached to this chat — selected documents,
    uploaded files, and fetched URLs — so the model can (a) reference documents
    by UUID without calling search_documents and (b) answer "what's attached?"
    accurately and consistently.

    This is the single authoritative list of attachments. The model cannot
    remove any of these: they are user-controlled tabs in the attachments bar,
    each removed by its own ✕ button. The block says so explicitly so the model
    stops hallucinating a "cleared" / "detached" success it cannot perform.
    """
    file_attachments = file_attachments or []
    url_attachments = url_attachments or []
    if not (documents or file_attachments or url_attachments):
        return ""

    lines = [
        "## Attached to this chat",
        "These items are attached to the current conversation. This is the "
        "complete, authoritative list — if something is not listed here, it is "
        "NOT attached. When the user asks what is attached, answer from this "
        "list exactly.",
        "",
        "You CANNOT remove, detach, or clear any of them, and there is no tool "
        "to clear the conversation. Each is a tab in the attachments bar above "
        "the chat input that only the user can close with its ✕ button. If the "
        "user asks you to remove/detach/clear an attachment or the "
        "conversation, do NOT claim you did it — say you can't, name what is "
        "attached, and tell them to click the ✕ on that item's pill above the "
        "chat input.",
        "",
        "For documents below, use their UUIDs directly for tools like "
        "run_extraction or get_document_text — do NOT call search_documents to "
        "look them up.",
    ]
    for doc in documents:
        lines.append(f'- Document: "{doc.title}" (uuid: {doc.uuid})')
    for att in file_attachments:
        lines.append(f'- Uploaded file: "{getattr(att, "filename", "file")}"')
    for att in url_attachments:
        title = getattr(att, "title", None) or getattr(att, "url", "URL")
        url = getattr(att, "url", "")
        lines.append(f'- URL: "{title}" ({url})' if url else f'- URL: "{title}"')
    return "\n".join(lines)


async def _build_project_context(project_uuid: str, user: User) -> str:
    """Tell the agent a project is active and what it contains.

    Reuses ``get_project_overview`` + ``list_pins`` so the block matches the
    project home exactly. Lists each pin's ``target_id`` so the agent can pass
    them to ``run_pin_on_project``. Returns "" when the project is missing or
    unauthorized so a stale uuid never breaks the turn.
    """
    from app.services import project_service

    project = await project_service.get_authorized_project(project_uuid, user)
    if not project:
        return ""
    overview = await project_service.get_project_overview(project, user)
    pins = await project_service.list_pins(project)
    caps = overview["capabilities"]

    lines = [
        "## Active project",
        f'The user is working inside the project "{project.title}" '
        f"(uuid: {project.uuid}, state: {project.state}, "
        f"their role: {overview['role']}).",
    ]
    if project.description:
        lines.append(f"Description: {project.description}")
    kb_state = "ready" if caps["knowledge"]["ready"] else "not set up"
    lines.append(
        f"- {caps['files']['count']} file(s); project knowledge base {kb_state} "
        f"({caps['knowledge']['documents']} indexed)."
    )
    if pins:
        lines.append(
            "Pinned capabilities (pass pin_type + target_id to run_pin_on_project):"
        )
        for p in pins:
            lines.append(
                f'- {p["pin_type"]}: "{p["name"]}" (target_id: {p["target_id"]})'
            )
    else:
        lines.append("No capabilities are pinned to this project yet.")
    lines.append(
        "IMPORTANT: your other tools (search_documents, run_extraction, "
        "run_workflow, search_knowledge_base, etc.) still range the user's "
        "WHOLE workspace — do NOT silently narrow them to this project. Use the "
        "project tools (run_pin_on_project, list_project_documents, "
        "pin_to_project, unpin_from_project, set_project_status) only when the "
        "user explicitly refers to \"this project\", its files, a pinned item, "
        "or its status."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workspace inventory — gives the LLM awareness of the user's assets
# ---------------------------------------------------------------------------

_inventory_cache: dict[tuple[str, str | None], tuple[float, str]] = {}
_INVENTORY_TTL = 60.0  # seconds


def _relative_time(dt: datetime.datetime) -> str:
    """Format a datetime as a human-friendly relative string."""
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = int(seconds // 60)
        return f"{mins}m ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}h ago"
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


async def _build_workspace_inventory(
    user_id: str, team_id: str | None
) -> str:
    """Build a compact workspace summary, injected per turn as a
    <system-reminder> block on the user prompt (NOT the system prompt — its
    60s-TTL contents change turn-to-turn and would break the provider prompt
    cache there).

    Returns an empty string for brand-new users with zero assets.
    Results are cached in-memory for 60 seconds per (user_id, team_id).
    """
    cache_key = (user_id, team_id)
    now = time.monotonic()
    cached = _inventory_cache.get(cache_key)
    if cached and (now - cached[0]) < _INVENTORY_TTL:
        return cached[1]

    from app.models.knowledge import KnowledgeBase
    from app.models.search_set import SearchSet
    from app.models.validation_run import ValidationRun
    from app.models.workflow import Workflow

    # Build query filters — match team scope or personal
    if team_id:
        doc_filter = {
            "soft_deleted": {"$ne": True},
            "$or": [{"team_id": team_id}, {"user_id": user_id}],
        }
        ss_filter = {"$or": [{"team_id": team_id}, {"user_id": user_id}]}
        wf_filter = {"$or": [{"team_id": team_id}, {"user_id": user_id}]}
        kb_filter = {"$or": [{"team_id": team_id}, {"user_id": user_id}]}
    else:
        doc_filter = {"user_id": user_id, "soft_deleted": {"$ne": True}}
        ss_filter = {"user_id": user_id}
        wf_filter = {"user_id": user_id}
        kb_filter = {"user_id": user_id}

    # Parallel queries — lightweight counts + limited name lists
    (
        doc_count,
        recent_docs,
        search_sets,
        workflows,
        knowledge_bases,
        recent_activity,
    ) = await asyncio.gather(
        SmartDocument.find(doc_filter).count(),
        SmartDocument.find(doc_filter)
        .sort("-created_at")
        .limit(3)
        .to_list(),
        SearchSet.find(ss_filter).sort("-created_at").limit(5).to_list(),
        Workflow.find(wf_filter).sort("-created_at").limit(5).to_list(),
        KnowledgeBase.find(kb_filter).sort("-created_at").limit(5).to_list(),
        ActivityEvent.find(
            {"user_id": user_id, "status": "completed"}
        )
        .sort("-last_updated_at")
        .limit(3)
        .to_list(),
    )

    # Quick check: if the user has nothing, return empty
    total_items = (
        doc_count + len(search_sets) + len(workflows) + len(knowledge_bases)
    )
    if total_items == 0:
        _inventory_cache[cache_key] = (now, "")
        return ""

    # Detect post-demo state: only onboarding sample docs, no real content
    all_onboarding = doc_count > 0 and all(
        getattr(d, "is_onboarding_sample", False) for d in recent_docs
    ) and not search_sets and not workflows

    # Fetch validation scores for extraction sets (if any)
    quality_map: dict[str, float] = {}  # ss_uuid → score
    if search_sets:
        ss_uuids = [ss.uuid for ss in search_sets]
        validation_runs = await ValidationRun.find(
            {"item_kind": "search_set", "item_id": {"$in": ss_uuids}}
        ).sort("-created_at").to_list()
        # Keep only the latest run per item
        for vr in validation_runs:
            if vr.item_id not in quality_map:
                quality_map[vr.item_id] = vr.score

    # Build the inventory string
    lines: list[str] = ["## Your workspace"]

    # Documents
    if doc_count > 0:
        doc_names = ", ".join(
            f'"{d.title}"' for d in recent_docs[:3]
        )
        lines.append(
            f"- {doc_count} document{'s' if doc_count != 1 else ''}"
            f" (latest: {doc_names})"
        )

    # Extraction sets
    if search_sets:
        ss_parts: list[str] = []
        for ss in search_sets[:3]:
            label = f'"{ss.title}"'
            hints: list[str] = []
            if ss.verified:
                hints.append("verified")
            score = quality_map.get(ss.uuid)
            if score is not None:
                hints.append(f"{round(score)}/100")
            if hints:
                label += f" ({', '.join(hints)})"
            ss_parts.append(label)
        lines.append(
            f"- {len(search_sets)} extraction set"
            f"{'s' if len(search_sets) != 1 else ''}: "
            + ", ".join(ss_parts)
        )

    # Workflows
    if workflows:
        wf_parts: list[str] = []
        for wf in workflows[:3]:
            label = f'"{wf.name}"'
            if wf.num_executions:
                label += f" ({wf.num_executions} run{'s' if wf.num_executions != 1 else ''})"
            wf_parts.append(label)
        lines.append(
            f"- {len(workflows)} workflow"
            f"{'s' if len(workflows) != 1 else ''}: "
            + ", ".join(wf_parts)
        )

    # Knowledge bases
    if knowledge_bases:
        kb_parts: list[str] = []
        for kb in knowledge_bases[:3]:
            label = f'"{kb.title}"'
            if kb.status:
                label += f" ({kb.status})"
            kb_parts.append(label)
        lines.append(
            f"- {len(knowledge_bases)} knowledge base"
            f"{'s' if len(knowledge_bases) != 1 else ''}: "
            + ", ".join(kb_parts)
        )

    # Recent activity
    if recent_activity:
        lines.append("")
        lines.append("## Recent activity")
        for ev in recent_activity:
            ts = _relative_time(ev.last_updated_at) if ev.last_updated_at else ""
            title = ev.title or "Untitled"
            if ev.type == "conversation":
                lines.append(f'- "{title}" conversation ({ts})')
            elif ev.type == "search_set_run":
                touched = (
                    f" on {ev.documents_touched} doc{'s' if ev.documents_touched != 1 else ''}"
                    if ev.documents_touched
                    else ""
                )
                lines.append(f'- Ran "{title}" extraction{touched} ({ts})')
            elif ev.type == "workflow_run":
                lines.append(
                    f'- "{title}" workflow — {ev.status} ({ts})'
                )
            else:
                lines.append(f"- {title} ({ts})")

    # Active quality alerts for extraction templates
    if search_sets and not all_onboarding:
        from app.models.quality_alert import QualityAlert

        ss_uuids = [ss.uuid for ss in search_sets]
        active_alerts = await QualityAlert.find(
            {"item_kind": "search_set", "item_id": {"$in": ss_uuids}, "acknowledged": {"$ne": True}}
        ).sort("-created_at").limit(3).to_list()
        if active_alerts:
            lines.append("")
            lines.append("## Active quality alerts")
            for alert in active_alerts:
                lines.append(f"- {alert.message}")

    # Capabilities the user hasn't tried yet — enables progressive discovery
    if not all_onboarding and doc_count > 0:
        untried: list[str] = []
        if not search_sets and doc_count >= 1:
            untried.append(
                "**Extraction templates**: This user has documents but no extraction templates. "
                "If they mention wanting structured data, offer to build a template from one of their documents."
            )
        if search_sets and not workflows:
            untried.append(
                "**Workflows**: This user has extraction templates but no workflows. "
                "If they mention wanting to repeat a process or handle batches, suggest chaining extractions into a workflow."
            )
        if not knowledge_bases and doc_count >= 3:
            untried.append(
                "**Knowledge bases**: This user has several documents but no knowledge base. "
                "If they ask questions that span multiple documents, suggest building a KB for cross-document search."
            )
        if workflows and not any(True for wf in workflows if wf.num_executions and wf.num_executions > 0):
            untried.append(
                "**Workflow execution**: This user has workflows but hasn't run any. "
                "If they mention processing documents, remind them they can run their workflow."
            )
        if untried:
            lines.append("")
            lines.append("## Capabilities this user hasn't tried yet")
            lines.append(
                "Don't force these — only mention when the user's question or context "
                "naturally connects. One gentle suggestion at most per conversation."
            )
            for hint in untried[:3]:
                lines.append(f"- {hint}")

    # Cross-session behavioral memory — tools the user actually exercises
    try:
        from app.services import user_memory_service

        patterns = await user_memory_service.build_patterns_block(user_id, team_id)
        if patterns:
            lines.append("")
            lines.append(patterns)
    except Exception as _e:
        logger.warning("Could not load user memory patterns: %s", _e)

    # Post-demo bridge: guide users who only have the onboarding sample
    if all_onboarding:
        lines.append("")
        lines.append("## Post-demo guidance")
        lines.append(
            "This user has only the onboarding sample — no real documents yet. "
            "Guide them to one concrete next step:\n"
            "- **Upload documents**: 'Upload a few documents you're working with "
            "and I'll help you extract data or build a custom template.'\n"
            "- **Explore the sample**: 'Want me to show you something else with "
            "the sample proposal? I can run a different template or search the "
            "knowledge base.'\n"
            "- **Start certification**: 'The Vandal Workflow Architect program "
            "walks you through everything with guided labs.'\n"
            "Don't repeat the demo. Suggest uploading their own document as the "
            "highest-value next action."
        )

    result = "\n".join(lines)

    # Cache with TTL and enforce max size
    if len(_inventory_cache) > 100:
        # Evict oldest entries
        sorted_keys = sorted(
            _inventory_cache, key=lambda k: _inventory_cache[k][0]
        )
        for k in sorted_keys[:50]:
            del _inventory_cache[k]
    _inventory_cache[cache_key] = (now, result)

    return result


async def _finalize(
    conversation: ChatConversation,
    assistant_message: str,
    documents: list[SmartDocument],
    usage,
    activity_id: Optional[str],
    user_id: str,
    thinking: Optional[str] = None,
    thinking_duration: Optional[float] = None,
    tool_calls: Optional[list[dict]] = None,
    tool_results: Optional[list[dict]] = None,
    segments: Optional[list[dict]] = None,
    citations: Optional[list[dict]] = None,
) -> None:
    """Save assistant message and update activity metrics."""
    await conversation.add_message(
        ChatRole.ASSISTANT,
        assistant_message,
        thinking=thinking,
        thinking_duration=thinking_duration,
        tool_calls=tool_calls,
        tool_results=tool_results,
        segments=segments,
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
                # Prompt-cache observability (uplift plan Phase 1.5): stash
                # cache hit/write totals per turn so cache health is queryable
                # from activity data without a schema change.
                cache_read = int(getattr(usage, "cache_read_tokens", 0) or 0)
                cache_write = int(getattr(usage, "cache_write_tokens", 0) or 0)
                if cache_read or cache_write:
                    ev.meta_summary = {
                        **(ev.meta_summary or {}),
                        "cache_read_tokens": cache_read,
                        "cache_write_tokens": cache_write,
                    }
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
