"""KBSuggestion model - community suggestions for knowledge base improvements."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


class KBSuggestion(Document):
    """A suggestion from a user to add a source or improve a knowledge base."""

    uuid: str = ""
    knowledge_base_uuid: str
    suggested_by_user_id: str
    suggested_by_name: Optional[str] = None
    suggestion_type: str  # "add_url" | "add_document" | "general"
    url: Optional[str] = None
    document_uuid: Optional[str] = None
    note: Optional[str] = None
    status: str = "pending"  # "pending" | "accepted" | "rejected"
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    class Settings:
        name = "kb_suggestions"
        indexes = ["uuid", "knowledge_base_uuid", "status"]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
