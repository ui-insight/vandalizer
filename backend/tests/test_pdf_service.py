"""Tests for app.services.pdf_service.

The service delegates to reportlab; these tests invoke the entry points with
real items and assert on the resulting PDF bytes. We don't parse the PDF —
just confirm it's a well-formed document of sensible size so regressions in
reportlab integration surface quickly.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.pdf_service import (
    _format_inline,
    _normalize_for_pdf,
    generate_extraction_pdf,
    generate_fillable_template,
    render_workflow_pdf,
)


def _item(searchphrase: str, title: str | None = None) -> SimpleNamespace:
    """Shape-compatible stand-in for SearchSetItem used by pdf_service."""
    return SimpleNamespace(searchphrase=searchphrase, title=title)


class TestGenerateFillableTemplate:
    def test_returns_valid_pdf_with_indexed_field_names(self):
        items = [_item("pi_name", "PI Name"), _item("award_amount")]
        pdf_bytes, field_names = generate_fillable_template("Grant Fields", items)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 500
        assert field_names == ["field_0", "field_1"]

    def test_empty_items_still_produces_pdf(self):
        pdf_bytes, field_names = generate_fillable_template("Empty", [])
        assert pdf_bytes.startswith(b"%PDF-")
        assert field_names == []

    def test_missing_title_falls_back_to_extraction_template(self):
        # Empty title should not crash; a placeholder is used instead.
        pdf_bytes, _ = generate_fillable_template("", [_item("field_a")])
        assert pdf_bytes.startswith(b"%PDF-")

    def test_many_fields_trigger_page_break(self):
        # 30 fields on letter-sized pages with ~48pt per row guarantees at
        # least one page break, exercising the c.showPage() branch.
        items = [_item(f"f_{i}") for i in range(30)]
        pdf_bytes, field_names = generate_fillable_template("Many", items)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(field_names) == 30
        # A multi-page PDF is noticeably larger than a one-page one.
        assert len(pdf_bytes) > 2000

    def test_item_with_neither_title_nor_searchphrase_uses_fallback_label(self):
        # Both title and searchphrase empty → label becomes "Field N".
        # The PDF still generates; we just verify it doesn't crash.
        pdf_bytes, names = generate_fillable_template("Fallback", [_item("", None)])
        assert pdf_bytes.startswith(b"%PDF-")
        assert names == ["field_0"]


class TestGenerateExtractionPdf:
    def test_report_pdf_contains_header_and_rows(self):
        items = [_item("pi", "PI"), _item("amount", "Amount")]
        results = {"pi": "Jane Doe", "amount": "$500,000"}
        pdf = generate_extraction_pdf(
            "NSF Budget", items, results, ["proposal.pdf"],
        )
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 1000

    def test_missing_result_for_field_is_blank(self):
        items = [_item("k1", "Key 1"), _item("k2", "Key 2")]
        pdf = generate_extraction_pdf("T", items, {"k1": "v1"}, [])
        assert pdf.startswith(b"%PDF-")

    def test_no_documents_omits_documents_meta_segment(self):
        items = [_item("k", "K")]
        pdf = generate_extraction_pdf("T", items, {"k": "v"}, [])
        assert pdf.startswith(b"%PDF-")

    def test_title_only_item_renders_without_searchphrase_label(self):
        # When item.title is truthy, it's used as label.
        items = [_item("internal_key", "Pretty Label")]
        pdf = generate_extraction_pdf("T", items, {"internal_key": "val"}, [])
        assert pdf.startswith(b"%PDF-")

    def test_searchphrase_used_when_title_empty(self):
        items = [_item("just_a_key", None)]
        pdf = generate_extraction_pdf("T", items, {"just_a_key": "v"}, ["a.pdf", "b.pdf"])
        assert pdf.startswith(b"%PDF-")


class TestNormalizeForPdf:
    def test_non_breaking_hyphen_becomes_ascii(self):
        # U+2011 is outside Helvetica's WinAnsi encoding and rendered as ■.
        assert _normalize_for_pdf("non‑expert") == "non-expert"

    def test_minus_sign_and_figure_dash_normalize(self):
        assert _normalize_for_pdf("a−b‒c‐d") == "a-b-c-d"

    def test_zero_width_chars_are_stripped(self):
        assert _normalize_for_pdf("a​b­c﻿d") == "abcd"

    def test_regular_dashes_are_preserved(self):
        # Regular hyphen, en-dash, em-dash are in WinAnsi and render fine.
        text = "a-b – c — d"
        assert _normalize_for_pdf(text) == text

    def test_workflow_pdf_handles_non_breaking_hyphens(self):
        # End-to-end smoke test for the bug being fixed.
        md = "• Be a non‑expert\n• Drive cross‑functional teams"
        pdf = render_workflow_pdf(md, title="Workflow Results")
        assert pdf.startswith(b"%PDF-")


class TestFormatInline:
    def test_triple_asterisk_produces_nested_bold_italic(self):
        # The bug: bold regex would non-greedily consume one leading `*`,
        # leaving stray `*`s that the italic regex paired *across* `</b>`,
        # producing `<b><i>x</b></i>` and crashing reportlab.
        assert _format_inline("***REQUIRED Components***") == "<b><i>REQUIRED Components</i></b>"

    def test_triple_underscore_produces_nested_bold_italic(self):
        assert _format_inline("___emphasis___") == "<b><i>emphasis</i></b>"

    def test_double_asterisk_still_renders_bold(self):
        assert _format_inline("**bold**") == "<b>bold</b>"

    def test_single_asterisk_still_renders_italic(self):
        assert _format_inline("*italic*") == "<i>italic</i>"

    def test_workflow_pdf_with_triple_asterisk_markdown_does_not_crash(self):
        # Regression: production crash on `***REQUIRED Components***` from
        # an LLM extraction output. Should render cleanly now.
        md = "**DATES**\n\n***REQUIRED Components***\n\nMore body text."
        pdf = render_workflow_pdf(md, title="Workflow Results")
        assert pdf.startswith(b"%PDF-")


def _pdf_text(pdf: bytes) -> str:
    import fitz

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


class TestWorkflowPdfOversizedTables:
    """Tables reportlab can't fit on a page used to fail the whole export."""

    def _flowables(self, headers, rows):
        from app.services.pdf_service import _styles, _table_flowables

        return _table_flowables(headers, rows, _styles(), 470.0)

    def _blocks(self, flowables):
        from reportlab.platypus import Table

        return [f for f in flowables if isinstance(f, Table)]

    def test_table_with_many_columns_renders_every_value(self):
        # 22 columns left each one about a word wide; the header row alone
        # grew taller than the page and reportlab raised LayoutError.
        rows = [{f"column_{c}": f"value-{r}-{c} " + "padding words " * 6 for c in range(22)} for r in range(8)]

        text = _pdf_text(render_workflow_pdf(rows, title="Wide"))

        for r in range(8):
            for c in range(22):
                assert f"value-{r}-{c} " in text
        assert "Row 8 of 8" in text

    def test_many_columns_become_one_block_per_row(self):
        headers = [f"h{i}" for i in range(22)]
        flow = self._flowables(headers, [[f"v{r}-{c}" for c in range(22)] for r in range(3)])

        blocks = self._blocks(flow)
        assert len(blocks) == 3
        # Field/Value header + one line per column.
        assert all(len(b._cellvalues) == 23 for b in blocks)

    def test_markdown_table_with_many_columns_renders(self):
        md = (
            "| " + " | ".join(f"h{i}" for i in range(22)) + " |\n"
            + "|" + "---|" * 22 + "\n"
            + "| " + " | ".join(f"cell{i} some longer text here" for i in range(22)) + " |\n"
        )

        text = _pdf_text(render_workflow_pdf(md, title="Wide markdown"))

        assert "cell0 some" in text and "cell21 some" in text

    def test_nine_to_twelve_short_columns_stay_a_grid(self):
        for cols in (9, 12):
            headers = [f"c{i}" for i in range(cols)]
            flow = self._flowables(headers, [[f"v{i}" for i in range(cols)] for _ in range(40)])
            (grid,) = flow
            assert len(grid._cellvalues) == 41  # header + 40 rows, one table

    def test_nine_columns_of_long_text_become_blocks(self):
        headers = [f"c{i}" for i in range(9)]
        rows = [["a fairly long description of the award " * 8 for _ in range(9)] for _ in range(2)]

        assert len(self._blocks(self._flowables(headers, rows))) == 2

    def test_eight_columns_are_always_a_grid(self):
        headers = [f"c{i}" for i in range(8)]
        rows = [["a fairly long description of the award " * 8 for _ in range(8)]]

        (grid,) = self._flowables(headers, rows)
        assert len(grid._cellvalues) == 2

    def test_wide_table_keeps_columns_that_share_a_header(self):
        headers = ["a (3)", "a", "a"] + [f"h{i}" for i in range(10)]
        (block,) = self._blocks(self._flowables(headers, [[f"v{i}" for i in range(13)]]))

        names = [row[0].getPlainText() for row in block._cellvalues[1:]]
        values = [row[1].getPlainText() for row in block._cellvalues[1:]]
        assert names == headers
        assert values == [f"v{i}" for i in range(13)]

    def test_wide_table_with_ragged_or_no_rows(self):
        headers = [f"h{i}" for i in range(13)]

        (block,) = self._blocks(self._flowables(headers, [["only", "two"]]))
        assert len(block._cellvalues) == 14

        (empty,) = self._flowables(headers, [])
        assert len(empty._cellvalues) == 14

    def test_cell_longer_than_a_page_keeps_every_word(self):
        words = [f"w{i}" for i in range(6000)]
        long_text = " ".join(words)

        for data in ({"summary": long_text}, [{"a": long_text, "b": "x"}]):
            found = set(_pdf_text(render_workflow_pdf(data)).split())
            assert set(words) <= found

    def test_extraction_pdf_value_longer_than_a_page_renders(self):
        pdf = generate_extraction_pdf(
            "Long", [_item("summary", "Summary")], {"summary": "word " * 6000}, ["award.pdf"],
        )
        assert pdf.startswith(b"%PDF-")
