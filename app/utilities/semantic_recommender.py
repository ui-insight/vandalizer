import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings
from devtools import debug
from langchain_openai import OpenAIEmbeddings

from app.models import (
    SmartDocument,
)


class SemanticRecommender:
    def __init__(self, persist_directory=None) -> None:
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings()

        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.persist_directory.as_posix(),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )

        # Create or get collection for recommendations
        self.collection_name = "semantic_recommendations"
        try:
            self.collection = self.client.get_collection(self.collection_name)
        except:
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

        try:
            # Create search context from selected documents
            search_text = ""
            search_text += "Documents selected:"

            for doc in selected_documents:
                search_text += f"\n{doc.raw_text}"

            # Generate embedding for search
            search_embedding = self.embeddings.embed_query(search_text)

            # Build query filters
            where_filters = {}
            # if user_id:
            #     where_filters["user_id"] = user_id
            # if space:
            #     where_filters["space"] = space

            # Search vector database
            results = self.collection.query(
                query_embeddings=[search_embedding],
                n_results=limit,
                where=where_filters if where_filters else None,
                include=["metadatas", "documents", "distances"],
            )

            recommendations = []
            if results and results["ids"]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i]
                    distance = results["distances"][0][i]
                    similarity_score = 1 - distance  # Convert distance to similarity
                    if similarity_score < min_similarity:
                        continue
                    # Parse context from metadata
                    context = json.loads(metadata.get("context", "{}"))
                    debug(metadata)
                    recommendation = {
                        "identifier": metadata["identifier"],
                        "recommendation_type": metadata["recommendation_type"],
                        "similarity_score": similarity_score,
                        "num_executions": metadata.get("num_executions", 0),
                        "created_at": metadata.get("created_at"),
                        "context": context,
                    }
                    recommendations.append(recommendation)

            print(recommendations)
            return recommendations

        except Exception as e:
            print(f"Error searching semantic recommendations: {str(e)}")
            return []

    def ingest_recommendation_item(
        self, ingestion_text: str, identifier: str, recommendation_type: str
    ) -> Dict[str, Any]:
        """Ingest (or upsert) a semantic into the vector store, averaging embeddings on each run."""
        try:
            new_embedding = self.embeddings.embed_query(ingestion_text)
            uuid4 = uuid.uuid4().hex
            doc_id = f"{ingestion_text}_{identifier}_{uuid4}"

            # 1) Fetch any existing record
            existing = self.collection.get(
                ids=[doc_id], include=["embeddings", "metadatas"]
            )

            # 2) Decide: update vs. add
            if existing.get("ids"):
                # We have an old record → average embeddings
                old_embed = existing["embeddings"][0]
                meta = existing["metadatas"][0] or {}
                old_count = meta.get("num_executions", 1)

                new_count = old_count + 1
                avg_embed = [
                    (oe * old_count + ne) / new_count
                    for oe, ne in zip(old_embed, new_embedding)
                ]

                updated_meta = {
                    **meta,
                    "num_executions": new_count,
                }

                self.collection.update(
                    ids=[doc_id],
                    embeddings=[avg_embed],
                    documents=[ingestion_text],
                    metadatas=[updated_meta],
                )

            else:
                # No existing record → add fresh
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

            return {
                "status": "success",
                "document_id": doc_id,
                "recommendation_id": identifier,
                "message": f"Upserted recommendation '{identifier}', run #{new_count}",
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}
