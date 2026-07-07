"""Document Manager  - ChromaDB-backed document ingestion and semantic search for RAG."""

import hashlib
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

# Process-wide singletons. ChromaDB's default (ONNX MiniLM) does a stateful,
# file-descriptor-heavy tarball extraction on first use; constructing a fresh
# instance per task can exhaust fds (EMFILE on `onnx.tar.gz`) because Chroma's
# `_download_model_if_not_exists` re-extracts whenever the extracted folder
# isn't complete. Caching one instance per worker process ensures the model is
# initialized exactly once.
_EF_LOCK = threading.Lock()
_DEFAULT_EF: Any = None
_DM_LOCK = threading.Lock()
_SHARED_DM: "DocumentManager | None" = None


def get_default_embedding_function() -> Any:
    """Return a process-wide cached ChromaDB default embedding function.

    Lazily initialized on first call (inside the Celery worker process, after
    fork) so model download/extraction happens once per process.
    """
    global _DEFAULT_EF
    if _DEFAULT_EF is None:
        with _EF_LOCK:
            if _DEFAULT_EF is None:
                from chromadb.utils import embedding_functions
                _DEFAULT_EF = embedding_functions.DefaultEmbeddingFunction()
    return _DEFAULT_EF


def get_document_manager() -> "DocumentManager":
    """Return a process-wide cached DocumentManager.

    Reusing one DocumentManager (and therefore one PersistentClient + one
    embedding function instance) across tasks prevents fd leaks and repeated
    ONNX model initialization.
    """
    global _SHARED_DM
    if _SHARED_DM is None:
        with _DM_LOCK:
            if _SHARED_DM is None:
                _SHARED_DM = DocumentManager()
    return _SHARED_DM


