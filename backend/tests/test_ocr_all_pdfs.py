"""OCR_ALL_PDFS: every PDF is read by OCR, and nothing else is ever stored.

The PDF here is a clean, digitally-born page — exactly the kind the local
fast path would normally take — so each test also proves the fast path and
the PyMuPDF fallback are never consulted.
"""

from unittest.mock import patch

import pymupdf
import pytest

from app.services import document_readers as dr
from app.services import ocr_client

BODY = "Budget justification for the cryo-EM project. " * 20


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), BODY, fontsize=11)
    doc.save(str(path))
    doc.close()
    return str(path)


def _no_local(*_a, **_k):
    raise AssertionError("a local reading was consulted under OCR_ALL_PDFS")


def _read(pdf, ocr, report=None, **kw):
    report = {} if report is None else report
    with patch.object(dr, "_ocr_all_pdfs", return_value=True), \
         patch.object(dr, "ocr_extract_text_from_pdf", side_effect=ocr), \
         patch.object(dr, "_local_markdown_extract_from_pdf", side_effect=_no_local), \
         patch.object(dr, "_fast_path_with_page_ocr", side_effect=_no_local), \
         patch.object(dr, "_pymupdf_extract_with_pages", side_effect=_no_local), \
         patch.object(dr, "_local_reading_for_ocr_outage", side_effect=_no_local):
        return dr._read_pdf_text_and_markers(pdf, report=report, **kw), report


def test_digital_pdf_still_goes_to_ocr_with_exact_page_markers(pdf):
    def ocr(path, report=None):
        report["ocr_completed"] = True
        return "<!-- page 1 -->\n\nOCR reading of the page."

    (text, markers), _ = _read(pdf, ocr)
    assert text == "OCR reading of the page."
    assert markers == [{"char_offset": 0, "kind": "page", "value": 1}]


def test_short_ocr_text_is_kept(pdf):
    def ocr(path, report=None):
        report["ocr_completed"] = True
        return "Signed."

    (text, _), _ = _read(pdf, ocr)
    assert text == "Signed."


def test_ocr_never_ran_fails_loudly(pdf):
    def ocr(path, report=None):
        report["ocr_skipped"] = "unconfigured"
        return ""

    with pytest.raises(dr.DocumentReadError, match="unconfigured"):
        _read(pdf, ocr)


def test_ocr_permanently_rejected_fails_loudly(pdf):
    with pytest.raises(dr.DocumentReadError, match="OCR service did not read"):
        _read(pdf, lambda path, report=None: "")


def test_ocr_read_nothing_stores_nothing(pdf):
    def ocr(path, report=None):
        report["ocr_completed"] = True
        return ""

    (text, markers), report = _read(pdf, ocr)
    assert (text, markers) == ("", [])
    assert report["text_layer_rejected"] is True
    assert report["text_layer_rejected_reason"] == "ocr_all_pdfs"


def test_outage_on_final_attempt_still_raises(pdf):
    def ocr(path, report=None):
        raise ocr_client.OcrUnavailableError("down")

    with pytest.raises(ocr_client.OcrUnavailableError):
        _read(pdf, ocr, local_on_ocr_outage=True)


def test_setting_off_keeps_default_flow(pdf):
    with patch.object(dr, "_ocr_all_pdfs", return_value=False), \
         patch.object(dr, "ocr_extract_text_from_pdf", side_effect=AssertionError("OCR called")), \
         patch.object(dr, "_local_markdown_extract_from_pdf", return_value=("local", [])):
        text, _ = dr._read_pdf_text_and_markers(pdf, report={})
    assert text == "local"
