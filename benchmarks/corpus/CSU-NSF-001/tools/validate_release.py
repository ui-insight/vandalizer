#!/usr/bin/env python3
"""Validate structural invariants for the CSU-NSF-001 benchmark release.

The keys live in the tree and the documents live on a release, so the checks
split the same way. Everything that reads only the keys — question parity
between JSON and CSV, version agreement, the budget total, and the structural
rules the corroborating sets must obey — runs with `--keys` alone, which is
what a pull-request job can do. Give it `--binaries` as well and the page
bounds are checked against PDFs actually opened rather than against the
expected page counts recorded here, the reference-citation cross-check runs
over the extracted narrative, and the policy invariants below are checked —
they read the documents, so the key-only job cannot speak to them.

Run: uv run --with pypdf --with python-docx python \\
       benchmarks/corpus/CSU-NSF-001/tools/validate_release.py \\
       --keys benchmarks/corpus/CSU-NSF-001 [--binaries DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from pypdf import PdfReader


EXPECTED_PDFS = {
    "01_CSU_Synthetic_FA_Rate_Agreement.pdf": 2,
    "02_CSU_Synthetic_Budget_Policy.pdf": 3,
    "03_Project_Summary.pdf": 1,
    "04_Project_Description.pdf": 13,
    "05_Budget_Justification.pdf": 3,
    "06_Data_Management_Plan.pdf": 2,
    "07_References_Cited.pdf": 3,
    "08_Facilities_Equipment_Resources.pdf": 2,
    "09_Mentoring_Plan.pdf": 1,
    "10_Biographical_Sketch_PI.pdf": 2,
    "11_Biographical_Sketch_CoPI.pdf": 2,
    "12_Current_Pending_PI.pdf": 2,
    "13_Current_Pending_CoPI.pdf": 2,
    "14_Synergistic_Activities_PI.pdf": 1,
    "15_Synergistic_Activities_CoPI.pdf": 1,
    "16_CSU_Research_Infrastructure_Summary.pdf": 2,
}
# 16 documents, 42 pages. These are observed page counts, not policy limits:
# PAPPG 24-1 removed the three-page cap on a biographical sketch, so a sketch
# growing a page is a re-layout to notice, not a compliance failure.

# The system inputs that are not PDFs. All three are workbooks a question can
# cite, and all three are listed in the manifest, so the set has to be spelled
# out rather than assumed to be the budget alone.
WORKBOOKS = {
    "CSU_NSF_001_Budget.xlsx",
    "COA_PI.xlsx",
    "COA_CoPI.xlsx",
}
BUDGET_WORKBOOK = "CSU_NSF_001_Budget.xlsx"

DISPLAY_BUDGET_TOTAL = 1184398.51

# Every document was exported by the same LibreOffice, and every page carries
# the synthetic-corpus banner. Both are cheap to state and expensive to lose:
# a re-render by a different build is what moves page boundaries under the
# answer key, and a page without the banner is a page that could be mistaken
# for a real proposal.
EXPECTED_PRODUCER = "LibreOffice 24.2"
PAGE_BANNER = "SYNTHETIC BENCHMARK"


# ----------------------------------------------------------- policy invariants
#
# Three rules the v0.5.0 modernization established, each one a defect the
# corpus actually carried. They are stated here so the document set cannot
# drift back into them silently.
#
# (a) The Facilities, Equipment and Other Resources statement quantifies
#     nothing. PAPPG 24-1 II.D.2.g asks for a narrative description of the
#     resources available; a dollar figure there reads as an offer of
#     institutional cost sharing, which the proposal does not make.
# (b) The subaward MTDC threshold is one number, stated identically wherever
#     it appears and equal to the constant the budget workbook computes with.
# (c) Current and Pending (Other) Support carries no "recently completed"
#     category. PAPPG 24-1 II.D.2.h removed it; v0.4.0's document still had
#     the heading.
NO_MONEY_PDF = "08_Facilities_Equipment_Resources.pdf"
MONEY = re.compile(r"\$\s*[\d,.]+")
QUANTIFIED_MONEY = re.compile(r"\b\d[\d,.]*\s*(?:thousand|million|billion)\b", re.I)

SUBAWARD_PDFS = (
    "01_CSU_Synthetic_FA_Rate_Agreement.pdf",
    "02_CSU_Synthetic_Budget_Policy.pdf",
    "05_Budget_Justification.pdf",
)
# Matched over whitespace-normalised text, because the sentence wraps in every
# one of the three documents and one of them writes "of the subaward" where the
# others write "of each subaward". A pattern that only matched the rate
# agreement's exact wording would find nothing in the Budget Justification and
# report agreement between two documents and a silence.
SUBAWARD_SENTENCE = re.compile(r"first\s+\$([\d,]+)\s+of\s+(?:each|the)\s+subaward", re.I)
SUBAWARD_THRESHOLD = 50000
# The row of the budget workbook's Assumptions sheet that holds the same number
# as a constant the formulas use. Looked up by label rather than by cell, so a
# row inserted above it does not turn the check into a comparison with nothing.
WORKBOOK_CAP_LABEL = "subaward mtdc inclusion cap"

CURRENT_PENDING_PDFS = (
    "12_Current_Pending_PI.pdf",
    "13_Current_Pending_CoPI.pdf",
)


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def is_completed_category_heading(line: str) -> bool:
    """Is this line a support-category heading naming a 'completed' category?

    Heading-shaped, not word-shaped, and the distinction is the whole check.
    "Completed" is legitimate prose in these documents: the CHIPS §10634
    certification every personnel document carries says the senior personnel
    "have completed the requisite research security training", and the
    infrastructure summary — which is not a Current and Pending document and
    is not checked here — has a table column of "Completed" project statuses.
    What PAPPG 24-1 removed is the *category*, which appears as its own short
    line: v0.4.0 wrote it "Recently completed (listed for completeness)".

    So: drop a parenthetical gloss, drop the form's leading asterisk and a
    trailing colon, and ask whether what is left is a label of a few words with
    no sentence punctuation, one of which is "completed".
    """
    text = re.sub(r"\([^)]*\)", " ", line).strip()
    text = text.lstrip("*").strip().rstrip(":").strip()
    if not text or "." in text:
        return False
    words = text.split()
    return len(words) <= 4 and any(word.strip(",;:").lower() == "completed" for word in words)


def workbook_number(path: Path, label: str) -> float | None:
    """The numeric cell on the row whose label cell reads *label*, or None.

    Read with `zipfile` rather than openpyxl: this tool ships with the corpus
    and runs from an environment carrying pypdf and python-docx, and a workbook
    is a zip of XML — a cell holds an index into the shared-string table, an
    inline string, or a literal value.
    """
    with zipfile.ZipFile(path) as archive:
        members = set(archive.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in members:
            table = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iterfind(".//{*}t"))
                      for item in table.iterfind("{*}si")]

        def cell_text(cell) -> str:
            kind = cell.get("t")
            if kind == "s":
                raw = cell.findtext("{*}v")
                index = int(raw) if raw and raw.isdigit() else None
                return shared[index] if index is not None and index < len(shared) else ""
            if kind == "inlineStr":
                return "".join(node.text or "" for node in cell.iterfind(".//{*}t"))
            return cell.findtext("{*}v") or ""

        for part in sorted(name for name in members
                           if name.startswith("xl/worksheets/") and name.endswith(".xml")):
            for row in ET.fromstring(archive.read(part)).iterfind(".//{*}row"):
                cells = list(row.iterfind("{*}c"))
                texts = [cell_text(cell) for cell in cells]
                if not any(text.strip().lower() == label for text in texts):
                    continue
                for cell, text in zip(cells, texts):
                    if cell.get("t") in (None, "n") and text.strip():
                        try:
                            return float(text)
                        except ValueError:
                            continue
    return None


def check_policy_invariants(page_text: dict[str, list[str]], budget_workbook: Path,
                            failures: list[str]) -> None:
    """The three rules above, each violation reported with its file and detail."""
    pages = page_text.get(NO_MONEY_PDF)
    if pages is None:
        fail(f"{NO_MONEY_PDF}: absent, so the no-quantification rule went unchecked",
             failures)
    else:
        for number, text in enumerate(pages, start=1):
            for hit in MONEY.findall(text) + QUANTIFIED_MONEY.findall(text):
                fail(f"{NO_MONEY_PDF} p.{number}: facilities statement quantifies a "
                     f"resource ({hit.strip()!r}); it must describe what is available "
                     f"without putting a figure on it", failures)

    if budget_workbook is None or not budget_workbook.exists():
        cap = None
        fail(f"{BUDGET_WORKBOOK}: absent, so the subaward threshold was compared with "
             f"nothing", failures)
    else:
        cap = workbook_number(budget_workbook, WORKBOOK_CAP_LABEL)
        if cap is None:
            fail(f"{BUDGET_WORKBOOK}: no numeric cell on a row labelled "
                 f"'{WORKBOOK_CAP_LABEL}'; the subaward threshold was compared with "
                 f"nothing", failures)
        elif cap != SUBAWARD_THRESHOLD:
            fail(f"{BUDGET_WORKBOOK}: subaward MTDC inclusion cap is {cap:,.0f}, "
                 f"expected {SUBAWARD_THRESHOLD:,}", failures)

    for filename in SUBAWARD_PDFS:
        pages = page_text.get(filename)
        if pages is None:
            fail(f"{filename}: absent, so the subaward threshold went unchecked", failures)
            continue
        normalised = re.sub(r"\s+", " ", "\n".join(pages))
        stated = SUBAWARD_SENTENCE.findall(normalised)
        if not stated:
            fail(f"{filename}: states no subaward MTDC threshold; the three documents "
                 f"are checked against each other, so a document that stops saying it "
                 f"makes the agreement vacuous", failures)
            continue
        for value in stated:
            amount = int(value.replace(",", ""))
            if amount != SUBAWARD_THRESHOLD:
                fail(f"{filename}: subaward MTDC threshold stated as ${value}, expected "
                     f"${SUBAWARD_THRESHOLD:,}", failures)
            elif cap is not None and amount != cap:
                fail(f"{filename}: subaward MTDC threshold ${value} disagrees with the "
                     f"workbook's inclusion cap {cap:,.0f}", failures)

    for filename in CURRENT_PENDING_PDFS:
        pages = page_text.get(filename)
        if pages is None:
            fail(f"{filename}: absent, so the retired 'completed' category went "
                 f"unchecked", failures)
            continue
        for number, text in enumerate(pages, start=1):
            for line in text.splitlines():
                if is_completed_category_heading(line):
                    fail(f"{filename} p.{number}: current and pending support carries a "
                         f"retired 'completed' category heading ({line.strip()!r})",
                         failures)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True,
                        help="directory holding ground_truth.json, manifest.json, "
                             "benchmark_questions.csv")
    parser.add_argument("--binaries", type=Path,
                        help="directory holding the unpacked release assets "
                             "(pdf/, source/); omit for key-only checks")
    args = parser.parse_args()
    keys = args.keys
    binaries = args.binaries
    failures: list[str] = []

    ground_truth = json.loads((keys / "ground_truth.json").read_text())
    manifest = json.loads((keys / "manifest.json").read_text())
    with (keys / "benchmark_questions.csv").open(newline="", encoding="utf-8") as handle:
        csv_questions = list(csv.DictReader(handle))

    questions = ground_truth["questions"]
    if len(questions) != 30:
        fail(f"expected 30 ground-truth questions, found {len(questions)}", failures)
    if len(csv_questions) != 30:
        fail(f"expected 30 CSV questions, found {len(csv_questions)}", failures)

    json_by_id = {question["id"]: question for question in questions}
    csv_by_id = {question["id"]: question for question in csv_questions}
    if set(json_by_id) != set(csv_by_id):
        fail("ground_truth.json and benchmark_questions.csv question IDs differ", failures)
    for question_id in sorted(set(json_by_id) & set(csv_by_id)):
        json_question = json_by_id[question_id]
        csv_question = csv_by_id[question_id]
        for field in ("difficulty", "type", "question"):
            if str(json_question[field]) != csv_question[field]:
                fail(f"{question_id}: field '{field}' differs between JSON and CSV", failures)
        if str(bool(json_question["answerable"])) != csv_question["answerable"]:
            fail(f"{question_id}: answerable differs between JSON and CSV", failures)

    # With the binaries, page bounds are checked against the documents as they
    # actually are; without them, against the counts recorded above. The second
    # is weaker — it cannot notice a re-layout — which is why the asset job
    # exists at all.
    page_text: dict[str, list[str]] = {}
    if binaries is None:
        page_counts = dict(EXPECTED_PDFS)
    else:
        page_counts = {}
        for filename, expected_pages in EXPECTED_PDFS.items():
            path = binaries / "pdf" / filename
            if not path.exists():
                fail(f"missing PDF: {filename}", failures)
                continue
            reader = PdfReader(path)
            page_text[filename] = [page.extract_text() or "" for page in reader.pages]
            actual_pages = len(reader.pages)
            page_counts[filename] = actual_pages
            if actual_pages != expected_pages:
                fail(f"{filename}: expected {expected_pages} pages, found {actual_pages}", failures)
            producer = (reader.metadata or {}).get("/Producer") or ""
            if EXPECTED_PRODUCER not in producer:
                fail(f"{filename}: produced by {producer!r}, expected {EXPECTED_PRODUCER}",
                     failures)
            for number, text in enumerate(page_text[filename], start=1):
                if PAGE_BANNER not in text:
                    fail(f"{filename} p.{number}: missing the {PAGE_BANNER} banner",
                         failures)

    def workbook_missing(filename: str) -> bool:
        """Only the asset job can see the workbook; the tree job takes it on trust."""
        return binaries is not None and not (binaries / "source" / filename).exists()

    for question in questions:
        for source in question.get("sources", []):
            filename, page_number = source[0], source[1]
            if filename.endswith(".xlsx"):
                if workbook_missing(filename):
                    fail(f"{question['id']}: missing source workbook {filename}", failures)
                if page_number is not None:
                    fail(f"{question['id']}: workbook source must not have a page number", failures)
                continue
            if filename not in page_counts:
                fail(f"{question['id']}: unknown source document {filename}", failures)
            elif not isinstance(page_number, int):
                fail(f"{question['id']}: {filename} page must be an integer, "
                     f"found {page_number!r}", failures)
            elif not 1 <= page_number <= page_counts[filename]:
                fail(
                    f"{question['id']}: page {page_number} outside {filename} "
                    f"(1-{page_counts[filename]})",
                    failures,
                )

    for question in questions:
        corroborating = question.get("corroborating_sources")
        if corroborating is None:
            fail(f"{question['id']}: missing corroborating_sources", failures)
            continue
        if not question.get("answerable", True) and corroborating:
            fail(f"{question['id']}: unanswerable question has corroborating_sources", failures)
        canonical = {(s[0], s[1]) for s in question.get("sources", [])}
        for source in corroborating:
            filename, page_number = source[0], source[1]
            if (filename, page_number) in canonical:
                fail(f"{question['id']}: corroborating source duplicates sources: "
                     f"{filename} p.{page_number}", failures)
            if filename.endswith(".xlsx"):
                if workbook_missing(filename):
                    fail(f"{question['id']}: missing corroborating workbook {filename}", failures)
                if page_number is not None:
                    fail(f"{question['id']}: workbook corroborating source must not have a page",
                         failures)
                continue
            if filename not in page_counts:
                fail(f"{question['id']}: unknown corroborating document {filename}", failures)
            elif not isinstance(page_number, int):
                fail(f"{question['id']}: corroborating {filename} page must be an integer, "
                     f"found {page_number!r}", failures)
            elif not 1 <= page_number <= page_counts[filename]:
                fail(f"{question['id']}: corroborating page {page_number} outside {filename}",
                     failures)

    if binaries is not None:
        check_policy_invariants(page_text, binaries / "source" / BUDGET_WORKBOOK, failures)

        project_text = "\n".join(page_text.get("04_Project_Description.pdf", []))
        references_text = "\n".join(page_text.get("07_References_Cited.pdf", []))
        cited: set[int] = set()
        for bracket in re.findall(r"\[([0-9,\-\s]+)\]", project_text):
            for part in bracket.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = (int(value) for value in part.split("-", 1))
                    cited.update(range(start, end + 1))
                elif part:
                    cited.add(int(part))
        listed = {int(value) for value in re.findall(r"(?m)^\s*\[(\d+)\]", references_text)}
        expected_references = set(range(1, 25))
        if cited != expected_references:
            fail(f"Project Description citation set is {sorted(cited)}, expected 1-24", failures)
        if listed != expected_references:
            fail(f"References Cited set is {sorted(listed)}, expected 1-24", failures)

    system_inputs = set(manifest["system_input_files"])
    expected_inputs = set(EXPECTED_PDFS) | WORKBOOKS
    if system_inputs != expected_inputs:
        fail("manifest system_input_files does not match release inputs", failures)
    if manifest.get("version") != ground_truth.get("version"):
        fail("manifest and ground-truth versions differ", failures)
    if ground_truth.get("display_budget_total") != DISPLAY_BUDGET_TOTAL:
        fail("display budget total changed", failures)

    if failures:
        print("RELEASE VALIDATION: FAIL")
        for message in failures:
            print(f"- {message}")
        sys.exit(1)

    if binaries is None:
        print(
            f"RELEASE VALIDATION: PASS (keys only; {len(questions)} questions, "
            f"pages bounded by EXPECTED_PDFS, reference cross-check skipped)"
        )
    else:
        print(
            f"RELEASE VALIDATION: PASS (keys and binaries; {len(questions)} questions, "
            f"{sum(page_counts.values())} PDF pages, 24 references)"
        )


if __name__ == "__main__":
    main()
