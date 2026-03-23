"""Knowledge Base models for curated document/URL corpora."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


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
    # Crawl fields
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    parent_source_uuid: Optional[str] = None  # links crawled children to parent
    crawled_urls: Optional[list[str]] = None  # list of discovered URLs (on parent)
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    processed_at: Optional[datetime.datetime] = None

    class Settings:
        name = "knowledge_base_sources"
        indexes = ["uuid", "knowledge_base_uuid"]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex


class KnowledgeBaseReference(Document):
    """A lightweight bookmark to a verified/shared KB.

    Does NOT duplicate ChromaDB data — points to the original KB's collection.
    When the user chats with a referenced KB, the system resolves to the
    source KB's ``collection_name``.
    """

    uuid: str = ""
    user_id: str
    team_id: Optional[str] = None
    source_kb_uuid: str  # the verified KB being referenced
    note: Optional[str] = None
    pinned: bool = False
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc),
    )

    class Settings:
        name = "knowledge_base_references"
        indexes = ["uuid", "user_id", "source_kb_uuid", "team_id"]

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
    shared_with_team: bool = False
    verified: bool = False
    organization_ids: list[str] = Field(default_factory=list)  # Org UUIDs for visibility scoping
    status: str = "empty"  # empty | building | ready | error
    total_sources: int = 0
    sources_ready: int = 0
    sources_failed: int = 0
    total_chunks: int = 0
    collection_name: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "knowledge_bases"
        indexes = ["uuid", "user_id", "team_id"]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
        if not self.collection_name:
            self.collection_name = f"kb_{self.uuid}"
