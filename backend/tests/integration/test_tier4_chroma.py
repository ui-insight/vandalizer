"""Tier 4 integration tests — exercises ChromaDB via DocumentManager.

Uses a temporary PersistentClient pointed at an ephemeral directory, so no
external server is required. The default embedding function downloads an ONNX
model on first use; subsequent runs use the local cache.

Set INTEGRATION_CHROMA=1 to run.
"""

import os
import tempfile

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_CHROMA"),
        reason="Set INTEGRATION_CHROMA=1 to run ChromaDB integration tests",
    ),
    pytest.mark.integration_tier4,
]


@pytest.fixture
def chroma_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def doc_manager(chroma_dir):
    from app.services.document_manager import DocumentManager

    return DocumentManager(persist_directory=chroma_dir)


# ---------------------------------------------------------------------------
# DocumentManager — user document collection round-trip
# ---------------------------------------------------------------------------

class TestUserCollectionRoundTrip:
    def test_add_then_query_returns_chunks(self, doc_manager):
        doc_manager.add_document(
            user_id="u1",
            doc_path="/fake/path",
            document_name="grant.pdf",
            document_id="doc-1",
            raw_text=(
                "Principal investigator: Alice. "
                "The project investigates RNA splicing factors. "
                "Total budget is $1.5M over three years."
            ),
        )

        # Query returns chunks containing relevant content
        results = doc_manager.query_documents(
            user_id="u1", query="who is the principal investigator", k=2,
        )

        assert isinstance(results, list)
        assert len(results) >= 1
        # Each result has content + metadata
        for r in results:
            assert "content" in r
            assert "metadata" in r
            assert r["metadata"]["document_id"] == "doc-1"
            assert r["metadata"]["user_id"] == "u1"

    def test_document_exists_reflects_state(self, doc_manager):
        assert doc_manager.document_exists("u1", "doc-x") is False

        doc_manager.add_document(
            user_id="u1", doc_path="/p", document_name="x", document_id="doc-x",
            raw_text="some content here",
        )
        assert doc_manager.document_exists("u1", "doc-x") is True

    def test_delete_removes_document(self, doc_manager):
        doc_manager.add_document(
            user_id="u1", doc_path="/p", document_name="y", document_id="doc-y",
            raw_text="content to delete",
        )
        assert doc_manager.document_exists("u1", "doc-y") is True

        doc_manager.delete_document("u1", "doc-y")
        assert doc_manager.document_exists("u1", "doc-y") is False

    def test_delete_nonexistent_is_noop(self, doc_manager):
        # Must not raise even if the document was never added
        doc_manager.delete_document("u1", "never-existed")

    def test_query_filtered_by_doc_ids(self, doc_manager):
        doc_manager.add_document(
            user_id="u1", doc_path="/p", document_name="a", document_id="doc-a",
            raw_text="alpha document about budgets",
        )
        doc_manager.add_document(
            user_id="u1", doc_path="/p", document_name="b", document_id="doc-b",
            raw_text="beta document about budgets",
        )

        results = doc_manager.query_documents(
            user_id="u1", query="budgets", filter_docs=["doc-a"], k=4,
        )

        # All returned chunks must come from doc-a only
        for r in results:
            assert r["metadata"]["document_id"] == "doc-a"

    def test_user_collections_are_isolated(self, doc_manager):
        doc_manager.add_document(
            user_id="alice", doc_path="/p", document_name="a", document_id="alice-doc",
            raw_text="Alice's confidential note",
        )

        # Bob should not see Alice's doc — separate collection per user
        bob_results = doc_manager.query_documents(
            user_id="bob", query="confidential", k=4,
        )
        for r in bob_results:
            assert r["metadata"]["user_id"] != "alice"


# ---------------------------------------------------------------------------
# DocumentManager — KB collection round-trip
# ---------------------------------------------------------------------------

class TestKBCollectionRoundTrip:
    def test_add_to_kb_returns_chunk_count(self, doc_manager):
        text = "knowledge base entry about funding eligibility. " * 30
        n = doc_manager.add_to_kb(
            kb_uuid="kb-1",
            source_id="src-1",
            source_name="policy.md",
            raw_text=text,
        )

        assert n >= 1
        results = doc_manager.query_kb(kb_uuid="kb-1", query="funding eligibility", k=2)
        assert len(results) >= 1
        for r in results:
            assert r["metadata"]["source_id"] == "src-1"

    def test_add_to_kb_empty_text_returns_zero(self, doc_manager):
        n = doc_manager.add_to_kb(
            kb_uuid="kb-2", source_id="empty", source_name="x", raw_text="",
        )
        assert n == 0

    def test_delete_kb_source_removes_only_that_source(self, doc_manager):
        doc_manager.add_to_kb("kb-3", "src-a", "a.md", "content for source A " * 20)
        doc_manager.add_to_kb("kb-3", "src-b", "b.md", "content for source B " * 20)

        doc_manager.delete_kb_source("kb-3", "src-a")

        results = doc_manager.query_kb("kb-3", "content", k=10)
        for r in results:
            assert r["metadata"]["source_id"] == "src-b"

    def test_delete_kb_collection_is_idempotent(self, doc_manager):
        doc_manager.add_to_kb("kb-4", "src", "name", "some content here " * 5)
        doc_manager.delete_kb_collection("kb-4")
        # Second delete should be a no-op (collection no longer exists)
        doc_manager.delete_kb_collection("kb-4")

    def test_query_kb_min_similarity_floor_gates_out_of_scope(self, doc_manager):
        """A high relevance floor turns an off-topic query into an empty result.

        The KB holds only grant-budget text. An unrelated query ("how do I bake
        sourdough bread") still surfaces chunks at min_similarity=0.0 (default,
        ungated) because vector search always returns the top-k. With a high
        floor those weakly-related chunks fall below the threshold and drop out,
        so the RAG caller sees an empty set and abstains.
        """
        doc_manager.add_to_kb(
            kb_uuid="kb-floor",
            source_id="budget",
            source_name="budget.md",
            raw_text=(
                "The grant budget allocates $1.5M across three fiscal years. "
                "Personnel costs cover two postdoctoral researchers and a "
                "graduate assistant. Indirect cost recovery is 52 percent."
            ),
        )

        off_topic = "how do I bake sourdough bread at home"

        # Ungated: vector search returns chunks regardless of how weak the match.
        ungated = doc_manager.query_kb("kb-floor", off_topic, k=4, min_similarity=0.0)
        assert len(ungated) >= 1
        # Every returned chunk carries a computed similarity in [0, 1].
        for r in ungated:
            assert 0.0 <= r["similarity"] <= 1.0

        # A floor above the best off-topic score empties the result set.
        best = max(r["similarity"] for r in ungated)
        gated = doc_manager.query_kb(
            "kb-floor", off_topic, k=4, min_similarity=best + 0.01,
        )
        assert gated == []

        # An in-scope query still clears a moderate floor.
        in_scope = doc_manager.query_kb(
            "kb-floor", "what is the indirect cost rate", k=4, min_similarity=0.05,
        )
        assert len(in_scope) >= 1
