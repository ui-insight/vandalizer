"""A list compiled from knowledge-base passages keeps each item in its section.

Support ticket: with an NIH award letter selected, chat was asked for the full
NIH prior-approval list. It searched the NIH Grants Policy Statement and
returned a table that credited 8.1.1.5 (direct charging administrative and
clerical salaries) to Exhibit 7, gave the equipment threshold as "a GPS
threshold" though the passage said $25,000, left out the Exhibit 7 row for
8.1.2.17, and listed 40 source references, repeats and unrelated passages
included, under a search card that said 8 passages.

These run against the bundled chapter the ticket's passages came from, cut the
way the knowledge base cuts it.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat_service import _mark_used_citations
from app.services.document_manager import CHUNK_OVERLAP, CHUNK_SIZE, _split_text_with_offsets
from app.services.kb_answer_grounding import used_snippet_refs
from app.services.kb_section_context import SectionIndex
from tests.test_agentic_kb_page_hedging import _result, _search

CHAPTER_8 = (
    Path(__file__).resolve().parents[1]
    / "seeds/knowledge_bases/content/nih-gps-fy2026-08.txt"
).read_text()
CHUNKS = [c for c, _ in _split_text_with_offsets(CHAPTER_8, CHUNK_SIZE, CHUNK_OVERLAP)]
NAME = "NIH Grants Policy Statement (FY 2026 revision) — Chapter 8: Administrative Requirements"

EXHIBIT_7 = "Exhibit 7. Summary of Actions Requiring NIH Prior Approval"


def _chunk(containing: str) -> str:
    """The first passage holding *containing*, as the knowledge base stores it."""
    return next(c for c in CHUNKS if containing in c)


@pytest.fixture(scope="module")
def index() -> SectionIndex:
    return SectionIndex(CHAPTER_8)


class TestSectionOfAPassage:
    def test_a_slice_from_the_middle_of_a_section_names_that_section(self, index):
        # The equipment threshold is the last bullet of 8.1.2.5; its passage
        # starts after a page break and never names the section.
        passage = _chunk("Purchase of a unit of equipment exceeding $25,000")
        assert "8.1.2.5" not in passage
        assert index.section_for(passage) == (
            "8.1.2 Prior Approval Requirements > 8.1.2.5 Change in Scope"
        )

    def test_a_standard_term_is_not_placed_in_the_prior_approval_exhibit(self, index):
        passage = _chunk("Administrative or clerical services are integral")
        section = index.section_for(passage)
        assert section is not None
        assert section.startswith("8.1.1 NIH Standard Terms of Award > 8.1.1.")
        assert "Exhibit" not in section

    def test_the_continuation_of_a_table_names_the_table(self, index):
        # The row for 8.1.2.17 is on the exhibit's second page.
        passage = _chunk("(8.1.2.17)\nAll instances.")
        assert EXHIBIT_7 not in passage
        assert index.section_for(passage) == (
            f"8.1 CHANGES IN PROJECT AND BUDGET > 8.1.2 Prior Approval Requirements > {EXHIBIT_7}"
        )

    def test_an_exhibit_ends_at_the_next_numbered_heading(self, index):
        passage = _chunk("Capital expenditures for land or buildings require NIH prior approval")
        assert "Exhibit" not in (index.section_for(passage) or "")

    def test_nearly_every_passage_of_the_chapter_gets_a_section(self, index):
        unlabelled = [c for c in CHUNKS if index.section_for(c) is None]
        assert len(unlabelled) <= 1  # only the text before the first heading

    @pytest.mark.parametrize("line", [
        "75.100. Pass-through entities may, but are not required, to negotiate a rate with one",
        "8.1.2.5 Change in Scope) for details about what the request must hold.",
        "7. Fixed Rates for the Life of the Sponsored Agreement.",
    ])
    def test_a_wrapped_sentence_is_not_a_heading(self, line):
        text = f"1.0 Opening Part\n1.2 Other Heading\nx\n1.1 Real Heading\nBody text of the real section goes on for a while here.\n{line}\nMore body text that the passage is made of, long enough to find."
        assert SectionIndex(text).section_for("More body text that the passage is made of") == "1.1 Real Heading"

    def test_ecfr_section_signs_are_headings(self):
        text = (
            "Subpart D—Post Federal Award Requirements\n"
            "§ 200.308 Revision of budget and program plans.\n"
            "(a) The approved budget for the Federal award summarizes the financial aspects.\n"
        )
        assert SectionIndex(text).section_for("(a) The approved budget for the Federal award") == (
            "§ 200.308 Revision of budget and program plans."
        )

    @pytest.mark.parametrize("line", [
        "1.5 FTE Research Assistant", "10.5 Million Dollars Awarded", "192.168.1.1 Server Address",
    ])
    def test_a_lone_numbered_line_in_a_document_without_numbered_sections_is_not_a_heading(self, line):
        text = f"Budget notes.\n{line}\nBody text of the budget that is long enough to be found in the source."
        assert SectionIndex(text).section_for("Body text of the budget that is long enough") is None

    def test_a_passage_found_under_two_sections_gets_no_label(self):
        boilerplate = "Requests must be made in writing to the grants management officer before the change."
        text = (f"1.1 Equipment Purchases\n{boilerplate}\n1.2 Travel Changes\n{boilerplate}\n"
                "1.3 Other Changes\nNothing else needs approval under this policy at all.\n")
        index = SectionIndex(text)
        assert index.section_for(boilerplate) is None
        assert index.section_for("Nothing else needs approval under this policy at all.") == "1.3 Other Changes"

    def test_ecfr_supplements_and_reserved_sections_end_the_section_before_them(self):
        text = ("§ 774.1 Introduction.\nThe Commerce Control List is in Supplement No. 1 to this part.\n"
                "§ 774.2 [Reserved]\n"
                "Supplement No. 1 to Part 774—The Commerce Control List\n"
                "1E001 Technology according to the General Technology Note for the development of items.\n")
        assert SectionIndex(text).section_for("1E001 Technology according to the General Technology Note") == (
            "Supplement No. 1 to Part 774—The Commerce Control List"
        )

    def test_a_passage_far_past_the_last_heading_found_gets_no_label(self):
        filler = "An entry in a long list that has headings in a style not recognised here.\n" * 800
        text = f"§ 744.22 Restrictions on certain end uses.\nRule text.\n{filler}Zurmat Group of Companies, House No. 319, Kabul, listed here.\n"
        index = SectionIndex(text)
        assert index.section_for("Rule text.\nAn entry in a long list") == "§ 744.22 Restrictions on certain end uses."
        assert index.section_for("Zurmat Group of Companies, House No. 319, Kabul, listed here.") is None

    def test_no_bundled_ecfr_passage_is_labelled_with_a_section_a_supplement_closed(self):
        content = Path(__file__).resolve().parents[1] / "seeds/knowledge_bases/content"
        for name in ("ecfr-title15-part774.txt", "ecfr-title15-part744.txt"):
            text = (content / name).read_text()
            index = SectionIndex(text)
            first_supplement = text.index("\nSupplement No. 1 to Part")
            for chunk, offset in _split_text_with_offsets(text, CHUNK_SIZE, CHUNK_OVERLAP):
                if offset > first_supplement + 5:
                    assert not (index.section_for(chunk) or "").startswith("§"), (name, offset)

    def test_a_source_without_headings_or_a_passage_not_in_it_has_no_section(self, index):
        assert SectionIndex("Plain prose with no headings at all.").section_for("Plain prose") is None
        assert index.section_for("This sentence is nowhere in chapter eight of the statement.") is None
        assert index.section_for("") is None


def _url_source(content: str = CHAPTER_8) -> SimpleNamespace:
    return SimpleNamespace(
        uuid="src-1", source_type="url", url="https://grants.nih.gov/policy-and-compliance/nihgps#ch8",
        source_reference=None, content=content, document_uuid=None,
    )


async def _search_on(ctx, results, sources=None):
    with patch("tests.test_agentic_kb_page_hedging._make_context", return_value=ctx), \
         patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(return_value={})):
        out, _ = await _search(results, sources=sources)
    return out


def _context():
    from tests.test_chat_tools import _make_context

    return _make_context()


class TestSearchResults:
    @pytest.mark.asyncio
    async def test_each_passage_carries_its_section(self):
        ctx = _context()
        out = await _search_on(ctx, [
            _result(_chunk("Purchase of a unit of equipment exceeding $25,000"), source_name=NAME),
        ], sources=[_url_source()])
        assert out[0]["section"].endswith("8.1.2.5 Change in Scope")
        assert "where the passage BEGINS" in out[0]["citation_note"]

    @pytest.mark.asyncio
    async def test_no_section_and_no_note_when_the_source_text_is_not_stored(self):
        ctx = _context()
        out = await _search_on(ctx, [_result("Travel is reimbursed at cost.")],
                               sources=[_url_source(content=None)])
        assert "section" not in out[0]
        assert "citation_note" not in out[0]

    @pytest.mark.asyncio
    async def test_a_passage_a_second_search_returns_again_is_one_source(self):
        ctx = _context()
        first = [_result("Carryover needs approval.", chunk_id="src-1_chunk_4"),
                 _result("Change in scope needs approval.", chunk_id="src-1_chunk_5")]
        await _search_on(ctx, first)
        shown = list(ctx.deps.citation_annotations.pop("call-1"))
        again = [_result("Change in scope needs approval.", chunk_id="src-1_chunk_5"),
                 _result("Pre-award costs over 90 days.", chunk_id="src-1_chunk_9")]
        out = await _search_on(ctx, again)
        shown += ctx.deps.citation_annotations.pop("call-1")

        # The model still gets both passages of the second search …
        assert len(out) == 2
        # … and the source list holds each chunk once, numbered in order.
        assert [c["chunk_id"] for c in shown] == ["src-1_chunk_4", "src-1_chunk_5", "src-1_chunk_9"]
        assert [c["ref"] for c in shown] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_a_search_returning_only_seen_passages_adds_no_sources(self):
        ctx = _context()
        await _search_on(ctx, [_result("Carryover needs approval.", chunk_id="k1")])
        ctx.deps.citation_annotations.clear()
        out = await _search_on(ctx, [_result("Carryover needs approval.", chunk_id="k1")])
        assert len(out) == 1
        assert ctx.deps.citation_annotations == {}


def _retrieved(passages: list[str], name: str = NAME, index: SectionIndex | None = None):
    """Citations and their texts, as a turn's searches leave them."""
    citations = [{"ref": i, "document_title": name, "page": None} for i, _ in enumerate(passages, 1)]
    texts = {
        i: f"{(index.section_for(p) if index else None) or ''}\n{p}"
        for i, p in enumerate(passages, 1)
    }
    return citations, texts


