"""The whole page-citation chain, over a real PDF, end to end.

Every other test in this area covers one seam. This one runs a real file
through the production path — extraction, marker resolution, chunk metadata,
citation rendering and the model-facing note — because a chain of individually
correct links still tells the user nothing if they aren't joined.

The document deliberately has uneven page density (a dense page followed by
sparse ones), which is what defeats interpolation: spreading a page count
evenly across the text assumes uniform density, and real proposals are not
uniform. Measured on the project's benchmark corpus, an interpolated page on a
68-page proposal is exactly right ~4.5% of the time and off by a median of 6
pages, so the distinction this chain carries is not cosmetic.

See #603.
"""

from unittest.mock import patch

import pytest

import app.services.document_readers as dr
from app.services.chat_service import annotate_pages, build_document_segments
from app.services.document_manager import DocumentManager
from app.services.page_locator import locator_for_meta


class _FakeCollection:
    def __init__(self) -> None:
        self.metadatas: list[dict] = []

    def add(self, ids, documents, metadatas):  # noqa: ARG002 - mirrors Chroma
        self.metadatas = metadatas


class _Doc:
    """Stands in for the SmartDocument that document chat loads."""

    def __init__(self, text: str, markers: list[dict]) -> None:
        self.uuid, self.title = "u1", "Proposal.pdf"
        self.raw_text, self.text_markers = text, markers
        self.task_status = "complete"
        self.extraction_nonletter_ratio = None


@pytest.fixture
def uneven_pdf(tmp_path) -> str:
    """A real 6-page PDF whose first page holds most of the text."""
    import pymupdf

    doc = pymupdf.open()
    for page_no in range(6):
        page = doc.new_page()
        lines = 30 if page_no == 0 else 3
        y = 60
        for i in range(lines):
            page.insert_text((60, y), f"Page {page_no + 1} line {i} of proposal body text.")
            y += 12
    path = tmp_path / "uneven.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def _chunk_metadata(text: str, markers: list[dict]) -> list[dict]:
    dm = object.__new__(DocumentManager)
    dm.chunk_size, dm.chunk_overlap = 500, 100
    collection = _FakeCollection()
    with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
        dm.add_to_kb("kb1", "src1", "Proposal.pdf", text, markers)
    return collection.metadatas


def _page_at(offset: int, markers: list[dict]) -> int | None:
    page = None
    for m in markers:
        if m.get("char_offset", 0) > offset:
            break
        if m.get("kind") == "page":
            page = m.get("value")
    return page


class TestMeasuredPagesEndToEnd:
    """A digitally-native PDF: real boundaries, cited without a hedge."""

    def test_real_pdf_flows_through_to_an_exact_citation(self, uneven_pdf):
        # No OCR service in tests. Left unpatched, the real client spends ~30s
        # in connection timeouts before degrading to PyMuPDF; returning "" is
        # the same branch, reached immediately.
        with patch.object(dr, "ocr_extract_text_from_pdf", return_value=""):
            text, markers = dr.extract_text_with_markers(uneven_pdf, "pdf")
        pages = [m for m in markers if m.get("kind") == "page"]

        assert len(pages) >= 2
        assert not any(m.get("approximate") for m in pages)

        # ... into the model's context
        annotated = annotate_pages(text, markers)
        assert "[p. 1]" in annotated
        assert "[p. ~" not in annotated

        # ... into chunk metadata, which every citation renderer reads
        metas = _chunk_metadata(text, markers)
        assert metas
        assert all("page_approximate" not in m for m in metas)

        # ... and out to the label a user sees
        sample = next(m for m in metas if "page" in m)
        assert locator_for_meta(sample) == f"p. {sample['page']}"

        # ... with a note that does not hedge
        segments, _, _, _ = build_document_segments([_Doc(text, markers)])
        assert "approximate" not in segments[0].text.lower()


class TestInterpolatedPagesEndToEnd:
    """A scanned PDF: OCR returns flat text, so boundaries are estimated.

    Only the OCR network call is simulated — it is replaced with the document's
    own text, which is the contract the endpoint honours (flat text, no page
    structure). Everything downstream is production code.
    """

    def test_real_pdf_flows_through_to_a_hedged_citation(self, uneven_pdf):
        true_text, true_markers = dr._pymupdf_extract_with_pages(uneven_pdf)

        with patch.object(dr, "ocr_extract_text_from_pdf", return_value=true_text):
            text, markers = dr.extract_text_with_markers(uneven_pdf, "pdf")

        pages = [m for m in markers if m.get("kind") == "page"]
        assert pages, "OCR path produced no page markers"
        assert all(m.get("approximate") is True for m in pages)

        annotated = annotate_pages(text, markers)
        assert "[p. ~1]" in annotated

        metas = _chunk_metadata(text, markers)
        assert metas
        assert all(m["page_approximate"] is True for m in metas if "page" in m)

        sample = next(m for m in metas if "page" in m)
        assert locator_for_meta(sample) == f"p. ~{sample['page']}"

        segments, _, _, _ = build_document_segments([_Doc(text, markers)])
        assert "approximate" in segments[0].text.lower()

    def test_the_hedge_is_warranted_not_cosmetic(self, uneven_pdf):
        """The estimate genuinely disagrees with the truth on this document.

        If interpolation happened to be exact, hedging would be noise. It
        isn't: uneven page density means the evenly-spread estimate lands on
        the wrong page for real offsets.
        """
        true_text, true_markers = dr._pymupdf_extract_with_pages(uneven_pdf)
        estimated = dr._interpolate_page_markers(true_text, len(true_markers))

        step = max(1, len(true_text) // 100)
        disagreements = sum(
            1
            for off in range(0, len(true_text), step)
            if _page_at(off, true_markers) != _page_at(off, estimated)
        )

        assert disagreements > 0, (
            "interpolation matched the real boundaries everywhere; this fixture "
            "no longer exercises the case the approximate flag exists for"
        )
