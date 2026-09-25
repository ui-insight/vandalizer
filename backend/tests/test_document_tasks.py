"""Tests for app.tasks.document_tasks — document extraction, update, cleanup, and semantic ingestion.

Covers: perform_extraction_and_update,
update_document_fields, _check_folder_watch_automations, cleanup_document,
perform_semantic_ingestion.
"""

from unittest.mock import MagicMock, patch

import pytest

from bson import ObjectId



def _set_containing(db, key):
    """The $set of the write that carried `key`.

    Ingestion writes bookkeeping and the status transition separately (the
    status write is guarded so it cannot resurrect a failed extraction), so
    these look up a write by what it carries rather than by position.
    """
    for call in db.smart_document.update_one.call_args_list:
        payload = call[0][1].get("$set", {})
        if key in payload:
            return payload
    raise AssertionError(f"no update wrote {key!r}")


def _status_sequence(db):
    return [
        call[0][1]["$set"]["task_status"]
        for call in db.smart_document.update_one.call_args_list
        if "task_status" in call[0][1].get("$set", {})
    ]




# ---------------------------------------------------------------------------
# perform_extraction_and_update
# ---------------------------------------------------------------------------


class TestPerformExtractionAndUpdate:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_empty_when_doc_not_found(self, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        result = perform_extraction_and_update(document_uuid="missing", extension="pdf")
        assert result == ""

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("Extracted text content", [{"char_offset": 0, "kind": "page", "value": 1}]),
    )
    def test_extracts_text_for_pdf(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == "Extracted text content"
        # Should set raw_text, token_count, and text_markers (Phase 1 citations).
        update_call = db.smart_document.update_one.call_args_list[-1]
        update_set = update_call[0][1]["$set"]
        assert update_set["raw_text"] == "Extracted text content"
        assert update_set["processing"] is False
        assert update_set["token_count"] > 0
        assert update_set["text_markers"] == [{"char_offset": 0, "kind": "page", "value": 1}]

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("Extracted text content", [{"char_offset": 0, "kind": "page", "value": 1}]),
    )
    def test_ocr_stage_is_written_when_the_reader_reaches_ocr(
        self, mock_extract, MockSettings, mock_get_db,
    ):
        """OCR is where a slow ingestion spends its minutes — up to ~25 during
        an outage — and the UI named "extracting" for all of it. The reader
        hands back a stage callback; the task turns it into a status write."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        # Stand in for the reader deciding the local fast path won't do.
        mock_extract.side_effect = lambda *a, **kw: (
            kw["on_stage"]("ocr"),
            ("Extracted text content", []),
        )[1]

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        stage_writes = [
            c for c in db.smart_document.update_one.call_args_list
            if c[0][1].get("$set", {}).get("task_status") == "ocr"
        ]
        assert len(stage_writes) == 1
        # Written through advance_task_status, so a document that already
        # failed is not quietly un-failed by a stage marker.
        assert stage_writes[0][0][0]["task_status"] == {"$ne": "error"}

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("Extracted text content", [{"char_offset": 0, "kind": "page", "value": 1}]),
    )
    def test_a_failing_stage_write_does_not_fail_the_extraction(
        self, mock_extract, MockSettings, mock_get_db,
    ):
        """Reporting progress must never cost us the document."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        def reader(*a, **kw):
            from app.services.document_readers import _report_stage
            _report_stage(lambda _s: (_ for _ in ()).throw(RuntimeError("mongo gone")), "ocr")
            return ("Extracted text content", [])

        mock_extract.side_effect = reader

        assert perform_extraction_and_update(
            document_uuid="doc-1", extension="pdf",
        ) == "Extracted text content"

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("Extracted text content", [{"char_offset": 0, "kind": "page", "value": 1}]),
    )
    def test_force_ocr_is_passed_to_pdf_reader(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf", force_ocr=True)

        _, call_kwargs = mock_extract.call_args
        assert call_kwargs["force_ocr"] is True
        assert call_kwargs["ocr_required"] is False

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("Extracted text content", [{"char_offset": 0, "kind": "page", "value": 1}]),
    )
    def test_ocr_required_is_passed_to_pdf_reader(self, mock_extract, MockSettings, mock_get_db):
        """The reader is where the two reasons for a forced re-read part
        company, so the reason has to survive the hop through Celery — a task
        that forwards only force_ocr silently re-reads a refused text layer
        the permissive way."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(
            document_uuid="doc-1", extension="pdf", force_ocr=True, ocr_required=True,
        )

        _, call_kwargs = mock_extract.call_args
        assert call_kwargs["ocr_required"] is True

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.convert_to_markdown", return_value="| col1 | col2 |")
    def test_uses_convert_to_markdown_for_xlsx(self, mock_convert, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "data.xlsx"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="xlsx")

        assert result == "| col1 | col2 |"
        mock_convert.assert_called_once()

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_with_markers", side_effect=RuntimeError("corrupt file"))
    def test_handles_extraction_error_gracefully(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "bad.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == ""
        # Should mark the doc as errored with a specific message so the UI
        # can surface the failure rather than rendering an empty document.
        update_call = db.smart_document.update_one.call_args_list[-1]
        update_set = update_call[0][1]["$set"]
        assert update_set["processing"] is False
        assert update_set["task_status"] == "error"
        assert "extraction failed" in update_set["error_message"].lower()
        # Any previously stored quality measurement no longer describes the
        # (now empty) text.
        assert update_set["extraction_nonletter_ratio"] is None

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("Clean extracted budget narrative text.", []),
    )
    def test_clean_extraction_stores_low_nonletter_ratio(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "test.pdf"}
        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["extraction_nonletter_ratio"] < 0.05

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=("⌘∂■ ♥♃Ω ⌘∂◊ " * 500, []),
    )
    def test_garbled_extraction_stores_high_nonletter_ratio(self, mock_extract, MockSettings, mock_get_db):
        """A CID-mangled text layer must be measurable downstream — this ratio
        is what gates the low-quality warning in document chat."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "garbled.pdf"}
        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        # Ω in the sample is a genuine letter, so the ratio is 8/9, not 1.0 —
        # the metric is unicode-aware by design.
        assert update_set["extraction_nonletter_ratio"] > 0.8

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        side_effect=FileNotFoundError("no such file: 'gone.pdf'"),
    )
    def test_missing_source_file_warns_not_pages_sentry(self, mock_extract, MockSettings, mock_get_db):
        """A file deleted mid-processing (E2E teardown / retention sweep) is a
        benign race: mark the doc but log at warning, never logger.exception
        (which would page Sentry as a fault)."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "gone.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        with patch("app.tasks.document_tasks.logger") as mock_logger:
            result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == ""
        mock_logger.exception.assert_not_called()
        mock_logger.warning.assert_called()
        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert "no longer available" in update_set["error_message"].lower()

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_with_markers", return_value=("", []))
    def test_marks_error_when_extraction_returns_no_text(self, mock_extract, MockSettings, mock_get_db):
        """OCR returning an empty string (endpoint down, image-only PDF) is the
        most common silent failure — it must be surfaced, not hidden."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "scan.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == ""
        update_call = db.smart_document.update_one.call_args_list[-1]
        update_set = update_call[0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert update_set["raw_text"] == ""
        assert update_set["error_message"]  # not None / not empty
        # No rejection flag: this is the generic "nothing came back" case.
        assert "fonts don't map to characters" not in update_set["error_message"]

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    def test_rejected_text_layer_gets_a_message_naming_the_cause(
        self, MockSettings, mock_get_db,
    ):
        """"Retry — it might be a blip" is wrong advice for a PDF whose own
        text layer was refused: the message has to say what happened so the
        user knows re-uploading a scanned copy is the fix."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "garbled.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        def reject(path, extension, report=None, force_ocr=False, ocr_required=False,
                   local_on_ocr_outage=False, on_stage=None):
            report["text_layer_rejected"] = True
            report["text_layer_rejected_reason"] = "classifier"
            return "", []

        with patch(
            "app.services.document_readers.extract_text_with_markers", side_effect=reject,
        ):
            result = perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        assert result == ""
        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert update_set["error_message"] == (
            "This PDF's text layer is unreadable (its fonts don't map to "
            "characters), and OCR could not read the pages. Retry extraction "
            "once OCR is available, or re-upload a printed or scanned copy."
        )

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    def test_a_layer_refused_under_ocr_required_gets_its_own_message(
        self, MockSettings, mock_get_db,
    ):
        """The other half of the gate diagnoses nothing about the fonts — the
        PDF reads as text_based and it was its stored text that was refused —
        and OCR was plainly available, so "retry once OCR is available" invites
        a click that does the same thing again."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "garbled.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        def reject(path, extension, report=None, force_ocr=False, ocr_required=False,
                   local_on_ocr_outage=False, on_stage=None):
            report["text_layer_rejected"] = True
            report["text_layer_rejected_reason"] = "ocr_required"
            return "", []

        with patch(
            "app.services.document_readers.extract_text_with_markers", side_effect=reject,
        ):
            perform_extraction_and_update(
                document_uuid="doc-1", extension="pdf",
                force_ocr=True, ocr_required=True,
            )

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert update_set["error_message"] == (
            "OCR read this document's pages and found nothing usable, and its "
            "own text layer was already refused as unreadable. Retry extraction "
            "in case the OCR service was degraded, or re-upload a printed or "
            "scanned copy of the document."
        )

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    def test_rejected_text_layer_is_remembered_on_the_document(
        self, MockSettings, mock_get_db,
    ):
        """This same write clears the ratio, which is the only other evidence
        that a non-OCR reading of this file is unacceptable. The refusal is
        recorded beside the error so the next retry still requires OCR
        instead of falling back to the layer that was just refused."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "garbled.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        def reject(path, extension, report=None, force_ocr=False, ocr_required=False,
                   local_on_ocr_outage=False, on_stage=None):
            report["text_layer_rejected"] = True
            return "", []

        with patch(
            "app.services.document_readers.extract_text_with_markers", side_effect=reject,
        ):
            perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["text_layer_rejected"] is True
        assert update_set["extraction_nonletter_ratio"] is None

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.pdf_page_count", return_value=1)
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=(
            "Award Number: 2026-0412. Total costs approved for the period.",
            [{"char_offset": 0, "kind": "page", "value": 1}],
        ),
    )
    def test_a_successful_reading_clears_the_rejected_layer(
        self, mock_extract, mock_page_count, MockSettings, mock_get_db,
    ):
        """The retry route sets text_layer_rejected from the non-letter ratio
        before OCR has confirmed anything. Left set after OCR read the pages
        fine, a ratio false positive would pin the document to OCR-only
        re-reads for good — failing outright whenever OCR is down, for a
        document whose local reading was never actually bad."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "path": "checkboxes.pdf", "text_layer_rejected": True,
        }

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(
            document_uuid="doc-1", extension="pdf", force_ocr=True, ocr_required=True,
        )

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["error_message"] is None
        assert update_set["text_layer_rejected"] is False

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.pdf_page_count", return_value=3)
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=(
            "page one\npage two\npage three",
            [
                {"char_offset": 0, "kind": "page", "value": 1},
                {"char_offset": 9, "kind": "page", "value": 2},
                {"char_offset": 18, "kind": "page", "value": 3},
            ],
        ),
    )
    def test_persists_num_pages_for_pdf(
        self, mock_extract, mock_page_count, MockSettings, mock_get_db,
    ):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "three.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["num_pages"] == 3

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.pdf_page_count", return_value=10)
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=(
            "text from the eight pages that had a text layer",
            [{"char_offset": i, "kind": "page", "value": i + 1} for i in range(8)],
        ),
    )
    def test_num_pages_counts_pages_not_markers(
        self, mock_extract, mock_page_count, MockSettings, mock_get_db,
    ):
        """PyMuPDF emits no marker for a page with no text and no form fields
        (see document_readers._pymupdf_extract_with_pages), so a scanned or
        mixed PDF has fewer page markers than pages. num_pages must come from
        the PDF itself, not from len(markers)."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "mixed.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["num_pages"] == 10

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch(
        "app.services.document_readers.extract_text_with_markers",
        return_value=(
            "## Sheet1\nrow\n## Sheet2\nrow\n## Sheet3\nrow",
            [
                {"char_offset": 0, "kind": "sheet", "value": "Sheet1"},
                {"char_offset": 14, "kind": "sheet", "value": "Sheet2"},
                {"char_offset": 28, "kind": "sheet", "value": "Sheet3"},
            ],
        ),
    )
    def test_xlsx_sheet_markers_do_not_set_num_pages(
        self, mock_extract, MockSettings, mock_get_db,
    ):
        """Sheets are not pages — an XLSX must not get a fabricated page count."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "book.xlsx"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="xlsx")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert "num_pages" not in update_set

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.pdf_page_count", return_value=5)
    @patch("app.services.document_readers.extract_text_with_markers", return_value=("", []))
    def test_failed_extraction_clears_num_pages(
        self, mock_extract, mock_page_count, MockSettings, mock_get_db,
    ):
        """A reprocess that now yields no text must not leave a stale page count
        next to an empty raw_text."""
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "scan.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        update_set = db.smart_document.update_one.call_args_list[-1][0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert update_set["num_pages"] == 0

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_readers.extract_text_from_file", return_value="text")
    def test_sets_processing_status_to_extracting(self, mock_extract, MockSettings, mock_get_db):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": "f.pdf"}

        settings = MagicMock()
        settings.upload_dir = "/uploads"
        MockSettings.return_value = settings

        perform_extraction_and_update(document_uuid="doc-1", extension="pdf")

        # First update should set processing=True, task_status=extracting
        first_update = db.smart_document.update_one.call_args_list[0]
        assert first_update[0][1]["$set"]["task_status"] == "extracting"


