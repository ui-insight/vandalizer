"""Chat schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    activity_id: Optional[str] = None
    document_uuids: list[str] = []
    folder_uuids: list[str] = []
    model: Optional[str] = None
    knowledge_base_uuid: Optional[str] = None
    include_onboarding_context: bool = False
    is_first_session: bool = False


class AddLinkRequest(BaseModel):
    link: str
    current_activity_id: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    messages: list[dict]
    url_attachments: list[dict] = []
    file_attachments: list[dict] = []


class ChatDownloadRequest(BaseModel):
    content: str
    format: str = "txt"


class TruncateContextRequest(BaseModel):
    conversation_uuid: str
    cutoff_index: int = 0


class CompactContextRequest(BaseModel):
    conversation_uuid: str


class ClearContextRequest(BaseModel):
    conversation_uuid: str
