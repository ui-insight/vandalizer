"""Re-ingest all knowledge base sources into ChromaDB.

Fixes knowledge bases that were ingested while _split_text() had a missing
return statement, resulting in 0 chunks in ChromaDB despite sources showing
as "ready" in MongoDB.

Sources with stored content are re-chunked directly (no re-fetch).
Sources without stored content are re-fetched from their URLs.

Usage:
    cd backend
    python -m scripts.reingest_knowledge_bases [--chroma-host HOST]

    # Inside Docker (default — uses PersistentClient):
    python -m scripts.reingest_knowledge_bases

    # Outside Docker (connects to ChromaDB HTTP server):
    python -m scripts.reingest_knowledge_bases --chroma-host localhost:8000
"""

import argparse
import asyncio
import logging
from datetime import datetime

import chromadb

from app.config import Settings
from app.database import init_db
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.services.document_manager import _split_text

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def get_chroma_client(host: str | None) -> chromadb.ClientAPI:
    """Create a ChromaDB client.

    Resolution order:
      1. Explicit --chroma-host flag
      2. CHROMADB_HOST env var
      3. Try 'chromadb:8000' (Docker Compose service name)
      4. Fall back to PersistentClient (local dev)
    """
    import os
    import socket

    if not host:
        host = os.environ.get("CHROMADB_HOST")

    if not host:
        # Inside Docker Compose the service name 'chromadb' resolves
        try:
            socket.getaddrinfo("chromadb", 8000)
            host = "chromadb:8000"
        except socket.gaierror:
            pass

    if host:
        parts = host.split(":")
        hostname = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 8000
        logger.info("Connecting to ChromaDB at %s:%d", hostname, port)
        return chromadb.HttpClient(host=hostname, port=port)
    else:
        from app.services.document_manager import get_chroma_client as _get_chroma
        settings = Settings()
        logger.info("Using PersistentClient at %s", settings.chromadb_persist_dir)
        return _get_chroma(settings.chromadb_persist_dir)


def add_to_kb(client: chromadb.ClientAPI, kb_uuid: str, source_id: str,
              source_name: str, raw_text: str) -> int:
    """Chunk text and add to a KB collection. Returns chunk count."""
    text_splits = _split_text(raw_text, CHUNK_SIZE, CHUNK_OVERLAP)
    if not text_splits:
        return 0

    collection = client.get_or_create_collection(name=f"kb_{kb_uuid}")

    ids = []
    documents = []
    metadatas = []
    for i, chunk in enumerate(text_splits):
        ids.append(f"{source_id}_chunk_{i}")
        documents.append(chunk)
        metadatas.append({
            "source_id": source_id,
            "source_name": source_name,
            "chunk_index": i,
            "total_chunks": len(text_splits),
            "timestamp": datetime.now().isoformat(),
        })

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(text_splits)


async def recalculate_stats(kb: KnowledgeBase) -> None:
    """Recalculate source stats from actual source documents."""
    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
    ).to_list()
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
    await kb.save()


async def main(chroma_host: str | None) -> None:
    settings = Settings()
    await init_db(settings)
    client = get_chroma_client(chroma_host)

    kbs = await KnowledgeBase.find_all().to_list()
    logger.info("Found %d knowledge bases", len(kbs))

    total_rechunked = 0
    total_refetched = 0
    total_failed = 0

    for kb in kbs:
        sources = await KnowledgeBaseSource.find(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
        ).to_list()

        if not sources:
            continue

        kb_chunks_before = kb.total_chunks
        logger.info("KB %r (%s): %d sources, %d chunks recorded",
                     kb.title, kb.uuid[:8], len(sources), kb.total_chunks)

        for src in sources:
            # Case 1: source has stored content — re-chunk without re-fetching
            if src.content and src.content.strip():
                chunk_count = add_to_kb(
                    client, kb.uuid, src.uuid,
                    src.url_title or src.url or src.uuid,
                    src.content,
                )
                src.chunk_count = chunk_count
                src.status = "ready"
                src.error_message = None
                await src.save()
                if chunk_count > 0:
                    total_rechunked += 1
                    logger.info("  Re-chunked %s: %d chunks",
                                src.url_title or src.url or src.uuid, chunk_count)
                else:
                    total_failed += 1
                    logger.warning("  Re-chunk produced 0 chunks for %s",
                                   src.url_title or src.url or src.uuid)

            # Case 2: URL source without stored content — needs re-fetch
            elif src.source_type == "url" and src.url:
                logger.warning("  Source %s has no stored content — re-fetch needed. "
                               "Use the UI to re-add this URL.", src.url)
                total_failed += 1

            else:
                logger.warning("  Skipped source %s: no content and not a URL", src.uuid)
                total_failed += 1

        await recalculate_stats(kb)
        kb = await KnowledgeBase.get(kb.id)
        logger.info("  KB %r: %d → %d chunks", kb.title, kb_chunks_before, kb.total_chunks)

    logger.info("Done. Re-chunked: %d, Failed/skipped: %d",
                total_rechunked, total_failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-ingest KB sources into ChromaDB")
    parser.add_argument("--chroma-host", default=None,
                        help="ChromaDB HTTP host:port (e.g. localhost:8000). "
                             "Omit to use PersistentClient.")
    args = parser.parse_args()
    asyncio.run(main(args.chroma_host))
