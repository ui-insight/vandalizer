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
    UserPromptPart,
)


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(Document):
    role: ChatRole
    message: str
    thinking: Optional[str] = None
    thinking_duration: Optional[float] = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "chat_message"

    def to_dict(self) -> dict:
        d = {"role": self.role.value, "content": self.message}
        if self.thinking:
            d["thinking"] = self.thinking
        if self.thinking_duration is not None:
            d["thinking_duration"] = self.thinking_duration
        return d

    def to_model_message(self) -> ModelMessage:
        if self.role == ChatRole.USER:
            return ModelRequest(parts=[UserPromptPart(content=self.message)])
        elif self.role == ChatRole.ASSISTANT:
            return ModelResponse(parts=[TextPart(content=self.message)])
        elif self.role == ChatRole.SYSTEM:
            return ModelRequest(parts=[SystemPromptPart(content=self.message)])
        return ModelRequest(parts=[UserPromptPart(content=self.message)])


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
    ) -> ChatMessage:
        msg = ChatMessage(
            role=role,
            message=content,
            thinking=thinking or None,
            thinking_duration=thinking_duration,
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

    async def to_model_messages(self) -> list[ModelMessage]:
        msgs = await ChatMessage.find({"_id": {"$in": self.messages}}).to_list()
        order = {mid: i for i, mid in enumerate(self.messages)}
        msgs.sort(key=lambda m: order.get(m.id, 0))

        result: list[ModelMessage] = []

        # When context has been compacted, prepend the summary
        if self.context_mode == "compacted" and self.compact_summary:
            result.append(ModelRequest(parts=[SystemPromptPart(
                content=f"Previous conversation summary:\n{self.compact_summary}"
            )]))

        # Only include messages from the cutoff index onward
        if self.context_mode in ("truncated", "compacted") and self.context_cutoff_index > 0:
            active_msgs = msgs[self.context_cutoff_index:]
        else:
            active_msgs = msgs

        result.extend([m.to_model_message() for m in active_msgs])
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
