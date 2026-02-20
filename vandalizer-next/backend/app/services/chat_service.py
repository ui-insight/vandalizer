"""Chat service  - streaming chat with full document context."""

import json
import logging
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
from app.services.config_service import get_user_model_name
from app.services.llm_service import create_chat_agent

logger = logging.getLogger(__name__)


async def chat_stream(
    message: str,
    document_uuids: list[str],
    conversation_uuid: str,
    user_id: str,
    space: Optional[str] = None,
    activity_id: Optional[str] = None,
    settings=None,
    model_override: Optional[str] = None,
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
    sys_config_doc = {
        "available_models": cfg.available_models,
        "llm_endpoint": cfg.llm_endpoint,
    }

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
    for att in file_attachments:
        if att.content:
            attachment_context += (
                f"\n\n## Document: {att.filename}\n\n{att.content[:10000]}\n"
            )

    # Load message history
    previous_messages: list[ModelMessage] = await conversation.to_model_messages()

    # Build prompt — keep it clean; system prompt handles behavior
    full_text = _get_full_text(documents)
    agent = create_chat_agent(model_name, system_config_doc=sys_config_doc)

    parts: list[str] = []
    if full_text:
        parts.append(full_text)
    if attachment_context:
        parts.append(attachment_context)

    if parts:
        prompt = f"{message}\n\n---\n\n{''.join(parts)}"
    else:
        prompt = message

    # Stream the response
    full_response: list[str] = []
    full_thinking: list[str] = []
    thinking_started_at: float | None = None
    thinking_duration: float | None = None
    thinking_done_emitted = False

    try:
        async with agent.iter(
            prompt, message_history=previous_messages
        ) as agent_run:
            async for node in agent_run:
                if Agent.is_model_request_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:
                            chunk, is_thinking, is_text = _event_to_chunk(
                                event, full_response, full_thinking,
                            )
                            # Start thinking timer on first thinking chunk
                            if is_thinking and thinking_started_at is None:
                                thinking_started_at = time.monotonic()
                            # Emit thinking_done when first text arrives after thinking
                            if is_text and thinking_started_at and not thinking_done_emitted:
                                thinking_duration = round(
                                    time.monotonic() - thinking_started_at, 1
                                )
                                thinking_done_emitted = True
                                yield json.dumps({
                                    "kind": "thinking_done",
                                    "content": "",
                                    "duration": thinking_duration,
                                }) + "\n"
                            if chunk:
                                yield chunk

            if agent_run.result:
                usage = agent_run.result.usage()
                assistant_message = agent_run.result.output
                thinking_text = "".join(full_thinking) or None
                await _finalize(
                    conversation, assistant_message, documents,
                    usage, activity_id, user_id,
                    thinking=thinking_text,
                    thinking_duration=thinking_duration,
                )

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


def _event_to_chunk(
    event, full_response: list[str], full_thinking: list[str],
) -> tuple[Optional[str], bool, bool]:
    """Convert a pydantic-ai stream event to a JSON chunk string.

    Returns (chunk_json, is_thinking, is_text).
    """
    if isinstance(event, PartStartEvent):
        if isinstance(event.part, TextPart):
            content = event.part.content or ""
            full_response.append(content)
            return json.dumps({"kind": "text", "content": content}) + "\n", False, True
        elif isinstance(event.part, ThinkingPart):
            content = event.part.content or ""
            full_thinking.append(content)
            return json.dumps({"kind": "thinking", "content": content}) + "\n", True, False
    elif isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            content = event.delta.content_delta or ""
            full_response.append(content)
            return json.dumps({"kind": "text", "content": content}) + "\n", False, True
        elif isinstance(event.delta, ThinkingPartDelta):
            content = event.delta.content_delta or ""
            full_thinking.append(content)
            return json.dumps({"kind": "thinking", "content": content}) + "\n", True, False
    return None, False, False


def _get_full_text(documents: list[SmartDocument]) -> str:
    """Combine document texts for direct-prompt chat."""
    parts = []
    for doc in documents:
        if doc.raw_text:
            parts.append(f"\n\n## Document: {doc.title}\n{doc.raw_text}")
    return "".join(parts)


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
                ev.tokens_input = usage.request_tokens or 0
                ev.tokens_output = usage.response_tokens or 0
                ev.total_tokens = (usage.request_tokens or 0) + (usage.response_tokens or 0)
            ev.documents_touched = len(documents)
            from datetime import datetime, timezone
            ev.finished_at = datetime.now(timezone.utc)
            ev.last_updated_at = datetime.now(timezone.utc)
            await ev.save()
