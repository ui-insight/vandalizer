"""A damaged .xlsx is told apart from a failure a retry can fix.

Support ticket: a corrupted workbook passed the upload check (it only looks for
an xl/ folder in the zip), then failed extraction with "File conversion failed
after 1 attempts: - XlsxConverter threw XMLSyntaxError …", and the user was told
to use Retry extraction, which could never work. The viewer showed a bare
"Sheet rendering not available".
"""

import base64
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pytest

from app.config import Settings
from app.services.document_readers import (
    DocumentReadError,
    UnreadableFileError,
    describe_damaged_workbook,
    extract_sheet_json_from_xlsx,
    extract_text_from_file,
    extract_text_from_xlsx,
)


def _good(path):
    wb = openpyxl.Workbook()
    wb.active["A1"] = "Budget"
    wb.active["B1"] = 1200
    wb.save(path)
    return str(path)


def _rewrite(src, dst, transform):
    """Copy a workbook, passing each member through ``transform(name, data)``."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for name in zin.namelist():
            zout.writestr(name, transform(name, zin.read(name)))
    return str(dst)


@pytest.fixture
def good(tmp_path):
    return _good(tmp_path / "good.xlsx")


@pytest.fixture
def truncated_xml(tmp_path, good):
    """Passes the upload container check; workbook.xml is cut off mid-tag."""
    return _rewrite(
        good, tmp_path / "broken.xlsx",
        lambda n, d: d[: len(d) // 2] if n == "xl/workbook.xml" else d,
    )


@pytest.fixture
def truncated_sheet(tmp_path, good):
    return _rewrite(
        good, tmp_path / "broken-sheet.xlsx",
        lambda n, d: d[: len(d) // 2] if n == "xl/worksheets/sheet1.xml" else d,
    )


@pytest.fixture
def truncated_zip(tmp_path, good):
    raw = open(good, "rb").read()
    path = tmp_path / "cut.xlsx"
    path.write_bytes(raw[: len(raw) * 2 // 3])
    return str(path)


class TestDescribeDamagedWorkbook:
    def test_entity_declaration_is_refused_not_raised(self, tmp_path, good):
        """A part declaring an entity (never written by Excel) is reported,
        not left to raise out of the check (defusedxml raised EntitiesForbidden)."""
        evil = _rewrite(
            good, tmp_path / "entity.xlsx",
            lambda n, d: (
                b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
                if n == "xl/workbook.xml" else d
            ),
        )
        assert "xl/workbook.xml" in describe_damaged_workbook(evil)

    def test_large_valid_part_is_not_damaged(self, tmp_path):
        """A big valid sheet streams through without being called damaged."""
        wb = openpyxl.Workbook()
        ws = wb.active
        for r in range(1, 5001):
            ws.append([r, f"row {r}", r * 1.5])
        path = tmp_path / "big.xlsx"
        wb.save(path)
        assert describe_damaged_workbook(str(path)) is None

    def test_a_good_workbook_is_not_damaged(self, good):
        assert describe_damaged_workbook(good) is None

    def test_a_cut_off_xml_part_is_named(self, truncated_xml):
        message = describe_damaged_workbook(truncated_xml)
        assert message.startswith("This workbook is damaged")
        assert "xl/workbook.xml" in message
        assert "Save As" in message

    def test_a_cut_off_file_is_damaged(self, truncated_zip):
        assert "cut off" in describe_damaged_workbook(truncated_zip)

    def test_a_bad_checksum_is_damaged(self, tmp_path, good):
        raw = bytearray(open(good, "rb").read())
        with zipfile.ZipFile(good) as zf:
            info = zf.getinfo("xl/workbook.xml")
        # Flip a byte inside the stored (compressed) data of that member.
        data_start = info.header_offset + 30 + len(info.filename) + len(info.extra)
        raw[data_start + 5] ^= 0xFF
        path = tmp_path / "crc.xlsx"
        path.write_bytes(bytes(raw))
        assert describe_damaged_workbook(str(path)).startswith("This workbook is damaged")

    def test_a_missing_file_is_not_called_damaged(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            describe_damaged_workbook(str(tmp_path / "gone.xlsx"))

    def test_accepts_bytes(self, truncated_xml):
        assert describe_damaged_workbook(io.BytesIO(open(truncated_xml, "rb").read()))


class TestReadersSayDamaged:
    def test_text_extraction_raises_the_final_error(self, truncated_xml):
        with pytest.raises(UnreadableFileError) as raised:
            extract_text_from_xlsx(truncated_xml)
        assert "XlsxConverter" not in str(raised.value)
        assert "damaged" in str(raised.value)

    def test_a_damaged_sheet_part_is_caught_too(self, truncated_sheet):
        with pytest.raises(UnreadableFileError):
            extract_text_from_xlsx(truncated_sheet)

    def test_the_generic_reader_passes_it_through_unwrapped(self, truncated_xml):
        with pytest.raises(UnreadableFileError) as raised:
            extract_text_from_file(truncated_xml, "xlsx")
        assert not str(raised.value).startswith("Could not read")

    def test_the_viewer_gets_the_reason(self, truncated_xml):
        with pytest.raises(UnreadableFileError, match="damaged"):
            extract_sheet_json_from_xlsx(truncated_xml)

    def test_a_good_workbook_still_reads_and_renders(self, good):
        assert "Budget" in extract_text_from_xlsx(good)
        assert extract_sheet_json_from_xlsx(good)["sheets"]

    def test_unreadable_is_still_a_document_read_error(self):
        # Every existing `except DocumentReadError` keeps catching it.
        assert issubclass(UnreadableFileError, DocumentReadError)


class TestExtractionTaskRecordsRetryability:
    def _run(self, tmp_path, filename):
        from app.tasks.document_tasks import perform_extraction_and_update

        db = MagicMock()
        db.smart_document.find_one.return_value = {"uuid": "doc-1", "path": filename}
        settings = MagicMock()
        settings.upload_dir = str(tmp_path)
        with patch("app.tasks.document_tasks.get_sync_db", return_value=db), \
             patch("app.config.Settings", return_value=settings):
            perform_extraction_and_update(document_uuid="doc-1", extension="xlsx")
        for call in db.smart_document.update_one.call_args_list:
            payload = call[0][1].get("$set", {})
            if payload.get("task_status") == "error":
                return payload
        raise AssertionError("no error write")

    def test_a_damaged_workbook_is_not_retryable(self, tmp_path, truncated_xml):
        written = self._run(tmp_path, "broken.xlsx")
        assert written["error_retryable"] is False
        assert written["error_message"].startswith("This workbook is damaged")

    def test_a_reader_crash_stays_retryable(self, tmp_path, good):
        with patch(
            "app.services.document_readers.extract_text_from_xlsx",
            side_effect=RuntimeError("worker ran out of memory"),
        ):
            written = self._run(tmp_path, "good.xlsx")
        # Unset means retryable (the default for every older document too).
        assert written.get("error_retryable") is not False


class TestUploadRejectsDamagedWorkbook:
    @pytest.mark.asyncio
    async def test_upload_refuses_with_the_reason(self, truncated_xml, tmp_path):
        from app.services.file_service import upload_document

        user = MagicMock(user_id="u1", is_admin=False)
        settings = Settings(max_upload_size_mb=5, upload_dir=str(tmp_path / "uploads"),
                            jwt_secret_key="t", environment="development")
        blob = base64.b64encode(open(truncated_xml, "rb").read()).decode()
        storage = MagicMock(write=AsyncMock())
        with patch("app.services.file_service.SmartDocument") as MockDoc, \
             patch("app.services.storage.get_storage", return_value=storage):
            MockDoc.find_one = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="This workbook is damaged"):
                await upload_document(blob=blob, filename="broken.xlsx",
                                      raw_extension="xlsx", user=user, settings=settings)
        storage.write.assert_not_called()

    def test_m365_attachment_intake_refuses_it(self, truncated_xml, good):
        from app.tasks.m365_tasks import _attachment_rejection

        assert _attachment_rejection("b.xlsx", open(truncated_xml, "rb").read()) == "damaged workbook"
        assert _attachment_rejection("g.xlsx", open(good, "rb").read()) is None
