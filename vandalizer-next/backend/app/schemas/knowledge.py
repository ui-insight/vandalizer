"""Knowledge Base schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel


class CreateKBRequest(BaseModel):
    title: str
    description: Optional[str] = None


class UpdateKBRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    shared_with_team: Optional[bool] = None
    group_ids: Optional[list[str]] = None


class AddDocumentsRequest(BaseModel):
    document_uuids: list[str]


class AddUrlsRequest(BaseModel):
    urls: list[str]
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    allowed_domains: str = ""  # comma-separated


class KBSourceResponse(BaseModel):
    uuid: str
    source_type: str
    document_uuid: Optional[str] = None
    url: Optional[str] = None
    url_title: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    chunk_count: int = 0
    created_at: Optional[str] = None


class KBResponse(BaseModel):
    uuid: str
    title: str
    description: Optional[str] = None
    status: str
    shared_with_team: bool = False
    verified: bool = False
    group_ids: list[str] = []
    total_sources: int = 0
    sources_ready: int = 0
    sources_failed: int = 0
    total_chunks: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class KBDetailResponse(KBResponse):
    sources: list[KBSourceResponse] = []


class KBStatusResponse(BaseModel):
    uuid: str
    status: str
    total_sources: int = 0
    sources_ready: int = 0
    sources_failed: int = 0
    total_chunks: int = 0
    sources: list[dict] = []
