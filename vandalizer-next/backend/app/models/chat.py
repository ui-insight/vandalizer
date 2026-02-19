"""Chat models — ChatMessage, FileAttachment, UrlAttachment, ChatConversation."""

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
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "chat_message"

    def to_dict(self) -> dict:
        return {"role": self.role.value, "content": self.message}

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
    messages: list[PydanticObjectId] = []
    file_attachments: list[PydanticObjectId] = []
    url_attachments: list[PydanticObjectId] = []
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "chat_conversation"

    async def add_message(self, role: ChatRole, content: str) -> ChatMessage:
        msg = ChatMessage(role=role, message=content)
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
        return [m.to_model_message() for m in msgs]

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
