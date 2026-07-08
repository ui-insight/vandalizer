"""Chat models  - ChatMessage, FileAttachment, UrlAttachment, ChatConversation."""

import datetime
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


# Replay-time micro-compaction (uplift plan Phase 3): old read-tool results
# are replaced with this marker when the conversation nears its context
# budget. Replay-only — the stored segments (and the UI/audit trail) keep the
# full payloads. The agentic system prompt tells the model it can re-run the
# tool if it needs the data again.
CLEARED_TOOL_RESULT_MARKER = "[Old tool result content cleared]"


class ChatMessage(Document):
    role: ChatRole
    message: str
    thinking: Optional[str] = None
    thinking_duration: Optional[float] = None
    tool_calls: Optional[list[dict]] = None
    tool_results: Optional[list[dict]] = None
    segments: Optional[list[dict]] = None
    citations: Optional[list[dict]] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "chat_message"

    def to_dict(self) -> dict:
        d = {"role": self.role.value, "content": self.message}
        if self.thinking:
            d["thinking"] = self.thinking
        if self.thinking_duration is not None:
            d["thinking_duration"] = self.thinking_duration
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_results:
            d["tool_results"] = self.tool_results
        if self.segments:
            d["segments"] = self.segments
        if self.citations:
            d["citations"] = self.citations
        return d

    def to_model_messages(
        self, cleared_tool_call_ids: frozenset[str] | set[str] = frozenset(),
    ) -> list[ModelMessage]:
        """Reconstruct pydantic-ai messages for this stored chat message.

        Assistant turns may expand into multiple messages when tool calls were
        made: the original ModelResponse (text + ToolCallParts), followed by a
        ModelRequest of ToolReturnParts, then any subsequent ModelResponse
        chunks. Walking ``segments`` preserves the interleaved order so the
        model sees real tool results on the next turn instead of fabricating
        them from its own prior text.

        Tool results whose call id is in ``cleared_tool_call_ids`` replay as
        ``CLEARED_TOOL_RESULT_MARKER`` instead of their stored content
        (micro-compaction; the ToolCallPart/ToolReturnPart pairing stays
        intact so the API never sees an orphaned tool call).
        """
        if self.role == ChatRole.USER:
            return [ModelRequest(parts=[UserPromptPart(content=self.message)])]
        if self.role == ChatRole.SYSTEM:
            return [ModelRequest(parts=[SystemPromptPart(content=self.message)])]
        if self.role != ChatRole.ASSISTANT:
            return [ModelRequest(parts=[UserPromptPart(content=self.message)])]

        if not self.segments:
            if self.message:
                return [ModelResponse(parts=[TextPart(content=self.message)])]
            return []

        messages: list[ModelMessage] = []
        response_parts: list = []
        request_parts: list = []

        def flush_response() -> None:
            if response_parts:
                messages.append(ModelResponse(parts=list(response_parts)))
                response_parts.clear()

        def flush_request() -> None:
            if request_parts:
                messages.append(ModelRequest(parts=list(request_parts)))
                request_parts.clear()

        for seg in self.segments:
            kind = seg.get("kind")
            if kind == "text":
                flush_request()
                content = seg.get("content", "")
                if content:
                    response_parts.append(TextPart(content=content))
            elif kind == "tool_call":
                flush_request()
                call = seg.get("call", {})
                call_id = call.get("tool_call_id") or ""
                if not call_id:
                    continue
                response_parts.append(ToolCallPart(
                    tool_name=call.get("tool_name", ""),
                    args=call.get("args", {}),
                    tool_call_id=call_id,
                ))
            elif kind == "tool_result":
                flush_response()
                result = seg.get("result", {})
                call_id = result.get("tool_call_id") or ""
                if not call_id:
                    continue
                content = result.get("content", "")
                if call_id in cleared_tool_call_ids:
                    content = CLEARED_TOOL_RESULT_MARKER
                request_parts.append(ToolReturnPart(
                    tool_name=result.get("tool_name", ""),
                    content=content,
                    tool_call_id=call_id,
                ))

        flush_response()
        flush_request()
        return messages


class FileAttachment(Document):
    filename: str
    file_type: Optional[str] = None
    content: str = ""
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    user_id: str

    class Settings:
        name = "file_attachment"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "filename": self.filename,
            "file_type": self.file_type,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user_id": self.user_id,
        }


class UrlAttachment(Document):
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    user_id: str

    class Settings:
        name = "url_attachment"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user_id": self.user_id,
        }


