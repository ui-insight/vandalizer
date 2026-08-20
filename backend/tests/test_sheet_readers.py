"""Server-side spreadsheet rendering for the document viewer.

These formats used to be parsed by SheetJS *in the browser*, over untrusted
uploads rendered in other people's sessions. That package left npm at 0.18.5
carrying two HIGH CVEs with no upgrade path — CVE-2023-30533 is prototype
pollution when parsing a crafted workbook, which is exactly this path. Moving
the parsing here removes the dependency and the exposure together.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from app.services.document_readers import (
    extract_sheet_json_from_csv,
    extract_sheet_json_from_xls,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _csv(text: str) -> dict:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
    try:
        f.write(text)
        f.close()
        return extract_sheet_json_from_csv(f.name)
    finally:
        os.unlink(f.name)


class TestCsv:
    def test_quoted_commas_stay_inside_their_cell(self):
        out = _csv('Name,Amount\n"Smith, J.",1200\n')
        sheet = out["sheets"][0]
        assert sheet["headers"] == ["Name", "Amount"]
        assert sheet["rows"] == [["Smith, J.", "1200"]]

    def test_a_ragged_row_is_padded_to_the_widest(self):
        """A short row would otherwise render as a jagged grid."""
        out = _csv("A,B,C\n1,2\n")
        assert out["sheets"][0]["rows"] == [["1", "2", ""]]

    def test_a_semicolon_file_is_sniffed(self):
        """Excel emits these under several European locales."""
        out = _csv("Name;Amount\nSmith;1200\n")
        assert out["sheets"][0]["headers"] == ["Name", "Amount"]

    def test_a_tab_file_is_sniffed(self):
        out = _csv("Name\tAmount\nSmith\t1200\n")
        assert out["sheets"][0]["headers"] == ["Name", "Amount"]

    def test_a_utf8_bom_is_not_part_of_the_first_header(self):
        """Excel writes one by default; left in place it corrupts the first
        column name and every lookup against it."""
        out = _csv("﻿Name,Amount\nSmith,1200\n")
        assert out["sheets"][0]["headers"][0] == "Name"

    def test_an_empty_file_is_not_an_error(self):
        out = _csv("")
        assert out["sheets"][0]["headers"] == []
        assert out["sheets"][0]["rows"] == []

    def test_a_header_only_file_has_no_rows(self):
        out = _csv("A,B\n")
        assert out["sheets"][0]["headers"] == ["A", "B"]
        assert out["sheets"][0]["rows"] == []

    def test_undecodable_bytes_do_not_raise(self):
        """Spreadsheets arrive in whatever the author's machine used."""
        f = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="wb")
        try:
            f.write("Name,Café\nSmith,1200\n".encode("cp1252"))
            f.close()
            out = extract_sheet_json_from_csv(f.name)
        finally:
            os.unlink(f.name)
        assert out["sheets"][0]["headers"][0] == "Name"


class TestXls:
    """Against a real BIFF file, not a mock — the point is that xlrd's API is
    driven correctly, which a stub could not tell us."""

    @pytest.fixture
    def workbook(self):
        return extract_sheet_json_from_xls(
            os.path.join(FIXTURES, "legacy_workbook.xls"),
        )

    def test_reads_every_sheet_with_its_name(self, workbook):
        assert [s["name"] for s in workbook["sheets"]] == ["Budget", "Hidden"]

    def test_headers_and_rows_split_as_the_viewer_expects(self, workbook):
        budget = workbook["sheets"][0]
        assert budget["headers"] == ["Name", "Amount", "Notes"]
        assert budget["rows"][0] == ["Smith, J.", "1200", "has, commas"]

    def test_a_whole_number_does_not_render_as_a_float(self, workbook):
        """xls stores everything as a double; 1200.0 in a grid reads as a bug."""
        assert workbook["sheets"][0]["rows"][0][1] == "1200"

    def test_a_real_decimal_is_preserved(self, workbook):
        assert workbook["sheets"][0]["rows"][1][1] == "900.5"

    def test_a_short_row_is_padded_to_the_sheet_width(self, workbook):
        assert workbook["sheets"][0]["rows"][1] == ["Jones", "900.5", ""]

    def test_a_hidden_sheet_is_marked_hidden(self, workbook):
        assert workbook["sheets"][0]["hidden"] is False
        assert workbook["sheets"][1]["hidden"] is True
