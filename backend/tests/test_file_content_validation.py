"""Tests for is_valid_file_content — magic byte and zip structure validation."""

import io
import zipfile

from app.utils.file_validation import is_valid_file_content


def _make_zip(entries: dict[str, str]) -> bytes:
    """Create an in-memory zip with the given filename->content entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestPDFValidation:
    def test_valid_pdf_header(self):
        data = b"%PDF-1.4 some content here"
        assert is_valid_file_content(data, "pdf") is True

    def test_pdf_header_not_at_byte_zero(self):
        """Some PDFs have a BOM or whitespace before %PDF-."""
        data = b"\xef\xbb\xbf%PDF-1.7 content"
        assert is_valid_file_content(data, "pdf") is True

    def test_random_bytes_not_pdf(self):
        data = b"this is just random text, not a PDF"
        assert is_valid_file_content(data, "pdf") is False

    def test_empty_bytes_not_pdf(self):
        assert is_valid_file_content(b"", "pdf") is False

    def test_extension_case_insensitive(self):
        data = b"%PDF-1.4 content"
        assert is_valid_file_content(data, "PDF") is True
        assert is_valid_file_content(data, ".pdf") is True

    def test_exe_disguised_as_pdf(self):
        """An EXE file renamed to .pdf should be rejected."""
        data = b"MZ\x90\x00" + b"\x00" * 1000
        assert is_valid_file_content(data, "pdf") is False


class TestDOCXValidation:
    def test_valid_docx(self):
        data = _make_zip({"word/document.xml": "<doc/>", "[Content_Types].xml": "<types/>"})
        assert is_valid_file_content(data, "docx") is True

    def test_zip_without_word_dir(self):
        """A valid zip but without word/ entries is not a real DOCX."""
        data = _make_zip({"readme.txt": "hello"})
        assert is_valid_file_content(data, "docx") is False

    def test_not_a_zip(self):
        assert is_valid_file_content(b"not a zip file", "docx") is False

    def test_wrong_magic_bytes(self):
        """Starts with something other than PK header."""
        assert is_valid_file_content(b"\x00\x00\x00\x00", "docx") is False


class TestXLSXValidation:
    def test_valid_xlsx(self):
        data = _make_zip({"xl/worksheets/sheet1.xml": "<ws/>", "[Content_Types].xml": "<types/>"})
        assert is_valid_file_content(data, "xlsx") is True

    def test_zip_without_xl_dir(self):
        data = _make_zip({"readme.txt": "hello"})
        assert is_valid_file_content(data, "xlsx") is False

    def test_docx_is_not_xlsx(self):
        """A DOCX file should not pass xlsx validation."""
        data = _make_zip({"word/document.xml": "<doc/>"})
        assert is_valid_file_content(data, "xlsx") is False


class TestUnsupportedExtensions:
    def test_xls_returns_false(self):
        """is_valid_file_content only checks pdf/docx/xlsx, not xls."""
        assert is_valid_file_content(b"\xd0\xcf\x11\xe0", "xls") is False

    def test_html_returns_false(self):
        assert is_valid_file_content(b"<html></html>", "html") is False
