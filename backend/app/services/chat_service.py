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
)

from app.models.activity import ActivityEvent, ActivityStatus
from app.models.chat import ChatConversation, ChatRole
from app.models.document import SmartDocument
from app.models.system_config import SystemConfig
from app.services.config_service import get_llm_model_by_name, get_user_model_name
from app.services.context_budget import (
    DocumentSegment,
    plan_and_compact_context,
)
from app.services.llm_service import (
    create_chat_agent,
    DOCUMENT_CHAT_SYSTEM_PROMPT,
    FIRST_SESSION_SYSTEM_PROMPT,
    HELP_CHAT_SYSTEM_PROMPT,
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
    if kb_uuid:
        try:
            from app.services.document_manager import DocumentManager
            dm = DocumentManager()
            kb_results = await asyncio.to_thread(dm.query_kb, kb_uuid, message, 8)
            if kb_results:
                kb_text = "\n\n## Knowledge Base Context:\n"
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
                        "content_preview": (r.get("content") or "")[:240],
                    })
                doc_segments.insert(0, DocumentSegment(label="kb", text=kb_text))
            else:
                logger.warning("KB query returned no results for kb_uuid=%s", kb_uuid)
        except Exception as e:
            logger.error("KB context retrieval failed for kb_uuid=%s: %s", kb_uuid, e)

    # Select system prompt based on whether we have document context.
    have_context = bool(doc_segments or attachment_segments)
    if have_context:
        system_prompt: Optional[str] = DOCUMENT_CHAT_SYSTEM_PROMPT
    elif is_first_session:
        # First-session onboarding: conversational value discovery.
        # Do NOT inject VANDALIZER_CONTEXT here — it's a technical how-to dump
        # that causes the LLM to skip the conversation and spit out directions.
        # The FIRST_SESSION_SYSTEM_PROMPT already has everything it needs.
        system_prompt = FIRST_SESSION_SYSTEM_PROMPT
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
        system_prompt = HELP_CHAT_SYSTEM_PROMPT
    else:
        system_prompt = None  # uses default

    # Resolve the model's context window and compact oversize components.
    model_config = await get_llm_model_by_name(model_name)
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

    try:
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
) -> None:
    """Save assistant message and update activity metrics."""
    await conversation.add_message(
        ChatRole.ASSISTANT,
        assistant_message,
        thinking=thinking,
        thinking_duration=thinking_duration,
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
