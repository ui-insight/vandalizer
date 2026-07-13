"""Tests for pure helpers in app.services.document_readers.

The heavy readers (pymupdf, markitdown, formulas) are tested elsewhere via
integration; this file covers the deterministic cell-formatting, markdown
sanitation, and DOCX-extras helpers that have no external side effects.
"""

from __future__ import annotations

import datetime
import zipfile

import pytest

from app.services.document_readers import (
    _format_xlsx_cell,
    clean_markdown_nans,
    extract_docx_extras,
    pdf_has_ocrable_content,
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


def _save_pdf(doc, tmp_path, name: str) -> str:
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return str(path)


class TestPdfHasOcrableContent:
    """Blank-page precheck: the OCR endpoint is a vision LLM that fabricates
    plausible text when handed a blank page, so PDFs must prove they have
    something to read before OCR runs. Rendering is the ground truth — a page
    that rasterizes to uniform white gives OCR nothing real to transcribe."""

    def test_blank_page_has_no_content(self, tmp_path):
        import pymupdf
        doc = pymupdf.open()
        doc.new_page()
        path = _save_pdf(doc, tmp_path, "blank.pdf")
        assert pdf_has_ocrable_content(path) is False

    def test_multiple_blank_pages_have_no_content(self, tmp_path):
        import pymupdf
        doc = pymupdf.open()
        for _ in range(3):
            doc.new_page()
        path = _save_pdf(doc, tmp_path, "blanks.pdf")
        assert pdf_has_ocrable_content(path) is False

    def test_text_layer_counts_as_content(self, tmp_path):
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello world")
        path = _save_pdf(doc, tmp_path, "text.pdf")
        assert pdf_has_ocrable_content(path) is True

    def test_embedded_image_counts_as_content(self, tmp_path):
        """A scanned page has no text layer but must still go to OCR."""
        import pymupdf
        img = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10))
        img.clear_with(0)  # solid black square
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(72, 72, 172, 172), pixmap=img)
        path = _save_pdf(doc, tmp_path, "scan.pdf")
        assert pdf_has_ocrable_content(path) is True

    def test_vector_ink_counts_as_content(self, tmp_path):
        """Outlined/vector text has no text layer and no images — it is only
        drawings. The raster pass must see its ink and let OCR run."""
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.draw_rect(
            pymupdf.Rect(72, 72, 200, 100), color=(0, 0, 0), fill=(0, 0, 0)
        )
        path = _save_pdf(doc, tmp_path, "vector.pdf")
        assert pdf_has_ocrable_content(path) is True

    def test_white_background_rect_is_still_blank(self, tmp_path):
        """A decorative white rectangle is a drawing, but renders as blank
        paper — structurally non-empty, visually empty. Must not reach OCR."""
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.draw_rect(
            pymupdf.Rect(0, 0, 612, 792), color=(1, 1, 1), fill=(1, 1, 1)
        )
        path = _save_pdf(doc, tmp_path, "white_rect.pdf")
        assert pdf_has_ocrable_content(path) is False

    def test_one_content_page_among_blanks_counts(self, tmp_path):
        import pymupdf
        doc = pymupdf.open()
        doc.new_page()
        page2 = doc.new_page()
        page2.insert_text((72, 72), "Only page 2 has text")
        path = _save_pdf(doc, tmp_path, "mixed.pdf")
        assert pdf_has_ocrable_content(path) is True

    def test_unreadable_file_fails_open(self, tmp_path):
        """A file PyMuPDF can't open must not be declared blank — OCR still
        gets its chance on odd-but-valid PDFs."""
        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"this is not a pdf")
        assert pdf_has_ocrable_content(str(junk)) is True