# ---------------------------------------------------------------------------
# update_document_fields
# ---------------------------------------------------------------------------


class TestUpdateDocumentFields:
    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_marks_document_complete(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"task_status": "extracting"}
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        update_document_fields(document_uuid="doc-1")

        db.smart_document.update_one.assert_called_once()
        update_set = db.smart_document.update_one.call_args[0][1]["$set"]
        assert update_set["task_status"] == "complete"

    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_preserves_error_status(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"task_status": "error"}

        update_document_fields(document_uuid="doc-1")

        # When extraction already flagged an error, we should clear the task_id
        # but not overwrite task_status with "complete".
        update_set = db.smart_document.update_one.call_args[0][1]["$set"]
        assert "task_status" not in update_set
        assert update_set["task_id"] is None
        mock_check.assert_not_called()

    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_early_when_doc_not_found(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        update_document_fields(document_uuid="missing")

        db.smart_document.update_one.assert_not_called()
        mock_check.assert_not_called()

    @patch("app.tasks.document_tasks._check_folder_watch_automations", side_effect=RuntimeError("boom"))
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_catches_folder_watch_errors(self, mock_get_db, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"task_status": "extracting"}
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        # Should not raise
        update_document_fields(document_uuid="doc-1")


class TestResumePendingKbSources:
    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.document_tasks.celery_app")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_complete_redispatches_pending_sources(self, mock_get_db, mock_celery, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {"task_status": "extracting"}
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)
        db.knowledge_base_sources.find.return_value = [
            {"uuid": "src-1", "knowledge_base_uuid": "kb-1"},
            {"uuid": "src-2", "knowledge_base_uuid": "kb-1"},
        ]

        update_document_fields(document_uuid="doc-1")

        # Each pending source is handed to the re-ingest task on the documents queue.
        assert mock_celery.send_task.call_count == 2
        names = {c.args[0] for c in mock_celery.send_task.call_args_list}
        assert names == {"tasks.documents.kb_ingest_document"}
        dispatched = {c.kwargs["args"][0] for c in mock_celery.send_task.call_args_list}
        assert dispatched == {"src-1", "src-2"}

    @patch("app.tasks.document_tasks._check_folder_watch_automations")
    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    @patch("app.tasks.document_tasks.celery_app")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_error_marks_pending_sources_errored(self, mock_get_db, mock_celery, mock_recalc, mock_check):
        from app.tasks.document_tasks import update_document_fields

        db = MagicMock()
        mock_get_db.return_value = db
        # First find_one: task_status for the gate. Second: error_message lookup.
        db.smart_document.find_one.side_effect = [
            {"task_status": "error"},
            {"error_message": "It may be image-only or encrypted."},
        ]
        db.knowledge_base_sources.find.return_value = [
            {"uuid": "src-1", "knowledge_base_uuid": "kb-1"},
        ]

        update_document_fields(document_uuid="doc-1")

        # The waiting source is flipped to error with the document's message.
        src_update = db.knowledge_base_sources.update_one.call_args[0]
        assert src_update[0] == {"uuid": "src-1"}
        assert src_update[1]["$set"]["status"] == "error"
        assert "image-only" in src_update[1]["$set"]["error_message"]
        mock_recalc.assert_called_once_with(db, "kb-1")
        # No re-ingest dispatched on failure.
        mock_celery.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# _check_folder_watch_automations
