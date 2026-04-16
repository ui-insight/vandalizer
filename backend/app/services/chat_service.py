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
)

from app.models.activity import ActivityEvent, ActivityStatus
from app.models.chat import ChatConversation, ChatRole
from app.models.document import SmartDocument
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services.access_control import TeamAccessContext
from app.services.config_service import get_user_model_name
from app.services.llm_service import (
    AGENTIC_CHAT_SYSTEM_PROMPT,
    create_agentic_chat_agent,
    create_chat_agent,
    DOCUMENT_CHAT_SYSTEM_PROMPT,
    FIRST_SESSION_AGENTIC_PROMPT_TEMPLATE,
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
            "I placed a sample NSF proposal in your workspace. Let me show you "
            "what Vandalizer does with it.\n\n"
            "Most tools just throw your document at an LLM and hope for the best. "
            "Vandalizer uses **validated extraction templates** — tested against "
            "real documents with known answers, so you know the accuracy *before* "
            "you trust the results.\n\n"
            "Let me find the right template…\n\n"
        )

        # -- Step 2: Search library ----------------------------------------------
        call_id_1 = str(uuid.uuid4())[:12]
        yield _tool_call("search_library", call_id_1, {"query": "NSF", "kind": "search_set"})
        await asyncio.sleep(0)  # flush chunk so spinner appears

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
        await asyncio.sleep(0)  # flush chunk so spinner appears before LLM extraction runs

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
            await asyncio.sleep(0)  # flush chunk so spinner appears

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
            "That's Vandalizer: **validated extraction** that you can measure and trust"
        )
        if ctx.kb_uuid:
            yield _text(
                ", plus **policy cross-reference** to catch compliance issues automatically"
            )
        yield _text(
            ".\n\n"
            "Here's how this fits your daily work:\n"
            "1. **Upload** your documents — they stay private and get auto-indexed\n"
            "2. **Extract** structured data with validated templates\n"
            "3. **Build & validate** your own templates from any document\n"
            "4. **Scale** with workflows and automation triggers\n\n"
            "What would you like to do next?\n\n"
            "[ACTION:upload-docs]Upload your documents[/ACTION]  "
            "[ACTION:start-cert]Start the Certification Program[/ACTION]\n"
        )

        # -- Finalize: save to conversation & activity ----------------------------
        assistant_message = "".join(full_text_parts)
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
        async for chunk in _run_scripted_demo(
            onboarding_context=onboarding_context,
            conversation=conversation,
            user=user,
            user_id=user_id,
            activity_id=activity_id,
            sys_config_doc=sys_config_doc,
        ):
            yield chunk
        return

    # Load documents
    documents: list[SmartDocument] = []
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(
            SmartDocument.uuid == doc_uuid,
        )
        if doc:
            documents.append(doc)

    # Build attachment context
    attachment_context = ""
    url_attachments = await conversation.get_url_attachments()
    for att in url_attachments:
        if att.content:
            attachment_context += (
                f"\n\n## Web Content: {att.title}\nSource: {att.url}\n\n"
                f"{att.content[:10000]}\n"
            )

    file_attachments = await conversation.get_file_attachments()
    logger.info(
        "Chat file attachments: count=%d with_content=%d",
        len(file_attachments),
        sum(1 for a in file_attachments if a.content),
    )
    for att in file_attachments:
        if att.content:
            attachment_context += (
                f"\n\n## Document: {att.filename}\n\n{att.content[:10000]}\n"
            )

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

    # Build prompt and select appropriate system prompt
    full_text = _get_full_text(documents)
    if document_uuids:
        logger.info(
            "Chat doc context: requested=%d found=%d with_text=%d text_len=%d",
            len(document_uuids),
            len(documents),
            sum(1 for d in documents if d.raw_text),
            len(full_text),
        )

    parts: list[str] = []

    # KB context: query ChromaDB for relevant chunks
    if kb_uuid:
        try:
            import asyncio
            from app.services.document_manager import get_document_manager
            dm = get_document_manager()
            kb_results = await asyncio.to_thread(dm.query_kb, kb_uuid, message, 8)
            if kb_results:
                kb_text = "\n\n## Knowledge Base Context:\n"
                for r in kb_results:
                    src = r.get("metadata", {}).get("source_name", "Unknown")
                    kb_text += f"\n**Source: {src}**\n{r['content']}\n"
                parts.append(kb_text)
            else:
                logger.warning("KB query returned no results for kb_uuid=%s", kb_uuid)
        except Exception as e:
            logger.error("KB context retrieval failed for kb_uuid=%s: %s", kb_uuid, e)

    if full_text:
        parts.append(full_text)
    if attachment_context:
        parts.append(attachment_context)

    # Build workspace inventory for organic and document-chat modes.
    # First-session / demo / help paths don't need it.
    team_id = str(user.current_team) if user and user.current_team else None
    inventory = ""
    if user and not is_first_session and not run_demo and not include_onboarding_context:
        try:
            inventory = await _build_workspace_inventory(user_id, team_id)
        except Exception as e:
            logger.warning("Workspace inventory failed: %s", e)

    # Select system prompt based on whether we have document context
    if parts:
        context_block = "\n\n".join(parts)
        prompt = (
            f"{message}\n\n"
            "--- BEGIN REFERENCE DOCUMENTS (provided for context only) ---\n"
            f"{context_block}\n"
            "--- END REFERENCE DOCUMENTS ---"
        )
        system_prompt = DOCUMENT_CHAT_SYSTEM_PROMPT
        if inventory:
            system_prompt = system_prompt + "\n\n" + inventory
    elif is_first_session or run_demo:
        if onboarding_context and onboarding_context.extraction_set_uuid:
            # Agentic demo: build a dynamic prompt with real UUIDs
            # so the agent can run live tool calls during the demo.
            system_prompt = FIRST_SESSION_AGENTIC_PROMPT_TEMPLATE.format(
                sample_doc_uuid=onboarding_context.sample_doc_uuid,
                sample_doc_title=onboarding_context.sample_doc_title,
                extraction_set_uuid=onboarding_context.extraction_set_uuid,
                extraction_set_title=onboarding_context.extraction_set_title,
                kb_uuid=onboarding_context.kb_uuid or "NOT AVAILABLE",
                kb_title=onboarding_context.kb_title or "N/A",
            )
        elif is_first_session:
            # Fallback: text-only conversational onboarding
            system_prompt = FIRST_SESSION_SYSTEM_PROMPT
        else:
            system_prompt = None  # run_demo but no seed content — use default
        prompt = message
    elif include_onboarding_context:
        # Inject Vandalizer help context only when explicitly requested
        # (triggered by the placeholder pills in the chat UI).
        prompt = (
            "--- BEGIN ONBOARDING CONTEXT ---\n"
            f"{VANDALIZER_CONTEXT}\n"
            "--- END ONBOARDING CONTEXT ---\n\n"
            f"User question: {message}"
        )
        system_prompt = HELP_CHAT_SYSTEM_PROMPT
    else:
        prompt = message
        if inventory:
            system_prompt = AGENTIC_CHAT_SYSTEM_PROMPT + "\n\n" + inventory
        else:
            system_prompt = None  # uses default

    # Select agent — agentic (with tools) when user context is available.
    # Agents are cached by model; per-request system prompts (including
    # workspace inventory) are passed via ``instructions`` at iter() time.
    deps = None
    if user and team_access:
        from app.services.chat_deps import AgenticChatDeps

        # Include onboarding sample doc UUID so agent tools can access it
        effective_doc_uuids = list(document_uuids)
        if onboarding_context and onboarding_context.sample_doc_uuid:
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
        )
        agent = create_agentic_chat_agent(
            model_name, system_config_doc=sys_config_doc,
        )
    else:
        agent = create_chat_agent(
            model_name, system_config_doc=sys_config_doc,
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

    try:
        think_parser = _ThinkTagParser()

        iter_kwargs: dict = {
            "message_history": previous_messages,
            "usage_limits": UsageLimits(request_limit=25, tool_calls_limit=15),
        }
        if deps is not None:
            iter_kwargs["deps"] = deps
        if system_prompt is not None:
            iter_kwargs["instructions"] = system_prompt

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
                )

    except UsageLimitExceeded:
        logger.warning("Chat usage limit reached for user %s", user_id)
        yield json.dumps({"kind": "error", "content": "This response used too many tool calls. Try breaking your request into smaller steps."}) + "\n"
        if activity_id:
            ev = await ActivityEvent.get(activity_id)
            if ev:
                ev.status = ActivityStatus.COMPLETED.value
                await ev.save()
    except Exception as e:
        logger.error(f"Chat stream error: {e}")
        yield json.dumps({"kind": "error", "content": str(e)}) + "\n"
        # Mark activity as failed
        if activity_id:
            ev = await ActivityEvent.get(activity_id)
            if ev:
                ev.status = ActivityStatus.FAILED.value
                ev.error = str(e)[:2000]
                await ev.save()



def _get_full_text(documents: list[SmartDocument]) -> str:
    """Combine document texts for direct-prompt chat."""
    parts = []
    for doc in documents:
        if doc.raw_text:
            parts.append(f"\n\n## Document: {doc.title}\n{doc.raw_text}")
    return "".join(parts)


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
    """Build a compact workspace summary for injection into the system prompt.

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
    )

    if activity_id:
        ev = await ActivityEvent.get(activity_id)
        if ev:
            # Reload conversation to get updated message count
            conversation = await ChatConversation.get(conversation.id)
            ev.message_count = len(conversation.messages) if conversation else 0
            ev.status = ActivityStatus.COMPLETED.value
            if usage:
                ev.tokens_input = usage.request_tokens or 0
                ev.tokens_output = usage.response_tokens or 0
                ev.total_tokens = (usage.request_tokens or 0) + (usage.response_tokens or 0)
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
