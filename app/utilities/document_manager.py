import re
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
import pypandoc
from chromadb.config import Settings
from devtools import debug
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

from app import app
from app.celery_worker import celery_app
from app.utilities.document_helpers import save_excel_to_html
from app.utilities.document_readers import (
    convert_to_markdown,
    extract_text_from_doc,
)

MIN_PDF_TEXT_LENGTH = 100
doctr_url = "https://ocr.insight.uidaho.edu/doctr"


def remove_images_from_markdown(markdown_text):
    """Remove all image references and their size attributes from markdown text"""
    # Remove inline images: ![alt text](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", markdown_text)

    # Remove reference-style images: ![alt text][id]
    text = re.sub(r"!\[([^\]]*)\]\[[^\]]*\]", "", text)

    # Remove pandoc image attributes like {width="0.46in" height="0.17in"}
    # This pattern matches curly braces containing width/height specifications
    text = re.sub(r'\{[^}]*(?:width|height)\s*=\s*"[^"]*"[^}]*\}', "", text)

    # Alternative more aggressive pattern - removes any standalone curly brace blocks with attributes
    # Use this if the above doesn't catch all cases
    # text = re.sub(r'\{(?:[^{}])*(?:width|height|style|class|id)\s*=\s*"[^"]*"(?:[^{}])*\}', '', text)

    # Remove any remaining standalone attribute blocks (more general)
    # This catches any {key="value"} patterns that might be left
    text = re.sub(r'\{[^{}]*="[^"]*"[^{}]*\}', "", text)

    # Remove reference definitions that are likely for images
    text = re.sub(r"^\s*\[[^\]]+\]:\s*[^\s]+.*$", "", text, flags=re.MULTILINE)

    # Clean up extra blank lines that might be left
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)

    # Clean up any extra spaces left on lines
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)

    return text.strip()


@celery_app.task(
    name="tasks.document.extraction",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def perform_extraction_and_update(document_uuid, extension):
    document = SmartDocument.objects(uuid=document_uuid).first()
    if not document:
        debug(f"Document with UUID {document_uuid} not found.")
        return ""

    absolute_path = document.absolute_path
    path_extension = absolute_path.suffix.lower()
    if path_extension == ".pdf" and (
        not document.raw_text or document.raw_text.strip() == ""
    ):
        # If raw_text is empty, we will perform OCR
        raw_text = extract_text_from_doc(absolute_path, doc=document)
        document.raw_text = raw_text
        document.processing = False
        document.downloadpath = str(Path(document.path))
        document.save()
        return raw_text

    debug("Performing OCR on document", document.title, absolute_path)
    document.processing = True
    document.task_status = "ocr"
    raw_text = ""
    extra_args = ["-V", "geometry:margin=2cm"]
    pdf_path = absolute_path.with_suffix(".pdf")
    document.path = str(Path(document.path).with_suffix(".pdf"))
    document.save()
    try:
        if extension in ["xlsx", "xls"]:
            # Convert to HTML
            debug("Extracting excel")
            html_path = absolute_path.with_suffix(".html")
            excel_path = absolute_path.with_suffix(".xlsx")
            save_excel_to_html(excel_path, html_path)
            raw_text = convert_to_markdown(excel_path)
            document.extension = "html"
            document.path = str(Path(document.path).with_suffix(".html"))
            document.raw_text = raw_text
        elif extension in ["docx", "doc"]:
            pypandoc.convert_file(
                absolute_path, "pdf", outputfile=pdf_path, extra_args=extra_args
            )
            raw_text = pypandoc.convert_file(absolute_path, "markdown")
            raw_text = remove_images_from_markdown(raw_text)
            document.raw_text = raw_text
        else:  # pdf and others
            raw_text = extract_text_from_doc(document.absolute_path, doc=document)
            document.raw_text = raw_text

        document.processing = False
        document.downloadpath = str(Path(document.path))
        document.save()

    except Exception as e:
        debug(f"Error extracting text from document {document_uuid}: {e}")
        document.raw_text = ""
        document.processing = False
        document.save()

    return raw_text


@celery_app.task(
    name="tasks.document.update",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def update_document_fields(document_uuid: str):
    document = SmartDocument.objects(uuid=document_uuid).first()
    document.task_id = None
    document.save()


@celery_app.task(
    name="tasks.document.cleanup",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def cleanup_document(document_uuid: str):
    """
    Delete the document record and its file when validation or ingestion fails.
    """
    document = SmartDocument.objects(uuid=document_uuid).first()

    document.task_id = None
    document.task_status = "error"
    document.processing = False
    document.save()


@celery_app.task(
    name="tasks.document.semantic_ingestion",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def perform_semantic_ingestion(raw_text, document_uuid, user_id):
    document = SmartDocument.objects(uuid=document_uuid).first()
    document.task_status = "readying"
    document.save()
    debug(document.path)
    debug(document.absolute_path)
    debug(document.uuid)
    debug(document.title)

    document_manager = DocumentManager()
    document_path = document.absolute_path
    document_manager.add_document(
        user_id=user_id,
        document_name=document.title,
        document_id=document.uuid,
        doc_path=document_path,
        raw_text=raw_text,
    )
    document.task_status = "complete"
    document.save()
    return document.uuid


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

    def __enter__(self):
        return self

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