class TestWhichPassagesAnAnswerUsed:
    """A chapter is one web source with no pages: its name fits every passage."""

    @pytest.fixture
    def retrieved(self, index):
        passages = [
            _chunk("(8.1.2.17)\nAll instances."),                               # 1 Exhibit 7, 2nd page
            _chunk("Purchase of a unit of equipment exceeding $25,000"),        # 2 8.1.2.5
            _chunk("Capital expenditures for land or buildings require"),      # 3 8.1.2.3
            _chunk("Exhibit 9. Use and Applicability of Program Income"),       # 4 program income
            _chunk("Exhibit 10. Summary of Audit Requirements"),               # 5 audit
            _chunk("Exhibit 8. Extramural Invention Reporting"),               # 6 inventions
        ]
        return _retrieved(passages, index=index)

    def test_a_row_naming_its_section_uses_the_passages_of_that_section(self, retrieved):
        citations, texts = retrieved
        row = ("| Change in scope | Includes purchase of a unit of equipment exceeding "
               f"$25,000 | [Source: {NAME}, 8.1.2.5] |")
        assert used_snippet_refs(row, citations, texts) == [2]

    def test_a_row_without_a_section_number_uses_the_passages_sharing_its_words(self, retrieved):
        citations, texts = retrieved
        row = ("| Retention of research grant funds when a career development award "
               f"(CDA) is awarded | All instances | [Source: {NAME}] |")
        assert used_snippet_refs(row, citations, texts) == [1]

    def test_unrelated_passages_of_the_same_chapter_are_not_sources(self, retrieved):
        citations, texts = retrieved
        answer = (
            f"| Capital expenditures for land or buildings | All instances | [Source: {NAME}, 8.1.2.3] |\n"
            f"| Purchase of a unit of equipment exceeding $25,000 | Change in scope | [Source: {NAME}, 8.1.2.5] |\n"
            f"| Retention of research grant funds when CDA awarded | All instances | [Source: {NAME}, Exhibit 7] |\n"
        )
        used = _mark_used_citations(answer, citations, texts)
        assert used == [1, 2, 3]
        assert [c["used"] for c in citations] == [True, True, True, False, False, False]

    def test_a_source_list_after_the_answer_adds_nothing_unrelated(self, retrieved):
        citations, texts = retrieved
        answer = (
            f"Capital expenditures for land or buildings need prior approval [Source: {NAME}, 8.1.2.3].\n\n"
            f"Sources:\n- [Source: {NAME}]\n- [Source: {NAME}]\n"
        )
        assert used_snippet_refs(answer, citations, texts) == [3]

    def test_a_short_fact_after_a_long_paragraph_keeps_its_passage(self, index):
        carryover = _chunk("8.1.2.4 Carryover of Unobligated Balances")
        equipment = _chunk("Purchase of a unit of equipment exceeding $25,000")
        citations, texts = _retrieved(
            [equipment, carryover, _chunk("Exhibit 10. Summary of Audit Requirements"),
             _chunk("Exhibit 8. Extramural Invention Reporting")], index=index,
        )
        paragraph = " ".join(carryover.split()[20:110]).rstrip(".,;: ")
        answer = (f"{paragraph}. Separately, buying one item of equipment above $25,000 "
                  f"is a change in scope. [Source: {NAME}]")
        assert used_snippet_refs(answer, citations, texts) == [1, 2]

    def test_a_numbered_citation_ends_the_claim_before_it(self, retrieved):
        citations, texts = retrieved
        answer = (f"Audits are required of recipients that expend federal awards [S5]. "
                  f"Capital expenditures for land or buildings need approval [Source: {NAME}].")
        assert used_snippet_refs(answer, citations, texts) == [3, 5]

    def test_a_dollar_amount_is_not_read_as_a_section_number(self, retrieved):
        citations, texts = retrieved
        texts = {**texts, 4: texts[4] + "\nA fee of 1.250.00 applies."}
        row = f"| Capital expenditures for land or buildings cost $1.250.00 | [Source: {NAME}] |"
        assert 4 not in used_snippet_refs(row, citations, texts)

    def test_when_the_claim_cannot_tell_them_apart_all_stay_sources(self, retrieved):
        citations, texts = retrieved
        assert used_snippet_refs(f"[Source: {NAME}]", citations, texts) == [1, 2, 3, 4, 5, 6]

    def test_without_passage_text_a_name_still_counts_for_all_of_the_source(self, retrieved):
        # Pre-fetched snippets and turns from before the text was kept.
        citations, _ = retrieved
        row = f"| Change in scope | All instances | [Source: {NAME}, 8.1.2.5] |"
        assert used_snippet_refs(row, citations) == [1, 2, 3, 4, 5, 6]
        assert used_snippet_refs(row, citations, {2: "only one text known"}) == [1, 2, 3, 4, 5, 6]

    def test_a_named_page_still_decides_first(self):
        citations = [
            {"ref": 1, "document_title": "PAPPG.pdf", "page": 54},
            {"ref": 2, "document_title": "PAPPG.pdf", "page": 139},
        ]
        texts = {1: "No-cost extensions run up to 12 months.", 2: "Unrelated text about travel."}
        assert used_snippet_refs(
            "No-cost extensions run up to 12 months [Source: PAPPG.pdf, p. 139].", citations, texts,
        ) == [2]

    def test_numbered_citations_are_untouched(self, retrieved):
        citations, texts = retrieved
        assert used_snippet_refs("Audits are required [S5].", citations, texts) == [5]


