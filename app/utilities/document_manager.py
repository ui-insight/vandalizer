from typing import List, Dict, Any
import os
from datetime import datetime
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma.vectorstores import Chroma
import chromadb
from chromadb.config import Settings
import uuid

from pathlib import Path
from app import app
import pymupdf
from devtools import debug
import httpx
from devtools import debug

from app.utilities.document_readers import ocr_extract_text_from_pdf

from flask import current_app


def get_absolute_path(document):
    user_id = document.user_id
    absolute_path = os.path.join(
        app.root_path, "static", "uploads", user_id, document.path
    )
    return absolute_path


def update_document_path(document, user_id):
    root_path = current_app.root_path
    absolute_path = get_absolute_path(document)
    if not os.path.exists(absolute_path):
        document_file_path = absolute_path
        # create user_id folder if not exists
        if not os.path.exists(os.path.join(root_path, "static", "uploads", user_id)):
            os.makedirs(os.path.join(root_path, "static", "uploads", user_id))
        # move document and files
        old_path = os.path.join(root_path, "static", "uploads", document.path)
        os.rename(old_path, document_file_path)
        if document.extension in ["xlsx", "xls", "docx"]:
            for f in os.listdir(os.path.join(root_path, "static", "uploads")):
                if f.startswith(document.uuid):
                    os.rename(
                        os.path.join(
                            root_path,
                            "static",
                            "uploads",
                            f,
                        ),
                        os.path.join(
                            root_path,
                            "static",
                            "uploads",
                            user_id,
                            f,
                        ),
                    )


class DocumentManager:
    def __init__(self, persist_directory: Path = Path(app.root_path) / "static" / "db"):
        """Initialize the document manager with a persistence directory."""
        self.upload_folder = Path(app.root_path) / "static" / "uploads"
        self.persist_directory = persist_directory.as_posix()
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, length_function=len
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

        vectorstore = Chroma(
            client=self.client,  # Use the existing client
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

        return vectorstore

    def add_document(
        self, user_id: str, doc_path: str, document_name: str, document_id: str
    ) -> str:
        """
        Add a document to a user's collection.
        Returns the document ID for future reference.
        """
        # Load and split the document
        debug(doc_path)
        splits = []
        # if html file
        if doc_path.endswith(".html"):
            text = ocr_extract_text_from_pdf(doc_path)
            with open(doc_path, "r", encoding="utf-8") as file:
                text = file.read()
            text_splits = self.text_splitter.split_text(text)
            splits = self.text_splitter.create_documents(text_splits)

        else:
            text = ocr_extract_text_from_pdf(doc_path)
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
                }
            )

        print("splits[0]: ", splits[0])
        print("len(splits): ", len(splits))

        # Get the user's collection and add the document
        vectorstore = self.get_user_collection(user_id)

        # Add new documents to existing collection
        vectorstore.add_documents(splits)

    def query_documents(
        self, user_id: str, query: str, filter_docs: List[str] = None, k: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Query a user's documents, optionally filtering by document IDs.
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
            print("filter_dict: ", filter_dict)
            results = vectorstore.similarity_search(
                query,
                k=k,
                filter=filter_dict,
            )
        else:
            results = vectorstore.similarity_search(query, k=k)

        formatted_results = [
            {"content": doc.page_content, "metadata": doc.metadata} for doc in results
        ]

        print("query: ", query)
        print("user_id: ", user_id)
        print("filter_docs: ", filter_docs)
        print("k: ", k)
        print("results: ", results)
        print("formatted_results: ", formatted_results)

        return formatted_results

    def document_exists(self, user_id: str, document_id: str) -> bool:
        """Check if a specific document exists in a user's collection."""
        vectorstore = self.get_user_collection(user_id)
        # Get the raw collection to use ChromaDB's filtering
        collection = self.client.get_or_create_collection(name=f"user_{user_id}_docs")
        if collection:
            # Check if any chunks with matching document_id exist
            results = collection.get(where={"document_id": document_id})
            return bool(results)
        return False

    def delete_document(self, user_id: str, document_id: str) -> None:
        """Delete a specific document from a user's collection."""
        vectorstore = self.get_user_collection(user_id)
        # Get the raw collection to use ChromaDB's filtering
        collection = self.client.get_or_create_collection(name=f"user_{user_id}_docs")
        if collection:
            # Delete all chunks with matching document_id
            collection.delete(where={"document_id": document_id})

    def list_user_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """List all documents in a user's collection with metadata."""
        collection = self.client.get_collection(name=f"user_{user_id}_docs")
        # Get all unique document IDs and their metadata
        results = collection.get()

        # Group by document_id to get unique documents
        documents = {}
        for i, metadata in enumerate(results["metadatas"]):
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
