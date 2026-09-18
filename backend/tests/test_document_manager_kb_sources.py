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
