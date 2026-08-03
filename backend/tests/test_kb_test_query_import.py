"""Unit tests for the bulk test-query import parser (CSV / XLSX)."""

import io

import pytest

from app.services.kb_test_query_import import (
    MAX_IMPORT_ROWS,
    TestQueryImportError,
    parse_test_query_import,
)


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def _xlsx(rows: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCsvParsing:
    def test_full_columns(self):
        data = _csv(
            "Question,Expected Answer,Category,Source or Section,Notes,ID\n"
            '"What is the F&A rate?","52% MTDC",factual,"Rate Agreement","check yearly",RATE-1\n'
        )
        rows, errors = parse_test_query_import("set.csv", data)
        assert errors == []
        assert rows == [{
            "row": 2,
            "query": "What is the F&A rate?",
            "expected_answer": "52% MTDC",
            "expected_answer_contains": None,
            "category": "factual",
            "expected_source_labels": ["Rate Agreement"],
            "notes": "check yearly",
            "external_id": "RATE-1",
        }]

    def test_header_aliases_and_case(self):
        data = _csv(
            "QUERY,Answer,Question Type,Sources,Comment,Stable ID\n"
            "Q1,A1,Summary,\"a; b\",n1,ID-1\n"
        )
        rows, _ = parse_test_query_import("set.csv", data)
        assert rows[0]["query"] == "Q1"
        assert rows[0]["expected_answer"] == "A1"
        assert rows[0]["category"] == "summary"
        assert rows[0]["expected_source_labels"] == ["a", "b"]
        assert rows[0]["notes"] == "n1"
        assert rows[0]["external_id"] == "ID-1"

    def test_question_only_column(self):
        data = _csv("Question\nOnly a question\n")
        rows, errors = parse_test_query_import("set.csv", data)
        assert errors == []
        assert rows[0]["query"] == "Only a question"
        assert rows[0]["expected_answer"] is None
        assert rows[0]["expected_source_labels"] == []
        assert rows[0]["external_id"] is None

    def test_bom_and_blank_rows(self):
        data = "﻿Question,Notes\nQ1,\n,,\n\nQ2,note\n".encode("utf-8")
        rows, errors = parse_test_query_import("set.csv", data)
        assert errors == []
        assert [r["query"] for r in rows] == ["Q1", "Q2"]

    def test_missing_question_column_rejected(self):
        data = _csv("Answer,Notes\nA1,n1\n")
        with pytest.raises(TestQueryImportError, match="question column"):
            parse_test_query_import("set.csv", data)

    def test_row_without_question_reported_not_fatal(self):
        data = _csv("Question,Answer\nQ1,A1\n,orphan answer\nQ3,A3\n")
        rows, errors = parse_test_query_import("set.csv", data)
        assert [r["query"] for r in rows] == ["Q1", "Q3"]
        assert errors == [{"row": 3, "error": "Missing question"}]

    def test_row_numbers_match_spreadsheet(self):
        rows, _ = parse_test_query_import("set.csv", _csv("Question\nQ1\nQ2\n"))
        assert [r["row"] for r in rows] == [2, 3]

    def test_row_cap(self):
        body = "".join(f"Q{i}\n" for i in range(MAX_IMPORT_ROWS + 1))
        with pytest.raises(TestQueryImportError, match="limit"):
            parse_test_query_import("set.csv", _csv("Question\n" + body))

    def test_cp1252_fallback(self):
        # A Windows-Excel CSV export with a smart quote; invalid as UTF-8.
        data = "Question\nWhat is the PI’s role?\n".encode("cp1252")
        rows, errors = parse_test_query_import("set.csv", data)
        assert errors == []
        assert "role" in rows[0]["query"]

    def test_empty_file_rejected(self):
        with pytest.raises(TestQueryImportError, match="empty"):
            parse_test_query_import("set.csv", _csv(""))


class TestXlsxParsing:
    def test_full_columns(self):
        data = _xlsx([
            ["Question", "Expected Answer", "Category", "Source", "Notes", "ID"],
            ["What changed in v2?", "Section 4 was added", "Summary", "Handbook", None, 7.0],
        ])
        rows, errors = parse_test_query_import("set.xlsx", data)
        assert errors == []
        assert rows[0]["query"] == "What changed in v2?"
        assert rows[0]["category"] == "summary"
        assert rows[0]["notes"] is None
        # Excel stores numbers as floats; 7.0 must come back as the stable id "7".
        assert rows[0]["external_id"] == "7"

    def test_blank_and_partial_rows(self):
        data = _xlsx([
            ["Question", "Answer"],
            ["Q1", "A1"],
            [None, None],
            [None, "orphan"],
        ])
        rows, errors = parse_test_query_import("set.xlsx", data)
        assert [r["query"] for r in rows] == ["Q1"]
        assert errors == [{"row": 4, "error": "Missing question"}]

    def test_corrupt_xlsx_rejected(self):
        with pytest.raises(TestQueryImportError, match="Excel"):
            parse_test_query_import("set.xlsx", b"not a zip archive")


class TestFileTypeDispatch:
    def test_legacy_xls_rejected_with_guidance(self):
        with pytest.raises(TestQueryImportError, match=r"\.xlsx or \.csv"):
            parse_test_query_import("set.xls", b"whatever")

    def test_unknown_extension_rejected(self):
        with pytest.raises(TestQueryImportError, match="Unsupported"):
            parse_test_query_import("set.txt", b"Question\nQ1\n")
