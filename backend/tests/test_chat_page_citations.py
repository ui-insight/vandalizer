"""Document chat must carry page structure into the model's context.

Page markers are already produced at ingest and persisted on the document
(``SmartDocument.text_markers``), and both extraction sources and KB chat
already resolve them. Document chat was the one consumer that dropped them: it
sent ``raw_text`` flat, so the model had no way to say which page a fact came
from — while KB chat, on the same screen, renders "(p. 12)".

See #603.
"""

from types import SimpleNamespace

from app.services.chat_service import annotate_pages, build_document_segments


def _markers(*offsets: int) -> list[dict]:
    return [
        {"char_offset": off, "kind": "page", "value": i + 1}
        for i, off in enumerate(offsets)
    ]


class TestAnnotatePages:
    def test_inserts_a_marker_at_each_page_boundary(self):
        # Irregular page lengths on purpose: uniform spacing is the
        # interpolator's signature and would (correctly) hedge these as ~.
        text = "AAAABBBBBCCC"
        out = annotate_pages(text, _markers(0, 4, 9))
        assert out == "[p. 1]\nAAAA[p. 2]\nBBBBB[p. 3]\nCCC"

    def test_text_content_is_preserved_exactly(self):
        """Stripping the inserted markers must give back the original text —
        the model has to see the document, not a mangled copy of it."""
        import re

        text = "The indirect rate is 54.5% of MTDC."
        out = annotate_pages(text, _markers(0, 20))
        assert re.sub(r"\[p\. \d+\]\n", "", out) == text

    def test_no_markers_returns_text_unchanged(self):
        """Non-PDF formats and documents ingested before markers existed."""
        text = "no page structure here"
        assert annotate_pages(text, []) == text
        assert annotate_pages(text, None) == text

    def test_ignores_non_page_markers(self):
        """XLSX markers describe sheets, not pages — they must not be rendered
        as page numbers."""
        markers = [{"char_offset": 0, "kind": "sheet", "value": "Budget"}]
        assert annotate_pages("abc", markers) == "abc"

    def test_offsets_past_end_of_text_are_dropped(self):
        """raw_text can be re-saved shorter than when markers were computed."""
        out = annotate_pages("short", _markers(0, 999))
        assert out == "[p. 1]\nshort"

    def test_out_of_order_markers_are_sorted(self):
        """Markers are ordered by char_offset, whatever order they arrive in."""
        page1_then_2 = _markers(0, 4)          # p1 @ 0, p2 @ 4
        out = annotate_pages("AAAABBBB", list(reversed(page1_then_2)))
        assert out == "[p. 1]\nAAAA[p. 2]\nBBBB"

    def test_empty_text_returns_empty(self):
        assert annotate_pages("", _markers(0)) == ""

    def test_marker_without_integer_page_is_skipped(self):
        markers = [{"char_offset": 0, "kind": "page", "value": None}]
        assert annotate_pages("abc", markers) == "abc"

    def test_approximate_markers_are_rendered_as_approximate(self):
        """Scanned PDFs go through OCR, whose page boundaries are evenly-spaced
        estimates rather than real ones (``_interpolate_page_markers``). Marking
        them ``[p. 2]`` would state a position the data cannot support."""
        markers = [dict(m, approximate=True) for m in _markers(0, 4)]
        out = annotate_pages("AAAABBBB", markers)
        assert out == "[p. ~1]\nAAAA[p. ~2]\nBBBB"

    def test_exact_markers_carry_no_approximation_hint(self):
        out = annotate_pages("AAAABBBB", _markers(0, 4))
        assert "~" not in out


def _doc(**kw):
    base = dict(uuid="u1", title="Proposal.pdf", raw_text="AAAABBBB",
                text_markers=None, task_status="complete",
                extraction_nonletter_ratio=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestBuildDocumentSegments:
    """The helper being correct proves nothing if chat doesn't call it — this
    is the wiring that actually puts pages in front of the model."""

    def test_paginated_document_reaches_the_model_with_pages(self):
        doc = _doc(text_markers=_markers(0, 4))
        segments, _, _, _ = build_document_segments([doc])

        assert len(segments) == 1
        assert "[p. 1]" in segments[0].text
        assert "[p. 2]" in segments[0].text

    def test_paginated_document_explains_the_markers(self):
        doc = _doc(text_markers=_markers(0, 4))
        segments, _, _, _ = build_document_segments([doc])
        assert "marks the start of page N" in segments[0].text

    def test_unpaginated_document_gets_no_page_note(self):
        """A DOCX has no page markers; promising page citations would invite
        the model to invent them."""
        segments, _, _, _ = build_document_segments([_doc(text_markers=None)])
        assert "marks the start of page N" not in segments[0].text
        assert "[p. " not in segments[0].text
        assert "AAAABBBB" in segments[0].text

    def test_document_without_text_is_reported_not_sent(self):
        segments, skipped, errored, _ = build_document_segments(
            [_doc(raw_text="", task_status="extracting")]
        )
        assert segments == []
        assert skipped == ["Proposal.pdf"]
        assert errored == []

    def test_errored_document_is_reported_separately(self):
        segments, skipped, errored, _ = build_document_segments(
            [_doc(raw_text="", task_status="error")]
        )
        assert segments == []
        assert errored == ["Proposal.pdf"]
        assert skipped == []

    def test_ocr_document_tells_the_model_its_pages_are_estimates(self):
        """Otherwise the model cites an estimated boundary as fact — the same
        confident-but-unsupported answer this project filed #609 about."""
        markers = [dict(m, approximate=True) for m in _markers(0, 4)]
        segments, _, _, _ = build_document_segments([_doc(text_markers=markers)])
        assert "approximate" in segments[0].text.lower()

    def test_exact_document_is_not_described_as_approximate(self):
        segments, _, _, _ = build_document_segments([_doc(text_markers=_markers(0, 4))])
        assert "approximate" not in segments[0].text.lower()

    def test_garbled_document_is_still_sent_but_reported(self):
        """#621 warns about garbled text layers. The refactor must keep that
        signal — a document with unusable text still reaches the model, but the
        caller has to be able to tell the user the answer is unreliable."""
        doc = _doc(extraction_nonletter_ratio=0.6)
        segments, _, _, low_quality = build_document_segments([doc])

        assert len(segments) == 1
        assert low_quality == ["Proposal.pdf"]

    def test_clean_document_is_not_reported_as_low_quality(self):
        _, _, _, low_quality = build_document_segments([_doc()])
        assert low_quality == []

    def test_one_segment_per_document_for_independent_trimming(self):
        docs = [_doc(uuid="a", title="A.pdf"), _doc(uuid="b", title="B.pdf")]
        segments, _, _, _ = build_document_segments(docs)
        assert [s.label for s in segments] == ["doc:A.pdf", "doc:B.pdf"]
