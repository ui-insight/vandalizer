"""Knowledge Base schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel

from app.utils.naming import EntityName, OptionalEntityName


class CreateKBRequest(BaseModel):
    title: EntityName
    description: Optional[str] = None


class UpdateKBRequest(BaseModel):
    title: OptionalEntityName = None
    description: Optional[str] = None
    shared_with_team: Optional[bool] = None
    organization_ids: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class AddDocumentsRequest(BaseModel):
    document_uuids: list[str]


class ConvertDocumentsRequest(BaseModel):
    """Wrap one or more SmartDocuments in a new KB so they can be retrieved
    instead of inlined. Used by the chat / workflow "Convert to Knowledge
    Base" affordance shown when a doc is too large for the current model.
    """
    document_uuids: list[str]
    title: Optional[str] = None  # defaults to the first doc's title


class ShareKBRequest(BaseModel):
    comment: Optional[str] = None


class AddUrlsRequest(BaseModel):
    urls: list[str]
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    allowed_domains: str = ""  # comma-separated


class KBSourceResponse(BaseModel):
    uuid: str
    source_type: str
    document_uuid: Optional[str] = None
    document_title: Optional[str] = None  # Resolved from SmartDocument for display
    url: Optional[str] = None
    url_title: Optional[str] = None
    custom_name: Optional[str] = None  # user-provided label; UI prefers this over title/url
    source_reference: Optional[str] = None  # user-verifiable provenance, shown as "Source: …"
    status: str
    error_message: Optional[str] = None
    chunk_count: int = 0
    created_at: Optional[str] = None


class KBSourceDetailResponse(KBSourceResponse):
    """Full source detail for the source inspector modal.

    Includes cached content (for URLs), crawl metadata, and references to
    parent/child sources when applicable.
    """

    content: Optional[str] = None  # Cached extracted text (URL sources)
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    parent_source_uuid: Optional[str] = None
    crawled_urls: Optional[list[str]] = None
    child_sources: list[KBSourceResponse] = []  # Crawled children (when this is a parent)
    processed_at: Optional[str] = None


class UpdateSourceRequest(BaseModel):
    """Patch a single KB source. Only fields explicitly present are applied;
    an empty string clears that field (reverts to the auto-derived value)."""
    custom_name: Optional[str] = None
    source_reference: Optional[str] = None


class KBResponse(BaseModel):
    uuid: str
    title: str
    description: Optional[str] = None
    status: str
    shared_with_team: bool = False
    team_owned: bool = False
    verified: bool = False
    organization_ids: list[str] = []
    tags: list[str] = []
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
    # Set by KB Autovalidate's apply path. Presence (not value) is what the UI
    # surfaces as a small "Optimized" chip.
    has_optimized_config: bool = False
    optimized_config_set_at: Optional[str] = None
    # AI-trust signals from the latest KB validation run.
    # Scores are 0-1; lift is also 0-1 (e.g., 0.28 == +28pts vs. baseline).
    last_validation_score: Optional[float] = None
    last_validation_baseline_score: Optional[float] = None
    last_validation_lift: Optional[float] = None
    last_validated_at: Optional[str] = None


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
    custom_name: Optional[str] = None  # user's chosen label, carried across export/import
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
    tags: list[str] = []
    sources: list[KBExportSource] = []


class ImportKBRequest(BaseModel):
    payload: KBExportPayload
    title: Optional[str] = None  # override title on import


class ImportKBResponse(BaseModel):
    uuid: str
    title: str
    imported_sources: int
