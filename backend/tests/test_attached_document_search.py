"""Long attached documents stay answerable when chat cuts them to fit.

On the 2026-10-29 attached-document eval, both DOE FOAs (132 and 151 pages)
were cut by the 75/25 head/tail trim, and the answer page sat in the cut
middle on 4 of 5 single-FOA items. The agent's only search matched workspace
file titles, so it guessed page ranges with get_document_text (up to 26 calls
on one turn), and re-reading an attached notice's inline pages grew one
request past the model's window.

Now the planner keeps the pages that best match the question, the agent can
search inside the attached documents, and tool results never resend what the
model holds and never outgrow the room the window has left.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import RequestUsage

from app.services import chat_tools
from app.services.chat_service import annotate_pages, documents_in_context
from app.services.chat_tools import get_document_text, search_attached_documents
from app.services.context_budget import (
    _DOCUMENT_CUT_MARKER,
    _TRUNCATED_MARKER,
    CUT_NOTE_PREFIX,
    DocumentSegment,
    ToolResultBudget,
    plan_and_compact_context,
)
from app.services.doc_passages import (
    DocumentContext,
    annotated_pages,
    context_after_compaction,
    rank_texts,
    strong_matches,
    terms,
)

TOPIC_PAGE = 37
FILLER = (
    "Applicants must follow the instructions in this announcement. The project narrative "
    "describes the technical approach, the team, and the management plan for the work. "
)


def _foa(pages: int = 60):
    """A long solicitation: a table of contents up front, filler pages, and one
    topic's award terms deep in the middle. Page lengths vary so the markers
    read as measured, not interpolated (page_locator.with_marker_provenance)."""
    raw, markers = "", []
    for p in range(1, pages + 1):
        markers.append({"kind": "page", "value": p, "char_offset": len(raw)})
        if p == 2:
            body = "Table of Contents. Topic Area 3.4 Rapid Solar Software Development ... 37\n"
        elif p == TOPIC_PAGE:
            body = (
                "Topic Area 3.4: Rapid Solar Software Development. DOE anticipates awards of "
                "up to $750,000 each, with a period of performance of up to 24 months.\n"
            )
        else:
            body = f"Section {p}. "
        body += FILLER * (6 + p % 3)
        raw += body + "\n"
    return raw, markers


def _segment(raw, markers, title="SETO_FOA.pdf", uuid="foa-1"):
    return DocumentSegment(
        label=f"doc:{title}",
        text=f"\n\n## Document: {title}\n{annotate_pages(raw, markers)}",
        source_uuid=uuid,
    )


def _plan(segment, question, window=20_000):
    return plan_and_compact_context(
        model_name="test-model", model_config={"context_window": window}, system_prompt="sys",
        user_message=question, history=[], documents=[segment], attachments=[],
        response_reserve=1_000,
    )


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


class TestRanking:
    def test_section_numbers_stay_whole_and_joined_words_keep_their_parts(self):
        assert "3.4" in terms("Topic Area 3.4: Rapid")
        assert "3" not in terms("Topic Area 3.4")
        assert {"ms-ne-3", "ms", "ne", "3"} <= set(terms("the MS-NE-3 workscope"))

    def test_the_page_naming_the_topic_ranks_above_pages_of_common_words(self):
        raw, markers = _foa()
        pages = [raw[m["char_offset"]:n["char_offset"]] for m, n in zip(markers, markers[1:])]
        ranked = rank_texts("what's the most we could request for Topic 3.4 Rapid Solar Software Development", pages)
        assert ranked[0].index + 1 in (2, TOPIC_PAGE)
        assert {r.index + 1 for r in ranked[:2]} == {2, TOPIC_PAGE}

    def test_one_common_word_of_a_long_question_is_not_a_match(self):
        texts = ["the project narrative", "Topic Area 3.4 award ceiling and project period"]
        strong = strong_matches(rank_texts("Topic 3.4 award ceiling for our project", texts), "Topic 3.4 award ceiling for our project")
        assert [r.index for r in strong] == [1]


# ---------------------------------------------------------------------------
# The planner keeps the pages that match the question
# ---------------------------------------------------------------------------


class TestTrimByPages:
    QUESTION = "Under this FOA, what's the most we could request for a Topic 3.4 Rapid Solar Software Development project?"

    def test_the_matching_middle_page_goes_with_the_question(self):
        raw, markers = _foa()
        result = _plan(_segment(raw, markers), self.QUESTION)
        assert any(a.kind == "documents_trimmed" for a in result.actions)
        text = result.documents[0].text
        assert "up to $750,000 each" in text
        assert not result.fatal

    def test_the_head_tail_cut_alone_would_have_dropped_it(self):
        raw, markers = _foa()
        result = _plan(_segment(raw, markers), "Summarize this announcement.")
        assert "up to $750,000 each" not in result.documents[0].text

    def test_every_gap_says_which_pages_it_skips_and_how_to_reach_them(self):
        raw, markers = _foa()
        text = _plan(_segment(raw, markers), self.QUESTION).documents[0].text
        assert f"{CUT_NOTE_PREFIX}pp. " in text
        assert "search_attached_documents" in text and "get_document_text" in text
        kept = [p.page for p in annotated_pages(text)]
        assert kept[0] == 1 and kept[-1] == 60 and TOPIC_PAGE in kept

    def test_the_trim_keeps_whole_pages_and_reports_them_as_held(self):
        raw, markers = _foa()
        seg = _segment(raw, markers)
        sent = _plan(seg, self.QUESTION).documents[0]
        held = documents_in_context([seg], [sent])["foa-1"]
        assert not held.whole
        assert TOPIC_PAGE in held.pages and 1 in held.pages and 60 in held.pages
        assert len(held.pages) < 60
        assert sent.source_uuid == "foa-1"

    def test_a_document_without_pages_keeps_the_head_tail_cut(self):
        seg = DocumentSegment(label="doc:sheet.xlsx", text="row value " * 12_000, source_uuid="x")
        text = _plan(seg, "Topic 3.4").documents[0].text
        assert _DOCUMENT_CUT_MARKER in text


class TestDocumentsInContext:
    def test_an_untrimmed_document_is_held_whole(self):
        raw, markers = _foa(6)
        seg = _segment(raw, markers)
        assert documents_in_context([seg], [seg])["foa-1"].whole is True

    def test_a_dropped_document_holds_nothing(self):
        raw, markers = _foa(6)
        held = documents_in_context([_segment(raw, markers)], [])["foa-1"]
        assert not held.whole and not held.pages

    def test_a_mid_page_cut_leaves_the_page_before_it_partial(self):
        original = "[p. 1]\none\n[p. 2]\ntwo two\n[p. 3]\nthree\n[p. 4]\nfour\n"
        sent = "[p. 1]\none\n[p. 2]\ntw" + _DOCUMENT_CUT_MARKER + "ree\n[p. 4]\nfour\n"
        held = context_after_compaction(original, sent, (_DOCUMENT_CUT_MARKER, _TRUNCATED_MARKER))
        assert held.pages == {1, 4}


# ---------------------------------------------------------------------------
# Room for tool results
# ---------------------------------------------------------------------------


def _response(input_tokens, output_tokens=100):
    return ModelResponse(parts=[TextPart("calling a tool")], usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens))


class TestToolResultBudget:
    def _budget(self):
        return ToolResultBudget(input_budget=100_000, planned_tokens=60_000, planned_messages=1, count=lambda t: len(t) // 4)

    def test_the_provider_reported_size_is_the_anchor(self):
        budget = self._budget()
        messages = [ModelRequest(parts=[UserPromptPart("q")]), _response(90_000, 500)]
        assert budget.available(messages) == 100_000 - 90_500 - 3_000

    def test_without_a_report_the_plan_and_what_the_run_added_count(self):
        budget = self._budget()
        messages = [ModelRequest(parts=[UserPromptPart("q")]), ModelResponse(parts=[TextPart("x" * 4_000)])]
        assert budget.available(messages) < 100_000 - 60_000 - 1_000 - 3_000 + 10

    def test_calls_from_one_response_share_the_room_and_the_next_response_resets_it(self):
        budget = self._budget()
        messages = [ModelRequest(parts=[UserPromptPart("q")]), _response(50_000, 0)]
        first = budget.available(messages)
        budget.spend(20_000)
        assert budget.available(messages) == first - 20_000
        messages += [ModelRequest(parts=[UserPromptPart("results")]), _response(70_000, 0)]
        assert budget.available(messages) == 100_000 - 70_000 - 3_000


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


def _doc(raw, markers, uuid="foa-1", title="SETO_FOA.pdf"):
    return SimpleNamespace(
        uuid=uuid, title=title, extension=".pdf", num_pages=len(markers or []) or None,
        raw_text=raw, text_markers=markers, team_id="team1", user_id="user1",
    )


def _ctx(*, attached=("foa-1",), held=None, budget=None, messages=None):
    deps = SimpleNamespace(
        team_id="team1", user_id="user1", context_document_uuids=list(attached),
        documents_in_context=dict(held or {}), tool_result_budget=budget,
    )
    return SimpleNamespace(deps=deps, messages=messages or [])


def _patched(*docs):
    p = patch("app.services.chat_tools.SmartDocument")
    mock = p.start()
    mock.find_one = AsyncMock(side_effect=list(docs))
    return p


class TestGetDocumentTextSkipsWhatIsHeld:
    @pytest.mark.asyncio
    async def test_a_document_sent_whole_is_pointed_at_not_resent(self):
        raw, markers = _foa(6)
        p = _patched(_doc(raw, markers))
        try:
            result = await get_document_text(_ctx(held={"foa-1": DocumentContext(whole=True)}), "foa-1")
        finally:
            p.stop()
        assert result["already_in_context"] is True and "text" not in result

    @pytest.mark.asyncio
    async def test_inline_pages_are_skipped_and_the_read_continues_past_them(self):
        raw, markers = _foa()
        held = DocumentContext(pages=set(range(1, 25)) | {37} | set(range(53, 61)))
        p = _patched(_doc(raw, markers))
        try:
            result = await get_document_text(_ctx(held={"foa-1": held}), "foa-1", start_page=1, end_page=60)
        finally:
            p.stop()
        assert result["start_page"] == 25 and result["end_page"] == 36
        assert result["next_page"] == 38
        assert "1–24, 37, 53–60" == result["pages_in_context_not_resent"]
        assert "Section 24." not in result["text"]

    @pytest.mark.asyncio
    async def test_a_read_of_held_pages_only_is_a_pointer_and_reads_are_remembered(self):
        raw, markers = _foa()
        ctx = _ctx(held={"foa-1": DocumentContext()})
        p = _patched(_doc(raw, markers), _doc(raw, markers))
        try:
            first = await get_document_text(ctx, "foa-1", start_page=30, end_page=32)
            again = await get_document_text(ctx, "foa-1", start_page=30, end_page=32)
        finally:
            p.stop()
        assert first["pages_returned"] == "30–32"
        assert again["already_in_context"] is True and again["pages_in_context"] == "30–32"

    @pytest.mark.asyncio
    async def test_a_read_shrinks_to_the_room_left(self):
        raw, markers = _foa()
        budget = ToolResultBudget(input_budget=20_000, planned_tokens=0, planned_messages=0, count=lambda t: len(t) // 4)
        messages = [_response(14_000, 0)]
        p = _patched(_doc(raw, markers))
        try:
            result = await get_document_text(_ctx(budget=budget, messages=messages), "foa-1")
        finally:
            p.stop()
        assert "text" in result and not result["complete"]
        assert len(result["text"]) // 4 <= 20_000 - 14_000 - 3_000

    @pytest.mark.asyncio
    async def test_with_no_room_left_the_read_is_refused_with_what_to_do(self):
        raw, markers = _foa()
        budget = ToolResultBudget(input_budget=20_000, planned_tokens=0, planned_messages=0, count=lambda t: len(t) // 4)
        p = _patched(_doc(raw, markers))
        try:
            result = await get_document_text(_ctx(budget=budget, messages=[_response(16_500, 0)]), "foa-1")
        finally:
            p.stop()
        assert "No room is left" in result["error"]
        assert "follow-up" in result["hint"]

    @pytest.mark.asyncio
    async def test_parallel_reads_from_one_response_share_the_room(self):
        raw, markers = _foa()
        budget = ToolResultBudget(input_budget=30_000, planned_tokens=0, planned_messages=0, count=lambda t: len(t) // 4)
        messages = [_response(20_000, 0)]
        p = _patched(*[_doc(raw, markers)] * 3)
        try:
            reads = [
                await get_document_text(_ctx(budget=budget, messages=messages), "foa-1", start_page=s, end_page=s + 9)
                for s in (1, 11, 21)
            ]
        finally:
            p.stop()
        sent = sum(len(r.get("text", "")) // 4 for r in reads)
        assert sent <= 30_000 - 20_000 - 3_000
        assert any("error" in r for r in reads)


class TestSearchAttachedDocuments:
    QUERY = "Topic 3.4 Rapid Solar Software Development award amount"

    @pytest.mark.asyncio
    async def test_it_finds_a_passage_on_a_cut_page_with_its_page_marker(self):
        raw, markers = _foa()
        p = _patched(_doc(raw, markers))
        try:
            result = await search_attached_documents(_ctx(held={"foa-1": DocumentContext(pages={1, 2, 3})}), self.QUERY)
        finally:
            p.stop()
        top = result["passages"][0]
        assert top["page"] == TOPIC_PAGE
        assert top["text"].startswith(f"[p. {TOPIC_PAGE}]\n")
        assert "$750,000" in top["text"]
        assert top["document"] == "SETO_FOA.pdf"

    @pytest.mark.asyncio
    async def test_a_match_on_a_page_already_held_is_a_pointer_with_a_snippet(self):
        raw, markers = _foa()
        p = _patched(_doc(raw, markers))
        try:
            result = await search_attached_documents(_ctx(held={"foa-1": DocumentContext(pages={2, TOPIC_PAGE})}), self.QUERY)
        finally:
            p.stop()
        on_topic = next(x for x in result["passages"] if x["page"] == TOPIC_PAGE)
        assert on_topic["already_in_context"] is True
        assert "text" not in on_topic and "3.4" in on_topic["snippet"]

    @pytest.mark.asyncio
    async def test_a_repeated_search_does_not_resend_its_passages(self):
        raw, markers = _foa()
        ctx = _ctx(held={"foa-1": DocumentContext()})
        p = _patched(_doc(raw, markers), _doc(raw, markers))
        try:
            await search_attached_documents(ctx, self.QUERY)
            again = await search_attached_documents(ctx, self.QUERY)
        finally:
            p.stop()
        assert all(x.get("already_in_context") for x in again["passages"])

    @pytest.mark.asyncio
    async def test_with_nothing_attached_it_points_to_the_title_search(self):
        result = await search_attached_documents(_ctx(attached=()), "cost share")
        assert "No documents are attached" in result["error"]
        assert "search_documents" in result["hint"]

    @pytest.mark.asyncio
    async def test_no_match_says_to_try_other_words_not_that_the_document_is_silent(self):
        raw, markers = _foa(8)
        p = _patched(_doc(raw, markers))
        try:
            result = await search_attached_documents(_ctx(), "cryogenic helium dewar")
        finally:
            p.stop()
        assert result["passages"] == []
        assert "Try the words the document itself would use" in result["note"]

    @pytest.mark.asyncio
    async def test_it_searches_every_attached_document_and_names_each(self):
        raw, markers = _foa()
        other = "Cost share of 20% is required for all R&D projects under this announcement.\n" + FILLER * 8
        p = _patched(_doc(raw, markers), _doc(other, None, uuid="cinr-1", title="CINR.pdf"))
        try:
            result = await search_attached_documents(_ctx(attached=("foa-1", "cinr-1")), "cost share R&D")
        finally:
            p.stop()
        assert result["passages"][0]["document"] == "CINR.pdf"
        assert {d["title"] for d in result["documents_searched"]} == {"SETO_FOA.pdf", "CINR.pdf"}


class TestToolDescriptions:
    def test_the_search_tool_is_registered_as_a_read(self):
        names = {t.__name__ for t in chat_tools.TOOLS}
        assert "search_attached_documents" in names
        assert "search_attached_documents" in chat_tools.COMPACTABLE_TOOLS

    def test_search_documents_says_it_finds_files_by_title_not_passages(self):
        doc = chat_tools.search_documents.__doc__
        assert "by title" in doc and "never searches inside" in doc
        assert "search_attached_documents" in doc