def get_chroma_client(persist_directory: str | None = None) -> chromadb.ClientAPI:
    """Create a ChromaDB client — HttpClient if CHROMADB_HOST is set, else PersistentClient.

    PersistentClient is not process-safe for concurrent writers. Any deployment
    with more than one writer (multi-worker uvicorn + Celery) must set
    CHROMADB_HOST and run the Chroma server container.
    """
    from app.config import Settings

    settings = Settings()
    host = (settings.chromadb_host or "").strip()
    if host:
        hostname, _, port_str = host.partition(":")
        port = int(port_str) if port_str else 8000
        return chromadb.HttpClient(
            host=hostname,
            port=port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    if persist_directory is None:
        persist_directory = settings.chromadb_persist_dir
    Path(persist_directory).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=persist_directory,
        settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
    )


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into overlapping chunks without external dependencies."""
    return [c for c, _ in _split_text_with_offsets(text, chunk_size, chunk_overlap)]


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
# Don't decorate continuation chunks with headers longer than this — a huge
# header would crowd out the chunk's own content in the embedding.
_TABLE_HEADER_MAX_CHARS = 300


def _find_table_spans(text: str) -> list[tuple[int, int, str]]:
    """Locate markdown pipe tables (runs of ≥2 consecutive ``| … |`` lines).

    Returns ``(start_offset, end_offset, header_text)`` per table, where
    ``header_text`` is the first row plus the ``|---|`` separator row when one
    follows (MarkItDown .docx tables have one; the xlsx serializer's sheets
    don't). Used by the splitter to avoid breaking mid-table and to repeat the
    header on continuation chunks so numbers keep their column context.
    """
    spans: list[tuple[int, int, str]] = []
    rows: list[tuple[int, str]] = []
    pos = 0

    def _close() -> None:
        if len(rows) < 2:
            return
        header = rows[0][1]
        if _TABLE_SEPARATOR_RE.match(rows[1][1]):
            header = f"{header}\n{rows[1][1]}"
        spans.append((rows[0][0], rows[-1][0] + len(rows[-1][1]), header))

    for line in text.split("\n"):
        if _TABLE_ROW_RE.match(line):
            rows.append((pos, line))
        else:
            _close()
            rows = []
        pos += len(line) + 1
    _close()
    return spans


def _split_text_with_offsets(
    text: str, chunk_size: int, chunk_overlap: int,
) -> list[tuple[str, int]]:
    """Same as _split_text but also returns each chunk's start offset in the
    normalized source text. The offset lets callers map a chunk back to its
    location (page number, sheet name, etc.) when source markers are known.

    Markdown pipe tables get special treatment: the splitter prefers breaking
    before a table (or at a row boundary inside one) instead of mid-row, and a
    chunk that starts inside a table is prefixed with that table's header rows
    so its numbers keep their column labels. The header prefix is decoration
    only — the returned offset still points at the chunk's original position,
    so page/sheet marker mapping is unaffected.
    """
    normalized = text.strip()
    if not normalized:
        return []

    table_spans = _find_table_spans(normalized) if "|" in normalized else []

    def _span_containing(pos: int) -> tuple[int, int, str] | None:
        for span in table_spans:
            if span[0] < pos < span[1]:
                return span
        return None

    chunks: list[tuple[str, int]] = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    text_length = len(normalized)

    while start < text_length:
        end = min(text_length, start + chunk_size)
        if end < text_length:
            span = _span_containing(end)
            if span is not None and span[0] > start + chunk_size // 2:
                # The window ends mid-table and the table starts late enough in
                # the window: break before the table instead of through it.
                end = span[0]
            elif span is not None:
                # Mid-table with no room to break before it (table longer than
                # the window): break at a row boundary, never mid-row.
                row_break = normalized.rfind("\n", start + chunk_size // 2, end)
                if row_break > start:
                    end = row_break
            else:
                preferred_break = normalized.rfind("\n\n", start + chunk_size // 2, end)
                if preferred_break == -1:
                    preferred_break = normalized.rfind(" ", start + chunk_size // 2, end)
                if preferred_break > start:
                    end = preferred_break

        # Track where the *stripped* chunk actually starts in the source so
        # marker lookup matches a meaningful position.
        chunk_raw = normalized[start:end]
        chunk = chunk_raw.strip()
        if chunk:
            leading = len(chunk_raw) - len(chunk_raw.lstrip())
            offset = start + leading
            span = _span_containing(offset)
            if (
                span is not None
                and offset > span[0]
                and 0 < len(span[2]) <= _TABLE_HEADER_MAX_CHARS
                and not chunk.startswith(span[2])
            ):
                chunk = f"{span[2]}\n{chunk}"
            chunks.append((chunk, offset))

        if end >= text_length:
            break

        next_start = max(start + step, end - chunk_overlap)
        if next_start <= start:
            next_start = end
        # Don't let the overlap restart mid-row: snap to the start of the row
        # (or the next row when snapping back would stall the loop).
        span = _span_containing(next_start)
        if span is not None:
            row_start = normalized.rfind("\n", span[0], next_start) + 1
            if row_start > start:
                next_start = row_start
            else:
                next_newline = normalized.find("\n", next_start)
                if next_newline != -1:
                    next_start = next_newline + 1
        start = next_start

    return chunks


def _location_for_offset(offset: int, markers: list[dict]) -> dict:
    """Return the most recent marker at or before *offset*.

    Used by add_document to tag each chunk with the page (or sheet) it came
    from. Returns an empty dict when no markers apply.
    """
    if not markers:
        return {}
    location: dict = {}
    for m in markers:
        if m.get("char_offset", 0) > offset:
            break
        location = m
    return location


def _user_collection_name(user_id: str) -> str:
    """Build a ChromaDB-legal collection name for a user's document corpus.

    Chroma requires collection names of 3-63 chars, starting/ending alphanumeric,
    containing only ``[a-zA-Z0-9._-]``. ``user_id`` is frequently an email
    address (``@`` and ``.`` are illegal, and ``.`` risks the IPv4/`..` rules), so
    sanitize the readable part and always append a hash of the raw id to guarantee
    uniqueness — two ids that sanitize to the same token must not share a
    collection (that would cross-contaminate users' documents).
    """
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id or "").strip("_-")[:40] or "anon"
    # Non-cryptographic: just a short stable suffix to keep distinct user_ids
    # that sanitize to the same token in separate collections.
    digest = hashlib.sha1(
        (user_id or "").encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:10]
    return f"user_{safe}_{digest}"


class DocumentManager:
    """Synchronous document manager  - safe to call from asyncio.to_thread()."""

    def __init__(
        self,
        persist_directory: str | None = None,
        embedding_function: Any = None,
    ) -> None:
        if persist_directory is None:
            from app.config import Settings
            persist_directory = Settings().chromadb_persist_dir
        self.persist_directory = persist_directory
        self.chunk_size = 1000
        self.chunk_overlap = 200

        self.client = get_chroma_client(persist_directory)
        # Always pass an explicit embedding function to get_or_create_collection
        # so Chroma doesn't construct a fresh ONNXMiniLM_L6_V2 per collection.
        self.embedding_function = embedding_function or get_default_embedding_function()

    def get_user_collection(self, user_id: str) -> chromadb.Collection:
        return self.client.get_or_create_collection(
            name=_user_collection_name(user_id),
            embedding_function=self.embedding_function,
        )

    def add_document(
        self,
        user_id: str,
        doc_path: str,
        document_name: str,
        document_id: str,
        raw_text: Optional[str] = None,
        text_markers: Optional[list[dict]] = None,
    ) -> int:
        """Chunk and embed *raw_text* into the user's collection.

        ``text_markers`` is the optional output of
        ``document_readers.extract_text_with_markers`` — when present, each
        chunk's metadata is tagged with the page or sheet it came from so
        retrieval results can render citations like "PAPPG p. 234".

        Returns the number of chunks written. ``0`` means the document had no
        extractable text — callers should treat that as "not retrieval-ready"
        rather than an error.
        """
        text = raw_text or ""
        if not text:
            return 0

        text_splits = _split_text_with_offsets(text, self.chunk_size, self.chunk_overlap)
        if not text_splits:
            return 0

        collection = self.get_user_collection(user_id)
        markers = sorted(
            (m for m in (text_markers or []) if isinstance(m, dict)),
            key=lambda m: m.get("char_offset", 0),
        )

        ids = []
        documents = []
        metadatas = []
        for i, (chunk, offset) in enumerate(text_splits):
            ids.append(f"{document_id}_chunk_{i}")
            documents.append(chunk)
            meta: dict = {
                "document_id": document_id,
                "document_name": document_name,
                "chunk_index": i,
                "total_chunks": len(text_splits),
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
            }
            location = _location_for_offset(offset, markers)
            kind = location.get("kind")
            value = location.get("value")
            if kind == "page" and isinstance(value, int):
                meta["page"] = value
            elif kind == "sheet" and isinstance(value, str):
                meta["sheet"] = value
            metadatas.append(meta)

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(text_splits)

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
            ids_list = (results.get("ids") or [[]])[0]
            dists_list = (results.get("distances") or [[]])[0]
            for i, doc in enumerate(results["documents"][0]):
                metadata = (
                    results["metadatas"][0][i] if results.get("metadatas") else {}
                )
                output.append({
                    "content": doc,
                    "metadata": metadata,
                    "chunk_id": ids_list[i] if i < len(ids_list) else None,
                    "score": dists_list[i] if i < len(dists_list) else None,
                })

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
        """Get or create a ChromaDB collection for a knowledge base.

        ``get_or_create_collection`` writes to the Chroma store, so this must
        only be used on write paths (ingestion). Read paths (retrieval) must
        use :meth:`get_kb_collection_readonly` — otherwise a read against a
        not-yet-ingested KB silently creates an empty collection, and a read
        against a read-only Chroma store raises "attempt to write a readonly
        database" where the user only wanted to retrieve.
        """
        collection_name = f"kb_{kb_uuid}"
        return self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

    def get_kb_collection_readonly(self, kb_uuid: str) -> Optional["chromadb.Collection"]:
        """Fetch an existing KB collection for reads, never creating it.

        Returns ``None`` when the collection doesn't exist yet (KB never
        ingested). Unlike :meth:`get_kb_collection`, this issues no write, so
        retrieval degrades to "no results" instead of failing on a read-only
        Chroma store.
        """
        collection_name = f"kb_{kb_uuid}"
        try:
            return self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
            )
        except Exception:
            return None

    def add_to_kb(
        self,
        kb_uuid: str,
        source_id: str,
        source_name: str,
        raw_text: str,
        text_markers: Optional[list[dict]] = None,
    ) -> int:
        """Chunk text, embed, and add to a KB collection. Returns chunk count.

        ``text_markers`` lets KB ingestion preserve page/sheet citations the
        same way per-user ingestion does. Sources without markers (web URLs,
        plaintext) just omit the page metadata.
        """
        text_splits = _split_text_with_offsets(raw_text, self.chunk_size, self.chunk_overlap)
        if not text_splits:
            return 0

        collection = self.get_kb_collection(kb_uuid)
        markers = sorted(
            (m for m in (text_markers or []) if isinstance(m, dict)),
            key=lambda m: m.get("char_offset", 0),
        )

        ids = []
        documents = []
        metadatas = []
        for i, (chunk, offset) in enumerate(text_splits):
            ids.append(f"{source_id}_chunk_{i}")
            documents.append(chunk)
            meta: dict = {
                "source_id": source_id,
                "source_name": source_name,
                "chunk_index": i,
                "total_chunks": len(text_splits),
                "timestamp": datetime.now().isoformat(),
            }
            location = _location_for_offset(offset, markers)
            kind = location.get("kind")
            value = location.get("value")
            if kind == "page" and isinstance(value, int):
                meta["page"] = value
            elif kind == "sheet" and isinstance(value, str):
                meta["sheet"] = value
            metadatas.append(meta)

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(text_splits)

    def query_kb(
        self,
        kb_uuid: str,
        query: str,
        k: int = 8,
        min_similarity: float = 0.0,
        where: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """Similarity search on a KB collection.

        ``min_similarity`` (cosine, 0-1) is a relevance floor: chunks scoring
        below it are dropped from the result. The default 0.0 disables the
        filter, preserving legacy behaviour for every caller that doesn't opt
        in. A positive floor lets RAG callers treat "retrieved only weakly
        related junk" the same as "retrieved nothing" — handing the model an
        empty set so it abstains rather than answering from off-topic chunks.

        ``where`` is an optional ChromaDB metadata filter (e.g. restrict the
        search to specific sources by ``source_name``).
        """
        collection = self.get_kb_collection_readonly(kb_uuid)
        if collection is None:
            return []
        results = collection.query(query_texts=[query], n_results=k, where=where)

        output = []
        if results and results.get("documents"):
            ids_list = (results.get("ids") or [[]])[0]
            dists_list = (results.get("distances") or [[]])[0]
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                dist = dists_list[i] if i < len(dists_list) else None
                # Chroma returns squared-L2 distances and the default embedding
                # function yields unit vectors, so d = 2(1 - cos); map back to
                # cosine similarity clamped to [0, 1] for consumers that want a
                # higher-is-better relevance signal.
                similarity = None
                if isinstance(dist, (int, float)):
                    similarity = max(0.0, min(1.0, 1.0 - dist / 2.0))
                # Apply the relevance floor. We only drop chunks we can actually
                # score; a None similarity (missing distance) is kept rather than
                # silently filtered, so a degraded distance signal never causes a
                # spurious abstention.
                if min_similarity > 0.0 and similarity is not None and similarity < min_similarity:
                    continue
                output.append({
                    "content": doc,
                    "metadata": metadata,
                    "chunk_id": ids_list[i] if i < len(ids_list) else None,
                    "score": dist,
                    "similarity": similarity,
                })
        return output

    def delete_kb_collection(self, kb_uuid: str) -> None:
        """Drop an entire KB collection. No-op if the collection never existed."""
        collection_name = f"kb_{kb_uuid}"
        try:
            self.client.get_collection(name=collection_name)
        except Exception:
            return
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

    def rename_kb_source(self, kb_uuid: str, source_id: str, new_name: str) -> None:
        """Rewrite source_name on every chunk for this source.

        Keeps retrieval citations in sync with the user-facing label.
        """
        try:
            collection = self.get_kb_collection(kb_uuid)
            existing = collection.get(where={"source_id": source_id})
        except Exception as e:
            logger.error(f"Error reading KB source {source_id} for rename: {e}")
            return
        ids = existing.get("ids") or []
        metadatas = existing.get("metadatas") or []
        if not ids:
            return
        updated: list[dict] = []
        for meta in metadatas:
            m = dict(meta or {})
            m["source_name"] = new_name
            updated.append(m)
        try:
            collection.update(ids=ids, metadatas=updated)
        except Exception as e:
            logger.error(f"Error updating KB source {source_id} metadata: {e}")
