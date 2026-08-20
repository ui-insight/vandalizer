"""The `approximate` flag has to survive all the way into chunk metadata.

`page_locator.location_meta` being correct proves nothing on its own: KB chat,
workflow citations and search sets all read the page off the *chunk metadata*
written at ingest, not off the marker. If the flag stops at the helper, every
one of those still renders an interpolated page as though it were measured.

See #603.
"""

from unittest.mock import patch

from app.services.document_manager import DocumentManager


class _FakeCollection:
    """Captures what would have been written to Chroma."""

    def __init__(self) -> None:
        self.metadatas: list[dict] = []

    def add(self, ids, documents, metadatas):  # noqa: ARG002 - mirrors Chroma's API
        self.metadatas = metadatas


def _manager() -> DocumentManager:
    """A DocumentManager without a Chroma client — only chunking is exercised."""
    dm = object.__new__(DocumentManager)
    dm.chunk_size = 100
    dm.chunk_overlap = 0
    return dm


def _markers(approximate: bool) -> list[dict]:
    marker = {"char_offset": 0, "kind": "page", "value": 1}
    if approximate:
        marker["approximate"] = True
    return [marker]


class TestKbChunkMetadata:
    def test_interpolated_page_reaches_chunk_metadata(self):
        dm, collection = _manager(), _FakeCollection()
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            dm.add_to_kb("kb1", "src1", "Scanned.pdf", "x" * 250, _markers(True))

        assert collection.metadatas, "no chunks were written"
        assert all(m["page"] == 1 for m in collection.metadatas)
        assert all(m["page_approximate"] is True for m in collection.metadatas)

    def test_measured_page_writes_no_flag(self):
        """Chunks for measured pages keep exactly the shape they had before,
        so existing collections stay comparable without a re-index."""
        dm, collection = _manager(), _FakeCollection()
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            dm.add_to_kb("kb1", "src1", "Native.pdf", "x" * 250, _markers(False))

        assert collection.metadatas
        assert all(m["page"] == 1 for m in collection.metadatas)
        assert all("page_approximate" not in m for m in collection.metadatas)

    def test_sheet_sources_get_no_page_at_all(self):
        dm, collection = _manager(), _FakeCollection()
        markers = [{"char_offset": 0, "kind": "sheet", "value": "Budget"}]
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            dm.add_to_kb("kb1", "src1", "Budget.xlsx", "x" * 250, markers)

        assert collection.metadatas
        assert all(m.get("sheet") == "Budget" for m in collection.metadatas)
        assert all("page" not in m and "page_approximate" not in m
                   for m in collection.metadatas)


class TestUserDocumentChunkMetadata:
    """The per-user document collection uses the same helper; document chat's
    retrieval path reads it, so it must hedge identically."""

    def test_interpolated_page_reaches_chunk_metadata(self):
        dm, collection = _manager(), _FakeCollection()
        with patch.object(DocumentManager, "get_user_collection", return_value=collection):
            dm.add_document("user1", "/tmp/scanned.pdf", "Scanned.pdf", "doc1",
                            "x" * 250, _markers(True))

        assert collection.metadatas
        assert all(m["page_approximate"] is True for m in collection.metadatas)
