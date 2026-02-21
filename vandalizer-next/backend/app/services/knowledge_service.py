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
from app.services.document_manager import DocumentManager

logger = logging.getLogger(__name__)

_dm: DocumentManager | None = None


def _get_dm() -> DocumentManager:
    global _dm
    if _dm is None:
        _dm = DocumentManager()
    return _dm


async def list_knowledge_bases(user_id: str) -> list[KnowledgeBase]:
    return await KnowledgeBase.find(
        KnowledgeBase.user_id == user_id,
    ).sort(-KnowledgeBase.created_at).to_list()


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


async def get_knowledge_base(uuid: str, user_id: str) -> KnowledgeBase | None:
    return await KnowledgeBase.find_one(
        KnowledgeBase.uuid == uuid,
        KnowledgeBase.user_id == user_id,
    )


async def get_kb_sources(kb_uuid: str) -> list[KnowledgeBaseSource]:
    return await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).sort(-KnowledgeBaseSource.created_at).to_list()


async def update_knowledge_base(
    uuid: str, user_id: str,
    title: str | None = None, description: str | None = None,
) -> KnowledgeBase | None:
    kb = await get_knowledge_base(uuid, user_id)
    if not kb:
        return None
    if title is not None:
        t = title.strip()
        if t:
            kb.title = t[:300]
    if description is not None:
        kb.description = description[:5000] or None
    kb.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await kb.save()
    return kb


async def delete_knowledge_base(uuid: str, user_id: str) -> bool:
    kb = await get_knowledge_base(uuid, user_id)
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
    kb: KnowledgeBase, document_uuids: list[str],
) -> int:
    """Add SmartDocuments to a KB and ingest them. Returns count added."""
    added = 0
    for doc_uuid in document_uuids:
        doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
        if not doc:
            continue
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


async def add_urls(kb: KnowledgeBase, urls: list[str]) -> int:
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
        )
        await source.insert()
        added += 1

        # Ingest inline
        await _ingest_url_source(source, kb)

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


async def _ingest_url_source(source: KnowledgeBaseSource, kb: KnowledgeBase) -> None:
    source.status = "processing"
    await source.save()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(source.url)
            resp.raise_for_status()
            raw_html = resp.text[:500000]

        raw_text = _extract_text_from_html(raw_html)
        if not raw_text.strip():
            source.status = "error"
            source.error_message = "Failed to extract text from URL"
            await source.save()
            return

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
    except Exception as e:
        logger.error(f"Error ingesting URL source {source.uuid}: {e}")
        source.status = "error"
        source.error_message = str(e)[:2000]
        await source.save()
