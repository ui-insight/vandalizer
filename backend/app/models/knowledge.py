"""Knowledge Base models for curated document/URL corpora."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class KnowledgeBaseSource(Document):
    """A single source (document or URL) within a knowledge base."""

    uuid: str = ""
    knowledge_base_uuid: str
    source_type: str  # "document" | "url"
    document_uuid: Optional[str] = None
    url: Optional[str] = None
    url_title: Optional[str] = None
    custom_name: Optional[str] = None  # user-provided label; overrides auto-derived title
    # The document's filename, captured when its text was ingested. The KB
    # keeps answering from the indexed chunks after the document is deleted
    # from Files, and without this the row has nothing to show but its UUID.
    document_title: Optional[str] = None
    source_reference: Optional[str] = None  # user-verifiable provenance (origin URL / citation); shown as "Source: …"
    # Sources in the same KB that this one revises (a supplement, policy
    # notice or FAQ that amends a base document). Retrieval searches this
    # source whenever one of those is retrieved, and tells the model this one
    # governs where they conflict. Set by the KB owner; see set_source_amends.
    amends_source_uuids: list[str] = Field(default_factory=list)
    content: Optional[str] = None
    # "skipped" is transient: the crawler marks a navigation page skipped and
    # then deletes the record, so it should not be seen on a stored source.
    # "held": a fetched page carried hidden or AI-addressed text and was not
    # embedded; it waits for the user to add it anyway or remove it.
    status: str = "pending"  # pending | processing | ready | error | skipped | held
    error_message: Optional[str] = None
    chunk_count: int = 0
    # The chunker that cut the indexed chunks (kb_chunking.CHUNKER_VERSION),
    # written with the ingestion stamp. None: indexed before it was recorded,
    # by the fixed 1,000/200 window. scripts/rechunk_knowledge_bases.py
    # rebuilds sources below the current version.
    chunker_version: Optional[int] = None
    # True when the fetched web page's extracted text was cut off at the fetcher
    # size cap — the source is "ready" but incomplete, so the UI shows a warning
    # rather than a clean check. Only set for URL sources.
    truncated: bool = False
    # Caveats recorded by the last successful fetch that are not failures
    # (``WebFetchResult.advisories``): currently ``"hidden_text_unchecked"``,
    # a fetched PDF whose hidden-text scrub could not inspect the file, so its
    # indexed text may include content the page never displays. Replaced —
    # so cleared — by every later successful fetch. Rows from before this
    # field existed read as empty. Only set for URL sources.
    warnings: list[str] = Field(default_factory=list)
    # Why the last fetch was held instead of embedded
    # (``fetched_page_screen.PageFinding.to_dict()``: kind, reason, excerpt,
    # fingerprint). Empty once a fetch is indexed. On a source that already
    # answers, a held refresh leaves status "ready" and the previous text in
    # place, and this list is what the user reviews.
    review_findings: list[dict] = Field(default_factory=list)
    # Fingerprints of findings the user chose to add anyway. A later fetch is
    # held only for findings not in this list, so approving a page once does
    # not re-hold it on every refresh, and new hidden text still does.
    accepted_finding_fingerprints: list[str] = Field(default_factory=list)
    # Crawl fields
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    parent_source_uuid: Optional[str] = None  # links crawled children to parent
    crawled_urls: Optional[list[str]] = None  # list of discovered URLs (on parent)
    # Pages the crawl fetched and mined for links but judged to be navigation
    # rather than content, so they were never embedded (on parent).
    skipped_urls: Optional[list[str]] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    # Last time the source's chunks were written (kept in step with
    # last_ingested_at for readers that predate the split below).
    processed_at: Optional[datetime.datetime] = None
    # --- Currency: refresh / ingestion provenance, per source ---
    # Written by app.utils.kb_source_currency at every ingest and refresh site;
    # None on rows from before they existed (readers fall back to processed_at).
    last_refresh_attempted_at: Optional[datetime.datetime] = None  # a refresh started, whatever came of it
    last_retrieved_at: Optional[datetime.datetime] = None  # text last successfully obtained (fetch passed the gates / document read)
    last_ingested_at: Optional[datetime.datetime] = None  # chunks last written to the index
    # When the text this source currently holds and serves was retrieved. A
    # failed refresh leaves it alone — that is the "retained content" date.
    content_retrieved_at: Optional[datetime.datetime] = None
    content_hash: Optional[str] = None  # sha256 of the text handed to the indexer
    last_refresh_outcome: Optional[str] = None  # refreshed | unchanged | retrieval_failed | ingestion_failed
    last_refresh_error: Optional[str] = None
    # When a refresh was last queued — tells a queued refresh from one whose
    # worker died (see kb_url_refresh.is_in_flight).
    refresh_queued_at: Optional[datetime.datetime] = None
    # sha256 of a fetch refused by the collapse gate. If the next refresh
    # returns the same bytes, the page really is that short now and the gate
    # steps aside -- a transient shell does not come back identical twice.
    last_collapsed_hash: Optional[str] = None

    class Settings:
        name = "knowledge_base_sources"
        # A unique (knowledge_base_uuid, url) index also exists but is NOT
        # listed here: it must not be Beanie-managed, because building it over
        # legacy duplicate rows would crash every process at init. The web app
        # creates it at startup via
        # knowledge_service.ensure_source_url_unique_index(), which dedupes
        # first and then builds.
        indexes = ["uuid", "knowledge_base_uuid"]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex


class KnowledgeBaseSourceVersion(Document):
    """One dated version of a URL source's text.

    ``KnowledgeBaseSource.content`` holds only the text the source serves now;
    a refresh that picks up a revised page overwrites it. Each distinct text
    the source has served is kept here, so what the source said when an
    answer was produced can still be read, compared and exported after the
    page has changed. Written by app.services.kb_source_versions.

    A version is in effect from ``in_effect_from`` until ``superseded_at``
    (None on the current version). ``last_confirmed_at`` is the latest
    refresh that fetched the page and found this exact text again.
    """

    uuid: str = ""
    source_uuid: str
    knowledge_base_uuid: str
    number: int  # 1, 2, … per source, in the order the versions took effect
    url: Optional[str] = None
    url_title: Optional[str] = None
    content: str = ""
    content_hash: str
    char_count: int = 0
    truncated: bool = False
    # When this text was fetched (the capture date) and when its chunks were
    # written, i.e. when answers started coming from it.
    captured_at: Optional[datetime.datetime] = None
    in_effect_from: Optional[datetime.datetime] = None
    superseded_at: Optional[datetime.datetime] = None
    last_confirmed_at: Optional[datetime.datetime] = None
    # How this text arrived: ingest (first fetch), refresh, supplied_text
    # (catalog/repair text, no fetch) or baseline (the text a source already
    # held when history began; its dates are the source's own).
    origin: str = "ingest"
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "knowledge_base_source_versions"
        indexes = ["uuid", "source_uuid", "knowledge_base_uuid"]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


#: How long a URL preview is kept for the user to review before it expires.
URL_PREVIEW_TTL = datetime.timedelta(hours=2)

#: Preview page verdicts. The first two can be added; the rest are shown so the
#: user sees what happened to each URL, but adding them would do nothing useful.
PREVIEW_ADDABLE_VERDICTS = frozenset({"good", "low"})


class KBUrlPreview(Document):
    """A fetch of URLs for review before any of them enter a knowledge base.

    The pages live in ``KBUrlPreviewPage`` (one row each, since a page's text
    can run to millions of characters). Committing ingests the stored text of
    the pages the user kept, so what was reviewed is exactly what is indexed.
    Expired previews are removed by the TTL index.
    """

    uuid: str = Field(default_factory=lambda: uuid4().hex)
    knowledge_base_uuid: str
    user_id: str
    urls: list[str] = Field(default_factory=list)
    crawl_enabled: bool = False
    max_crawl_pages: int = 5
    allowed_domains: str = ""
    # running → ready (or error, or canceled) → committed
    status: str = "running"
    error_message: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=_utcnow)
    # When a worker picked the preview up, and when it last recorded a page.
    # Without them a preview no worker ever ran looked the same as one still
    # fetching, and spun until the TTL removed it (support ticket).
    started_at: Optional[datetime.datetime] = None
    progress_at: Optional[datetime.datetime] = None
    expires_at: datetime.datetime = Field(default_factory=lambda: _utcnow() + URL_PREVIEW_TTL)

    class Settings:
        name = "kb_url_previews"
        indexes = [
            "uuid",
            IndexModel([("expires_at", 1)], expireAfterSeconds=0),
        ]


class KBUrlPreviewPage(Document):
    """One fetched page of a ``KBUrlPreview`` and what it would add."""

    preview_uuid: str
    page_id: str = Field(default_factory=lambda: uuid4().hex)
    order: int = 0
    url: str
    final_url: Optional[str] = None
    title: Optional[str] = None
    # The page this one was crawled from; None for a URL the user entered.
    parent_url: Optional[str] = None
    # good | low (addable) · empty | error | duplicate | navigation (not addable)
    verdict: str
    reason: Optional[str] = None
    text: str = ""
    char_count: int = 0
    chunk_count: int = 0
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    # Hidden or AI-addressed text found when the page was fetched
    # (fetched_page_screen). Committing such a page holds it for review
    # instead of indexing it, as adding the URL directly would.
    review_findings: list[dict] = Field(default_factory=list)
    expires_at: datetime.datetime = Field(default_factory=lambda: _utcnow() + URL_PREVIEW_TTL)

    class Settings:
        name = "kb_url_preview_pages"
        indexes = [
            [("preview_uuid", 1), ("order", 1)],
            IndexModel([("expires_at", 1)], expireAfterSeconds=0),
        ]


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


class KnowledgeBaseUsage(Document):
    """Per-user usage record for a knowledge base.

    Keyed on the canonical KB uuid (references resolve to their source KB
    before chat, so a referenced KB shares its usage record with the
    original). Powers the per-user "Recently Used" sort on the KB lists.
    """

    user_id: str
    kb_uuid: str
    last_used_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc),
    )
    use_count: int = 1

    class Settings:
        name = "knowledge_base_usage"
        indexes = [
            [("user_id", 1), ("kb_uuid", 1)],
        ]


class KnowledgeBase(Document):
    """A curated knowledge base built from documents and URLs."""

    uuid: str = ""
    title: str
    description: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    shared_with_team: bool = False
    team_owned: bool = False
    verified: bool = False
    # An implicit KB is owned by a Project (its auto-ingesting collection). It is
    # never shown in the normal KB lists — it's reached only through its project.
    implicit: bool = False
    organization_ids: list[str] = Field(default_factory=list)  # Org UUIDs for visibility scoping
    tags: list[str] = Field(default_factory=list)  # User-defined free-form tags (e.g. version, status)
    status: str = "empty"  # empty | building | ready | error
    total_sources: int = 0
    sources_ready: int = 0
    sources_failed: int = 0
    total_chunks: int = 0
    collection_name: Optional[str] = None
    resource_config: dict = Field(default_factory=dict)  # provenance markers (e.g. {"seed_id": ...})
    # Optimized RAG settings discovered by KB Autovalidate. When present, the
    # headless RAG path consults this dict to pick k / model / prompt variant
    # / etc. Keys correspond to ``RAGConfig`` fields. None = use defaults.
    rag_config_override: Optional[dict] = None
    rag_config_override_set_at: Optional[datetime.datetime] = None
    rag_config_override_run_uuid: Optional[str] = None  # which optimization run produced it
    # When scripts/rechunk_knowledge_bases.py last re-cut this KB's sources
    # with a new chunker. Settings tuned before it were tuned on other
    # chunks and other similarities, so the Optimized badge reads stale.
    rechunked_at: Optional[datetime.datetime] = None
    # Re-fetch web sources automatically: None (off) | daily | weekly | monthly.
    # See services/kb_url_refresh.py.
    url_refresh_interval: Optional[str] = None
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
