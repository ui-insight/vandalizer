import sys

from app.models import SmartDocument

try:
    import pysqlite3

    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings
from devtools import debug
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

from app import app
from app.celery import celery_app
from app.utilities.document_readers import (
    extract_text_from_doc,
)

MIN_PDF_TEXT_LENGTH = 100
doctr_url = "https://ocr.insight.uidaho.edu/doctr"


@celery_app.task
def perform_extraction_and_update(document_uuid, doc_path):
    document = SmartDocument.objects(uuid=document_uuid).first()
    debug("Performing OCR on document", document.title)
    document.processing = True
    try:
        extracted_text = extract_text_from_doc(doc_path)
        document.raw_text = extracted_text
        debug(
            "Extraction completed, saving document",
            document.title,
            document.raw_text[:100],
        )
        document.processing = False
        document.save()
    except Exception:
        document.processing = False
        document.raw_text = ""
        document.save()


@celery_app.task
def perform_semantic_ingestion(document_uuid, user_id, raw_text=None):
    document = SmartDocument.objects(uuid=document_uuid).first()
    document.processing = True
    document.save()

    document_manager = DocumentManager()

    document_path = document.absolute_path

    document_manager.add_document(
        user_id=user_id,
        document_name=document.title,
        document_id=document.uuid,
        doc_path=document_path,
        raw_text=raw_text,
    )
    document.processing = False
    document.save()


def perform_ocr_and_semantic_ingestion(document_uuid, user_id):
    document = SmartDocument.objects(uuid=document_uuid).first()
    document_path = document.absolute_path
    perform_extraction_and_update.delay(document.uuid, str(document_path))
    document = document.reload()
    perform_semantic_ingestion.delay(document.uuid, user_id, document.raw_text)
    document.processing = False
    document.save()


class DocumentManager:
    def __init__(
        self, persist_directory: Path = Path(app.root_path) / "static" / "db"
    ) -> None:
        """Initialize the document manager with a persistence directory."""
        self.upload_folder = Path(app.root_path) / "static" / "uploads"
        self.persist_directory = persist_directory.as_posix()
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_directory.as_posix(),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )

    def get_user_collection(self, user_id: str) -> Chroma:
        """Get or create a collection for a specific user."""
        collection_name = f"user_{user_id}_docs"
        # Check if collection exists in the client
        try:
            self.client.get_or_create_collection(name=collection_name)
        except ValueError:
            # Collection doesn't exist, create an empty collection
            self.client.create_collection(name=collection_name)

        return Chroma(
            client=self.client,  # Use the existing client
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

    def add_document(
        self,
        user_id: str,
        doc_path: str,
        document_name: str,
        document_id: str,
        raw_text=None,
    ) -> str:
        """Add a document to a user's collection.
        Returns the document ID for future reference.
        """
        # Load and split the document
        debug(doc_path)
        splits = []
        text = raw_text
        if not text or (text and len(text) == 0):
            text = extract_text_from_doc(doc_path)
        debug(len(text))
        text_splits = self.text_splitter.split_text(text)
        splits = self.text_splitter.create_documents(text_splits)
        debug(len(splits))

        # Add metadata to each split
        for i, split in enumerate(splits):
            if split.metadata is None:
                split.metadata = {}
            split.metadata.update(
                {
                    "document_id": document_id,
                    "document_name": document_name,
                    "chunk_index": i,
                    "total_chunks": len(splits),
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id,
                },
            )

        # Get the user's collection and add the document
        vectorstore = self.get_user_collection(user_id)

        # Add new documents to existing collection
        vectorstore.add_documents(splits)

    def query_documents(
        self,
        user_id: str,
        query: str,
        filter_docs: Optional[list[str]] = None,
        k: int = 4,
    ) -> list[dict[str, Any]]:
        """Query a user's documents, optionally filtering by document IDs.
        Returns relevant document chunks with their metadata.
        """
        vectorstore = self.get_user_collection(user_id)

        results = []

        # Prepare filter if specific documents are requested
        # filter_dict = None
        if filter_docs:
            # remove extension from filter_docs
            filter_docs = [doc.split(".")[0] for doc in filter_docs]
            filter_dict = {"document_id": {"$in": filter_docs}}
            # filter_dict = {
            #     "$and": [{"document_id": {"$eq": doc_id}} for doc_id in filter_docs]
            # }
            results = vectorstore.similarity_search(
                query,
                k=k,
                filter=filter_dict,
            )
        else:
            results = vectorstore.similarity_search(query, k=k)

        return [
            {"content": doc.page_content, "metadata": doc.metadata} for doc in results
        ]

    def document_exists(self, user_id: str, document_id: str) -> bool:
        """Check if a specific document exists in a user's collection."""
        self.get_user_collection(user_id)
        # Get the raw collection to use ChromaDB's filtering
        collection = self.client.get_or_create_collection(name=f"user_{user_id}_docs")
        if collection:
            # Check if any chunks with matching document_id exist
            results = collection.get(where={"document_id": document_id})
            return bool(results)
        return False

    def delete_document(self, user_id: str, document_id: str) -> None:
        """Delete a specific document from a user's collection."""
        self.get_user_collection(user_id)
        # Get the raw collection to use ChromaDB's filtering
        collection = self.client.get_or_create_collection(name=f"user_{user_id}_docs")
        if collection:
            # Delete all chunks with matching document_id
            collection.delete(where={"document_id": document_id})

    def list_user_documents(self, user_id: str) -> list[dict[str, Any]]:
        """List all documents in a user's collection with metadata."""
        collection = self.client.get_collection(name=f"user_{user_id}_docs")
        # Get all unique document IDs and their metadata
        results = collection.get()

        # Group by document_id to get unique documents
        documents = {}
        for _i, metadata in enumerate(results["metadatas"]):
            if not metadata:
                continue
            doc_id = metadata.get("document_id")
            if doc_id not in documents:
                documents[doc_id] = {
                    "document_id": doc_id,
                    "document_name": metadata["document_name"],
                    "timestamp": metadata["timestamp"],
                    "chunk_count": metadata["total_chunks"],
                }

        return list(documents.values())
