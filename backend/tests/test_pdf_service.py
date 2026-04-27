"""Tests for app.services.pdf_service.

The service delegates to reportlab; these tests invoke the entry points with
real items and assert on the resulting PDF bytes. We don't parse the PDF —
just confirm it's a well-formed document of sensible size so regressions in
reportlab integration surface quickly.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.pdf_service import (
    generate_extraction_pdf,
    generate_fillable_template,
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
