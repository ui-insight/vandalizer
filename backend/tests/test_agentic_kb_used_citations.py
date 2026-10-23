"""Only the passages an agentic KB answer cites are its sources (#993).

Main's fix numbered the pre-fetched KB snippets and marked the ones the answer
cited. On v5 most KB passages come from the agent's own search_knowledge_base
calls, whose citations carried no number, so every one of them was listed
under "Sources:" whether the answer used it or not.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat_service import _mark_used_citations
from tests.test_agentic_kb_page_hedging import _result, _search


@pytest.mark.asyncio
async def test_search_citations_are_numbered_after_the_prefetched_snippets():
    from tests.test_chat_tools import _make_context

    ctx = _make_context()
    ctx.deps.kb_snippet_ref = 3  # [S1]..[S3] were pre-fetched this turn
    with patch("tests.test_agentic_kb_page_hedging._make_context", return_value=ctx), \
         patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(return_value={})):
        _, ctx = await _search([
            _result("The page limit is 15.", page=137),
            _result("Travel is reimbursed at cost.", page=54),
        ])

    citations = ctx.deps.citation_annotations["call-1"]
    assert [c["ref"] for c in citations] == [4, 5]
    assert citations[0]["cite_label"] == "Award Terms.pdf · p. 137"
    assert ctx.deps.kb_snippet_ref == 5


def _chip(ref, page, title="PAPPG.pdf"):
    return {"ref": ref, "document_title": title, "page": page}


def test_only_the_cited_searched_passage_is_used():
    citations = [_chip(1, 54), _chip(2, 139), _chip(3, 212)]
    used = _mark_used_citations("Up to 12 months [Source: PAPPG.pdf, p. 139].", citations)
    assert used == [2]
    assert [c["used"] for c in citations] == [False, True, False]


def test_a_not_found_answer_uses_none_of_them():
    citations = [_chip(1, 54), _chip(2, 139)]
    assert _mark_used_citations("The knowledge base doesn't cover this.", citations) == []
    assert all(c["used"] is False for c in citations)


def test_unnumbered_citations_are_left_as_sources():
    web = {"document_title": "nsf.gov", "url": "https://nsf.gov"}
    citations = [web, _chip(1, 54)]
    _mark_used_citations("Nothing cited.", citations)
    assert "used" not in web
    assert _mark_used_citations("x", [web]) is None
