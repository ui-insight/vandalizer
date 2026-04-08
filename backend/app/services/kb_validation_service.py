"""Knowledge Base validation service - retrieval precision, source health, chunk coverage."""

import asyncio
import logging

import httpx

from app.models.kb_test_query import KBTestQuery
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.services.document_manager import get_document_manager

logger = logging.getLogger(__name__)


def _get_dm():
    return get_document_manager()


async def check_source_health(kb_uuid: str) -> dict:
    """Check health of all sources in a knowledge base.

    For URL sources: HTTP HEAD check.
    For document sources: verify SmartDocument still has text.
    """
    from app.models.document import SmartDocument

    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).to_list()

    if not sources:
        return {"total": 0, "healthy": 0, "unhealthy": 0, "ratio": 1.0, "details": []}

    details = []
    healthy = 0

    for source in sources:
        entry = {
            "uuid": source.uuid,
            "source_type": source.source_type,
            "name": source.url_title or source.url or source.document_uuid or "Unknown",
            "status": "unknown",
        }

        if source.source_type == "url" and source.url:
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.head(source.url)
                    if resp.status_code < 400:
                        entry["status"] = "healthy"
                        healthy += 1
                    else:
                        entry["status"] = "unhealthy"
                        entry["error"] = f"HTTP {resp.status_code}"
            except Exception as e:
                entry["status"] = "unhealthy"
                entry["error"] = str(e)[:200]
        elif source.source_type == "document" and source.document_uuid:
            doc = await SmartDocument.find_one(SmartDocument.uuid == source.document_uuid)
            if doc and (doc.raw_text or "").strip():
                entry["status"] = "healthy"
                healthy += 1
            else:
                entry["status"] = "unhealthy"
                entry["error"] = "Document not found or has no text"
        else:
            entry["status"] = "unhealthy"
            entry["error"] = "Missing source reference"

        details.append(entry)

    total = len(sources)
    return {
        "total": total,
        "healthy": healthy,
        "unhealthy": total - healthy,
        "ratio": healthy / total if total > 0 else 0.0,
        "details": details,
    }


async def check_chunk_coverage(kb_uuid: str) -> dict:
    """Check chunk coverage - what fraction of sources have chunks."""
    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).to_list()

    if not sources:
        return {"total": 0, "with_chunks": 0, "without_chunks": 0, "ratio": 1.0, "total_chunks": 0}

    with_chunks = sum(1 for s in sources if s.chunk_count > 0)
    total_chunks = sum(s.chunk_count for s in sources)

    return {
        "total": len(sources),
        "with_chunks": with_chunks,
        "without_chunks": len(sources) - with_chunks,
        "ratio": with_chunks / len(sources) if sources else 0.0,
        "total_chunks": total_chunks,
    }


async def check_retrieval_precision(
    kb_uuid: str,
    test_queries: list[KBTestQuery],
) -> dict:
    """Test retrieval quality against sample queries.

    For each query, runs semantic search and checks if expected sources appear in top results.
    """
    if not test_queries:
        return {"total_queries": 0, "avg_precision": 0.0, "details": []}

    dm = _get_dm()
    details = []
    precision_sum = 0.0

    for tq in test_queries:
        try:
            results = await asyncio.to_thread(dm.query_kb, kb_uuid, tq.query, 8)
        except Exception as e:
            details.append({
                "query": tq.query,
                "precision": 0.0,
                "error": str(e)[:200],
            })
            continue

        if not results:
            details.append({"query": tq.query, "precision": 0.0, "retrieved_sources": []})
            continue

        # Check how many expected sources appear in retrieved results
        retrieved_sources = []
        for doc_text, metadata in results:
            source_name = metadata.get("source_name", "") if isinstance(metadata, dict) else ""
            retrieved_sources.append(source_name)

        if tq.expected_source_labels:
            hits = sum(
                1 for label in tq.expected_source_labels
                if any(label.lower() in src.lower() for src in retrieved_sources)
            )
            precision = hits / len(tq.expected_source_labels) if tq.expected_source_labels else 0.0
        else:
            # If no expected labels, just check we got results
            precision = 1.0 if results else 0.0

        # Check expected_answer_contains if set
        answer_match = None
        if tq.expected_answer_contains:
            combined_text = " ".join(text for text, _ in results)
            answer_match = tq.expected_answer_contains.lower() in combined_text.lower()
            if not answer_match:
                precision *= 0.5  # Penalize if expected content not found

        precision_sum += precision
        details.append({
            "query": tq.query,
            "precision": round(precision, 3),
            "retrieved_sources": retrieved_sources[:5],
            "expected_sources": tq.expected_source_labels,
            "answer_match": answer_match,
        })

    avg_precision = precision_sum / len(test_queries) if test_queries else 0.0

    return {
        "total_queries": len(test_queries),
        "avg_precision": round(avg_precision, 3),
        "details": details,
    }


async def run_kb_validation(
    kb_uuid: str,
    user_id: str,
) -> dict:
    """Run full validation on a knowledge base.

    Combines source health, chunk coverage, and retrieval precision into a unified result.
    """
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        raise ValueError("Knowledge base not found")

    # Run health and coverage checks in parallel
    health_task = check_source_health(kb_uuid)
    coverage_task = check_chunk_coverage(kb_uuid)
    test_queries = await KBTestQuery.find(
        KBTestQuery.knowledge_base_uuid == kb_uuid,
    ).to_list()

    health, coverage = await asyncio.gather(health_task, coverage_task)

    # Run retrieval precision if test queries exist
    retrieval = await check_retrieval_precision(kb_uuid, test_queries) if test_queries else {
        "total_queries": 0, "avg_precision": 0.0, "details": [],
    }

    # Compute unified score: retrieval 50% + health 30% + coverage 20%
    retrieval_score = retrieval["avg_precision"] * 100
    health_score = health["ratio"] * 100
    coverage_score = coverage["ratio"] * 100

    if test_queries:
        raw_score = retrieval_score * 0.5 + health_score * 0.3 + coverage_score * 0.2
    else:
        # Without test queries, weight health and coverage more
        raw_score = health_score * 0.6 + coverage_score * 0.4

    result = {
        "kb_uuid": kb_uuid,
        "kb_title": kb.title,
        "source_health": health,
        "chunk_coverage": coverage,
        "retrieval_precision": retrieval,
        "raw_score": round(raw_score, 1),
        "num_test_queries": len(test_queries),
        "num_sources": health["total"],
        # Match the shape expected by persist_validation_run
        "sources": [{"label": s["name"], "status": s["status"]} for s in health["details"]],
        "num_runs": 1,
    }

    # Persist the validation run
    from app.services.quality_service import persist_validation_run

    await persist_validation_run(
        item_kind="knowledge_base",
        item_id=kb_uuid,
        item_name=kb.title,
        run_type="kb_validation",
        result=result,
        user_id=user_id,
    )

    return result
