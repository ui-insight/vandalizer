"""``delete_kb_source`` has to tell its caller whether the chunks are gone.

It logs and swallows every Chroma error, so the return value is the only
evidence a caller has that the delete happened. The project-KB mirror is the
caller that needs it: it deletes a document's chunks and re-adds them under the
same deterministic ids (``<document_uuid>_chunk_<i>``) with ``collection.add``,
which skips ids that already exist. A delete that quietly failed would
therefore leave the first extraction's text in place under a row stamped with
the *new* text's fingerprint — and the currency gate would certify that row as
current from then on (#887 follow-up).
"""

from unittest.mock import MagicMock, patch

from app.services.document_manager import DocumentManager


def _manager() -> DocumentManager:
    """A DocumentManager without a Chroma client — the collection is patched."""
    return object.__new__(DocumentManager)


class TestDeleteKbSource:
    def test_a_delete_that_ran_reports_true(self):
        collection = MagicMock()
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            assert _manager().delete_kb_source("kb1", "doc-1") is True

        collection.delete.assert_called_once_with(where={"source_id": "doc-1"})

    def test_a_delete_that_raised_reports_false(self):
        """The failure is still logged and still swallowed — callers that only
        want best effort are unchanged — but it is no longer indistinguishable
        from a delete that worked."""
        collection = MagicMock()
        collection.delete.side_effect = RuntimeError("chroma compaction in progress")
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            assert _manager().delete_kb_source("kb1", "doc-1") is False

    def test_a_collection_that_cannot_be_opened_reports_false(self):
        with patch.object(
            DocumentManager, "get_kb_collection", side_effect=RuntimeError("no client"),
        ):
            assert _manager().delete_kb_source("kb1", "doc-1") is False


class TestChromaAddBatching:
    """ChromaDB refuses a single ``add`` larger than its reported maximum and
    raises rather than writing what fits.

    Nothing enforced that ceiling, so ingestion worked until a source was long
    enough and then failed outright — about 4.4 M characters at the default
    1,000/200 chunking. No cap let a URL source reach that until
    ``kb_url_max_chars`` raised the fetch limit to 5 M, which is why this is a
    prerequisite for that change and not a tidy-up alongside it.
    """

    def _manager_with_batch(self, max_batch: int) -> DocumentManager:
        mgr = _manager()
        mgr.chunk_size = 1000
        mgr.chunk_overlap = 200
        mgr.client = MagicMock()
        mgr.client.get_max_batch_size.return_value = max_batch
        return mgr

    def test_a_source_over_the_limit_is_added_in_several_calls(self):
        mgr = self._manager_with_batch(100)
        collection = MagicMock()
        # 250 chunks at a 100-item ceiling — three calls, none over the limit.
        text = "word " * 50_000

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            count = mgr.add_to_kb("kb1", "src-1", "Long Reg", text)

        assert collection.add.call_count >= 3
        assert all(
            len(c.kwargs["ids"]) <= 100 for c in collection.add.call_args_list
        )
        # Every chunk reached Chroma exactly once, and the count is honest.
        added = [i for c in collection.add.call_args_list for i in c.kwargs["ids"]]
        assert len(added) == count == len(set(added))

    def test_batches_keep_ids_documents_and_metadata_aligned(self):
        """A slicing bug here would attach the wrong text to the wrong id and
        be invisible until retrieval cited the wrong span."""
        mgr = self._manager_with_batch(10)
        collection = MagicMock()

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            mgr.add_to_kb("kb1", "src-1", "Long Reg", "word " * 10_000)

        for call in collection.add.call_args_list:
            ids, docs, metas = call.kwargs["ids"], call.kwargs["documents"], call.kwargs["metadatas"]
            assert len(ids) == len(docs) == len(metas)
            for chunk_id, meta in zip(ids, metas):
                assert chunk_id == f"src-1_chunk_{meta['chunk_index']}"

    def test_a_source_under_the_limit_is_still_one_call(self):
        mgr = self._manager_with_batch(5461)
        collection = MagicMock()

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            mgr.add_to_kb("kb1", "src-1", "Short", "word " * 200)

        assert collection.add.call_count == 1

    def test_a_client_that_cannot_report_a_maximum_gets_a_bounded_one(self):
        """Falling back to an unbounded write would reintroduce the failure on
        exactly the clients least able to survive it."""
        mgr = self._manager_with_batch(0)
        mgr.client.get_max_batch_size.side_effect = RuntimeError("no such method")

        assert mgr._max_add_batch() == DocumentManager._FALLBACK_MAX_ADD_BATCH

        mgr.client.get_max_batch_size.side_effect = None
        mgr.client.get_max_batch_size.return_value = 0
        assert mgr._max_add_batch() == DocumentManager._FALLBACK_MAX_ADD_BATCH
