"""Knowledge Base service — CRUD, source management, and ChromaDB operations."""

import asyncio
import datetime
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.models.document import SmartDocument
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.user import User
from app.services import access_control
from app.services.document_manager import DocumentManager

logger = logging.getLogger(__name__)

_dm: DocumentManager | None = None


def _get_dm() -> DocumentManager:
    global _dm
    if _dm is None:
        _dm = DocumentManager()
    return _dm


async def list_knowledge_bases(
    user_id: str,
    team_id: str | None = None,
    user_org_ancestry: list[str] | None = None,
) -> list[KnowledgeBase]:
    if team_id:
        kbs = await KnowledgeBase.find(
            {"$or": [
                {"user_id": user_id},
                {"shared_with_team": True, "team_id": team_id},
                {"verified": True},
            ]},
        ).sort(-KnowledgeBase.created_at).to_list()
    else:
        kbs = await KnowledgeBase.find(
            {"$or": [
                {"user_id": user_id},
                {"verified": True},
            ]},
        ).sort(-KnowledgeBase.created_at).to_list()

    # Org visibility: exclude KBs scoped to orgs the user doesn't belong to
    # Never filter out user's own KBs
    if user_org_ancestry is not None:
        kbs = [
            kb for kb in kbs
            if kb.user_id == user_id
            or not kb.organization_ids
            or bool(set(kb.organization_ids) & set(user_org_ancestry))
        ]

    return kbs


async def create_knowledge_base(
    title: str, user_id: str, team_id: str | None = None,
    description: str | None = None,
) -> KnowledgeBase:
    kb = KnowledgeBase(
        title=title[:300],
        description=(description or "")[:5000] or None,
        user_id=user_id,
        team_id=team_id,
    )
    await kb.insert()
    return kb


async def get_knowledge_base(
    uuid: str,
    user: User,
    *,
    manage: bool = False,
    user_org_ancestry: list[str] | None = None,
    allow_admin: bool = False,
) -> KnowledgeBase | None:
    return await access_control.get_authorized_knowledge_base(
        uuid,
        user,
        manage=manage,
        user_org_ancestry=user_org_ancestry,
        allow_admin=allow_admin,
    )


async def get_kb_sources(kb_uuid: str) -> list[KnowledgeBaseSource]:
    return await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).sort(-KnowledgeBaseSource.created_at).to_list()


async def update_knowledge_base(
    uuid: str, user: User,
    title: str | None = None, description: str | None = None,
    shared_with_team: bool | None = None,
    organization_ids: list[str] | None = None,
    user_org_ancestry: list[str] | None = None,
) -> KnowledgeBase | None:
    kb = await get_knowledge_base(
        uuid,
        user,
        manage=True,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        return None
    if title is not None:
        t = title.strip()
        if t:
            kb.title = t[:300]
    if description is not None:
        kb.description = description[:5000] or None
    if shared_with_team is not None:
        kb.shared_with_team = shared_with_team
    if organization_ids is not None:
        kb.organization_ids = organization_ids
    kb.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await kb.save()
    return kb

async def share_with_team(
    uuid: str,
    user: User,
    *,
    user_org_ancestry: list[str] | None = None,
) -> KnowledgeBase | None:
    """Toggle shared_with_team for an authorized knowledge base."""
    kb = await get_knowledge_base(
        uuid,
        user,
        manage=True,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        return None
    kb.shared_with_team = not kb.shared_with_team
    kb.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await kb.save()
    return kb


async def delete_knowledge_base(
    uuid: str,
    user: User,
    *,
    user_org_ancestry: list[str] | None = None,
) -> bool:
    kb = await get_knowledge_base(
        uuid,
        user,
        manage=True,
        user_org_ancestry=user_org_ancestry,
        allow_admin=True,
    )
    if not kb:
        return False
    # Delete ChromaDB collection
    try:
        dm = _get_dm()
        await asyncio.to_thread(dm.delete_kb_collection, kb.uuid)
    except Exception as e:
        logger.error(f"Error deleting KB collection: {e}")
    # Delete sources
    await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
    ).delete()
    await kb.delete()
    return True


async def recalculate_stats(kb: KnowledgeBase) -> None:
    """Recalculate source stats from actual source documents."""
    sources = await get_kb_sources(kb.uuid)
    kb.total_sources = len(sources)
    kb.sources_ready = sum(1 for s in sources if s.status == "ready")
    kb.sources_failed = sum(1 for s in sources if s.status == "error")
    kb.total_chunks = sum(s.chunk_count for s in sources if s.status == "ready")
    if kb.total_sources == 0:
        kb.status = "empty"
    elif kb.sources_ready + kb.sources_failed >= kb.total_sources:
        kb.status = "error" if kb.sources_failed > 0 and kb.sources_ready == 0 else "ready"
    else:
        kb.status = "building"
    kb.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await kb.save()


async def add_documents(
    kb: KnowledgeBase,
    document_uuids: list[str],
    user: User,
) -> int:
    """Add SmartDocuments to a KB and ingest them. Returns count added."""
    added = 0
    team_access = await access_control.get_team_access_context(user)
    for doc_uuid in document_uuids:
        doc = await access_control.get_authorized_document(
            doc_uuid,
            user,
            team_access=team_access,
            allow_admin=True,
        )
        if not doc:
            raise ValueError(f"Document not found: {doc_uuid}")
        # Skip duplicates
        existing = await KnowledgeBaseSource.find_one(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
            KnowledgeBaseSource.document_uuid == doc_uuid,
        )
        if existing:
            continue

        source = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type="document",
            document_uuid=doc.uuid,
        )
        await source.insert()
        added += 1

        # Ingest inline (in background thread for ChromaDB)
        await _ingest_document_source(source, kb)

    if added:
        await recalculate_stats(kb)
    return added


