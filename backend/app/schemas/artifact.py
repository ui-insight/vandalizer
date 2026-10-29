from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.chat_export import ExportMessage


class CreateArtifactRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    html: str = Field(min_length=1, max_length=262144)
    request_id: str = Field(min_length=1, max_length=100)
    project_uuid: Optional[str] = Field(default=None, max_length=200)


class ReviseArtifactRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    html: str = Field(min_length=1, max_length=262144)
    base_revision: str = Field(min_length=1, max_length=64)


class PublishArtifactRequest(BaseModel):
    revision: str = Field(min_length=1, max_length=64)
    separate_link: bool = False


class ShareArtifactRequest(BaseModel):
    team_id: Optional[str] = Field(default=None, max_length=200)
    revision: Optional[str] = Field(default=None, min_length=1, max_length=64)


class ChatArtifactRequest(BaseModel):
    title: str = Field(default="Chat transcript", min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=100)
    messages: list[ExportMessage] = Field(min_length=1, max_length=1000)
    project_uuid: Optional[str] = Field(default=None, max_length=200)
    conversation_uuid: Optional[str] = Field(default=None, max_length=200)
