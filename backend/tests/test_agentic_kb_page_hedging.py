"""The agentic KB path must hedge pages the way the classic path does.

`chat_service` routes every KB citation through `page_locator` — `cited_pages`
for which page a passage actually falls on, `annotate_chunk_pages` so the model
can see where a chunk crosses a break, and `page_approximate` so an interpolated
OCR page renders as `p. ~12` instead of `p. 12`.

`chat_tools.search_knowledge_base` — the flagship v5 path — read
`metadata["page"]` directly, so it reintroduced both bugs `page_locator` exists
to prevent: an estimated page stated as exact, and a chunk cited by the page it
starts on rather than the page the answer is on.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_chat_tools import _make_context


def _kb() -> MagicMock:
    kb = MagicMock()
    kb.uuid, kb.title, kb.status, kb.verified = "kb-1", "Grants KB", "ready", True
    kb.user_id, kb.team_id = "user1", "team1"
    return kb


def _result(content: str, **meta) -> dict:
    base = {"source_id": "src-1", "source_name": "Award Terms.pdf"}
    base.update(meta)
    return {"content": content, "metadata": base, "chunk_id": "c-1", "score": 0.9}


async def _search(results: list[dict], query: str = "what is the award amount"):
    ctx = _make_context()
    ctx.tool_call_id = "call-1"
    rag_cfg = MagicMock(k=10)
    # Beanie Documents are patched as whole classes: class-level field access
    # (``KnowledgeBase.uuid``) raises on an uninitialized collection, so
    # patching only ``find_one`` is not enough. Same convention as
    # test_chat_tools.py.
    with (
        patch("app.services.chat_tools.KnowledgeBase") as kb_cls,
        patch("app.services.chat_tools.KnowledgeBaseSource") as source_cls,
        patch("app.services.kb_validation_service._ensure_system_config_loaded",
              new=AsyncMock(return_value=None)),
        patch("app.services.kb_validation_service.retrieve_kb_chunks",
              new=AsyncMock(return_value=(results, rag_cfg, None))),
        patch("app.services.user_memory_service.record_kb_query", new=AsyncMock()),
    ):
        kb_cls.find_one = AsyncMock(return_value=_kb())
        source_cls.find.return_value.to_list = AsyncMock(return_value=[])
        from app.services.chat_tools import search_knowledge_base

        out = await search_knowledge_base(ctx, query, kb_uuid="kb-1")
    return out, ctx


def _passages(out: list[dict]) -> list[dict]:
    return [e for e in out if "content" in e]


def _note(out: list[dict]) -> str:
    """The citation guidance, wherever it rides.

    It sits on each passage rather than as a leading pseudo-entry: the UI
    renders every element of this result as a passage, so a note dict of its
    own inflated the passage count and took a preview slot.
    """
    return " ".join(
        dict.fromkeys(e["citation_note"] for e in out if e.get("citation_note"))
    )


class TestApproximatePages:
    @pytest.mark.asyncio
    async def test_an_interpolated_page_is_marked_approximate(self):
        out, ctx = await _search([
            _result("The award is $4,200,000.", page=12, page_approximate=True),
        ])
        assert _passages(out)[0]["page_approximate"] is True
        assert ctx.deps.citation_annotations["call-1"][0]["page_approximate"] is True

    @pytest.mark.asyncio
    async def test_a_measured_page_is_not(self):
        out, ctx = await _search([_result("The award is $4,200,000.", page=12)])
        entry = _passages(out)[0]
        assert entry["page"] == 12
        assert "page_approximate" not in entry
        assert ctx.deps.citation_annotations["call-1"][0]["page_approximate"] is False

    @pytest.mark.asyncio
    async def test_the_model_is_told_what_the_estimate_means(self):
        """A tilde nobody explained gets normalised away and the estimate is
        restated as fact — the classic path carries this label for that reason."""
        out, _ = await _search([_result("text", page=3, page_approximate=True)])
        note = _note(out)
        assert "ESTIMATE" in note
        assert "never say" in note.lower()

    @pytest.mark.asyncio
    async def test_no_note_when_every_page_was_measured(self):
        out, _ = await _search([_result("text", page=3)])
        assert _note(out) == ""
        assert len(out) == 1


class TestChunksThatSpanPages:
    # A chunk starting on page 2 whose second half is page 3.
    SPANNING = dict(page=2, page_end=3, page_breaks="[[26, 3]]")

    @pytest.mark.asyncio
    async def test_the_answer_page_wins_over_the_starting_page(self):
        out, _ = await _search(
            [_result("Budget narrative follows.\nThe award amount is $4.2M.",
                     **self.SPANNING)],
            query="award amount",
        )
        assert _passages(out)[0]["page"] == 3

    @pytest.mark.asyncio
    async def test_an_ambiguous_match_cites_the_range_not_a_guess(self):
        out, _ = await _search(
            [_result("Nothing relevant here.\nNor anything here either.",
                     **self.SPANNING)],
            query="award amount",
        )
        entry = _passages(out)[0]
        assert entry["page"] == 2
        assert entry["page_end"] == 3

    @pytest.mark.asyncio
    async def test_page_breaks_are_marked_in_the_text_the_model_reads(self):
        out, _ = await _search(
            [_result("Budget narrative follows.\nThe award amount is $4.2M.",
                     **self.SPANNING)],
            query="award amount",
        )
        assert "[p. 3]" in _passages(out)[0]["content"]
        assert "runs across pages" in _note(out)

    @pytest.mark.asyncio
    async def test_a_spanning_approximate_chunk_hedges_its_break_markers(self):
        out, _ = await _search(
            [_result("Budget narrative follows.\nThe award amount is $4.2M.",
                     page_approximate=True, **self.SPANNING)],
            query="award amount",
        )
        assert "[p. ~3]" in _passages(out)[0]["content"]


class TestUnpagedSources:
    @pytest.mark.asyncio
    async def test_a_sheet_source_still_carries_its_sheet(self):
        out, _ = await _search([_result("Row data", sheet="Budget")])
        entry = _passages(out)[0]
        assert entry["sheet"] == "Budget"
        assert "page" not in entry

    @pytest.mark.asyncio
    async def test_a_source_with_no_location_cites_nothing(self):
        out, ctx = await _search([_result("Some text")])
        entry = _passages(out)[0]
        assert "page" not in entry and "sheet" not in entry
        assert ctx.deps.citation_annotations["call-1"][0]["page"] is None


class TestTheResultStaysAListOfPassages:
    """The UI treats every element of this tool's result as a passage: it
    counts them for "Found N relevant passages", previews the first three, and
    copies them. A note prepended as its own dict inflated the count by one,
    took a preview slot as a blank "Source ·" row, and led the copied text with
    an empty [Source] block."""

    @pytest.mark.asyncio
    async def test_guidance_does_not_add_a_pseudo_passage(self):
        out, _ = await _search([
            _result("text one", page=3, page_approximate=True),
            _result("text two", page=4, page_approximate=True),
        ])
        assert len(out) == 2
        assert all("content" in e and "source_name" in e for e in out)

    @pytest.mark.asyncio
    async def test_every_passage_carries_the_guidance(self):
        out, _ = await _search([
            _result("text one", page=3, page_approximate=True),
            _result("text two", page=4, page_approximate=True),
        ])
        assert all("ESTIMATE" in e["citation_note"] for e in out)

    @pytest.mark.asyncio
    async def test_no_guidance_key_when_nothing_needs_hedging(self):
        out, _ = await _search([_result("text", page=3)])
        assert "citation_note" not in out[0]


class TestVerbatimTextForMatching:
    SPANNING = dict(page=2, page_end=3, page_breaks="[[26, 3]]")

    @pytest.mark.asyncio
    async def test_a_spanning_passage_exposes_its_unannotated_text(self):
        """The annotated copy is for the model; anything matching against the
        document needs the text the document actually contains."""
        raw = "Budget narrative follows.\nThe award amount is $4.2M."
        out, _ = await _search([_result(raw, **self.SPANNING)], query="award amount")
        entry = out[0]
        assert "[p. 3]" in entry["content"]
        assert entry["content_verbatim"] == raw
        assert "[p." not in entry["content_verbatim"]

    @pytest.mark.asyncio
    async def test_a_single_page_passage_needs_no_second_copy(self):
        out, _ = await _search([_result("Plain single-page text.", page=3)])
        assert "content_verbatim" not in out[0]
