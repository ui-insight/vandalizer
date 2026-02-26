import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings
from devtools import debug

from app.models import SmartDocument
from app.utilities.config import settings


class SemanticRecommender:
    def __init__(self, persist_directory=None) -> None:
        self.persist_directory = persist_directory or "./chroma_db"

        # Determine if we should use ChromaDB server or persistent client
        use_server = settings.use_chroma_server or settings.environment in [
            "staging",
            "production",
        ]

        if use_server:
            # Use HttpClient to connect to ChromaDB server
            debug(
                f"Connecting to ChromaDB server at {settings.chroma_host}:{settings.chroma_port}"
            )
            try:
                self.client = chromadb.HttpClient(
                    host=settings.chroma_host,
                    port=settings.chroma_port,
                    settings=ChromaSettings(
                        anonymized_telemetry=False,
                    ),
                )
                debug("Successfully connected to ChromaDB server")
            except Exception as e:
                debug(f"Failed to connect to ChromaDB server: {e}")
                debug("Falling back to persistent client")
                use_server = False

        if not use_server:
            # Use PersistentClient for local development
            debug(f"Using persistent ChromaDB client at {self.persist_directory}")
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    is_persistent=True,
                    # Performance optimization: allow more threads for parallel processing
                    allow_reset=True,
                ),
            )

        # Ensure our collection exists (or create it)
        existing = {col.name for col in self.client.list_collections()}
        self.collection_name = "semantic_recommendations"

        if self.collection_name in existing:
            self.collection = self.client.get_collection(self.collection_name)
        else:
            # Use all-MiniLM-L6-v2 (faster, smaller model than default)
            # Default is sentence-transformers/all-MiniLM-L12-v2 which is slower
            try:
                from chromadb.utils import embedding_functions

                embedding_func = (
                    embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"  # 80MB, 2x faster than L12
                    )
                )
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=embedding_func,
                )
            except Exception as e:
                debug(
                    f"Failed to use optimized embedding model, falling back to default: {e}"
                )
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )

        # Check collection size for early exit optimization
        self.is_empty = self.collection.count() == 0

    def search_recommendations(
        self,
        selected_documents: List[SmartDocument],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search for recommendations based on selected documents."""
        # Re-check if collection is actually empty (in case items were added since initialization)
        try:
            count = self.collection.count()
            self.is_empty = count == 0
            if self.is_empty:
                debug("Collection is empty, search will return no results")
        except Exception as e:
            debug(f"Error checking collection count: {e}")
            # Continue anyway - let the search handle it

        # Proceed with search even if empty - ChromaDB will return empty results naturally
        min_similarity = 0.7

        # Build the text prompt using a summary instead of full raw_text
        # This dramatically improves performance for large documents
        MAX_CHARS_PER_DOC = 2000  # ~500 tokens, enough for semantic matching

        doc_summaries = []
        for doc in selected_documents:
            # Use title + truncated beginning of document
            text = doc.raw_text or ""
            if len(text) > MAX_CHARS_PER_DOC:
                text = text[:MAX_CHARS_PER_DOC] + "..."
            doc_summaries.append(f"{doc.title}: {text}")

        search_text = "Documents selected:\n" + "\n".join(doc_summaries)

        try:
            # If the collection is empty, .query may still return empty lists rather than error,
            # but wrap anyway in case Chromadb changes behavior.
            results = self.collection.query(
                query_texts=[search_text],
                n_results=limit,
                include=["metadatas", "distances"],
            )
            print(results)
            recommendations = []
            ids = results.get("ids", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]

            for doc_id, metadata, distance in zip(ids, metas, dists):
                similarity = 1 - distance
                if similarity < min_similarity:
                    continue

                # Safely parse context
                try:
                    context = json.loads(metadata.get("context", "{}"))
                except json.JSONDecodeError:
                    context = {}

                recommendations.append(
                    {
                        "identifier": metadata.get("identifier"),
                        "recommendation_type": metadata.get("recommendation_type"),
                        "similarity_score": similarity,
                        "num_executions": metadata.get("num_executions", 0),
                        "created_at": metadata.get("created_at"),
                        "context": context,
                    }
                )

            debug(f"Found {len(recommendations)} valid recommendations")
            return recommendations

        except Exception as e:
            debug(f"Error during search_recommendations: {e}")
            return []

    def ingest_recommendation_item(
        self, ingestion_text: str, identifier: str, recommendation_type: str
    ) -> Dict[str, Any]:
        """Ingest (or upsert) an item into the vector store, averaging embeddings on each run."""
        try:
            doc_uuid = uuid.uuid4().hex
            doc_id = f"{identifier}_{doc_uuid}"

            # Try to fetch existing; if it fails or is empty, we'll add fresh
            try:
                existing = self.collection.get(ids=[doc_id], include=["metadatas"])
                has_existing = bool(existing.get("ids"))
            except Exception:
                debug("No existing record found or error fetching it, will create new")
                has_existing = False

            if has_existing:
                meta = existing["metadatas"][0] or {}
                old_count = meta.get("num_executions", 1)
                new_count = old_count + 1

                updated_meta = {**meta, "num_executions": new_count}

                self.collection.update(
                    ids=[doc_id],
                    documents=[ingestion_text],
                    metadatas=[updated_meta],
                )
            else:
                new_count = 1
                initial_meta = {
                    "identifier": identifier,
                    "recommendation_type": recommendation_type,
                    "num_executions": new_count,
                }
                self.collection.add(
                    documents=[ingestion_text],
                    metadatas=[initial_meta],
                    ids=[doc_id],
                )
                # Update empty flag since we just added an item
                self.is_empty = False

            debug("Successfully ingested item to recommendations")
            return {
                "status": "success",
                "document_id": doc_id,
                "recommendation_id": identifier,
                "message": f"Upserted recommendation '{identifier}', run #{new_count}",
            }

        except Exception as e:
            debug(f"Error ingesting recommendation item: {e}")
            return {"status": "error", "error": str(e)}