def test_the_prompt_asks_for_sections_exact_figures_and_one_row_per_item():
    from app.services import llm_service

    prompt = next(
        v for v in vars(llm_service).values()
        if isinstance(v, str) and "## Knowledge-base grounding (IMPORTANT)" in v
    )
    assert "A result's `section` says where the passage sits" in prompt
    assert "give each item one row" in prompt
    assert "copy amounts, percentages and time limits exactly" in prompt


class TestPrefetchedSnippets:
    """A question that names a sponsor's rulebook is answered from snippets
    fetched before the model runs; they need their section as much as the
    passages the search tool returns."""

    @pytest.mark.asyncio
    async def test_a_prefetched_snippet_carries_its_section(self, index):
        from app.services import chat_service

        passage = _chunk("Purchase of a unit of equipment exceeding $25,000")
        results = [{"content": passage, "metadata": {"source_id": "src-1", "source_name": NAME},
                    "chunk_id": "src-1_chunk_40", "score": 0.9}]
        with patch.object(chat_service, "_kb_section_indexes", AsyncMock(return_value={"src-1": index})), \
             patch("app.services.knowledge_service.resolve_openable_documents", new=AsyncMock(return_value={})):
            segment, sources = await chat_service._render_kb_segment(results, "List NIH prior approvals")
        assert f"**[S1] Source: {NAME}**\n_Section: 8.1.2 Prior Approval Requirements > 8.1.2.5 Change in Scope_\n" in segment.text
        assert "is where the snippet BEGINS" in segment.text
        # The citation check still finds the snippet under its source name.
        assert "exceeding $25,000" in chat_service._cited_source_texts([segment])[NAME]
        assert [s["ref"] for s in sources] == [1]

    @pytest.mark.asyncio
    async def test_no_section_line_when_the_source_text_is_not_available(self):
        from app.services import chat_service

        results = [{"content": "Travel is reimbursed at cost.", "metadata": {"source_id": "src-9", "source_name": "Travel.pdf"},
                    "chunk_id": "c9", "score": 0.9}]
        # No database here: loading the sources fails and is not fatal.
        with patch("app.services.knowledge_service.resolve_openable_documents", new=AsyncMock(return_value={})):
            segment, _ = await chat_service._render_kb_segment(results, "q")
        assert "_Section:" not in segment.text
        assert "BEGINS" not in segment.text
