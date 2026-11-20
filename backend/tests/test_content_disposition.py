"""Content-Disposition headers for any filename (download.json support ticket)."""

from urllib.parse import unquote

import pytest

from app.utils.content_disposition import content_disposition


def _parts(header: str) -> tuple[str, str]:
    fallback = header.split('filename="', 1)[1].split('"', 1)[0]
    return fallback, unquote(header.split("filename*=UTF-8''", 1)[1])


@pytest.mark.parametrize("name", [
    "Year-by-Year Budget — nih-r01-neuroscience.xlsx",
    "Zażółć gęślą jaźń.pdf",
    "研究計画.docx",
    "Report Final.pdf",
])
def test_any_name_encodes_as_latin1_and_round_trips(name):
    header = content_disposition(name)
    header.encode("latin-1")  # what Starlette does with every header
    fallback, full = _parts(header)
    assert full == name
    assert fallback.isascii() and fallback


def test_fallback_keeps_what_ascii_can_say():
    fallback, _ = _parts(content_disposition("Year-by-Year Budget — nih-r01-neuroscience.xlsx"))
    assert fallback == "Year-by-Year Budget nih-r01-neuroscience.xlsx"


@pytest.mark.parametrize("name", ['a"b.pdf', "a\\b.pdf", "a\r\nSet-Cookie: x=1.pdf"])
def test_quotes_backslashes_and_line_breaks_stay_out_of_the_header(name):
    header = content_disposition(name)
    assert "\r" not in header and "\n" not in header
    fallback, full = _parts(header)
    assert '"' not in fallback and "\\" not in fallback
    assert full == name


def test_disposition_and_empty_name():
    assert content_disposition("x.pdf", "inline").startswith("inline;")
    assert _parts(content_disposition(""))[0] == "download"
