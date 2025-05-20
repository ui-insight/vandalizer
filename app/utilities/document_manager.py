import sys

import pypandoc

from flask import current_app

from app.models import SmartDocument

try:
    import pysqlite3

    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.utilities.excel_helper import save_excel_to_html

import chromadb
from chromadb.config import Settings
from devtools import debug
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

from app import app
from app.celery_worker import celery_app

from app.utilities.document_readers import (
    extract_text_from_doc,
    extract_text_from_html,
)
import os

MIN_PDF_TEXT_LENGTH = 100
doctr_url = "https://ocr.insight.uidaho.edu/doctr"


@celery_app.task
def perform_extraction_and_update(document_uuid, doc_path, extension, upload_dir):
    document = SmartDocument.objects(uuid=document_uuid).first()
    debug("Performing OCR on document", document.title, extension)
    document.processing = True
    raw_text = ""
    try:
        if extension == "docx":
            pdf_path = Path(upload_dir) / f"{document_uuid}.pdf"
            docx_path = Path(upload_dir) / f"{document_uuid}.docx"
            pypandoc.convert_file(docx_path, "pdf", outputfile=pdf_path)
            extension = "pdf"
            raw_text = extract_text_from_doc(pdf_path)

        elif extension in ["xlsx", "xls"]:
            # Convert to HTML
            html_path = Path(upload_dir) / f"{document_uuid}.html"
            excel_path = Path(upload_dir) / f"{document_uuid}.{extension}"
            save_excel_to_html(excel_path, html_path)
            extension = "html"
            raw_text = extract_text_from_html(html_path)

        elif extension == "pdf":
            # Extract text from PDF in a background thread
            pdf_path = os.path.join(upload_dir, f"{document_uuid}.pdf")

            raw_text = extract_text_from_doc(doc_path)
        else:
            # For other file types, use the generic text extraction
            raw_text = extract_text_from_doc(doc_path)

        document.raw_text = raw_text
        debug(
            "Extraction completed, saving document",
            document.title,
            document.raw_text[:100],
        )
        document.save()
    except Exception:
        document.raw_text = ""
        document.save()
    return raw_text


@celery_app.task
def update_document_fields(document_uuid: str):
    document = SmartDocument.objects(uuid=document_uuid).first()
    document.processing = False
    document.task_id = None
    document.save()


@celery_app.task
def cleanup_document(document_uuid: str):
    """
    Delete the document record and its file when validation or ingestion fails.
    """
    document = SmartDocument.objects(uuid=document_uuid).first()

    if not document:
        debug("Document not found for cleanup:", document_uuid)
        return

    document.processing = False
    document.task_id = None
    document.save()
    # if document:
    #     try:
    #         os.remove(document_file_path)
    #     except Exception as e:
    #         debug(f"Error removing file {document_file_path}: {e}")

    #     document.delete()


@celery_app.task
def perform_semantic_ingestion(raw_text, document_uuid, user_id):
    document = SmartDocument.objects(uuid=document_uuid).first()
    if not document.valid:
        debug("Document not validated, reason: ", document.validation_feedback)
        return

    with DocumentManager() as document_manager:
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
    return document.uuid


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

    def close(self):
        """Explicitly close the ChromaDB client to prevent resource leaks."""
        if hasattr(self, "client") and self.client:
            try:
                self.client.close()
            except Exception as e:
                print(f"Error closing ChromaDB client: {e}")

    def __del__(self):
        """Destructor to ensure client is closed if object is garbage collected."""
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # always close—even if an exception is raised
        self.close()

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
        # Check if the document exists before deleting
        if not self.document_exists(user_id, document_id):
            debug(f"Document {document_id} does not exist for user {user_id}.")
            return
        # Get the raw collection to use ChromaDB's filtering
        try:
            collection = self.client.get_or_create_collection(
                name=f"user_{user_id}_docs"
            )
            # Delete all chunks with matching document_id
            collection.delete(where={"document_id": document_id})
        except Exception as e:
            debug(f"Error deleting document {document_id} for user {user_id}: {e}")
            raise
            # close the client

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
