"""Tests for app.utils.file_validation — allowed extensions and content checks."""

from app.utils.file_validation import is_allowed_file


def test_allowed_extensions():
    assert is_allowed_file("report.pdf") is True
    assert is_allowed_file("data.xlsx") is True
    assert is_allowed_file("doc.docx") is True
    assert is_allowed_file("spreadsheet.xls") is True


def test_disallowed_extensions():
    assert is_allowed_file("script.py") is False
    assert is_allowed_file("image.png") is False
    assert is_allowed_file("archive.zip") is False
    assert is_allowed_file("page.html") is False


def test_no_extension():
    assert is_allowed_file("README") is False


def test_case_insensitive():
    assert is_allowed_file("report.PDF") is True
    assert is_allowed_file("data.XLSX") is True
    assert is_allowed_file("doc.Docx") is True