# ---------------------------------------------------------------------------


class TestCheckFolderWatchAutomations:
    def test_returns_early_when_doc_not_found(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = None

        _check_folder_watch_automations(db, "doc-1")
        db.automation.find.assert_not_called()

    def test_returns_early_when_folder_is_root(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "folder": "0"}

        _check_folder_watch_automations(db, "doc-1")
        db.automation.find.assert_not_called()

    def test_returns_early_when_no_automations_match(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "folder": "folder-abc"}
        db.automation.find.return_value = []

        _check_folder_watch_automations(db, "doc-1")

    def test_skips_automation_with_non_matching_file_type(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "folder": "f1", "extension": "txt", "title": "test.txt",
        }
        db.automation.find.return_value = [{
            "_id": ObjectId(),
            "name": "PDF only",
            "action_type": "workflow",
            "action_id": str(ObjectId()),
            "trigger_config": {"file_types": ["pdf"]},
        }]

        _check_folder_watch_automations(db, "doc-1")

        # Should not create any trigger event or call workflow
        db.workflow.find_one.assert_not_called()

    def test_skips_automation_matching_exclude_pattern(self):
        from app.tasks.document_tasks import _check_folder_watch_automations

        db = MagicMock()
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "folder": "f1", "extension": "pdf", "title": "DRAFT_report.pdf",
        }
        db.automation.find.return_value = [{
            "_id": ObjectId(),
            "name": "Skip drafts",
            "action_type": "workflow",
            "action_id": str(ObjectId()),
            "trigger_config": {"file_types": [], "exclude_patterns": "DRAFT_*"},
        }]

        _check_folder_watch_automations(db, "doc-1")
        db.workflow.find_one.assert_not_called()

    @patch("app.services.passive_triggers.create_folder_watch_trigger", return_value={"_id": "evt-1"})
    def test_creates_trigger_event_for_workflow_automation(self, mock_create_trigger):
        from app.tasks.document_tasks import _check_folder_watch_automations

        wf_oid = ObjectId()
        db = MagicMock()
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "folder": "f1", "extension": "pdf", "title": "report.pdf",
        }
        db.automation.find.return_value = [{
            "_id": ObjectId(),
            "name": "Auto extract",
            "action_type": "workflow",
            "action_id": str(wf_oid),
            "trigger_config": {},
        }]
        db.workflow.find_one.return_value = {"_id": wf_oid, "name": "My WF"}

        _check_folder_watch_automations(db, "doc-1")

        mock_create_trigger.assert_called_once()


# ---------------------------------------------------------------------------
# cleanup_document
# ---------------------------------------------------------------------------


class TestCleanupDocument:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_sets_error_status(self, mock_get_db):
        from app.tasks.document_tasks import cleanup_document

        db = MagicMock()
        mock_get_db.return_value = db
        # No pre-existing error_message — cleanup should add the generic fallback.
        db.smart_document.find_one.return_value = {"error_message": None}
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        cleanup_document(document_uuid="doc-1")

        update_set = db.smart_document.update_one.call_args[0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert update_set["processing"] is False
        assert "error_message" in update_set

    @patch("app.tasks.document_tasks.get_sync_db")
    def test_preserves_specific_error_message(self, mock_get_db):
        from app.tasks.document_tasks import cleanup_document

        db = MagicMock()
        mock_get_db.return_value = db
        # The extraction task already wrote a specific message — don't overwrite.
        db.smart_document.find_one.return_value = {"error_message": "OCR endpoint timed out"}
        db.smart_document.update_one.return_value = MagicMock(matched_count=1)

        cleanup_document(document_uuid="doc-1")

        update_set = db.smart_document.update_one.call_args[0][1]["$set"]
        assert update_set["task_status"] == "error"
        assert "error_message" not in update_set

    @patch("app.tasks.document_tasks.get_sync_db")
    def test_handles_missing_document(self, mock_get_db):
        from app.tasks.document_tasks import cleanup_document

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        # Should not raise
        cleanup_document(document_uuid="missing")
        db.smart_document.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# perform_semantic_ingestion
# ---------------------------------------------------------------------------


class TestPerformSemanticIngestion:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_empty_when_doc_not_found(self, mock_get_db):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        result = perform_semantic_ingestion(raw_text="text", document_uuid="missing", user_id="user1")
        assert result == ""

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_ingests_document_and_returns_uuid(self, mock_get_db, MockSettings, MockDM):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Report.pdf", "path": "uploads/report.pdf",
        }

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        # add_document now returns an int chunk count for the writeback step.
        dm_instance.add_document.return_value = 5
        MockDM.return_value = dm_instance

        result = perform_semantic_ingestion(raw_text="content", document_uuid="doc-1", user_id="user1")

        assert result == "doc-1"
        dm_instance.add_document.assert_called_once_with(
            user_id="user1",
            document_name="Report.pdf",
            document_id="doc-1",
            doc_path="uploads/report.pdf",
            raw_text="content",
            text_markers=[],
        )
        # The bookkeeping write should reflect the chunk count and ready flag.
        final_update = _set_containing(db, "chromadb_ready")
        assert final_update["chromadb_ready"] is True
        assert final_update["chunk_count"] == 5

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_previous_chunks_are_deleted_before_re_adding(
        self, mock_get_db, MockSettings, MockDM,
    ):
        """Chunk ids are deterministic (``<uuid>_chunk_<i>``), so a shorter
        second extraction would leave the tail of the first one behind and
        retrieval would keep answering from the old text."""
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Report.pdf", "path": "uploads/report.pdf",
        }

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        dm_instance.add_document.return_value = 2
        MockDM.return_value = dm_instance

        perform_semantic_ingestion(
            raw_text="re-extracted content", document_uuid="doc-1", user_id="user1",
        )

        dm_instance.delete_document.assert_called_once_with("user1", "doc-1")
        # Order matters: deleting after the add would wipe the new chunks too.
        assert [c[0] for c in dm_instance.mock_calls[:2]] == [
            "delete_document", "add_document",
        ]

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_failed_re_extraction_keeps_the_previous_chunks(
        self, mock_get_db, MockSettings, MockDM,
    ):
        """The extraction task returns "" on a failed read rather than
        raising, so the chain still ingests. Deleting the old chunks then
        would strip a document that was searchable a minute ago out of
        retrieval entirely — worse than leaving the old text beside an
        error state."""
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Report.pdf", "path": "uploads/report.pdf",
            "raw_text": "",
        }

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        dm_instance.add_document.return_value = 0
        MockDM.return_value = dm_instance

        perform_semantic_ingestion(raw_text="", document_uuid="doc-1", user_id="user1")

        dm_instance.delete_document.assert_not_called()

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_sets_task_status_to_readying_then_complete(self, mock_get_db, MockSettings, MockDM):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Doc", "path": "p",
        }
        MockSettings.return_value = MagicMock(chromadb_persist_dir="/data")
        dm = MagicMock()
        dm.add_document.return_value = 3
        MockDM.return_value = dm

        perform_semantic_ingestion(raw_text="text", document_uuid="doc-1", user_id="u1")

        # readying while it works, complete once it has.
        assert _status_sequence(db) == ["readying", "complete"]

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_writes_ingest_error_on_failure(self, mock_get_db, MockSettings, MockDM):
        """When chunking fails, chromadb_ready stays False and ingest_error is
        written so the UI can surface a meaningful state."""
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Doc", "path": "p",
        }
        MockSettings.return_value = MagicMock(chromadb_persist_dir="/data")
        dm = MagicMock()
        dm.add_document.side_effect = RuntimeError("embedding service down")
        MockDM.return_value = dm

        with pytest.raises(RuntimeError):
            perform_semantic_ingestion(raw_text="text", document_uuid="doc-1", user_id="u1")

        final_update = _set_containing(db, "ingest_error")
        assert final_update["chromadb_ready"] is False
        assert "embedding service down" in final_update["ingest_error"]

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_re_ingesting_a_project_document_refreshes_the_project_kb(
        self, mock_get_db, MockSettings, MockDM, recalc,
    ):
        """End to end on the retry path: retry-extraction re-dispatches the
        chain, and the mirror at the end of this task must replace the
        project's chunks, not skip them because a row exists."""
        from app.tasks.document_tasks import perform_semantic_ingestion
        from app.utils import kb_source_currency as currency

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Report.pdf", "path": "uploads/report.pdf",
            "folder": "proj-root", "text_markers": [],
        }
        # proj-root is itself the project root.
        db.smart_folder.find_one.return_value = {"parent_id": "0"}
        db.project.find_one.return_value = {"uuid": "p1", "kb_uuid": "kb1"}
        db.knowledge_base_sources.find_one.return_value = {
            "_id": ObjectId(),
            "status": "ready",
            "chunk_count": 3,
            "content_hash": currency.content_fingerprint("the first, bad extraction"),
        }

        MockSettings.return_value = MagicMock(chromadb_persist_dir="/data/chroma")
        dm = MagicMock()
        dm.add_document.return_value = 5
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 6
        MockDM.return_value = dm

        result = perform_semantic_ingestion(
            raw_text="the re-extracted text", document_uuid="doc-1", user_id="user1",
        )

        assert result == "doc-1"
        dm.delete_kb_source.assert_called_once_with("kb1", "doc-1")
        dm.add_to_kb.assert_called_once()
        assert dm.add_to_kb.call_args.kwargs["raw_text"] == "the re-extracted text"
        written = db.knowledge_base_sources.update_one.call_args[0][1]["$set"]
        assert written["chunk_count"] == 6
        assert written["status"] == "ready"
        assert written["content_hash"] == currency.content_fingerprint(
            "the re-extracted text"
        )
        recalc.assert_called_once_with(db, "kb1")


