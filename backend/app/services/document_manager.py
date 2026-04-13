"""Document Manager  - ChromaDB-backed document ingestion and semantic search for RAG."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


def get_chroma_client(persist_directory: str | None = None) -> chromadb.ClientAPI:
    """Create a ChromaDB PersistentClient with consistent settings.

    All code that needs a ChromaDB client should use this function to avoid
    the 'instance already exists with different settings' error.
    """
    if persist_directory is None:
        from app.config import Settings

        persist_directory = Settings().chromadb_persist_dir
    Path(persist_directory).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=persist_directory,
        settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
    )


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into overlapping chunks without external dependencies."""
    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    text_length = len(normalized)

    while start < text_length:
        end = min(text_length, start + chunk_size)
        if end < text_length:
            preferred_break = normalized.rfind("\n\n", start + chunk_size // 2, end)
            if preferred_break == -1:
                preferred_break = normalized.rfind(" ", start + chunk_size // 2, end)
            if preferred_break > start:
                end = preferred_break

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        next_start = max(start + step, end - chunk_overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


class DocumentManager:
    """Synchronous document manager  - safe to call from asyncio.to_thread()."""

    def __init__(self, persist_directory: str | None = None) -> None:
        if persist_directory is None:
            from app.config import Settings
            persist_directory = Settings().chromadb_persist_dir
        self.persist_directory = persist_directory
        self.chunk_size = 1000
        self.chunk_overlap = 200

        self.client = get_chroma_client(persist_directory)

    def get_user_collection(self, user_id: str) -> chromadb.Collection:
        collection_name = f"user_{user_id}_docs"
        return self.client.get_or_create_collection(name=collection_name)

    def add_document(
        self,
        user_id: str,
        doc_path: str,
        document_name: str,
        document_id: str,
        raw_text: Optional[str] = None,
    ) -> None:
        text = raw_text or ""
        if not text:
            return

        text_splits = _split_text(text, self.chunk_size, self.chunk_overlap)
        if not text_splits:
            return

        collection = self.get_user_collection(user_id)

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(text_splits):
            ids.append(f"{document_id}_chunk_{i}")
            documents.append(chunk)
            metadatas.append(
                {
                    "document_id": document_id,
                    "document_name": document_name,
                    "chunk_index": i,
                    "total_chunks": len(text_splits),
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id,
                }
            )

        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def query_documents(
        self,
        user_id: str,
        query: str,
        filter_docs: Optional[list[str]] = None,
        k: int = 4,
    ) -> list[dict[str, Any]]:
        collection = self.get_user_collection(user_id)

        where_filter = None
        if filter_docs:
            clean_ids = [doc.split(".")[0] for doc in filter_docs]
            where_filter = {"document_id": {"$in": clean_ids}}

        results = collection.query(
            query_texts=[query],
            n_results=k,
            where=where_filter,
        )

        output = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                metadata = (
                    results["metadatas"][0][i] if results.get("metadatas") else {}
                )
                output.append({"content": doc, "metadata": metadata})

        return output

    def document_exists(self, user_id: str, document_id: str) -> bool:
        collection = self.get_user_collection(user_id)
        results = collection.get(where={"document_id": document_id})
        return bool(results and results.get("ids"))

    def delete_document(self, user_id: str, document_id: str) -> None:
        if not self.document_exists(user_id, document_id):
            return
        collection = self.get_user_collection(user_id)
        collection.delete(where={"document_id": document_id})

    # --- Knowledge Base methods ---

    def get_kb_collection(self, kb_uuid: str) -> chromadb.Collection:
        """Get or create a ChromaDB collection for a knowledge base."""
        collection_name = f"kb_{kb_uuid}"
        return self.client.get_or_create_collection(name=collection_name)

    def add_to_kb(
        self,
        kb_uuid: str,
        source_id: str,
        source_name: str,
        raw_text: str,
    ) -> int:
        """Chunk text, embed, and add to a KB collection. Returns chunk count."""
        text_splits = _split_text(raw_text, self.chunk_size, self.chunk_overlap)
        if not text_splits:
            return 0

        collection = self.get_kb_collection(kb_uuid)

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

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(text_splits)

    def query_kb(
        self,
        kb_uuid: str,
        query: str,
        k: int = 8,
    ) -> list[dict[str, Any]]:
        """Similarity search on a KB collection."""
        collection = self.get_kb_collection(kb_uuid)
        results = collection.query(query_texts=[query], n_results=k)

        output = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                output.append({"content": doc, "metadata": metadata})
        return output

    def delete_kb_collection(self, kb_uuid: str) -> None:
        """Drop an entire KB collection."""
        collection_name = f"kb_{kb_uuid}"
        try:
            self.client.delete_collection(name=collection_name)
        except Exception as e:
            logger.error(f"Error deleting KB collection {collection_name}: {e}")

    def delete_kb_source(self, kb_uuid: str, source_id: str) -> None:
        """Remove all chunks for a single source from a KB collection."""
        try:
            collection = self.get_kb_collection(kb_uuid)
            collection.delete(where={"source_id": source_id})
        except Exception as e:
            logger.error(f"Error deleting KB source {source_id}: {e}")
