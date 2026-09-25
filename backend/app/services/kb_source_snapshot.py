"""The knowledge base as a validation run found it: which sources, which
version of each, and how many chunks.

A run's score is a measurement of the KB at run time, but the run used to
keep only health ratios and a total chunk count. Once sources were added,
refreshed, re-indexed or removed, nobody could say what an older run had
measured, or whether two runs had measured the same KB (support ticket).
Each run now records this snapshot, and the results export carries it.

A source's version is its content hash — a fingerprint of the exact text
that was indexed — together with when that text was retrieved and indexed.
``fingerprint`` hashes (source id, content hash, chunk count, status) over
every source, so two runs over an unchanged KB share it and any change to
the source list or to what a source holds changes it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.utils.kb_source_currency import export_provenance


def _display_name(source: Any) -> str:
    return (
        getattr(source, "custom_name", None)
        or getattr(source, "document_title", None)
        or getattr(source, "url_title", None)
        or getattr(source, "url", None)
        or getattr(source, "document_uuid", None)
        or ""
    )


def build_source_snapshot(sources: list) -> dict:
    """Pure: the snapshot of ``sources`` (KnowledgeBaseSource rows)."""
    entries = []
    for s in sorted(sources, key=lambda s: getattr(s, "uuid", "") or ""):
        prov = export_provenance(s)
        currency = prov.pop("currency")
        entries.append({
            "source_uuid": getattr(s, "uuid", "") or "",
            "source_type": getattr(s, "source_type", None),
            "name": _display_name(s),
            "document_uuid": getattr(s, "document_uuid", None),
            "url": getattr(s, "url", None),
            **prov,
            "content_hash": currency["content_hash"],
            "content_hash_algorithm": currency["content_hash_algorithm"],
            "content_hash_recorded": currency["content_hash_recorded"],
            "content_retrieved_at": currency["content_retrieved_at"],
            "last_ingested_at": currency["last_ingested_at"],
        })
    identity = [
        [e["source_uuid"], e["content_hash"], e["chunk_count"], e["status"]]
        for e in entries
    ]
    digest = hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()
    return {
        "recorded": True,
        "fingerprint": digest[:12],
        "total_sources": len(entries),
        "total_chunks": sum(e["chunk_count"] for e in entries),
        "sources": entries,
    }


async def snapshot_kb_sources(kb_uuid: str) -> dict:
    from app.models.knowledge import KnowledgeBaseSource

    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).to_list()
    return build_source_snapshot(sources)


def legacy_source_snapshot(snapshot: dict) -> dict | None:
    """The best a run recorded before snapshots existed: each source's id,
    type, name and health from its source-health check, and the KB's total
    chunk count. No versions or per-source chunks — ``recorded`` is False so
    an export never passes this off as the full record."""
    health = snapshot.get("source_health") or {}
    details = health.get("details") or []
    if not details:
        return None
    return {
        "recorded": False,
        "fingerprint": None,
        "total_sources": health.get("total", len(details)),
        "total_chunks": (snapshot.get("chunk_coverage") or {}).get("total_chunks"),
        "sources": [
            {
                "source_uuid": d.get("uuid") or "",
                "source_type": d.get("source_type"),
                "name": d.get("name") or "",
                "health": d.get("status"),
            }
            for d in details
        ],
    }