def _normalize_url(url: str) -> str:
    """Ensure URL has a protocol prefix."""
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def add_urls(
    kb: KnowledgeBase, urls: list[str],
    crawl_enabled: bool = False,
    max_crawl_pages: int = 5,
    allowed_domains: str = "",
) -> int:
    """Add URLs to a KB and ingest them. Returns count added."""
    added = 0
    for url in urls:
        url = _normalize_url(url or "")
        if not url:
            continue
        # Skip duplicates
        existing = await KnowledgeBaseSource.find_one(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
            KnowledgeBaseSource.url == url,
        )
        if existing:
            continue

        source = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type="url",
            url=url[:2000],
            crawl_enabled=crawl_enabled,
            max_crawl_pages=max_crawl_pages,
        )
        await source.insert()
        added += 1

        # Ingest inline
        parent_html = await _ingest_url_source(source, kb)

        # Crawl child pages if enabled
        if crawl_enabled and parent_html:
            crawled = await _crawl_from_source(source, kb, max_crawl_pages, allowed_domains, parent_html)
            added += crawled

    if added:
        await recalculate_stats(kb)
    return added


async def remove_source(kb: KnowledgeBase, source_uuid: str) -> bool:
    source = await KnowledgeBaseSource.find_one(
        KnowledgeBaseSource.uuid == source_uuid,
        KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
    )
    if not source:
        return False
    try:
        dm = _get_dm()
        await asyncio.to_thread(dm.delete_kb_source, kb.uuid, source.uuid)
    except Exception as e:
        logger.error(f"Error deleting KB source from ChromaDB: {e}")
    await source.delete()
    await recalculate_stats(kb)
    return True


# --- Crawling ---


def _normalize_crawl_url(url: str) -> str:
    """Normalize a URL for deduplication: strip fragments, trailing slashes."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    clean = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        clean += f"?{parsed.query}"
    return clean


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract absolute HTTP(S) links from HTML."""
    from urllib.parse import urljoin, urlparse

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        normalized = _normalize_crawl_url(absolute)
        if normalized not in seen:
            seen.add(normalized)
            links.append(normalized)
    return links


