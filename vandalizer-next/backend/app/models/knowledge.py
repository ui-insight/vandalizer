"""Knowledge Base models for curated document/URL corpora."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document


class KnowledgeBaseSource(Document):
    """A single source (document or URL) within a knowledge base."""

    uuid: str = ""
    knowledge_base_uuid: str
    source_type: str  # "document" | "url"
    document_uuid: Optional[str] = None
    url: Optional[str] = None
    url_title: Optional[str] = None
    content: Optional[str] = None
    status: str = "pending"  # pending | processing | ready | error
    error_message: Optional[str] = None
    chunk_count: int = 0
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    processed_at: Optional[datetime.datetime] = None

    class Settings:
        name = "knowledge_base_sources"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex


class KnowledgeBase(Document):
    """A curated knowledge base built from documents and URLs."""

    uuid: str = ""
    title: str
    description: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    space: Optional[str] = None
    status: str = "empty"  # empty | building | ready | error
    total_sources: int = 0
    sources_ready: int = 0
    sources_failed: int = 0
    total_chunks: int = 0
    collection_name: Optional[str] = None
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    updated_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    class Settings:
        name = "knowledge_bases"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
        if not self.collection_name:
            self.collection_name = f"kb_{self.uuid}"
