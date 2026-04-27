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
    organization_ids: Optional[list[str]] = None


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
    organization_ids: list[str] = []
    total_sources: int = 0
    sources_ready: int = 0
    sources_failed: int = 0
    total_chunks: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Scope & ownership fields for the UI
    user_id: Optional[str] = None
    scope: Optional[str] = None  # "mine" | "team" | "verified" | "reference"
    is_reference: bool = False
    source_kb_uuid: Optional[str] = None  # set when is_reference=True
    reference_uuid: Optional[str] = None  # the reference's own uuid


class KBListResponse(BaseModel):
    items: list[KBResponse] = []
    total: int = 0


class AdoptKBRequest(BaseModel):
    note: Optional[str] = None
    team_id: Optional[str] = None  # adopt to a specific team (default: personal)


class KBReferenceResponse(BaseModel):
    uuid: str
    source_kb_uuid: str
    user_id: str
    team_id: Optional[str] = None
    note: Optional[str] = None
    pinned: bool = False
    created_at: Optional[str] = None


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


# --- Export / Import ---

KB_EXPORT_FORMAT_VERSION = 1


class KBExportSource(BaseModel):
    source_type: str  # "document" | "url"
    document_uuid: Optional[str] = None
    document_title: Optional[str] = None  # snapshot of SmartDocument.title at export time
    url: Optional[str] = None
    url_title: Optional[str] = None
    content: Optional[str] = None  # cached raw text (for URLs) or document raw_text (for docs)
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    parent_source_uuid: Optional[str] = None
    crawled_urls: Optional[list[str]] = None


class KBExportPayload(BaseModel):
    format_version: int = KB_EXPORT_FORMAT_VERSION
    exported_at: Optional[str] = None
    title: str
    description: Optional[str] = None
    sources: list[KBExportSource] = []


class ImportKBRequest(BaseModel):
    payload: KBExportPayload
    title: Optional[str] = None  # override title on import


class ImportKBResponse(BaseModel):
    uuid: str
    title: str
    imported_sources: int