# ---------------------------------------------------------------------------
# Project KB membership sync (move into / out of a Project's folder tree)
# ---------------------------------------------------------------------------


class TestFindProjectForFolder:
    def test_returns_none_for_root_or_empty(self):
        from app.tasks.document_tasks import _find_project_for_folder

        db = MagicMock()
        assert _find_project_for_folder(db, None) is None
        assert _find_project_for_folder(db, "0") is None
        db.project.find_one.assert_not_called()

    def test_walks_ancestry_to_project_root(self):
        from app.tasks.document_tasks import _find_project_for_folder

        db = MagicMock()
        # child -> parent -> root("0")
        db.smart_folder.find_one.side_effect = [
            {"parent_id": "parent"},
            {"parent_id": "0"},
        ]
        db.project.find_one.return_value = {"uuid": "p1", "kb_uuid": "kb1"}

        project = _find_project_for_folder(db, "child")

        assert project["uuid"] == "p1"
        # The $in query should include every folder in the ancestry chain.
        ancestors = db.project.find_one.call_args[0][0]["root_folder_uuid"]["$in"]
        assert ancestors == ["child", "parent"]


class TestSyncProjectKbOnMove:
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_returns_empty_when_doc_missing(self, mock_get_db):
        from app.tasks.document_tasks import sync_project_kb_on_move

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = None

        assert sync_project_kb_on_move("missing", "f1") == ""

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_manager.DocumentManager")
    def test_moving_into_project_ingests_into_kb(self, MockDM, MockSettings, mock_get_db):
        from app.tasks.document_tasks import sync_project_kb_on_move

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1",
            "folder": "proj-root",
            "title": "Composer-Performer Agreement",
            "raw_text": "Performance Date & Time: 4.29.26",
            "text_markers": [],
        }
        # proj-root is itself the project root.
        db.smart_folder.find_one.return_value = {"parent_id": "0"}
        db.project.find_one.return_value = {"uuid": "p1", "kb_uuid": "kb1"}
        db.knowledge_base_sources.find_one.return_value = None  # not a dupe

        dm = MagicMock()
        dm.add_to_kb.return_value = 4
        MockDM.return_value = dm
        MockSettings.return_value = MagicMock()

        result = sync_project_kb_on_move("doc-1", None)

        assert result == "doc-1"
        dm.add_to_kb.assert_called_once()
        db.knowledge_base_sources.insert_one.assert_called_once()

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_manager.DocumentManager")
    def test_moving_out_of_project_removes_from_kb(
        self, MockDM, MockSettings, mock_get_db, recalc,
    ):
        from app.tasks.document_tasks import sync_project_kb_on_move

        db = MagicMock()
        mock_get_db.return_value = db
        # Doc now lives at the root (no project).
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "folder": "0"}
        # Old folder resolves to a project.
        db.smart_folder.find_one.return_value = {"parent_id": "0"}
        db.project.find_one.return_value = {"uuid": "p1", "kb_uuid": "kb1"}
        db.knowledge_base_sources.find_one.return_value = {
            "_id": ObjectId(),
            "chunk_count": 3,
        }

        dm = MagicMock()
        MockDM.return_value = dm
        MockSettings.return_value = MagicMock()

        result = sync_project_kb_on_move("doc-1", "old-proj-root")

        assert result == "doc-1"
        dm.delete_kb_source.assert_called_once_with("kb1", "doc-1")
        db.knowledge_base_sources.delete_one.assert_called_once()
        # KB counters recomputed from the remaining rows, not decremented: a
        # row a failed refresh left at status "error" was never in
        # sources_ready, so a blind -1 would drift the count for good.
        recalc.assert_called_once_with(db, "kb1")
        db.knowledge_bases.update_one.assert_not_called()


def _mirror_row(**overrides):
    """A ``knowledge_base_sources`` row for a document already mirrored into
    a project KB. Defaults describe a healthy, current row; override to
    describe a stale, legacy or errored one."""
    row = {
        "_id": ObjectId(),
        "uuid": "src-1",
        "knowledge_base_uuid": "kb1",
        "source_type": "document",
        "document_uuid": "doc-1",
        "status": "ready",
        "error_message": None,
        "chunk_count": 4,
    }
    row.update(overrides)
    return row


