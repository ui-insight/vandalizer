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
    document_uuids: list[str] = []
    folder_uuids: list[str] = []


class AddFolderRequest(BaseModel):
    folder_uuid: str
    include_subfolders: bool = True


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
    allowed_domains: str = ""  # comma-separated hosts, optionally with path prefixes (example.com/irb)


class KBSourceCurrency(BaseModel):
    """Refresh / ingestion provenance for one source (see
    app.utils.kb_source_currency). Lets an evaluator verify source currency
    from the UI or the export without re-fetching every original."""

    # never_ingested | ingested | refreshed | unchanged | retained_previous
    # | retrieval_failed | ingestion_failed
    status: str
    last_refresh_attempted_at: Optional[str] = None
    last_retrieved_at: Optional[str] = None
    last_ingested_at: Optional[str] = None
    # When the text currently held and served was retrieved — unchanged by a
    # failed refresh, so it is the "retained content" date.
    content_retrieved_at: Optional[str] = None
    content_hash: Optional[str] = None
    content_hash_algorithm: str = "sha256"
    # False when the hash was computed just now from the retained snapshot
    # because the source predates hash recording at ingest.
    content_hash_recorded: bool = False
    last_refresh_outcome: Optional[str] = None
    last_refresh_error: Optional[str] = None


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
    # URL source whose extracted text was cut off at the fetcher size cap:
    # "ready" but incomplete, so the UI warns instead of showing a clean check.
    truncated: bool = False
    created_at: Optional[str] = None
    # When the source's text was last fetched/ingested. Surfaced on the list
    # so a user can tell how stale a URL snapshot is before refreshing it.
    processed_at: Optional[str] = None
    currency: Optional[KBSourceCurrency] = None


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
    # Navigation pages the crawl followed for links but did not embed
    skipped_urls: Optional[list[str]] = None
    child_sources: list[KBSourceResponse] = []  # Crawled children (when this is a parent)


class UpdateSourceRequest(BaseModel):
    """Patch a single KB source. Only fields explicitly present are applied;
    an empty string clears that field (reverts to the auto-derived value)."""
    custom_name: Optional[str] = None
    source_reference: Optional[str] = None


class KBOptimizationStatusResponse(BaseModel):
    """What the "Optimized" chip means for this KB, and whether it still holds.

    ``applied``: tuned RAG settings are live. ``stale``: live, but the sources
    or test questions have changed materially since they were tuned.
    ``available``: a completed optimization has settings that were never
    applied (or were reverted). See ``services/kb_optimization_status``.
    """
    state: str  # applied | stale | available
    applied_at: Optional[str] = None
    applied_run_uuid: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_uuid: Optional[str] = None
    tuned_keys: list[str] = []
    stale: bool = False
    stale_reasons: list[str] = []
    sources_at_run: int = 0
    sources_added: int = 0
    sources_removed: int = 0
    queries_at_run: int = 0
    queries_added: int = 0
    queries_removed: int = 0
    queries_edited: int = 0


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
    # Whether the requesting user may perform manage-level actions (add sources,
    # rename, share, delete). Lets the UI disable those affordances up front
    # instead of letting the user complete a flow that ends in a 403 — e.g. an
    # adopted verified catalog KB, which is viewable by everyone but manageable
    # only by its owner, an examiner, or an admin. Defaults True because the
    # endpoints that don't set it explicitly (create/import/adopt) only ever
    # return a KB the requester just became the owner of.
    can_manage: bool = True
    # Set by KB Autovalidate's apply path. Presence (not value) is what the UI
    # surfaces as a small "Optimized" chip.
    has_optimized_config: bool = False
    optimized_config_set_at: Optional[str] = None
    # Full story behind the chip — applied / stale / available, when, from
    # which run, and what changed since. None when there is nothing to say.
    # Populated by the v2 list and the detail endpoint.
    optimization: Optional[KBOptimizationStatusResponse] = None
    # AI-trust signals from the latest KB validation run.
    # Scores are 0-1; lift is also 0-1 (e.g., 0.28 == +28pts vs. baseline).
    last_validation_score: Optional[float] = None
    last_validation_baseline_score: Optional[float] = None
    last_validation_lift: Optional[float] = None
    last_validated_at: Optional[str] = None
    # Per-requesting-user: when this user last chatted with the KB. Powers the
    # "Recently Used" sort. None = never used (or legacy pre-tracking usage).
    last_used_at: Optional[str] = None


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
