"""Only the snippets a KB answer cites are listed as its sources.

Support ticket: with the QA Smoke KB attached, "According to QA Smoke, what
are the DOE travel reimbursement rules?" was correctly answered "the KB
doesn't contain that", yet 7–10 PAPPG.pdf chips (p. ~54, ~139, ~212 …) sat
under it as "Sources". Every retrieved snippet was listed whether or not the
answer used it, and on the NIH specific-aims answer the same file showed up
in several chips that supported nothing in particular.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.kb_answer_grounding import expand_snippet_refs, used_snippet_refs


def _src(ref, title, page=None, page_end=None, cite_label=None):
    return {
        "ref": ref,
        "document_title": title,
        "page": page,
        "page_end": page_end,
        "cite_label": cite_label or (f"{title}, p. {page}" if page else title),
    }


# What retrieval returned for the DOE travel question: the KB's nearest
# passages, none of them about DOE travel.
PAPPG = [
    _src(1, "PAPPG.pdf", 54, cite_label="PAPPG.pdf, p. ~54"),
    _src(2, "PAPPG.pdf", 139, cite_label="PAPPG.pdf, p. ~139"),
    _src(3, "PAPPG.pdf", 212, cite_label="PAPPG.pdf, p. ~212"),
    _src(4, "NIH_GPS.pdf", 88),
]


class TestUsedSnippetRefs:
    def test_a_not_found_answer_uses_none_of_what_was_searched(self):
        answer = (
            "The QA Smoke knowledge base does not contain information about DOE "
            "travel reimbursement rules. The retrieved passages cover NSF proposal "
            "preparation and award administration, not DOE travel. You could check "
            "DOE's financial assistance regulations directly or add them to the KB."
        )
        assert used_snippet_refs(answer, PAPPG) == []

    def test_only_the_cited_chunk_of_a_file_is_used(self):
        """The repeated-chips half of the ticket: one file, many chunks, and
        the answer drew on one of them."""
        answer = (
            "A no-cost extension of up to 12 months may be approved by the "
            "grantee organization [S2]. Further extensions need NSF approval [S2]."
        )
        assert used_snippet_refs(answer, PAPPG) == [2]

    def test_grouped_and_adjacent_citations_all_count(self):
        answer = "Both agencies require it [S1, S4]. The PAPPG repeats this [S3][S1]."
        assert used_snippet_refs(answer, PAPPG) == [1, 3, 4]

    def test_a_number_no_snippet_carries_is_ignored(self):
        assert used_snippet_refs("As stated [S9].", PAPPG) == []

    def test_a_filename_citation_with_a_page_picks_that_chunk(self):
        """The format the prompt used to ask for, which a model can still fall
        back on after seeing it in earlier turns."""
        answer = "Extensions are allowed [Source: PAPPG.pdf, p. 139]."
        assert used_snippet_refs(answer, PAPPG) == [2]

    def test_a_filename_citation_without_a_page_counts_for_the_file(self):
        answer = "See the NIH policy [Source: NIH_GPS.pdf]."
        assert used_snippet_refs(answer, PAPPG) == [4]

    def test_a_page_range_snippet_covers_a_page_inside_it(self):
        sources = [_src(1, "Guide.pdf", 10, page_end=12)]
        assert used_snippet_refs("[Source: Guide.pdf, p. 11]", sources) == [1]
        assert used_snippet_refs("[Source: Guide.pdf, p. 14]", sources) == []


class TestExpandSnippetRefs:
    def test_numbers_become_the_readable_citation(self):
        answer = "Up to 12 months [S2]. Both agree [S1, S4]."
        assert expand_snippet_refs(answer, PAPPG) == (
            "Up to 12 months [Source: PAPPG.pdf, p. ~139]. "
            "Both agree [Source: PAPPG.pdf, p. ~54; NIH_GPS.pdf, p. 88]."
        )

    def test_an_unknown_number_is_left_as_written(self):
        assert expand_snippet_refs("Odd [S9].", PAPPG) == "Odd [S9]."

    def test_an_answer_without_numbers_is_unchanged(self):
        answer = "The KB does not cover DOE travel."
        assert expand_snippet_refs(answer, PAPPG) == answer


class TestRenderedSnippetsAreNumbered:
    @pytest.mark.asyncio
    async def test_each_snippet_and_its_source_share_a_number(self):
        from app.services import chat_service

        results = [
            {
                "content": f"passage {i}",
                "metadata": {"source_name": "PAPPG.pdf", "source_id": f"src-{i}", "page": p},
                "chunk_id": f"c{i}",
            }
            for i, p in enumerate([54, 139], start=1)
        ]
        with patch(
            "app.services.knowledge_service.resolve_openable_documents",
            new=AsyncMock(return_value={}),
        ):
            segment, sources = await chat_service._render_kb_segment(results, "q")

        assert [s["ref"] for s in sources] == [1, 2]
        assert "[S1] Source: PAPPG.pdf" in segment.text
        assert "[S2] Source: PAPPG.pdf" in segment.text
        assert sources[1]["cite_label"].startswith("PAPPG.pdf, p.")
