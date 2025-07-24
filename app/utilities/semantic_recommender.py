import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings
from devtools import debug
from langchain_openai import OpenAIEmbeddings

from app.models import SmartDocument


class SemanticRecommender:
    def __init__(self, persist_directory=None) -> None:
        self.persist_directory = persist_directory or "./chroma_db"
        self.embeddings = OpenAIEmbeddings()

        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )

        # Ensure our collection exists (or create it)
        existing = {col.name for col in self.client.list_collections()}
        self.collection_name = "semantic_recommendations"

        if self.collection_name in existing:
            self.collection = self.client.get_collection(self.collection_name)
        else:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    def search_recommendations(
        self,
        selected_documents: List[SmartDocument],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search for recommendations based on selected documents."""
        min_similarity = 0.9

        # Build the text prompt
        search_text = "Documents selected:\n" + "\n".join(
            doc.raw_text for doc in selected_documents
        )

        try:
            # Generate embedding
            search_embedding = self.embeddings.embed_query(search_text)

            # If the collection is empty, .query may still return empty lists rather than error,
            # but wrap anyway in case Chromadb changes behavior.
            results = self.collection.query(
                query_embeddings=[search_embedding],
                n_results=limit,
                include=["metadatas", "documents", "distances"],
            )

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
            new_embedding = self.embeddings.embed_query(ingestion_text)
            doc_uuid = uuid.uuid4().hex
            doc_id = f"{identifier}_{doc_uuid}"

            # Try to fetch existing; if it fails or is empty, we'll add fresh
            try:
                existing = self.collection.get(
                    ids=[doc_id], include=["embeddings", "metadatas"]
                )
                has_existing = bool(existing.get("ids"))
            except Exception:
                debug("No existing record found or error fetching it, will create new")
                has_existing = False

            if has_existing:
                old_embed = existing["embeddings"][0]
                meta = existing["metadatas"][0] or {}
                old_count = meta.get("num_executions", 1)
                new_count = old_count + 1

                # Average embeddings
                avg_embed = [
                    (oe * old_count + ne) / new_count
                    for oe, ne in zip(old_embed, new_embedding)
                ]
                updated_meta = {**meta, "num_executions": new_count}

                self.collection.update(
                    ids=[doc_id],
                    embeddings=[avg_embed],
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
                    embeddings=[new_embedding],
                    documents=[ingestion_text],
                    metadatas=[initial_meta],
                    ids=[doc_id],
                )

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