def _project_doc(text="Performance Date & Time: 4.29.26"):
    """A smart_document living directly under a project's root folder."""
    return {
        "uuid": "doc-1",
        "folder": "proj-root",
        "title": "Composer-Performer Agreement",
        "raw_text": text,
        "text_markers": [],
    }


_PROJECT = {"uuid": "p1", "kb_uuid": "kb1"}


class TestProjectKbMirrorRefresh:
    """A document already in a project KB must be re-chunked when its text
    changed, and left completely alone when it did not (#887 follow-up)."""

    def test_unchanged_text_is_not_re_embedded(self):
        """The gate that keeps a file move — or a forty-file folder move —
        from re-embedding a subtree nobody edited."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        text = "Performance Date & Time: 4.29.26"
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = _mirror_row(
            content_hash=currency.content_fingerprint(text),
        )
        dm = MagicMock()

        _mirror_into_project_kb(db, dm, _project_doc(text), _PROJECT, text)

        dm.delete_kb_source.assert_not_called()
        dm.add_to_kb.assert_not_called()
        db.knowledge_base_sources.update_one.assert_not_called()
        db.knowledge_base_sources.insert_one.assert_not_called()
        db.knowledge_bases.update_one.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_re_extracted_text_replaces_the_old_chunks(self, recalc):
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        new_text = "Performance Date & Time: 29 April 2026, 7:30pm"
        row = _mirror_row(
            content_hash=currency.content_fingerprint("the first, bad extraction"),
        )
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = row
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 7

        _mirror_into_project_kb(db, dm, _project_doc(new_text), _PROJECT, new_text)

        # Chunks are keyed by document_uuid in a project KB, not by the row's uuid.
        dm.delete_kb_source.assert_called_once_with("kb1", "doc-1")
        # Order matters: deleting after the add would wipe the new chunks too.
        assert [c[0] for c in dm.mock_calls[:2]] == ["delete_kb_source", "add_to_kb"]
        assert dm.add_to_kb.call_args.kwargs["raw_text"] == new_text
        assert dm.add_to_kb.call_args.kwargs["source_id"] == "doc-1"

        db.knowledge_base_sources.insert_one.assert_not_called()
        where, update = db.knowledge_base_sources.update_one.call_args[0]
        assert where == {"_id": row["_id"]}
        written = update["$set"]
        assert written["chunk_count"] == 7
        assert written["status"] == "ready"
        assert written["error_message"] is None
        assert written["document_title"] == "Composer-Performer Agreement"
        assert written["content_hash"] == currency.content_fingerprint(new_text)
        assert written["last_ingested_at"] is not None
        assert written["last_retrieved_at"] is not None

        # Recomputed from the rows, never incremented: this row was already
        # counted when it was inserted, and its old chunk_count is the number
        # the new one replaces.
        recalc.assert_called_once_with(db, "kb1")
        db.knowledge_bases.update_one.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_a_row_with_no_fingerprint_refreshes_once(self, recalc):
        """Rows the mirror wrote before this change carry no ``content_hash``.
        They are stale by definition, refresh on the next pass, and the stamp
        written then settles them — no migration."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        text = "Performance Date & Time: 4.29.26"
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = _mirror_row()  # legacy: no hash
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 4

        _mirror_into_project_kb(db, dm, _project_doc(text), _PROJECT, text)

        dm.delete_kb_source.assert_called_once_with("kb1", "doc-1")
        dm.add_to_kb.assert_called_once()
        written = db.knowledge_base_sources.update_one.call_args[0][1]["$set"]
        assert written["content_hash"] == currency.content_fingerprint(text)
        recalc.assert_called_once_with(db, "kb1")

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_an_errored_row_refreshes_even_when_the_text_matches(self, recalc):
        """A matching hash on a row that never finished indexing is not
        evidence the chunks are there."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        text = "Performance Date & Time: 4.29.26"
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = _mirror_row(
            status="error",
            error_message="chroma collection gone",
            content_hash=currency.content_fingerprint(text),
        )
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 4

        _mirror_into_project_kb(db, dm, _project_doc(text), _PROJECT, text)

        dm.add_to_kb.assert_called_once()
        written = db.knowledge_base_sources.update_one.call_args[0][1]["$set"]
        assert written["status"] == "ready"
        assert written["error_message"] is None
        recalc.assert_called_once_with(db, "kb1")

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_a_row_claiming_zero_chunks_refreshes(self, recalc):
        """``ready`` with nothing indexed is the shape an empty add leaves
        behind; the hash alone must not certify it."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        text = "Performance Date & Time: 4.29.26"
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = _mirror_row(
            chunk_count=0, content_hash=currency.content_fingerprint(text),
        )
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 4

        _mirror_into_project_kb(db, dm, _project_doc(text), _PROJECT, text)

        dm.add_to_kb.assert_called_once()
        recalc.assert_called_once_with(db, "kb1")

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_manager.DocumentManager")
    def test_moving_a_document_whose_text_is_unchanged_costs_nothing(
        self, MockDM, MockSettings, mock_get_db,
    ):
        """sync_project_kb_on_move and sync_project_kb_on_folder_move both
        come through the mirror for every document they touch. Re-embedding a
        subtree whose text nobody edited is a real bill for no change in what
        retrieval returns."""
        from app.tasks.document_tasks import sync_project_kb_on_move
        from app.utils import kb_source_currency as currency

        text = "Performance Date & Time: 4.29.26"
        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = _project_doc(text)
        # proj-root is itself the project root; the old folder is the same tree.
        db.smart_folder.find_one.return_value = {"parent_id": "0"}
        db.project.find_one.return_value = dict(_PROJECT)
        db.knowledge_base_sources.find_one.return_value = _mirror_row(
            content_hash=currency.content_fingerprint(text),
        )

        dm = MagicMock()
        MockDM.return_value = dm
        MockSettings.return_value = MagicMock()

        assert sync_project_kb_on_move("doc-1", "proj-root") == "doc-1"

        dm.delete_kb_source.assert_not_called()
        dm.add_to_kb.assert_not_called()
        db.knowledge_base_sources.update_one.assert_not_called()
        db.knowledge_base_sources.insert_one.assert_not_called()

    @patch("app.tasks.document_tasks.get_sync_db")
    @patch("app.config.Settings")
    @patch("app.services.document_manager.DocumentManager")
    def test_moving_a_document_with_no_real_text_touches_nothing(
        self, MockDM, MockSettings, mock_get_db,
    ):
        """The move tasks guard on there being text to index, the way
        perform_semantic_ingestion does. Whitespace-only raw_text passed that
        guard when it read ``if text:``, and the row it wrote — ready, zero
        chunks — fails the currency gate, so every later move deleted, re-added
        nothing and recomputed the KB again."""
        from app.tasks.document_tasks import sync_project_kb_on_move

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = _project_doc("   \n\t ")
        db.smart_folder.find_one.return_value = {"parent_id": "0"}
        db.project.find_one.return_value = dict(_PROJECT)
        db.knowledge_base_sources.find_one.return_value = _mirror_row(chunk_count=0)

        dm = MagicMock()
        MockDM.return_value = dm
        MockSettings.return_value = MagicMock()

        assert sync_project_kb_on_move("doc-1", "proj-root") == "doc-1"

        dm.delete_kb_source.assert_not_called()
        dm.add_to_kb.assert_not_called()
        db.knowledge_base_sources.update_one.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_no_existing_row_stamps_the_fingerprint_on_insert(self, recalc):
        """The ruling amending this task's brief: the insert branch is
        otherwise unchanged, but it now writes an ingestion stamp too, so a
        document moved again with unchanged text is a no-op instead of a
        one-time re-embed the very first time the mirror sees it."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        text = "Performance Date & Time: 4.29.26"
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = None
        dm = MagicMock()
        dm.add_to_kb.return_value = 5

        _mirror_into_project_kb(db, dm, _project_doc(text), _PROJECT, text)

        dm.delete_kb_source.assert_not_called()
        db.knowledge_base_sources.insert_one.assert_called_once()
        inserted = db.knowledge_base_sources.insert_one.call_args[0][0]
        assert inserted["content_hash"] == currency.content_fingerprint(text)
        assert inserted["status"] == "ready"

        inc = db.knowledge_bases.update_one.call_args[0][1]["$inc"]
        assert inc["total_sources"] == 1
        recalc.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_a_refresh_that_fails_after_the_delete_marks_the_row(self, recalc):
        """The delete has already happened by the time add_to_kb can raise, so
        a row left at status "ready" with its old chunk_count describes chunks
        that are gone: the project card counts the document as indexed and
        retrieval finds nothing of it."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        new_text = "Performance Date & Time: 29 April 2026, 7:30pm"
        row = _mirror_row(
            content_hash=currency.content_fingerprint("the first, bad extraction"),
        )
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = row
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.side_effect = RuntimeError("chroma collection gone")

        with pytest.raises(RuntimeError, match="chroma collection gone"):
            _mirror_into_project_kb(db, dm, _project_doc(new_text), _PROJECT, new_text)

        dm.delete_kb_source.assert_called_once_with("kb1", "doc-1")
        where, update = db.knowledge_base_sources.update_one.call_args[0]
        assert where == {"_id": row["_id"]}
        written = update["$set"]
        assert written["status"] == "error"
        assert "chroma collection gone" in written["error_message"]
        # The chunks this row counted were deleted a moment ago, and
        # _recalculate_kb sums chunk_count over every row whatever its status:
        # leaving the old number would keep the KB advertising chunks that are
        # gone. Nothing stamps the new fingerprint either.
        assert written["chunk_count"] == 0
        assert "content_hash" not in written
        # The KB's sources_ready must not keep counting this one.
        recalc.assert_called_once_with(db, "kb1")

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_a_delete_that_failed_stops_the_refresh(self, recalc):
        """delete_kb_source logs and swallows, so its return value is the only
        evidence the old chunks are gone. Carrying on regardless would be the
        worst outcome available: add_to_kb writes the same deterministic ids
        with collection.add, which skips ids that already exist, so the first
        extraction's text would survive under a row stamped ready with the new
        text's fingerprint — and the gate would certify it as current forever."""
        from app.tasks.document_tasks import (
            ProjectKbDeleteFailed,
            _mirror_into_project_kb,
        )
        from app.utils import kb_source_currency as currency

        new_text = "Performance Date & Time: 29 April 2026, 7:30pm"
        row = _mirror_row(
            content_hash=currency.content_fingerprint("the first, bad extraction"),
        )
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = row
        dm = MagicMock()
        dm.delete_kb_source.return_value = False

        # Its own type, because the state it leaves is the opposite of the
        # one a failed re-add leaves: the old chunks are still answering.
        with pytest.raises(ProjectKbDeleteFailed, match="could not remove the previous chunks"):
            _mirror_into_project_kb(db, dm, _project_doc(new_text), _PROJECT, new_text)

        dm.add_to_kb.assert_not_called()
        written = db.knowledge_base_sources.update_one.call_args[0][1]["$set"]
        assert written["status"] == "error"
        assert "could not remove the previous chunks" in written["error_message"]
        assert written["chunk_count"] == 0
        assert "content_hash" not in written
        recalc.assert_called_once_with(db, "kb1")

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_a_failed_stamp_after_the_add_is_not_a_refresh_failure(self, recalc):
        """By the time the row write runs the new chunks are in Chroma and
        current, so a transient write failure there must not error the row
        and bell "removed and could not be replaced" — the project can answer
        from the document. The row keeps its previous fingerprint, so the next
        pass through the gate refreshes again."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        new_text = "Performance Date & Time: 29 April 2026, 7:30pm"
        row = _mirror_row(
            content_hash=currency.content_fingerprint("the first, bad extraction"),
        )
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = row
        db.knowledge_base_sources.update_one.side_effect = RuntimeError(
            "mongo write concern failed"
        )
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 7

        _mirror_into_project_kb(db, dm, _project_doc(new_text), _PROJECT, new_text)

        dm.add_to_kb.assert_called_once()
        # One attempt at the success stamp; no error row written over it.
        db.knowledge_base_sources.update_one.assert_called_once()
        written = db.knowledge_base_sources.update_one.call_args[0][1]["$set"]
        assert written["status"] == "ready"
        assert written["content_hash"] == currency.content_fingerprint(new_text)
        recalc.assert_not_called()

    @patch("app.tasks.knowledge_base_tasks._recalculate_kb")
    def test_a_failed_recount_after_the_stamp_leaves_the_row_ready(self, recalc):
        """The recount only maintains the KB's aggregate counters; failing it
        leaves them one pass stale, which is not a state the owner needs a
        bell for and not one that may un-stamp a row whose chunks are current."""
        from app.tasks.document_tasks import _mirror_into_project_kb
        from app.utils import kb_source_currency as currency

        new_text = "Performance Date & Time: 29 April 2026, 7:30pm"
        row = _mirror_row(
            content_hash=currency.content_fingerprint("the first, bad extraction"),
        )
        db = MagicMock()
        db.knowledge_base_sources.find_one.return_value = row
        dm = MagicMock()
        dm.delete_kb_source.return_value = True
        dm.add_to_kb.return_value = 7
        recalc.side_effect = RuntimeError("mongo find timed out")

        _mirror_into_project_kb(db, dm, _project_doc(new_text), _PROJECT, new_text)

        db.knowledge_base_sources.update_one.assert_called_once()
        written = db.knowledge_base_sources.update_one.call_args[0][1]["$set"]
        assert written["status"] == "ready"
        assert written["chunk_count"] == 7
        recalc.assert_called_once_with(db, "kb1")


# ---------------------------------------------------------------------------
# An extraction failure must survive the rest of the pipeline
# ---------------------------------------------------------------------------


class TestIngestionDoesNotResurrectFailedExtraction:
    """A document that extracted nothing must not end up marked "complete".

    Observed on the live deployment, 2026-08-11 17:41 UTC. A scanned PDF was
    uploaded while a 36 GB vLLM engine held the shared GPU. The OCR bridge
    answered `503 GPU held by llm-svc — retry shortly` three times in 3.5s,
    extraction returned "", and the guard in `perform_extraction_and_update`
    correctly set task_status="error" with a user-facing message.

    `update_document_fields` ran next and correctly declined to overwrite it.
    Then `perform_semantic_ingestion` finished and set task_status="complete"
    unconditionally, and the document was left with an error message it never
    showed, zero characters, and a green checkmark. Chat then answered "the
    document doesn't mention that" about a document containing nothing at all.

    The trigger was GPU contention, but the silence is this status write: any
    empty extraction is resurrected the same way, whatever caused it. That is
    why this is testable without OCR running — the failure is a *state*.
    """

    def _doc(self) -> dict:
        return {
            "uuid": "doc-1",
            "title": "05_Budget_Justification_degraded.pdf",
            "path": "uploads/scan.pdf",
            "raw_text": "",
            "task_status": "error",
            "error_message": "We couldn't extract any text from this document.",
        }

    def _status_writes(self, db) -> list:
        """Every task_status this call attempted to write, in order."""
        return [
            call[0][1]["$set"]["task_status"]
            for call in db.smart_document.update_one.call_args_list
            if "task_status" in call[0][1].get("$set", {})
        ]

    def _unguarded_status_writes(self, db) -> list:
        """*Any* status write that could land on an already-failed document.

        Checking only the terminal "complete" write is not enough, and missing
        that is what let the live bug survive a first fix: ingestion sets
        "readying" before it starts, which erases the error, after which the
        terminal write advances a document that no longer looks failed. Every
        status write has to carry the exclusion.

        The guard belongs in the query filter, not in a preceding read: these
        tasks run concurrently on separate queues, so a read-then-write check
        can be overtaken between the read and the update.
        """
        unguarded = []
        for call in db.smart_document.update_one.call_args_list:
            query, update = call[0][0], call[0][1]
            if "task_status" not in update.get("$set", {}):
                continue
            if query.get("task_status") != {"$ne": "error"}:
                unguarded.append((query, update["$set"]["task_status"]))
        return unguarded

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_successful_ingestion_does_not_clear_an_error_status(
        self, mock_get_db, MockSettings, MockDM
    ):
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = self._doc()

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        dm_instance.add_document.return_value = 0  # nothing to chunk: no text
        MockDM.return_value = dm_instance

        perform_semantic_ingestion(
            raw_text="", document_uuid="doc-1", user_id="user1"
        )

        assert self._unguarded_status_writes(db) == [], (
            "semantic ingestion wrote a task_status without excluding errored "
            "documents — this is the silent data loss"
        )

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_ingestion_failure_does_not_clear_an_error_status_either(
        self, mock_get_db, MockSettings, MockDM
    ):
        """The exception path writes "complete" too, and is if anything more
        likely to run on a document that already failed extraction."""
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = self._doc()

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        dm_instance.add_document.side_effect = RuntimeError("chroma unavailable")
        MockDM.return_value = dm_instance

        with pytest.raises(RuntimeError):
            perform_semantic_ingestion(
                raw_text="", document_uuid="doc-1", user_id="user1"
            )

        assert self._unguarded_status_writes(db) == []

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_a_healthy_document_is_still_marked_complete(
        self, mock_get_db, MockSettings, MockDM
    ):
        """The guard must not strand ordinary documents in a non-complete state."""
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = {
            "uuid": "doc-1", "title": "Report.pdf", "path": "uploads/report.pdf",
            "raw_text": "real content", "task_status": "extracting",
        }

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        dm_instance.add_document.return_value = 5
        MockDM.return_value = dm_instance

        perform_semantic_ingestion(
            raw_text="real content", document_uuid="doc-1", user_id="user1"
        )

        assert "complete" in self._status_writes(db)

    @patch("app.services.document_manager.DocumentManager")
    @patch("app.config.Settings")
    @patch("app.tasks.document_tasks.get_sync_db")
    def test_ingestion_bookkeeping_is_still_recorded_on_a_failed_document(
        self, mock_get_db, MockSettings, MockDM
    ):
        """Withholding "complete" must not also withhold chunk_count and
        chromadb_ready — those stay accurate regardless of extraction state."""
        from app.tasks.document_tasks import perform_semantic_ingestion

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = self._doc()

        settings = MagicMock()
        settings.chromadb_persist_dir = "/data/chroma"
        MockSettings.return_value = settings

        dm_instance = MagicMock()
        dm_instance.add_document.return_value = 0
        MockDM.return_value = dm_instance

        perform_semantic_ingestion(
            raw_text="", document_uuid="doc-1", user_id="user1"
        )

        written = {}
        for call in db.smart_document.update_one.call_args_list:
            written.update(call[0][1].get("$set", {}))
        assert written.get("chromadb_ready") is False
        assert written.get("chunk_count") == 0


# ---------------------------------------------------------------------------
# An OCR outage must retry, not be recorded as an unreadable document (#633)
# ---------------------------------------------------------------------------


class TestOcrOutageReachesTheRetryMachinery:
    """The extraction task's catch-all used to swallow every exception and
    record an error. That is what kept Celery's `autoretry_for` from ever
    engaging for an OCR outage — the exception never escaped the task body."""

    def _doc(self):
        return {
            "uuid": "doc-1",
            "title": "scan.pdf",
            "path": "uploads/scan.pdf",
            "extension": "pdf",
        }

    def _task(self, retries: int):
        """The bound task with `self.request.retries` set to *retries*."""
        from app.tasks.document_tasks import perform_extraction_and_update

        task = perform_extraction_and_update
        task.push_request(retries=retries)
        return task

    @patch("app.tasks.document_tasks.get_sync_db")
    def test_outage_is_reraised_while_retries_remain(self, mock_get_db, tmp_path):
        from app.services.ocr_client import OcrUnavailableError

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = self._doc()

        task = self._task(retries=0)
        try:
            with patch("app.services.document_readers.extract_text_with_markers",
                       side_effect=OcrUnavailableError("OCR down")), \
                 patch("app.tasks.document_tasks.Path") as MockPath:
                MockPath.return_value.exists.return_value = True
                with pytest.raises(OcrUnavailableError):
                    task.run("doc-1", "pdf")
        finally:
            task.pop_request()

        # Nothing recorded as a terminal error — the retry hasn't happened yet.
        statuses = _status_sequence(db)
        assert "error" not in statuses

    @patch("app.tasks.document_tasks.get_sync_db")
    def test_final_attempt_records_an_ocr_specific_message(self, mock_get_db):
        """Out of retries, the user needs to know the service was unreachable —
        not that their file has no text in it, which is a different problem
        with a different fix."""
        from app.services.ocr_client import OcrUnavailableError
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        mock_get_db.return_value = db
        db.smart_document.find_one.return_value = self._doc()

        task = self._task(retries=perform_extraction_and_update.max_retries)
        try:
            with patch("app.services.document_readers.extract_text_with_markers",
                       side_effect=OcrUnavailableError("OCR down")), \
                 patch("app.tasks.document_tasks.Path") as MockPath, \
                 patch("app.tasks.document_tasks._notify_document_processing_failed") as notify:
                MockPath.return_value.exists.return_value = True
                assert task.run("doc-1", "pdf") == ""
        finally:
            task.pop_request()

        written = _set_containing(db, "error_message")
        assert written["task_status"] == "error"
        assert "text-recognition service" in written["error_message"]
        # Not the generic extraction-failed wording.
        assert "Text extraction failed" not in written["error_message"]
        assert notify.called


# ---------------------------------------------------------------------------
# reap_stuck_documents
# ---------------------------------------------------------------------------


class _FakeSmartDocuments:
    """Just enough of a pymongo collection to evaluate the reaper's queries.

    The age cutoff lives in the Mongo filter, so a MagicMock that returns a
    canned list cannot tell a 10-minute-old lock from a 3-hour-old one. This
    evaluates ``$in``, ``$ne``, ``$lt``, ``$or`` and equality (``None``
    matching a null *or missing* field, as Mongo does) against real dicts.
    """

    def __init__(self, rows):
        self.rows = rows
        self.update_filters = []

    @staticmethod
    def _field_matches(row, key, cond):
        present = key in row
        value = row.get(key)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$in":
                    if value not in arg:
                        return False
                elif op == "$ne":
                    if value == arg:
                        return False
                elif op == "$lt":
                    if not present or value is None or not value < arg:
                        return False
                else:
                    raise NotImplementedError(op)
            return True
        if cond is None:
            return not present or value is None
        return value == cond

    def _matches(self, row, query):
        for key, cond in query.items():
            if key == "$or":
                if not any(self._matches(row, branch) for branch in cond):
                    return False
            elif not self._field_matches(row, key, cond):
                return False
        return True

    def find(self, query, projection=None):
        return [dict(r) for r in self.rows if self._matches(r, query)]

    def find_one(self, query, projection=None):
        hits = self.find(query)
        return hits[0] if hits else None

    def update_one(self, query, update):
        self.update_filters.append(query)
        for row in self.rows:
            if self._matches(row, query):
                row.update(update["$set"])
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)


class TestReapStuckDocuments:
    """A worker SIGKILLed mid-extraction leaves processing=True,
    task_status="extracting", raw_text="" — the shape the lock is taken in.
    The original sweep only re-joins a chain that *finished* extracting, so
    such a document said "Reading text…" forever (#812)."""

    def _db(self, rows):
        db = MagicMock()
        db.smart_document = _FakeSmartDocuments(rows)
        db.knowledge_base_sources.find.return_value = []
        return db

    @staticmethod
    def _stuck(uuid, **overrides):
        import datetime as _dt

        row = {
            "uuid": uuid,
            "title": f"{uuid}.pdf",
            "user_id": "owner1",
            "processing": True,
            "task_status": "extracting",
            "task_id": "celery-task",
            "raw_text": "",
            "created_at": _dt.datetime.now() - _dt.timedelta(hours=3),
            "updated_at": _dt.datetime.now() - _dt.timedelta(hours=3),
        }
        row.update(overrides)
        return row

    def _run(self, db):
        from app.tasks.document_tasks import reap_stuck_documents

        with patch("app.tasks.document_tasks.get_sync_db", return_value=db), \
             patch("app.tasks.document_tasks.update_document_fields") as update_step, \
             patch("app.tasks.document_tasks._notify_document_processing_failed") as notify, \
             patch("app.tasks.document_tasks._resume_pending_kb_sources") as resume:
            reap_stuck_documents.run()
        return update_step, notify, resume

    def test_lock_older_than_the_window_is_marked_failed_with_a_retry_hint(self):
        from app.tasks.document_tasks import _EXTRACTION_ABANDONED_MESSAGE

        row = self._stuck("doc-dead")
        db = self._db([row])

        update_step, notify, resume = self._run(db)

        assert row["processing"] is False
        assert row["task_status"] == "error"
        assert row["task_id"] is None
        assert row["error_message"] == _EXTRACTION_ABANDONED_MESSAGE
        assert "Retry the extraction" in row["error_message"]
        # Failed, not completed: the chain's update step would have stamped
        # "complete" over an empty document and re-fired folder automations.
        update_step.delay.assert_not_called()
        notify.assert_called_once_with(db, "doc-dead", _EXTRACTION_ABANDONED_MESSAGE)
        resume.assert_called_once_with(db, "doc-dead", extraction_failed=True)

    def test_lock_inside_the_window_is_left_alone(self):
        import datetime as _dt

        row = self._stuck(
            "doc-live",
            updated_at=_dt.datetime.now() - _dt.timedelta(minutes=10),
        )
        db = self._db([row])

        update_step, notify, resume = self._run(db)

        assert row["processing"] is True
        assert row["task_status"] == "extracting"
        assert "error_message" not in row
        update_step.delay.assert_not_called()
        notify.assert_not_called()
        resume.assert_not_called()

    def test_row_without_a_lock_stamp_is_aged_by_its_upload_time(self):
        """Rows written before the lock stamped updated_at have no clock of
        their own; an old upload still stranded is reaped, a fresh one is
        not."""
        import datetime as _dt

        old = self._stuck("doc-old-unstamped")
        del old["updated_at"]
        fresh = self._stuck(
            "doc-fresh-unstamped",
            created_at=_dt.datetime.now() - _dt.timedelta(minutes=10),
        )
        del fresh["updated_at"]
        db = self._db([old, fresh])

        _, notify, _ = self._run(db)

        assert old["task_status"] == "error"
        assert old["processing"] is False
        assert fresh["task_status"] == "extracting"
        assert fresh["processing"] is True
        assert notify.call_count == 1

    def test_write_is_guarded_on_the_lock_it_matched(self):
        """A document that completed (or was re-locked by a retry) between
        the find and the write must not be flipped to error under it."""
        row = self._stuck("doc-racing")
        db = self._db([row])

        # The row the find returns is a copy; mutate the store between the
        # find and the write the way a finishing worker would.
        original_find = db.smart_document.find

        def find_then_finish(query, projection=None):
            hits = original_find(query, projection)
            if query.get("processing") is True and hits:
                row["processing"] = False
                row["task_status"] = "complete"
                row["raw_text"] = "the text"
            return hits

        db.smart_document.find = find_then_finish

        _, notify, resume = self._run(db)

        assert row["task_status"] == "complete"
        assert "error_message" not in row
        notify.assert_not_called()
        resume.assert_not_called()
        guard = db.smart_document.update_filters[-1]
        assert guard["processing"] is True
        assert guard["updated_at"] == row["updated_at"]

    def test_soft_deleted_lock_is_not_reaped(self):
        row = self._stuck("doc-trashed", soft_deleted=True)
        db = self._db([row])

        _, notify, _ = self._run(db)

        assert row["task_status"] == "extracting"
        notify.assert_not_called()

    def test_finished_but_unadvanced_document_still_gets_the_update_step(self):
        """The original sweep: processing=False with text but an in-progress
        stage means the chain never ran update_document_fields. That path is
        unchanged and must not be confused with the dead-worker one."""
        finished = self._stuck(
            "doc-finished", processing=False, raw_text="extracted text",
        )
        dead = self._stuck("doc-dead")
        db = self._db([finished, dead])

        update_step, notify, _ = self._run(db)

        update_step.delay.assert_called_once_with("doc-finished")
        assert finished["task_status"] == "extracting"  # the update step sets it
        assert dead["task_status"] == "error"
        notify.assert_called_once()

    def test_one_bad_row_does_not_stop_the_sweep(self):
        first = self._stuck("doc-a")
        second = self._stuck("doc-b")
        db = self._db([first, second])

        from app.tasks.document_tasks import reap_stuck_documents

        with patch("app.tasks.document_tasks.get_sync_db", return_value=db), \
             patch("app.tasks.document_tasks.update_document_fields"), \
             patch("app.tasks.document_tasks._notify_document_processing_failed",
                   side_effect=[RuntimeError("bell down"), None]) as notify, \
             patch("app.tasks.document_tasks._resume_pending_kb_sources"):
            reap_stuck_documents.run()  # must not raise

        assert notify.call_count == 2
        assert first["task_status"] == "error"
        assert second["task_status"] == "error"


class TestExtractionStalenessIsOneDefinition:
    """The retry route and the reaper must age the same lock with the same
    clock (#835's complaint, applied to documents). The window is derived
    from Celery's hard time limit, which the extraction task inherits."""

    def test_window_is_twice_the_hard_time_limit(self):
        import datetime as _dt

        from app.celery_app import celery
        from app.services.extraction_staleness import (
            EXTRACTION_STALE_AFTER,
            EXTRACTION_TASK_HARD_TIME_LIMIT_SECONDS,
        )
        from app.tasks.document_tasks import perform_extraction_and_update

        # The extraction task sets no limit of its own, so the global one is
        # what SIGKILLs it; if someone gives it a longer one, this pins the
        # constant to follow.
        hard_limit = perform_extraction_and_update.time_limit or celery.conf.task_time_limit
        assert EXTRACTION_TASK_HARD_TIME_LIMIT_SECONDS == hard_limit
        assert EXTRACTION_STALE_AFTER == _dt.timedelta(seconds=2 * hard_limit)

    def test_route_and_reaper_share_the_constant(self):
        from app.routers import documents as documents_router
        from app.services.extraction_staleness import EXTRACTION_STALE_AFTER

        assert documents_router._EXTRACTION_STALE_AFTER is EXTRACTION_STALE_AFTER

    def test_helper_falls_back_to_created_at_when_unstamped(self):
        import datetime as _dt

        from app.services.extraction_staleness import (
            EXTRACTION_STALE_AFTER,
            extraction_is_stale,
        )

        now = _dt.datetime.now()
        old = now - EXTRACTION_STALE_AFTER - _dt.timedelta(minutes=1)
        recent = now - _dt.timedelta(minutes=10)

        assert extraction_is_stale(old, recent, now=now) is True
        assert extraction_is_stale(recent, old, now=now) is False
        assert extraction_is_stale(None, old, now=now) is True
        assert extraction_is_stale(None, recent, now=now) is False
        assert extraction_is_stale(None, None, now=now) is True
