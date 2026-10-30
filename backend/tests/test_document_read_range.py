"""Chat can read any part of a long document (#1007).

``get_document_text`` returned the first 30,000 characters and nothing else,
so a 100-page solicitation could not be read past roughly page 25 from chat.
Reads now go by page, stop on a page boundary at the cap, and say which pages
they hold and where to continue.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_tools import get_document_text, read_document_range

PAGE_CHARS = 1000


def _long_document(pages: int = 104, *, approximate: bool = False):
    """Pages of 950-1049 characters. Perfectly even spacing would read as
    interpolated OCR markers (page_locator.with_marker_provenance)."""
    raw, markers = "", []
    for p in range(1, pages + 1):
        markers.append({"kind": "page", "value": p, "char_offset": len(raw), "approximate": approximate})
        body = f"Page {p} of the solicitation. " + ("budget limits and eligibility " * 40)
        raw += body[:PAGE_CHARS - 50 + (p * 37) % 100] + "\n"
    return raw, markers


class TestReadByPage:
    def test_a_default_read_stops_on_a_page_boundary_and_says_where_to_continue(self):
        raw, markers = _long_document()
        read = read_document_range(raw, markers)
        assert read["start_page"] == 1
        assert read["end_page"] == 29
        assert read["next_page"] == 30
        assert read["page_count"] == 104
        assert read["complete"] is False
        assert read["text"].startswith("[p. 1]")
        assert "Page 29 of" in read["text"] and "Page 30 of" not in read["text"]

    def test_pages_past_the_first_read_are_reachable(self):
        raw, markers = _long_document()
        read = read_document_range(raw, markers, start_page=90)
        assert read["text"].startswith("[p. 90]")
        assert (read["start_page"], read["end_page"]) == (90, 104)
        assert read["next_page"] is None

    def test_a_requested_range_is_returned_exactly(self):
        raw, markers = _long_document()
        read = read_document_range(raw, markers, start_page=40, end_page=55)
        assert read["pages_returned"] == "40–55"
        assert "Page 39 of" not in read["text"] and "Page 56 of" not in read["text"]
        assert read["next_page"] is None

    def test_a_requested_range_longer_than_one_read_continues_inside_the_range(self):
        raw, markers = _long_document()
        read = read_document_range(raw, markers, start_page=10, end_page=80)
        assert (read["start_page"], read["end_page"], read["next_page"]) == (10, 38, 39)

    def test_a_short_document_is_read_whole(self):
        raw, markers = _long_document(4)
        read = read_document_range(raw, markers)
        assert read["complete"] is True and read["next_page"] is None
        assert read["pages_returned"] == "1–4"

    def test_an_interpolated_page_keeps_its_hedge(self):
        raw, markers = _long_document(10, approximate=True)
        assert read_document_range(raw, markers, start_page=3)["text"].startswith("[p. ~3]")

    @pytest.mark.parametrize("kwargs,needle", [
        ({"start_page": 200}, "outside this document (pages 1–104)"),
        ({"start_page": 0}, "outside this document"),
        ({"start_page": 50, "end_page": 40}, "before start_page"),
        ({"start_char": 100}, "read it by page"),
    ])
    def test_a_bad_range_is_an_error_with_a_way_forward(self, kwargs, needle):
        raw, markers = _long_document()
        read = read_document_range(raw, markers, **kwargs)
        assert needle in read["error"]
        assert read["hint"]

    def test_a_page_longer_than_one_read_is_cut_mid_page_with_a_resume_offset(self):
        raw = "x" * 70000 + "\n" + "y" * 10
        markers = [{"kind": "page", "value": 1, "char_offset": 0}, {"kind": "page", "value": 2, "char_offset": 70001}]
        read = read_document_range(raw, markers)
        assert read["page_cut_mid"] is True
        assert read["next_start_char"] == 30000
        assert read["end_page"] == 1


class TestReadByPosition:
    def test_a_document_without_pages_is_read_in_order(self):
        raw = "a" * 70000
        first = read_document_range(raw, None)
        assert (first["start_char"], first["end_char"], first["next_start_char"]) == (0, 30000, 30000)
        last = read_document_range(raw, None, start_char=60000)
        assert last["next_start_char"] is None and len(last["text"]) == 10000

    def test_asking_for_pages_of_a_pageless_document_explains_how_to_read_it(self):
        read = read_document_range("a" * 100, None, start_page=2)
        assert "no page markers" in read["error"]
        assert "start_char" in read["hint"]


def _doc(raw, markers):
    return SimpleNamespace(
        uuid="doc-1", title="Long solicitation.pdf", extension=".pdf", num_pages=104,
        raw_text=raw, text_markers=markers, team_id="team1", user_id="user1",
    )


def _ctx():
    ctx = MagicMock()
    ctx.deps.team_id, ctx.deps.user_id = "team1", "user1"
    return ctx


class TestTheChatTool:
    @pytest.mark.asyncio
    async def test_a_partial_read_tells_the_model_how_to_continue(self):
        raw, markers = _long_document()
        with patch("app.services.chat_tools.SmartDocument") as Doc:
            Doc.find_one = AsyncMock(return_value=_doc(raw, markers))
            result = await get_document_text(_ctx(), "doc-1")
        assert result["truncated"] is True
        assert "pp. 1–29 of 104" in result["note"]
        assert "start_page=30" in result["note"]
        assert result["page_citation_note"]

    @pytest.mark.asyncio
    async def test_the_tool_reads_a_requested_range(self):
        raw, markers = _long_document()
        with patch("app.services.chat_tools.SmartDocument") as Doc:
            Doc.find_one = AsyncMock(return_value=_doc(raw, markers))
            result = await get_document_text(_ctx(), "doc-1", start_page=95, end_page=104)
        assert result["pages_returned"] == "95–104"
        assert "Page 104 of" in result["text"]

    @pytest.mark.asyncio
    async def test_a_bad_range_comes_back_as_an_error(self):
        raw, markers = _long_document()
        with patch("app.services.chat_tools.SmartDocument") as Doc:
            Doc.find_one = AsyncMock(return_value=_doc(raw, markers))
            result = await get_document_text(_ctx(), "doc-1", start_page=500)
        assert "error" in result and "1–104" in result["error"]