async def _crawl_from_source(
    parent: KnowledgeBaseSource,
    kb: KnowledgeBase,
    max_pages: int,
    allowed_domains: str,
    parent_html: str,
) -> int:
    """BFS crawl from parent URL, creating child sources. Returns count added."""
    from urllib.parse import urlparse

    max_pages = max(1, min(max_pages, 50))

    # Build allowed domain set
    parent_domain = urlparse(parent.url).netloc.lower()
    domain_set: set[str] = {parent_domain}
    if allowed_domains:
        for d in allowed_domains.split(","):
            d = d.strip().lower()
            if d:
                domain_set.add(d)

    parent_normalized = _normalize_crawl_url(parent.url)
    visited: set[str] = {parent_normalized}
    queue: list[str] = []
    added = 0

    # Extract seed links from already-fetched parent HTML
    seed_links = _extract_links(parent_html, parent.url)
    logger.info(f"Crawl: found {len(seed_links)} links on parent page {parent.url}")
    for link in seed_links:
        if link not in visited:
            parsed = urlparse(link)
            if parsed.netloc.lower() in domain_set:
                queue.append(link)
                visited.add(link)

    logger.info(f"Crawl: {len(queue)} same-domain links queued (max_pages={max_pages}, domains={domain_set})")

    crawled_urls: list[str] = []

    while queue and added < max_pages:
        url = queue.pop(0)

        # Skip if already in this KB
        existing = await KnowledgeBaseSource.find_one(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
            KnowledgeBaseSource.url == url,
        )
        if existing:
            logger.debug(f"Crawl: skipping duplicate URL {url}")
            continue

        child = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type="url",
            url=url[:2000],
            parent_source_uuid=parent.uuid,
        )
        await child.insert()
        # _ingest_url_source returns the HTML on success
        child_html = await _ingest_url_source(child, kb)
        added += 1
        crawled_urls.append(url)
        logger.info(f"Crawl: added child {added}/{max_pages} — {url} (status={child.status})")

        # Extract more links from this page for BFS
        if child_html and added < max_pages:
            for link in _extract_links(child_html, url):
                if link not in visited:
                    parsed = urlparse(link)
                    if parsed.netloc.lower() in domain_set:
                        queue.append(link)
                        visited.add(link)

    # Update parent with crawled URL list
    parent.crawled_urls = crawled_urls
    await parent.save()

    logger.info(f"Crawl complete for {parent.url}: {added} child pages added")
    return added


# --- Ingestion helpers ---


async def _ingest_document_source(source: KnowledgeBaseSource, kb: KnowledgeBase) -> None:
    source.status = "processing"
    await source.save()
    try:
        doc = await SmartDocument.find_one(SmartDocument.uuid == source.document_uuid)
        if not doc or not (doc.raw_text or "").strip():
            source.status = "error"
            source.error_message = "Document not found or has no text"
            await source.save()
            return

        dm = _get_dm()
        chunk_count = await asyncio.to_thread(
            dm.add_to_kb, kb.uuid, source.uuid, doc.title, doc.raw_text,
        )
        source.chunk_count = chunk_count
        source.status = "ready"
        source.processed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await source.save()
    except Exception as e:
        logger.error(f"Error ingesting document source {source.uuid}: {e}")
        source.status = "error"
        source.error_message = str(e)[:2000]
        await source.save()


def _extract_text_from_html(html: str) -> str:
    """Extract clean text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_title_from_html(html: str, url: str) -> str:
    """Extract page title from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:200]
    from urllib.parse import urlparse
    return urlparse(url).netloc


async def _ingest_url_source(
    source: KnowledgeBaseSource, kb: KnowledgeBase,
) -> str | None:
    """Ingest a URL source. Returns the raw HTML on success (for crawling), None on failure."""
    source.status = "processing"
    await source.save()
    try:
        from app.utils.url_validation import validate_outbound_url

        validate_outbound_url(source.url)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(source.url)
            resp.raise_for_status()
            raw_html = resp.text[:500000]

        raw_text = _extract_text_from_html(raw_html)
        if not raw_text.strip():
            source.status = "error"
            source.error_message = "Failed to extract text from URL"
            await source.save()
            return None

        source.content = raw_text[:500000]
        source.url_title = _extract_title_from_html(raw_html, source.url)

        dm = _get_dm()
        chunk_count = await asyncio.to_thread(
            dm.add_to_kb, kb.uuid, source.uuid,
            source.url_title or source.url, raw_text,
        )
        source.chunk_count = chunk_count
        source.status = "ready"
        source.processed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await source.save()
        return raw_html
    except Exception as e:
        logger.error(f"Error ingesting URL source {source.uuid}: {e}")
        source.status = "error"
        source.error_message = str(e)[:2000]
        await source.save()
        return None
