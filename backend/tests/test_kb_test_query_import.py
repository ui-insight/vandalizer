"""Unit tests for the bulk test-query import parser (CSV / XLSX)."""

import io

import pytest

from app.services.kb_test_query_import import (
    MAX_IMPORT_ROWS,
    TestQueryImportError,
    parse_test_query_import,
    _split_source_labels,
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


# ---------------------------------------------------------------------------
# Source-label separators
# ---------------------------------------------------------------------------


def test_semicolons_separate_labels():
    assert _split_source_labels("Subpart A; Subpart B") == [
        "Subpart A", "Subpart B",
    ]


def test_semicolon_cell_keeps_commas_inside_labels():
    # The real failure: "Subpart D-iii — Monitoring, Reporting, Remedies &
    # Closeout | §§200.328-200.346" is ONE source. Splitting it on commas
    # invented two labels that match nothing, and tripled the denominator of
    # the retrieval-precision score.
    cell = (
        "Subpart D-iii — Monitoring, Reporting, Remedies & Closeout "
        "| §§200.328-200.346; Subpart E-i — Cost Principles"
    )
    assert _split_source_labels(cell) == [
        "Subpart D-iii — Monitoring, Reporting, Remedies & Closeout "
        "| §§200.328-200.346",
        "Subpart E-i — Cost Principles",
    ]


def test_quoted_label_keeps_its_commas():
    cell = '"Appendices I–IV | NOFO, Contract Provisions, Indirect Cost"'
    assert _split_source_labels(cell) == [
        "Appendices I–IV | NOFO, Contract Provisions, Indirect Cost",
    ]


def test_quoted_and_bare_labels_mix():
    assert _split_source_labels('"Monitoring, Reporting"; Subpart E') == [
        "Monitoring, Reporting", "Subpart E",
    ]


def test_quoting_a_single_label_within_a_comma_list_is_not_supported():
    """Quoting *part* of a comma list cannot be made to work.

    csv.reader consumes CSV quoting before this module runs, so the form is
    unreachable for the format most authors use — a cell written
    ``"A, B", C`` arrives here as ``A, B, C`` with nothing left to distinguish
    the intended grouping. Rather than support it only for XLSX and silently
    mis-split every CSV, the supported forms are the semicolon separator and a
    cell that names one real source. This test pins the actual behaviour so the
    limitation is visible rather than assumed away.
    """
    assert _split_source_labels('"A, B", C') == ['"A', 'B"', "C"]
    # The supported way to say the same thing:
    assert _split_source_labels("A, B; C") == ["A, B", "C"]


def test_a_cell_naming_one_real_source_is_not_split():
    """The rescue for an author who wrote a comma-bearing source name plainly.

    This is how the 2 CFR 200 set was poisoned: the name was written as-is,
    split into three labels that named nothing, and every question carrying it
    scored 0 retrieval precision on every run.
    """
    known = ["Subpart D-iii — Monitoring, Reporting, Remedies & Closeout | §§200.328-200.346"]
    cell = "Subpart D-iii — Monitoring, Reporting, Remedies & Closeout | §§200.328-200.346"

    assert _split_source_labels(cell, known) == [cell]
    # With no KB to check against, the old comma behaviour is unchanged.
    assert len(_split_source_labels(cell)) == 3


def test_a_comma_list_of_two_real_sources_still_splits():
    """The known-source check must not glue genuinely separate labels together."""
    known = ["Subpart A — Acronyms", "Subpart B — General"]
    assert _split_source_labels("Subpart A — Acronyms, Subpart B — General", known) == [
        "Subpart A — Acronyms", "Subpart B — General",
    ]


def test_a_label_containing_a_quote_is_not_corrupted():
    """The old per-character scanner consumed quote characters wherever they
    appeared, so a source genuinely named with them no longer matched."""
    assert _split_source_labels('Section 2 "Definitions"') == ['Section 2 "Definitions"']


def test_plain_comma_list_still_splits():
    assert _split_source_labels("Subpart A, Subpart B") == [
        "Subpart A", "Subpart B",
    ]


def test_blank_and_empty_segments_dropped():
    assert _split_source_labels("") == []
    assert _split_source_labels("   ") == []
    assert _split_source_labels("A;;B") == ["A", "B"]
    assert _split_source_labels(" A , B ") == ["A", "B"]


# ---------------------------------------------------------------------------
# Through the CSV layer, not just the splitter
# ---------------------------------------------------------------------------


def test_a_quoted_csv_cell_survives_as_one_label():
    """The gap that let the original fix ship broken.

    Every separator test above calls ``_split_source_labels`` with a raw
    string, which is not how the value arrives: ``csv.reader`` consumes the
    quoting first, so a quoted cell reached the splitter as bare text and was
    split on its commas anyway — the exact defect being fixed. Only an
    end-to-end parse can catch that.
    """
    known = ["Subpart D-ii — Procurement, Property & Subawards"]
    csv_text = (
        "Question,Source\n"
        'Q1,"Subpart D-ii — Procurement, Property & Subawards"\n'
    ).encode()

    rows, errors = parse_test_query_import(
        "t.csv", csv_text, known_source_names=known,
    )
    assert errors == []
    assert rows[0]["expected_source_labels"] == [
        "Subpart D-ii — Procurement, Property & Subawards",
    ]


def test_a_semicolon_csv_cell_survives_as_two_labels():
    csv_text = (
        "Question,Source\n"
        'Q1,"Subpart A — Acronyms; Subpart B — General"\n'
    ).encode()
    rows, _ = parse_test_query_import("t.csv", csv_text)
    assert rows[0]["expected_source_labels"] == [
        "Subpart A — Acronyms", "Subpart B — General",
    ]


def test_parsing_without_kb_context_keeps_the_old_comma_behaviour():
    csv_text = ("Question,Source\n" 'Q1,"Alpha, Beta"\n').encode()
    rows, _ = parse_test_query_import("t.csv", csv_text)
    assert rows[0]["expected_source_labels"] == ["Alpha", "Beta"]
