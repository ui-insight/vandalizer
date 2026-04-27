"""Tests for pure helpers in app.services.document_readers.

The heavy readers (pymupdf, markitdown, formulas) are tested elsewhere via
integration; this file covers the deterministic cell-formatting, markdown
sanitation, and DOCX-extras helpers that have no external side effects.
"""

from __future__ import annotations

import datetime
import io
import zipfile

import pytest

from app.services.document_readers import (
    _format_xlsx_cell,
    clean_markdown_nans,
    extract_docx_extras,
    remove_images_from_markdown,
)


class TestCleanMarkdownNans:
    def test_strips_nan_cells_and_literal_nan_tokens(self):
        content = "| A | NaN |\n| NaN |\n| value | NaN |"
        # First line has a real value A, NaN gets blanked and kept
        # Second line has only NaN → empty row, dropped
        # Third has a value, kept
        result = clean_markdown_nans(content)
        assert "NaN" not in result
        assert "value" in result
        assert "| A |" in result

    def test_preserves_separator_rows(self):
        # Separator rows (--- in every cell) should survive even though
        # they don't contain "real" values.
        result = clean_markdown_nans("| --- | --- |")
        assert "---" in result

    def test_passes_through_non_table_lines_untouched(self):
        result = clean_markdown_nans("Intro paragraph\n\n## Header\n\nPlain text")
        assert "Intro paragraph" in result
        assert "## Header" in result
        assert "Plain text" in result

    def test_all_nan_row_strips_nan_tokens_but_keeps_line(self):
        # The filter's second branch (all cells "---" or empty) keeps
        # pipe-only rows even after NaN scrubbing.
        result = clean_markdown_nans("| NaN | NaN |")
        assert "NaN" not in result
        assert "|" in result


class TestRemoveImagesFromMarkdown:
    def test_inline_image_syntax_removed(self):
        md = "Before ![alt](http://example.com/pic.png) after"
        result = remove_images_from_markdown(md)
        assert "!" not in result
        assert "http://example.com/pic.png" not in result
        assert "Before" in result
        assert "after" in result

    def test_reference_style_image_removed(self):
        md = "Text ![alt][ref] more\n\n[ref]: http://x/y.png"
        result = remove_images_from_markdown(md)
        assert "![alt][ref]" not in result
        # The link reference definition is also scrubbed
        assert "[ref]:" not in result

    def test_attribute_blocks_removed(self):
        md = 'Heading {width="100" height="200"}'
        result = remove_images_from_markdown(md)
        assert "width=" not in result
        assert "height=" not in result

    def test_whitespace_and_blank_lines_collapsed(self):
        md = "Line 1\n\n\n\n\nLine 2"
        result = remove_images_from_markdown(md)
        # Three or more blank lines should collapse to two (one blank)
        assert "\n\n\n" not in result


class TestFormatXlsxCell:
    def test_none_becomes_empty_string(self):
        assert _format_xlsx_cell(None) == ""

    def test_bool_formatted_as_uppercase_words(self):
        assert _format_xlsx_cell(True) == "TRUE"
        assert _format_xlsx_cell(False) == "FALSE"

    def test_datetime_with_zero_time_renders_date_only(self):
        dt = datetime.datetime(2026, 1, 5, 0, 0, 0)
        assert _format_xlsx_cell(dt) == "2026-01-05"

    def test_datetime_with_time_renders_with_space_separator(self):
        dt = datetime.datetime(2026, 1, 5, 9, 30, 15)
        result = _format_xlsx_cell(dt)
        assert result.startswith("2026-01-05 09:30:15")

    def test_date_instance_uses_isoformat(self):
        assert _format_xlsx_cell(datetime.date(2026, 3, 5)) == "2026-03-05"

    def test_time_instance_uses_isoformat(self):
        assert _format_xlsx_cell(datetime.time(10, 15, 0)) == "10:15:00"

    def test_integer_float_renders_without_decimal(self):
        assert _format_xlsx_cell(42.0) == "42"

    def test_fractional_float_trims_trailing_zeros(self):
        assert _format_xlsx_cell(3.1400) == "3.14"

    def test_float_rounds_to_four_decimals(self):
        assert _format_xlsx_cell(1.23456789) == "1.2346"

    def test_zero_float_preserved(self):
        assert _format_xlsx_cell(0.0) == "0"

    def test_string_pipes_escaped(self):
        assert _format_xlsx_cell("a|b") == r"a\|b"

    def test_string_backslashes_doubled(self):
        # Backslash escaping runs first; pipes still get escaped after
        assert _format_xlsx_cell("a\\b|c") == r"a\\b\|c"

    def test_string_newlines_collapsed_to_spaces_and_trimmed(self):
        assert _format_xlsx_cell("  line1\nline2  ") == "line1 line2"


class TestExtractDocxExtras:
    def test_missing_file_returns_empty_string(self, tmp_path):
        missing = tmp_path / "does_not_exist.docx"
        assert extract_docx_extras(str(missing)) == ""

    def test_non_zip_file_returns_empty_string(self, tmp_path):
        junk = tmp_path / "not-a-docx.docx"
        junk.write_bytes(b"this is clearly not a zip")
        assert extract_docx_extras(str(junk)) == ""

    def test_empty_docx_without_comments_or_revisions_returns_empty(self, tmp_path):
        """A valid zip with no word/ entries yields no extras."""
        docx = tmp_path / "empty.docx"
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr("[Content_Types].xml", "<x/>")
        assert extract_docx_extras(str(docx)) == ""

    def test_docx_with_comment_produces_markdown_section(self, tmp_path):
        """Build a minimal DOCX with one comment, confirm it surfaces."""
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        comments_xml = (
            f'<w:comments xmlns:w="{ns}">'
            f'  <w:comment w:author="Reviewer A" w:date="2026-03-01">'
            f'    <w:p><w:r><w:t>This needs revision.</w:t></w:r></w:p>'
            f'  </w:comment>'
            f'</w:comments>'
        )
        docx = tmp_path / "with_comments.docx"
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr("word/comments.xml", comments_xml)

        out = extract_docx_extras(str(docx))
        assert "## Comments" in out
        assert "Reviewer A" in out
        assert "This needs revision" in out

    def test_malformed_comments_xml_swallowed_without_crash(self, tmp_path):
        """Invalid XML in word/comments.xml triggers the ParseError branch."""
        docx = tmp_path / "bad_xml.docx"
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr("word/comments.xml", "<not valid xml")
        # Should return cleanly (possibly empty), not raise.
        extract_docx_extras(str(docx))

    def test_defusedxml_is_in_use(self):
        # Regression guard: the file's import line swap was the fix for
        # Bandit B314. If someone reverts it, this test flags it.
        import app.services.document_readers as dr
        source = dr.__loader__.get_source(dr.__name__) or ""
        assert "defusedxml.ElementTree" in source
        assert "import xml.etree.ElementTree as ET" not in source
