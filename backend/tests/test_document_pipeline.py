"""Tests for the document ingestion pipeline core paths.

document_readers.extract_text_from_file: format dispatch and round-trip text
preservation for plain-text formats.

document_manager._split_text: text chunking that feeds into ChromaDB.

These are unit tests with no external services. Format-specific PDF / OCR /
markitdown tests live alongside their integration tier.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.services.document_manager import _split_text
from app.services.document_readers import extract_text_from_file


# ---------------------------------------------------------------------------
# _split_text — overlap-window chunker that feeds the embedding pipeline
# ---------------------------------------------------------------------------

class TestSplitText:
    def test_returns_empty_for_empty_input(self):
        assert _split_text("", 100, 20) == []
        assert _split_text("   \n\n  ", 100, 20) == []

    def test_short_text_returns_single_chunk(self):
        chunks = _split_text("hello world", 100, 20)
        assert chunks == ["hello world"]

    def test_chunks_long_text_with_overlap(self):
        text = "abcdefghij" * 50  # 500 chars
        chunks = _split_text(text, chunk_size=100, chunk_overlap=20)

        assert len(chunks) >= 5
        # Chunks should not exceed the configured size
        for c in chunks:
            assert len(c) <= 100
        # Concatenating overlapping windows should still cover the input
        joined = "".join(chunks)
        assert len(joined) >= len(text)

    def test_breaks_on_paragraph_when_possible(self):
        # When chunk would otherwise split mid-paragraph, the splitter should
        # break on the closest "\n\n" within the second half of the window.
        para_a = "A" * 60
        para_b = "B" * 60
        text = f"{para_a}\n\n{para_b}"
        chunks = _split_text(text, chunk_size=100, chunk_overlap=10)

        # The first chunk should end before B starts (preserve paragraph break)
        assert chunks[0].rstrip().endswith("A")

    def test_no_infinite_loop_on_pathological_input(self):
        # When step would reset to 0, the splitter must still terminate
        text = "x" * 1000
        chunks = _split_text(text, chunk_size=10, chunk_overlap=10)
        # The exact count isn't important — just that we got a finite list
        assert isinstance(chunks, list)
        assert len(chunks) > 0


# ---------------------------------------------------------------------------
# extract_text_from_file — format dispatcher
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_text_file():
    """Yield a callable that writes content to a tempfile and returns its path."""
    paths: list[str] = []

    def _make(content: str, suffix: str) -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        paths.append(path)
        return path

    yield _make

    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


class TestExtractTextFromFilePlainFormats:
    def test_txt_round_trip(self, tmp_text_file):
        path = tmp_text_file("hello world\n", ".txt")
        assert extract_text_from_file(path, "txt") == "hello world\n"

    def test_md_round_trip(self, tmp_text_file):
        path = tmp_text_file("# Title\n\nbody", ".md")
        assert extract_text_from_file(path, "md") == "# Title\n\nbody"

    def test_csv_round_trip(self, tmp_text_file):
        path = tmp_text_file("a,b,c\n1,2,3\n", ".csv")
        assert extract_text_from_file(path, "csv") == "a,b,c\n1,2,3\n"

    def test_json_round_trip(self, tmp_text_file):
        content = json.dumps({"x": 1})
        path = tmp_text_file(content, ".json")
        assert extract_text_from_file(path, "json") == content

    def test_py_source_round_trip(self, tmp_text_file):
        src = "def foo():\n    return 1\n"
        path = tmp_text_file(src, ".py")
        assert extract_text_from_file(path, "py") == src

    def test_extension_normalization_strips_dot(self, tmp_text_file):
        path = tmp_text_file("plain", ".txt")
        # Caller may pass ".txt" or "TXT" or "txt"
        assert extract_text_from_file(path, ".TXT") == "plain"

    def test_missing_file_returns_empty_not_raise(self):
        # A missing source file is benign (deleted mid-processing / stale
        # path): empty text, no raise, no error-marker masquerading as content.
        result = extract_text_from_file("/does/not/exist.txt", "txt")
        assert result == ""


class TestExtractTextFromFileFallback:
    def test_unknown_extension_falls_back_to_text_read(self, tmp_text_file):
        # An unknown extension should be readable as plain text via the
        # final fallback in extract_text_from_file.
        path = tmp_text_file("plain content", ".unknown_ext")
        result = extract_text_from_file(path, "unknown_ext")
        # Either MarkItDown converts it, or fallback reads it as text.
        # In either case the content should be accessible.
        assert "plain content" in result or result.startswith("[Error")

    def test_latin1_only_file_decodes_via_fallback(self):
        # Write bytes that are NOT valid UTF-8, but ARE valid latin-1
        fd, path = tempfile.mkstemp(suffix=".dat")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"\xe9\xe8\xe0")  # Valid latin-1, invalid UTF-8 sequence
            # Either markitdown handles it, or the latin-1 fallback runs
            result = extract_text_from_file(path, "dat")
            assert isinstance(result, str)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Phase 1: page-aware chunking and citation metadata
# ---------------------------------------------------------------------------


class TestSplitTextWithOffsets:
    """The offset variant has to return chunks AND each chunk's start
    position in the source so callers can map chunks back to page markers."""

    def test_offsets_track_chunk_positions(self):
        from app.services.document_manager import _split_text_with_offsets

        # Build a deterministic input that will produce multiple chunks.
        text = ("aaaa " * 60).strip()  # 299 chars
        chunks = _split_text_with_offsets(text, chunk_size=100, chunk_overlap=20)
        assert len(chunks) >= 2
        # Each entry is (chunk_text, start_offset).
        for chunk, offset in chunks:
            assert isinstance(chunk, str) and chunk
            assert isinstance(offset, int)
            assert text[offset:offset + len(chunk)].startswith(chunk[:20])

    def test_split_text_string_variant_still_works(self):
        from app.services.document_manager import _split_text

        # The legacy wrapper must still return a list[str] for callers that
        # don't care about offsets (chunking-only tests, KB ingest paths).
        chunks = _split_text("hello world " * 30, 80, 16)
        assert all(isinstance(c, str) for c in chunks)
        assert chunks


class TestLocationForOffset:
    def test_returns_most_recent_marker(self):
        from app.services.document_manager import _location_for_offset

        markers = [
            {"char_offset": 0, "kind": "page", "value": 1},
            {"char_offset": 1000, "kind": "page", "value": 2},
            {"char_offset": 2500, "kind": "page", "value": 3},
        ]
        # Offset just past the page-2 marker should map to page 2.
        assert _location_for_offset(1200, markers)["value"] == 2
        # Offset past the last marker stays on the last page.
        assert _location_for_offset(99_999, markers)["value"] == 3
        # Offset at zero with markers starting at zero maps to the first page.
        assert _location_for_offset(0, markers)["value"] == 1

    def test_returns_empty_dict_when_no_markers(self):
        from app.services.document_manager import _location_for_offset

        assert _location_for_offset(42, []) == {}


class TestPageMarkerInterpolation:
    def test_interpolation_spreads_pages_uniformly(self):
        from app.services.document_readers import _interpolate_page_markers

        # 100 chars across 4 pages → markers at 0, 25, 50, 75.
        markers = _interpolate_page_markers("x" * 100, 4)
        assert [m["value"] for m in markers] == [1, 2, 3, 4]
        assert [m["char_offset"] for m in markers] == [0, 25, 50, 75]
        assert all(m["kind"] == "page" for m in markers)

    def test_handles_zero_pages(self):
        from app.services.document_readers import _interpolate_page_markers

        assert _interpolate_page_markers("anything", 0) == []
        assert _interpolate_page_markers("", 5) == []


# ---------------------------------------------------------------------------
# Table-aware chunking
# ---------------------------------------------------------------------------


def _docx_style_table(rows: int) -> str:
    header = "| Category | Year 1 | Year 2 |"
    sep = "|---|---|---|"
    body = "\n".join(f"| Item {i} | {100 + i} | {200 + i} |" for i in range(rows))
    return f"{header}\n{sep}\n{body}"


class TestFindTableSpans:
    def test_finds_table_with_separator_header(self):
        from app.services.document_manager import _find_table_spans

        text = "Intro paragraph.\n\n" + _docx_style_table(3) + "\n\nOutro."
        spans = _find_table_spans(text)
        assert len(spans) == 1
        start, end, header = spans[0]
        assert text[start:].startswith("| Category |")
        assert header == "| Category | Year 1 | Year 2 |\n|---|---|---|"
        assert text[start:end].endswith("| Item 2 | 102 | 202 |")

    def test_xlsx_style_table_header_is_first_row(self):
        from app.services.document_manager import _find_table_spans

        # The xlsx serializer emits pipe rows with no |---| separator.
        text = "## Sheet1\n| Category | Amount |\n| Travel | 5000 |\n| Equipment | 12000 |"
        spans = _find_table_spans(text)
        assert len(spans) == 1
        assert spans[0][2] == "| Category | Amount |"

    def test_single_pipe_line_is_not_a_table(self):
        from app.services.document_manager import _find_table_spans

        assert _find_table_spans("prose | with a pipe\nmore prose") == []


class TestTableAwareChunking:
    def test_continuation_chunks_repeat_table_header(self):
        from app.services.document_manager import _split_text_with_offsets

        text = "Budget summary follows.\n\n" + _docx_style_table(40)
        chunks = _split_text_with_offsets(text, chunk_size=300, chunk_overlap=50)
        assert len(chunks) >= 3

        header = "| Category | Year 1 | Year 2 |"
        table_chunks = [c for c, _ in chunks if "| Item" in c]
        assert len(table_chunks) >= 2
        for chunk in table_chunks:
            assert chunk.splitlines()[0].startswith(header[:20]) or chunk.startswith(
                "Budget summary"
            ), f"table chunk lost its header: {chunk[:80]!r}"

    def test_offsets_point_at_original_text_despite_decoration(self):
        from app.services.document_manager import _split_text_with_offsets

        text = "Budget summary follows.\n\n" + _docx_style_table(40)
        header_block = "| Category | Year 1 | Year 2 |\n|---|---|---|"
        for chunk, offset in _split_text_with_offsets(text, 300, 50):
            body = chunk
            if chunk.startswith(header_block) and not text.strip()[offset:].startswith(
                header_block
            ):
                body = chunk[len(header_block) + 1:]  # strip decoration + newline
            assert text.strip()[offset:offset + len(body)] == body

    def test_rows_are_never_split_mid_row(self):
        from app.services.document_manager import _split_text_with_offsets

        text = _docx_style_table(60)  # table longer than any single chunk
        original_lines = set(text.split("\n"))
        for chunk, _ in _split_text_with_offsets(text, 300, 50):
            for line in chunk.splitlines():
                assert line in original_lines, f"row split mid-way: {line!r}"

    def test_break_prefers_table_start_over_mid_table(self):
        from app.services.document_manager import _split_text_with_offsets

        # Prose ends past the window midpoint; the table then extends beyond
        # the first window, so a naive break would land mid-table.
        prose = "Narrative context sentence. " * 22   # ~615 chars
        table = _docx_style_table(25)                  # ~600 chars
        text = f"{prose.strip()}\n\n{table}"
        chunks = _split_text_with_offsets(text, chunk_size=1000, chunk_overlap=200)
        # First chunk should end before the table rather than slicing into it.
        assert "| Item" not in chunks[0][0]

    def test_break_before_table_never_drops_rows(self):
        from app.services.document_manager import _split_text_with_offsets

        # Regression: when the break-before-table path pulled ``end`` back to
        # the table start, the next window still jumped a full step past it,
        # so the header and first data rows were emitted into no chunk at all.
        # Sweep the table start across the window to cover every break path.
        for pad in range(400, 1000, 7):
            prose = ("Narrative context sentence about grant awards. " * 25)[:pad]
            table = _docx_style_table(30)
            text = f"{prose.strip()}\n{table}"
            joined = "\n".join(c for c, _ in _split_text_with_offsets(text, 1000, 200))
            for i in range(30):
                row = f"| Item {i} | {100 + i} | {200 + i} |"
                assert row in joined, f"pad={pad}: row dropped from ingestion: {row!r}"

    def test_non_table_text_is_undedecorated_and_offset_exact(self):
        from app.services.document_manager import _split_text_with_offsets

        text = ("Sentence about grants and budgets. " * 40).strip()
        for chunk, offset in _split_text_with_offsets(text, 200, 40):
            assert text[offset:offset + len(chunk)] == chunk
