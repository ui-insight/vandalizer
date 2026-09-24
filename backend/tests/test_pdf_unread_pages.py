"""A PDF page no reader gets text from must not vanish silently.

Support ticket: a 2-page budget ledger whose totals page the fast reader
flagged "needs OCR" was stored as complete with page 1 only — the viewer
showed both pages, the AI's copy had one, and nothing said so.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services import document_readers as dr
from app.services import document_service

BODY = "\n".join(
    f"Line item {i}: Personnel salary and fringe benefits allocation {1000 + i * 37}.00"
    for i in range(30)
)
TOTALS = "TOTALS\nTotal direct costs 412,993.00\nGrand total 623,619.43"


def _ledger(tmp_path, *, totals_as_image: bool, label: str | None = None) -> str:
    """Page 1 is text; page 2 is the totals page, as text or as a picture."""
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((50, 60), BODY, fontsize=9)
    page2 = doc.new_page()
    if totals_as_image:
        src = pymupdf.open()
        sp = src.new_page()
        sp.insert_text((50, 60), TOTALS, fontsize=14)
        page2.insert_image(page2.rect, stream=sp.get_pixmap(dpi=100).tobytes("png"))
        if label:
            page2.insert_text((50, 800), label, fontsize=8)
    else:
        page2.insert_text((50, 60), TOTALS, fontsize=11)
    path = tmp_path / "ledger.pdf"
    doc.save(str(path))
    return str(path)


def _read(path):
    report: dict = {}
    # No OCR service in tests; "" is the empty-200 an unhealthy service
    # returns, which is the branch that fell back and dropped the page.
    with patch.object(dr, "ocr_extract_text_from_pdf", return_value=""):
        text, markers = dr._extract_pdf_text_and_markers(path, report=report)
    return text, [m["value"] for m in markers], report


class TestReader:
    def test_a_page_no_reader_can_read_is_reported(self, tmp_path):
        text, pages, report = _read(_ledger(tmp_path, totals_as_image=True))
        assert pages == [1]
        assert report["unread_pages"] == [2]

    def test_a_picture_under_a_page_label_is_still_unread(self, tmp_path):
        """A stamp or "Page 2 of 2" on top of a scanned page is not a reading of it."""
        _, pages, report = _read(_ledger(tmp_path, totals_as_image=True, label="Page 2 of 2"))
        assert report["unread_pages"] == [2]

    def test_a_readable_document_reports_nothing(self, tmp_path):
        text, pages, report = _read(_ledger(tmp_path, totals_as_image=False))
        assert pages == [1, 2]
        assert "Grand total" in text
        assert "unread_pages" not in report

    def test_a_blank_page_is_not_unread(self, tmp_path):
        import pymupdf

        doc = pymupdf.open()
        doc.new_page().insert_text((50, 60), BODY, fontsize=9)
        doc.new_page()
        path = tmp_path / "blank.pdf"
        doc.save(str(path))
        _, pages, report = _read(str(path))
        assert pages == [1]
        assert "unread_pages" not in report

    def test_an_undrawn_image_resource_does_not_make_a_blank_page_unread(self):
        """get_images() lists shared resources a page never draws; ink decides."""
        white = SimpleNamespace(samples=bytes([255]) * 64)
        page = SimpleNamespace(
            rect=__import__("pymupdf").Rect(0, 0, 612, 792),
            number=1,
            get_image_info=lambda: [],
            get_images=lambda full=False: [(7, 0, 100, 100, 8, "DeviceRGB", "", "Im0", "")],
            get_pixmap=lambda **kw: white,
        )
        assert dr._page_has_unread_content(page, "") is False


class TestFastPath:
    """The classifier is a light pass; the full parse can still flag a page
    and hand it back with empty Markdown. That page used to be skipped."""

    CLEAN = SimpleNamespace(pdf_type="text_based", confidence=1.0, pages_needing_ocr=[])

    def _result(self, pages, pages_needing_ocr=()):
        return SimpleNamespace(
            pages=[SimpleNamespace(page=i, markdown=md, needs_ocr=flag, ocr_reason=None)
                   for i, (md, flag) in enumerate(pages)],
            pages_needing_ocr=list(pages_needing_ocr),
            pages_with_tables=[],
        )

    def _fast(self, path, result):
        import pdf_inspector

        with patch.object(pdf_inspector, "extract_pages_markdown", return_value=result):
            return dr._local_markdown_extract_from_pdf(path, self.CLEAN)

    def test_a_page_flagged_by_the_full_parse_declines_the_fast_path(self, tmp_path):
        path = _ledger(tmp_path, totals_as_image=False)
        result = self._result([(BODY, False), ("", True)], pages_needing_ocr=[2])
        # None sends the document down the OCR path, which reads page 2.
        assert self._fast(path, result) is None

    def test_the_per_page_flag_alone_is_enough(self, tmp_path):
        path = _ledger(tmp_path, totals_as_image=False)
        assert self._fast(path, self._result([(BODY, False), ("", True)])) is None

    def test_an_empty_page_that_is_not_blank_declines(self, tmp_path):
        path = _ledger(tmp_path, totals_as_image=False)
        assert self._fast(path, self._result([(BODY, False), ("", False)])) is None

    def test_a_blank_page_does_not_decline(self, tmp_path):
        import pymupdf

        doc = pymupdf.open()
        doc.new_page().insert_text((50, 60), BODY, fontsize=9)
        doc.new_page()
        path = tmp_path / "blank.pdf"
        doc.save(str(path))
        out = self._fast(str(path), self._result([(BODY, False), ("", False)]))
        assert out is not None
        assert [m["value"] for m in out[1]] == [1]


class TestWarning:
    def _doc(self, pages):
        return SimpleNamespace(ingestion_warnings=["unread_pages"], unread_pages=pages)

    def test_names_the_pages(self):
        assert document_service.ingestion_warning_text(self._doc([2])) == (
            "page 2 could not be read and is missing from its text"
        )
        assert "pages 2, 5 could not be read" in document_service.ingestion_warning_text(self._doc([2, 5]))

    def test_without_page_numbers_it_still_reads(self):
        assert "some pages could not be read" in document_service.ingestion_warning_text(self._doc([]))

    def test_counts_as_incomplete(self):
        assert document_service.is_partially_ingested(self._doc([2])) is True


@patch("app.tasks.document_tasks.get_sync_db")
@patch("app.config.Settings")
def test_task_stores_the_warning_and_the_pages(MockSettings, mock_get_db):
    from unittest.mock import MagicMock

    from app.tasks.document_tasks import perform_extraction_and_update

    db = MagicMock()
    mock_get_db.return_value = db
    db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "ledger.pdf"}
    MockSettings.return_value = MagicMock(upload_dir="/uploads")

    def read(*_a, report, **_kw):
        report["unread_pages"] = [2]
        return BODY, [{"char_offset": 0, "kind": "page", "value": 1}]

    with patch("app.services.document_readers.extract_text_with_markers", side_effect=read), \
         patch("app.services.document_readers.pdf_page_count", return_value=2):
        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

    update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
    assert "unread_pages" in update_set["ingestion_warnings"]
    assert update_set["unread_pages"] == [2]