class ChatConversation(Document):
    uuid: str
    title: str
    user_id: str
    team_id: Optional[str] = None
    is_first_session: bool = False
    messages: list[PydanticObjectId] = []
    file_attachments: list[PydanticObjectId] = []
    url_attachments: list[PydanticObjectId] = []
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    # Context management
    context_mode: str = "full"  # "full" | "truncated" | "compacted"
    context_cutoff_index: int = 0
    compact_summary: Optional[str] = None

    # Usage anchor for cheap context estimation (uplift plan Phase 2).
    # Stamped after each successful turn: the provider-reported context size
    # of that turn's final model request (input + cache read/write + output),
    # and the stored-message count at stamping time. The next turn's size is
    # then anchor + rough(new user message) — no tokenizer pass over history.
    # message_count mismatch (or 0 anchor) means "anchor stale, fall back to
    # token counting"; truncate/compact/clear endpoints reset these.
    last_context_tokens: int = 0
    last_context_message_count: int = -1

    # Replay-time micro-compaction boundary (uplift plan Phase 3). Compactable
    # tool results in messages BEFORE this index replay as
    # CLEARED_TOOL_RESULT_MARKER. Monotonic — it only advances (chat_service
    # moves it when the context estimate crosses the trigger), so the replayed
    # prefix stays byte-stable between advances and the provider prompt cache
    # keeps hitting.
    tool_results_cleared_before: int = 0

    # Write-tool confirmation handshake. Each entry is
    # {"fp": <fingerprint>, "turn": <message-count when armed>, "tool": <name>}.
    # A write tool only executes when a matching entry was armed on an EARLIER
    # turn, so the agent cannot self-confirm a mutation within a single turn —
    # a real user message must intervene. See chat_tools._confirm_gate.
    pending_confirmations: list[dict] = []

    class Settings:
        name = "chat_conversation"
        indexes = [
            "uuid",
            "user_id",
            "team_id",
            [("user_id", 1), ("updated_at", -1)],
            [("team_id", 1), ("updated_at", -1)],
        ]

    async def add_message(
        self,
        role: ChatRole,
        content: str,
        thinking: Optional[str] = None,
        thinking_duration: Optional[float] = None,
        tool_calls: Optional[list[dict]] = None,
        tool_results: Optional[list[dict]] = None,
        segments: Optional[list[dict]] = None,
        citations: Optional[list[dict]] = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            role=role,
            message=content,
            thinking=thinking or None,
            thinking_duration=thinking_duration,
            tool_calls=tool_calls or None,
            tool_results=tool_results or None,
            segments=segments or None,
            citations=citations or None,
        )
        await msg.insert()
        self.messages.append(msg.id)
        self.updated_at = datetime.datetime.now()
        await self.save()
        return msg

    async def get_messages(self) -> list[dict]:
        msgs = await ChatMessage.find({"_id": {"$in": self.messages}}).to_list()
        order = {mid: i for i, mid in enumerate(self.messages)}
        msgs.sort(key=lambda m: order.get(m.id, 0))
        return [m.to_dict() for m in msgs]

    def _cleared_tool_call_ids(
        self, msgs: list["ChatMessage"], compactable_tools: frozenset[str] | set[str],
    ) -> set[str]:
        """Tool-call ids whose results replay as the cleared marker.

        A result is cleared when its message sits before the persisted
        ``tool_results_cleared_before`` boundary AND its tool is compactable
        (read-type, safely re-runnable — never write-tool previews, which the
        confirm gate replays verbatim). Floor: the single most recent
        compactable result in the whole conversation is always kept, so the
        model retains at least one concrete result to ground on even when
        every result is old.
        """
        boundary = self.tool_results_cleared_before or 0
        if boundary <= 0 or not compactable_tools:
            return set()

        last_compactable_id: str | None = None
        for m in msgs:
            for seg in (m.segments or []):
                if seg.get("kind") != "tool_result":
                    continue
                r = seg.get("result", {})
                if r.get("tool_name") in compactable_tools and r.get("tool_call_id"):
                    last_compactable_id = r["tool_call_id"]

        cleared: set[str] = set()
        for i, m in enumerate(msgs):
            if i >= boundary:
                break
            for seg in (m.segments or []):
                if seg.get("kind") != "tool_result":
                    continue
                r = seg.get("result", {})
                call_id = r.get("tool_call_id")
                if (
                    call_id
                    and call_id != last_compactable_id
                    and r.get("tool_name") in compactable_tools
                ):
                    cleared.add(call_id)
        return cleared

    async def to_model_messages(
        self, compactable_tools: frozenset[str] | set[str] | None = None,
    ) -> list[ModelMessage]:
        msgs = await ChatMessage.find({"_id": {"$in": self.messages}}).to_list()
        order = {mid: i for i, mid in enumerate(self.messages)}
        msgs.sort(key=lambda m: order.get(m.id, 0))

        result: list[ModelMessage] = []

        # When context has been compacted, prepend the summary
        if self.context_mode == "compacted" and self.compact_summary:
            result.append(ModelRequest(parts=[SystemPromptPart(
                content=f"Previous conversation summary:\n{self.compact_summary}"
            )]))

        cleared_ids = (
            self._cleared_tool_call_ids(msgs, compactable_tools)
            if compactable_tools
            else set()
        )

        # Only include messages from the cutoff index onward
        if self.context_mode in ("truncated", "compacted") and self.context_cutoff_index > 0:
            active_msgs = msgs[self.context_cutoff_index:]
        else:
            active_msgs = msgs

        for m in active_msgs:
            result.extend(m.to_model_messages(cleared_tool_call_ids=cleared_ids))
        return result

    async def get_file_attachments(self) -> list[FileAttachment]:
        if not self.file_attachments:
            return []
        return await FileAttachment.find(
            {"_id": {"$in": self.file_attachments}}
        ).to_list()

    async def get_url_attachments(self) -> list[UrlAttachment]:
        if not self.url_attachments:
            return []
        return await UrlAttachment.find(
            {"_id": {"$in": self.url_attachments}}
        ).to_list()

    def generate_title(self) -> None:
        """Set title from conversation title, truncated to 50 chars."""
        if self.title and len(self.title) > 50:
            self.title = self.title[:50] + "..."