class TestBlankPdfSkipsOcr:
    """Blank PDFs must return empty text WITHOUT calling the OCR endpoint,
    so the empty-text guard in perform_extraction_and_update marks the
    document as an error instead of storing fabricated content."""

    def _blank_pdf(self, tmp_path) -> str:
        import pymupdf
        doc = pymupdf.open()
        doc.new_page()
        return _save_pdf(doc, tmp_path, "blank.pdf")

    def test_extract_text_with_markers_skips_ocr(self, tmp_path):
        from unittest.mock import patch
        import app.services.document_readers as dr

        path = self._blank_pdf(tmp_path)
        with patch.object(dr, "ocr_extract_text_from_pdf") as mock_ocr:
            text, markers = dr.extract_text_with_markers(path, "pdf")

        assert text == ""
        assert markers == []
        mock_ocr.assert_not_called()

    def test_extract_text_from_file_skips_ocr(self, tmp_path):
        from unittest.mock import patch
        import app.services.document_readers as dr

        path = self._blank_pdf(tmp_path)
        with patch.object(dr, "ocr_extract_text_from_pdf") as mock_ocr:
            result = dr.extract_text_from_file(path, "pdf")

        assert result == ""
        mock_ocr.assert_not_called()

    def test_pdf_with_text_still_reaches_ocr(self, tmp_path):
        """Regression guard: the precheck must not block normal PDFs."""
        from unittest.mock import patch
        import pymupdf
        import app.services.document_readers as dr

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Real document text")
        path = _save_pdf(doc, tmp_path, "real.pdf")

        ocr_result = "x" * 200  # long enough to pass MIN_PDF_TEXT_LENGTH
        with patch.object(
            dr, "ocr_extract_text_from_pdf", return_value=ocr_result
        ) as mock_ocr:
            text, _ = dr.extract_text_with_markers(path, "pdf")

        mock_ocr.assert_called_once()
        assert text == ocr_result


class TestExtractWithMarkersOcrFallback:
    """When OCR returns short-but-valid text and the PyMuPDF page-boundary
    refinement fails (corrupt PDF, or the source file removed mid-processing),
    the OCR text must be used rather than crashing the extraction task."""

    def test_pymupdf_failure_uses_ocr_text(self):
        from unittest.mock import patch
        import app.services.document_readers as dr

        with patch.object(dr, "ocr_extract_text_from_pdf", return_value="short ocr text"), \
             patch.object(dr, "_pymupdf_extract_with_pages",
                          side_effect=FileNotFoundError("no such file: 'gone.pdf'")), \
             patch.object(dr, "_pdf_page_count", return_value=1):
            text, markers = dr.extract_text_with_markers("gone.pdf", "pdf")

        assert text == "short ocr text"
        assert isinstance(markers, list)

    def test_pymupdf_failure_reraises_without_ocr_text(self):
        from unittest.mock import patch
        import app.services.document_readers as dr

        with patch.object(dr, "ocr_extract_text_from_pdf", return_value=""), \
             patch.object(dr, "_pymupdf_extract_with_pages",
                          side_effect=FileNotFoundError("no such file: 'gone.pdf'")):
            with pytest.raises(FileNotFoundError):
                dr.extract_text_with_markers("gone.pdf", "pdf")

    def test_extract_text_from_file_pymupdf_failure_uses_ocr_text(self):
        from unittest.mock import patch
        import app.services.document_readers as dr

        with patch.object(dr, "ocr_extract_text_from_pdf", return_value="short ocr text"), \
             patch.object(dr, "extract_text_from_pdf",
                          side_effect=FileNotFoundError("no such file: 'gone.pdf'")):
            assert dr.extract_text_from_file("gone.pdf", "pdf") == "short ocr text"

class TestExtractTextFromFileMissingFile:
    """A missing source file (deleted mid-processing / stale path) is benign:
    return empty text and log at warning, never error -> Sentry, and never a
    "[Error extracting content: ...]" placeholder that masquerades as content."""

    def test_missing_txt_returns_empty_and_warns(self, tmp_path):
        from unittest.mock import patch
        import app.services.document_readers as dr

        gone = str(tmp_path / "nope" / "8D112.txt")  # nonexistent
        with patch.object(dr, "logger") as mock_logger:
            result = dr.extract_text_from_file(gone, "txt")

        assert result == ""
        assert "[Error extracting content" not in result
        mock_logger.error.assert_not_called()
        mock_logger.warning.assert_called()
