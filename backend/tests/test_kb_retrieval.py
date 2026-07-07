"""Tests for the shared KB retrieval pipeline (``retrieve_kb_chunks``) and the
chat-side segment builder (``_build_kb_segment``).

These guard the "tuned config actually applies on the live path" seam: the
optimizer stores k / min_similarity / rerank / query_rewriting per KB, and both
the validation harness and streaming chat must route retrieval through the
same pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_service, kb_validation_service
from app.services.kb_validation_service import RAGConfig


def _chunk(i: int, source: str = "doc.pdf", **meta) -> dict:
    metadata = {"source_name": source, "source_id": f"src-{source}"}
    metadata.update(meta)
    return {
        "content": f"chunk {i} content",
        "metadata": metadata,
        "chunk_id": f"src-{source}_chunk_{i}",
        "score": 0.1 * i,
        "similarity": round(0.95 - 0.1 * i, 2),
    }


def _make_mock_run(output: str, tokens: int = 0):
    run = MagicMock()
    run.output = output
    usage = MagicMock()
    usage.input_tokens = tokens
    usage.output_tokens = 0
    usage.cache_read_tokens = 0
    usage.cache_write_tokens = 0
    run.usage = MagicMock(return_value=usage)
    return run


@pytest.mark.asyncio
async def test_explicit_config_k_and_floor_reach_query_kb():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[_chunk(0)])
    cfg = RAGConfig(k=4, min_similarity=0.35)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        results, resolved, tokens = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model", config=cfg,
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "q?", 4, 0.35)
    assert len(results) == 1
    assert resolved.k == 4
    assert tokens == 0


@pytest.mark.asyncio
async def test_kb_override_resolved_when_no_explicit_config():
    """A KB with an applied rag_config_override must drive retrieval with its
    tuned k, not the hardcoded legacy default."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    kb = MagicMock()
    kb.rag_config_override = {"k": 4, "min_similarity": 0.2}

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=kb)
        _, resolved, _ = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model",
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "q?", 4, 0.2)
    assert resolved.k == 4


@pytest.mark.asyncio
async def test_overfetch_multiplier_expands_pool():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    cfg = RAGConfig(k=4)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model", config=cfg, overfetch_multiplier=3,
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "q?", 12, 0.0)


@pytest.mark.asyncio
async def test_rerank_reduces_pool_and_scores_raw_query():
    """rerank='llm' retrieves an oversampled pool, then the rerank agent picks
    cfg.k — and it must be asked about the raw user query."""
    chunks = [_chunk(i) for i in range(5)]
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=chunks)

    captured = {}

    async def fake_run(prompt):
        captured["prompt"] = prompt
        return _make_mock_run("[3, 1]", tokens=77)

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)
    cfg = RAGConfig(k=2, rerank="llm")

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        results, _, tokens = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "the raw question?", "test-model", config=cfg,
        )

    # Pool oversampled by RERANK_POOL_MULTIPLIER.
    fake_dm.query_kb.assert_called_once_with("kb-1", "the raw question?", 4, 0.0)
    # Rerank output order respected.
    assert [r["chunk_id"] for r in results] == [chunks[3]["chunk_id"], chunks[1]["chunk_id"]]
    assert "the raw question?" in captured["prompt"]
    assert tokens == 77


@pytest.mark.asyncio
async def test_query_rewriting_rewrites_retrieval_but_not_rerank():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    cfg = RAGConfig(k=8, query_rewriting=True)

    rewriter = MagicMock()
    rewriter.run = AsyncMock(return_value=_make_mock_run("rewritten search terms", tokens=9))

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=rewriter):
        _, _, tokens = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "original question", "test-model", config=cfg,
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "rewritten search terms", 8, 0.0)
    assert tokens == 9


@pytest.mark.asyncio
async def test_build_kb_segment_trims_to_cfg_k_and_builds_sources():
    chunks = [
        _chunk(0, source="budget.xlsx", sheet="Year 1"),
        _chunk(1, source="proposal.pdf", page=12),
        _chunk(2, source="proposal.pdf", page=13),
    ]
    cfg = RAGConfig(k=2)

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(chunks, cfg, 0))):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert segment is not None
    # Over-fetched pool trimmed back to the tuned k.
    assert len(sources) == 2
    assert "budget.xlsx (Year 1)" in segment.text
    assert "proposal.pdf (p. 12)" in segment.text
    assert "chunk 2 content" not in segment.text
    assert sources[0]["document_title"] == "budget.xlsx"
    assert sources[0]["sheet"] == "Year 1"
    assert sources[1]["page"] == 12
    assert sources[0]["similarity"] == 0.95


@pytest.mark.asyncio
async def test_build_kb_segment_empty_retrieval_returns_none():
    cfg = RAGConfig()
    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=([], cfg, 0))):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert segment is None
    assert sources == []
