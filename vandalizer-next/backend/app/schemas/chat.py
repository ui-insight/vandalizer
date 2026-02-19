"""Chat schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    activity_id: Optional[str] = None
    document_uuids: list[str] = []
    current_space_id: Optional[str] = None
    folder_uuid: Optional[str] = None


class AddLinkRequest(BaseModel):
    link: str
    current_space_id: Optional[str] = None
    current_activity_id: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    messages: list[dict]
    url_attachments: list[dict] = []
    file_attachments: list[dict] = []


class ChatDownloadRequest(BaseModel):
    content: str
    format: str = "txt"
