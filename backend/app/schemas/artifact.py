import datetime
from typing import Annotated, Literal, Optional

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
    # Link access (see public_page_access). Omitted fields keep the link's
    # current settings; a new link defaults to anyone, never expiring.
    expires_at: Optional[datetime.datetime] = None
    audience: Optional[Literal["anyone", "signed_in"]] = None
    emails: Optional[list[Annotated[str, StringConstraints(max_length=254)]]] = Field(default=None, max_length=50)


class PublicLinkSettingsRequest(BaseModel):
    """Change an existing public link: the main link, or ``revision``'s version link."""
    revision: Optional[str] = Field(default=None, min_length=1, max_length=64)
    expires_at: Optional[datetime.datetime] = None
    audience: Literal["anyone", "signed_in"] = "anyone"
    emails: list[Annotated[str, StringConstraints(max_length=254)]] = Field(default_factory=list, max_length=50)


class ShareArtifactRequest(BaseModel):
    team_id: Optional[str] = Field(default=None, max_length=200)
    revision: Optional[str] = Field(default=None, min_length=1, max_length=64)


class ChatArtifactRequest(BaseModel):
    title: str = Field(default="Chat transcript", min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=100)
    messages: list[ExportMessage] = Field(min_length=1, max_length=1000)
    project_uuid: Optional[str] = Field(default=None, max_length=200)
    conversation_uuid: Optional[str] = Field(default=None, max_length=200)



class PageTextEdit(BaseModel):
    tag: str = Field(min_length=1, max_length=12)
    index: int = Field(ge=0, le=100000)
    original: str = Field(max_length=20000)
    text: str = Field(max_length=20000)


class PageTextEditsRequest(BaseModel):
    """Text the owner typed into the page in Edit text mode (page_text_edits)."""
    base_revision: str = Field(min_length=1, max_length=64)
    edits: list[PageTextEdit] = Field(min_length=1, max_length=200)
