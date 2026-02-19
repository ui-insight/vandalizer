"""Document Manager — ChromaDB-backed document ingestion and semantic search for RAG."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class DocumentManager:
    """Synchronous document manager — safe to call from asyncio.to_thread()."""

    def __init__(self, persist_directory: str = "data/chromadb") -> None:
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
        )

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

        text_splits = self.text_splitter.split_text(text)
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
