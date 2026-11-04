from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints

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


class RenameArtifactRequest(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class DuplicateArtifactRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=100)


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


class PageQuestionRequest(BaseModel):
    """A viewer's question or flag about a Page (or one spot on it)."""
    message: str = Field(min_length=1, max_length=2000)
    anchor_id: Optional[str] = Field(default=None, max_length=40)
    revision: Optional[str] = Field(default=None, max_length=64)


class PublicPageQuestionRequest(PageQuestionRequest):
    email: str = Field(min_length=3, max_length=320)
    name: Optional[str] = Field(default=None, max_length=120)
    # Left empty by people; filled by form-filling bots.
    website: Optional[str] = Field(default=None, max_length=200)


class PageAnswerRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    show_on_page: bool = False


class PageFeedbackSettingsRequest(BaseModel):
    public_questions: Optional[bool] = None
    hide_owner_name: Optional[bool] = None
    contact_label: Optional[str] = Field(default=None, max_length=120)
