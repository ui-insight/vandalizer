"""Attached-document answers must carry inspectable source chips.

The product promises sources are always inspectable, but that held only on the
KB and web paths: an answer about an attached document was told to write
"p. 3" inline, and that string is inert text — nothing to click, nothing to
verify. ``derive_document_citations`` turns the pages the model actually cited
into the same chip the KB path emits.

Attribution has to be unambiguous to be honest, which is what most of these
tests pin down: a chip pointing at the wrong document is worse than no chip.
"""

from types import SimpleNamespace

from app.services.chat_service import derive_document_citations

_PAGE_ONE = "Budget narrative for the proposal. "
_PAGE_TWO = "Letters of commitment are due Oct 5, 2026."


def _doc(*, uuid: str = "doc-1", approximate: bool = False, marked: bool = True):
    raw = _PAGE_ONE + _PAGE_TWO
    markers = None
    if marked:
        markers = [
            {"kind": "page", "value": 1, "char_offset": 0},
            {
                "kind": "page",
                "value": 2,
                "char_offset": len(_PAGE_ONE),
                "approximate": approximate,
            },
        ]
    return SimpleNamespace(
        uuid=uuid, title="Proposal.pdf", raw_text=raw, text_markers=markers,
    )


class TestDerivedCitations:
    def test_a_cited_page_becomes_a_clickable_chip(self):
        cites = derive_document_citations("The deadline is Oct 5 (p. 2).", [_doc()])
        assert len(cites) == 1
        assert cites[0]["document_uuid"] == "doc-1"
        assert cites[0]["page"] == 2
        # The preview anchors the viewer on the passage, not the page top.
        assert "Letters of commitment" in cites[0]["content_preview"]

    def test_page_pp_and_page_n_forms_are_all_recognized(self):
        cites = derive_document_citations("See page 1 and pp. 2.", [_doc()])
        assert [c["page"] for c in cites] == [1, 2]

    def test_repeat_references_produce_one_chip(self):
        cites = derive_document_citations("p. 2 ... again p. 2 ... p.2", [_doc()])
        assert len(cites) == 1

    def test_an_interpolated_page_keeps_its_hedge(self):
        """The chip reads "p. ~2"; dropping the flag would assert measured
        precision the OCR pipeline never had."""
        cites = derive_document_citations("around p. ~2", [_doc(approximate=True)])
        assert cites[0]["page_approximate"] is True

    def test_two_marked_documents_produce_nothing(self):
        """"p. 3" does not say whose page 3."""
        docs = [_doc(uuid="a"), _doc(uuid="b")]
        assert derive_document_citations("see p. 2", docs) == []

    def test_one_marked_document_alongside_an_unmarked_one_still_resolves(self):
        docs = [_doc(uuid="a"), _doc(uuid="b", marked=False)]
        cites = derive_document_citations("see p. 2", docs)
        assert len(cites) == 1
        assert cites[0]["document_uuid"] == "a"

    def test_a_document_without_page_markers_produces_nothing(self):
        assert derive_document_citations("see p. 2", [_doc(marked=False)]) == []

    def test_a_page_outside_the_document_is_ignored(self):
        """A hallucinated page number must not mint a chip that opens nothing."""
        assert derive_document_citations("see p. 9", [_doc()]) == []

    def test_no_page_references_produce_nothing(self):
        assert derive_document_citations("No citation here.", [_doc()]) == []

    def test_no_documents_produce_nothing(self):
        assert derive_document_citations("see p. 2", []) == []
