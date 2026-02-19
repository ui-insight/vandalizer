"""Chat service — streaming chat with RAG, ported from ChatManager."""

import asyncio
import json
import logging
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
from app.services.config_service import get_user_model_name
from app.services.document_manager import DocumentManager
from app.services.llm_service import (
    RagDeps,
    create_chat_agent,
    create_rag_agent,
)

logger = logging.getLogger(__name__)


async def chat_stream(
    message: str,
    document_uuids: list[str],
    conversation_uuid: str,
    user_id: str,
    space: Optional[str] = None,
    activity_id: Optional[str] = None,
    settings=None,
) -> AsyncGenerator[str, None]:
    """Async generator yielding newline-delimited JSON chunks for streaming chat."""

    # Resolve model
    model_name = await get_user_model_name(user_id)

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

    # Build prompt
    max_context_length = settings.max_context_length if settings else 100000

    prompt = ""
    if documents:
        prompt = "You are given the following document(s). "
    prompt += (
        "Answer the query clearly and concisely, formatting your response in "
        "well-structured markdown. Do not restate or include the original query "
        "in your answer."
    )

    # Decide direct vs RAG
    full_text = _get_full_text(documents)
    agent: Agent

    if len(full_text) < max_context_length:
        prompt += f"\n\n# Query: {message}\n\n# Context: \n{full_text}"
        agent = create_chat_agent(model_name)
    else:
        prompt += f"\n\n# Document(s): {[doc.uuid for doc in documents]}\n"
        agent = create_rag_agent(model_name)

    # Add attachment context
    if attachment_context:
        prompt = f"{prompt}\n\n---\n# Attached Context:{attachment_context}\n---\n"

    # Stream the response
    full_response: list[str] = []

    try:
        if len(full_text) >= max_context_length:
            # RAG path — needs deps, run in thread for sync ChromaDB calls
            doc_manager = DocumentManager(
                persist_directory=settings.chromadb_persist_dir if settings else "data/chromadb"
            )
            deps = RagDeps(
                doc_manager=doc_manager,
                user_id=user_id,
                documents=documents,
            )
            async with agent.iter(
                prompt, message_history=previous_messages, deps=deps
            ) as agent_run:
                async for node in agent_run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(agent_run.ctx) as stream:
                            async for event in stream:
                                chunk = _event_to_chunk(event, full_response)
                                if chunk:
                                    yield chunk

                if agent_run.result:
                    usage = agent_run.result.usage()
                    assistant_message = agent_run.result.output
                    await _finalize(
                        conversation, assistant_message, documents,
                        usage, activity_id, user_id,
                    )
        else:
            # Direct path — full text in prompt
            async with agent.iter(
                prompt, message_history=previous_messages
            ) as agent_run:
                async for node in agent_run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(agent_run.ctx) as stream:
                            async for event in stream:
                                chunk = _event_to_chunk(event, full_response)
                                if chunk:
                                    yield chunk

                if agent_run.result:
                    usage = agent_run.result.usage()
                    assistant_message = agent_run.result.output
                    await _finalize(
                        conversation, assistant_message, documents,
                        usage, activity_id, user_id,
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


def _event_to_chunk(event, full_response: list[str]) -> Optional[str]:
    """Convert a pydantic-ai stream event to a JSON chunk string."""
    if isinstance(event, PartStartEvent):
        if isinstance(event.part, TextPart):
            content = event.part.content or ""
            full_response.append(content)
            return json.dumps({"kind": "text", "content": content}) + "\n"
        elif isinstance(event.part, ThinkingPart):
            return json.dumps({"kind": "thinking", "content": event.part.content or ""}) + "\n"
    elif isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            content = event.delta.content_delta or ""
            full_response.append(content)
            return json.dumps({"kind": "text", "content": content}) + "\n"
        elif isinstance(event.delta, ThinkingPartDelta):
            return json.dumps({"kind": "thinking", "content": event.delta.content_delta or ""}) + "\n"
    return None


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
) -> None:
    """Save assistant message and update activity metrics."""
    await conversation.add_message(ChatRole.ASSISTANT, assistant_message)

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
