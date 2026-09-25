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


class TestOcrOutage:
    """#955: since #946 an unread page sends the PDF to OCR, so an OCR outage
    failed documents that used to be stored with that page missing. On the
    last attempt a good local reading is stored with the page named."""

    def _read(self, path, *, final=True, ocr_required=False, classification=None):
        from app.services.ocr_client import OcrUnavailableError

        report: dict = {}
        with patch.object(dr, "ocr_extract_text_from_pdf",
                          side_effect=OcrUnavailableError("OCR down")), \
             patch.object(dr, "_classify_pdf", return_value=classification):
            text, markers = dr._extract_pdf_text_and_markers(
                path, report=report, ocr_required=ocr_required,
                local_on_ocr_outage=final,
            )
        return text, [m["value"] for m in markers], report

    def test_final_attempt_stores_the_local_reading_with_the_page_named(self, tmp_path):
        text, pages, report = self._read(_ledger(tmp_path, totals_as_image=True))
        assert "Line item 0" in text
        assert pages == [1]
        assert report["unread_pages"] == [2]
        assert report["ocr_unavailable_local_fallback"] is True

    def test_earlier_attempts_still_raise_for_a_retry(self, tmp_path):
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        with pytest.raises(OcrUnavailableError):
            self._read(_ledger(tmp_path, totals_as_image=True), final=False)

    def test_ocr_required_still_raises(self, tmp_path):
        """A retry forced because the stored text was refused may never
        re-store the local reading, final attempt or not."""
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        with pytest.raises(OcrUnavailableError):
            self._read(_ledger(tmp_path, totals_as_image=True), ocr_required=True)

    def test_low_quality_local_reading_still_raises(self, tmp_path):
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        with patch("app.utils.extraction_quality.nonletter_ratio", return_value=0.9), \
             pytest.raises(OcrUnavailableError):
            self._read(_ledger(tmp_path, totals_as_image=True))

    def test_image_based_verdict_still_raises(self, tmp_path):
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        verdict = SimpleNamespace(pdf_type="image_based", confidence=1.0, pages_needing_ocr=[1])
        with pytest.raises(OcrUnavailableError):
            self._read(_ledger(tmp_path, totals_as_image=True), classification=verdict)

    def test_an_empty_local_reading_still_raises(self, tmp_path):
        """A fully scanned document has nothing local to store."""
        import pymupdf
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        src = pymupdf.open()
        src.new_page().insert_text((50, 60), TOTALS, fontsize=14)
        png = src[0].get_pixmap(dpi=100).tobytes("png")
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_image(page.rect, stream=png)
        path = tmp_path / "scan.pdf"
        doc.save(str(path))
        with pytest.raises(OcrUnavailableError):
            self._read(str(path))

    def test_no_unread_pages_still_raises(self, tmp_path):
        """OCR was wanted for something other than unread pages (a distrusted
        layer on a flagged page): the local reading isn't what was missing."""
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        with pytest.raises(OcrUnavailableError):
            self._read(_ledger(tmp_path, totals_as_image=False))


class TestOcrOutageTask:
    def _run(self, tmp_path, retries):
        from unittest.mock import MagicMock

        from app.services.ocr_client import OcrUnavailableError
        from app.tasks.document_tasks import perform_extraction_and_update

        _ledger(tmp_path, totals_as_image=True)
        db = MagicMock()
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "ledger.pdf"}
        settings = MagicMock(upload_dir=str(tmp_path), extraction_max_nonletter_ratio=0.25)
        task = perform_extraction_and_update
        task.push_request(retries=retries)
        try:
            with patch("app.tasks.document_tasks.get_sync_db", return_value=db), \
                 patch("app.config.Settings", return_value=settings), \
                 patch.object(dr, "ocr_extract_text_from_pdf",
                              side_effect=OcrUnavailableError("OCR down")), \
                 patch("app.tasks.document_tasks._notify_document_processing_failed") as notify:
                out = task.run("doc-1", "pdf")
        finally:
            task.pop_request()
        return out, db, notify

    def test_final_attempt_stores_the_document_with_the_warning(self, tmp_path):
        from app.tasks.document_tasks import perform_extraction_and_update

        out, db, notify = self._run(tmp_path, perform_extraction_and_update.max_retries)
        assert "Line item 0" in out
        written = next(
            c[0][1]["$set"] for c in db.smart_document.update_one.call_args_list
            if "raw_text" in c[0][1].get("$set", {})
        )
        assert written["unread_pages"] == [2]
        assert "unread_pages" in written["ingestion_warnings"]
        assert written.get("task_status") != "error"
        assert not notify.called

    def test_earlier_attempt_still_retries(self, tmp_path):
        import pytest

        from app.services.ocr_client import OcrUnavailableError

        with pytest.raises(OcrUnavailableError):
            self._run(tmp_path, 0)
