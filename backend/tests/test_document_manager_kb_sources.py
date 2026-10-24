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

import pytest

from app.services.document_manager import KB_REVISION_KEY, DocumentManager


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


def _writer() -> DocumentManager:
    """A DocumentManager that chunks and writes, into a patched collection."""
    mgr = _manager()
    mgr.chunk_size = 1000
    mgr.chunk_overlap = 200
    mgr.client = MagicMock()
    mgr.client.get_max_batch_size.return_value = 1000
    return mgr


class _FakeCollection:
    """Just enough of a Chroma collection to watch chunks come and go."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.fail_add_after: int | None = None
        self.fail_delete = False
        self.metadata: dict | None = None
        self.fail_modify = False

    def add(self, ids, documents, metadatas):
        for i, doc, meta in zip(ids, documents, metadatas):
            if self.fail_add_after is not None and len(self.rows) >= self.fail_add_after:
                raise RuntimeError("embedding service went away")
            self.rows.setdefault(i, {"document": doc, "metadata": meta})

    def get(self, where, include=None):
        ids = [i for i, r in self.rows.items() if r["metadata"]["source_id"] == where["source_id"]]
        return {"ids": ids, "metadatas": [self.rows[i]["metadata"] for i in ids]}

    def update(self, ids, metadatas):
        for i, meta in zip(ids, metadatas):
            self.rows[i]["metadata"] = meta

    def delete(self, ids=None, where=None):
        if self.fail_delete:
            raise RuntimeError("chroma compaction in progress")
        if where is not None:
            ids = [i for i, r in self.rows.items() if r["metadata"]["source_id"] == where["source_id"]]
        for i in list(ids or []):
            self.rows.pop(i, None)

    def modify(self, metadata):
        if self.fail_modify:
            raise RuntimeError("chroma went away")
        # Chroma replaces a collection's metadata; it does not merge.
        self.metadata = dict(metadata)

    @property
    def revision(self):
        return (self.metadata or {}).get(KB_REVISION_KEY)

    def text_of(self, source_id):
        return [r["document"] for r in self.rows.values() if r["metadata"]["source_id"] == source_id]


class TestReplaceKbSource:
    """A refresh used to delete a source's chunks and then embed the new text.

    The source had no chunks for the length of the embed, a failed embed left
    it with none, and a delete that failed quietly let ``add`` skip every
    deterministic id — the old text stayed indexed under a source marked
    refreshed (#726 follow-up).
    """

    def _manager(self) -> DocumentManager:
        return _writer()

    def _seeded(self, mgr):
        collection = _FakeCollection()
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            mgr.add_to_kb("kb1", "src-1", "APM 45.14", "old policy text. " * 200)
            mgr.add_to_kb("kb1", "src-2", "Other", "a neighbouring source. " * 50)
        return collection

    def test_new_text_replaces_old_and_leaves_other_sources_alone(self):
        mgr = self._manager()
        collection = self._seeded(mgr)
        other = collection.text_of("src-2")

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            count = mgr.replace_kb_source("kb1", "src-1", "APM 45.14", "new policy text. " * 300)

        texts = collection.text_of("src-1")
        assert count == len(texts) > 0
        assert all("new policy" in t for t in texts)
        assert collection.text_of("src-2") == other

    def test_a_failed_embed_keeps_the_old_chunks_and_none_of_the_new(self):
        mgr = self._manager()
        collection = self._seeded(mgr)
        before = sorted(collection.text_of("src-1"))
        collection.fail_add_after = len(collection.rows) + 1  # one new chunk lands, then failure

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            with pytest.raises(RuntimeError):
                mgr.replace_kb_source("kb1", "src-1", "APM 45.14", "new policy text. " * 300)

        assert sorted(collection.text_of("src-1")) == before

    def test_a_failed_delete_of_the_old_chunks_raises_instead_of_reporting_success(self):
        mgr = self._manager()
        collection = self._seeded(mgr)
        collection.fail_delete = True

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            with pytest.raises(RuntimeError):
                mgr.replace_kb_source("kb1", "src-1", "APM 45.14", "new policy text. " * 300)

    def test_a_second_refresh_replaces_the_first(self):
        mgr = self._manager()
        collection = self._seeded(mgr)

        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            mgr.replace_kb_source("kb1", "src-1", "APM 45.14", "second version. " * 300)
            mgr.replace_kb_source("kb1", "src-1", "APM 45.14", "third version. " * 300)

        assert all("third version" in t for t in collection.text_of("src-1"))


class TestKbRevision:
    """Every write to a KB's chunks stamps a new revision on its collection.
    A process's cached index over the chunks (kb_retrieval.index_for) checks
    it, so a rewrite is noticed even when it keeps the chunk count — a
    re-chunk — or the chunk ids too — a refresh by delete then add."""

    def _write(self, mgr, collection, *calls):
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            for name, *args in calls:
                getattr(mgr, name)("kb1", *args)

    def test_a_refresh_under_the_same_ids_gets_a_new_revision(self):
        mgr, collection = _writer(), _FakeCollection()
        self._write(mgr, collection, ("add_to_kb", "src-1", "APM 45.14", "policy text. " * 200))
        first, ids = collection.revision, set(collection.rows)
        assert first

        self._write(mgr, collection, ("delete_kb_source", "src-1"),
                    ("add_to_kb", "src-1", "APM 45.14", "policy tent. " * 200))
        assert set(collection.rows) == ids
        assert collection.revision not in (None, first)

    @pytest.mark.parametrize("call", [
        ("replace_kb_source", "src-1", "APM 45.14", "new policy text. " * 200),
        ("rename_kb_source", "src-1", "APM 45.14 (renamed)"),
        ("delete_kb_source", "src-1"),
    ], ids=lambda c: c[0])
    def test_each_write_gets_a_new_revision(self, call):
        mgr, collection = _writer(), _FakeCollection()
        self._write(mgr, collection, ("add_to_kb", "src-1", "APM 45.14", "old policy text. " * 200))
        before = collection.revision
        self._write(mgr, collection, call)
        assert collection.revision not in (None, before)

    def test_the_rest_of_the_collection_metadata_is_kept(self):
        mgr, collection = _writer(), _FakeCollection()
        collection.metadata = {"owner": "ops"}
        self._write(mgr, collection, ("add_to_kb", "src-1", "Name", "text. " * 100))
        assert collection.metadata["owner"] == "ops" and collection.revision

    def test_a_write_that_failed_part_way_still_gets_one(self):
        """The chunks it wrote before failing are in the store."""
        mgr, collection = _writer(), _FakeCollection()
        self._write(mgr, collection, ("add_to_kb", "src-1", "APM 45.14", "old policy text. " * 200))
        before = collection.revision
        collection.fail_add_after = len(collection.rows) + 1
        with pytest.raises(RuntimeError):
            self._write(mgr, collection, ("replace_kb_source", "src-1", "APM 45.14", "new policy text. " * 300))
        assert collection.revision not in (None, before)

    def test_a_stamp_that_fails_does_not_fail_the_write(self):
        mgr, collection = _writer(), _FakeCollection()
        collection.fail_modify = True
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            count = mgr.add_to_kb("kb1", "src-1", "Name", "text. " * 100)
            assert mgr.delete_kb_source("kb1", "src-1") is True
        assert count > 0 and collection.revision is None


class TestGetKbAllChunks:
    """What precise retrieval builds its per-base index from: every chunk,
    or nothing when the base is missing, unreadable, or too big to index."""

    def _with(self, collection) -> DocumentManager:
        mgr = _manager()
        mgr.get_kb_collection_readonly = MagicMock(return_value=collection)
        return mgr

    def test_returns_every_chunk_in_query_shape(self):
        coll = MagicMock()
        coll.count.return_value = 2
        coll.get.return_value = {
            "ids": ["s_chunk_0", "s_chunk_1"],
            "documents": ["first", "second"],
            "metadatas": [{"source_id": "s"}, {"source_id": "s"}],
        }
        chunks = self._with(coll).get_kb_all_chunks("kb")
        assert [c["chunk_id"] for c in chunks] == ["s_chunk_0", "s_chunk_1"]
        assert chunks[1] == {"content": "second", "metadata": {"source_id": "s"},
                             "chunk_id": "s_chunk_1", "score": None, "similarity": None}
        coll.get.assert_called_once_with(include=["documents", "metadatas"])

    def test_a_base_never_ingested_has_none(self):
        assert self._with(None).get_kb_all_chunks("kb") == []

    def test_a_base_over_the_limit_is_not_read(self):
        coll = MagicMock()
        coll.count.return_value = 10
        assert self._with(coll).get_kb_all_chunks("kb", limit=5) == []
        coll.get.assert_not_called()

    def test_a_failed_read_is_empty_not_an_error(self):
        coll = MagicMock()
        coll.count.return_value = 1
        coll.get.side_effect = RuntimeError("chroma down")
        assert self._with(coll).get_kb_all_chunks("kb") == []
