"""Reusable designs contain no original source values or page revisions."""
from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class PageTemplate(Document):
    uuid: str
    user_id: str
    owner_name: str
    team_id: Optional[str] = None
    name: str
    description: str = ''
    guidance: str = ''
    html: str
    fields: list[dict] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)
    deleted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = 'page_templates'
        indexes = [IndexModel('uuid', unique=True), 'user_id', 'team_id']


class PageTemplateDraft(Document):
    # Beanie supports custom _id types, although Document's annotation is ObjectId.
    id: str  # type: ignore[assignment]
    user_id: str
    html: str
    fields: list[dict] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = 'page_template_drafts'
        indexes = [IndexModel('created_at', expireAfterSeconds=86400), 'user_id']
