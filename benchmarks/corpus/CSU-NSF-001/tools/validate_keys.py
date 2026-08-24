"""Validate ground_truth.json source citations against the actual PDFs.

For every (file, page) a question cites, check that the page exists and that
the answer is actually findable there. An answer that turns up on a *different*
page is the signature of a stale page mapping after a re-layout.

Locates answers with the same helpers the product uses to resolve a citation
(`_pymupdf_extract_with_pages` + `page_for_offset`), so this checks the key
against what Vandalizer would actually see.

Exits non-zero on a missing file, a page out of range, a quoted figure that is
absent from the document cited, or an answer located on a different page.
Reasoned answers carry no distinctive figure and no verbatim quote, so this
pass cannot speak to them either way; they are listed separately.
`validate_keys2.py` is the pass that scores those. That list is pinned in
`KNOWN_UNVERIFIABLE`, because "cannot check this one" is otherwise an unbounded
excuse: a citation that lands there and is not pinned is checked by no pass at
all, so it fails the run until someone says out loud that it should not be.

Run: cd backend && uv run python \\
       ../benchmarks/corpus/CSU-NSF-001/tools/validate_keys.py \\
       --keys ../benchmarks/corpus/CSU-NSF-001 --binaries DIR
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


def repo_root() -> Path:
    """The Vandalizer checkout whose extraction helpers this pass borrows.

    In the tree this file sits four directories under the repository root. The
    corpus also keeps a copy of these tools beside the documents, outside any
    checkout, and the two copies are kept identical on purpose — so the search
    walks up first, then falls back to `VANDALIZER_REPO` and to the default
    clone location, rather than hard-coding one person's home directory.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend" / "app" / "services").is_dir():
            return parent
    candidates = [Path(os.environ["VANDALIZER_REPO"])] if os.environ.get("VANDALIZER_REPO") else []
    candidates.append(Path.home() / "vandalizer")
    for candidate in candidates:
        if (candidate / "backend" / "app" / "services").is_dir():
            return candidate
    raise SystemExit(
        "cannot find the vandalizer checkout: this pass imports the product's own "
        "extraction helpers, so point VANDALIZER_REPO at the repository root"
    )


REPO = repo_root()
sys.path.insert(0, str(REPO / "backend"))

import app.services.document_readers as dr  # noqa: E402
from app.services.extraction_sources import (  # noqa: E402
    find_quote_offset,
    normalize_with_map,
    page_for_offset,
)


# Every (question, document) pair this pass structurally cannot speak to, pinned
# so the set can only change deliberately. Two things land here: a reasoned
# answer, which quotes no figure and no verbatim phrase (that is what
# validate_keys2.py scores), and a supporting document in a multi-source answer
# that restates none of the figures — Q013 takes its dollar amounts from the
# Budget Justification and its rule from the Budget Policy, which quotes no
# figures at all.
#
# Without the pin, "cannot check this one" is an unbounded excuse: repoint a
# source at an unrelated document and a sibling source still carrying the figure
# would keep the run green forever. A pair reaching this list that is not named
# here fails the run instead, so an edit that quietly removes a citation from
# every pass has to be argued for in the diff. Extend with --allow-unverifiable.
KNOWN_UNVERIFIABLE = frozenset({
    ("Q006", "05_Budget_Justification.pdf"),
    ("Q012", "01_CSU_Synthetic_FA_Rate_Agreement.pdf"),
    ("Q012", "05_Budget_Justification.pdf"),
    ("Q013", "02_CSU_Synthetic_Budget_Policy.pdf"),
    ("Q013", "04_Project_Description.pdf"),
    ("Q015", "02_CSU_Synthetic_Budget_Policy.pdf"),
    ("Q015", "05_Budget_Justification.pdf"),
    ("Q019", "02_CSU_Synthetic_Budget_Policy.pdf"),
    ("Q019", "04_Project_Description.pdf"),
    ("Q019", "05_Budget_Justification.pdf"),
    ("Q021", "04_Project_Description.pdf"),
    ("Q021", "05_Budget_Justification.pdf"),
    ("Q021", "09_Mentoring_Plan.pdf"),
    ("Q022", "08_Facilities_Equipment_Resources.pdf"),
    ("Q024", "04_Project_Description.pdf"),
    ("Q024", "12_Current_Pending_PI.pdf"),
    ("Q024", "13_Current_Pending_CoPI.pdf"),
    ("Q025", "05_Budget_Justification.pdf"),
    ("Q025", "12_Current_Pending_PI.pdf"),
    ("Q027", "04_Project_Description.pdf"),
    ("Q027", "08_Facilities_Equipment_Resources.pdf"),
})


def parse_allow_unverifiable(values) -> set[tuple[str, str]]:
    """`--allow-unverifiable Q031:12_New_Document.pdf` -> ('Q031', '12_New_Document.pdf')."""
    allowed = set()
    for value in values or []:
        qid, fname = value.split(":", 1)
        allowed.add((qid, fname))
    return allowed


def numeric_tokens(s: str) -> list[str]:
    """Distinctive numbers in an answer — the part that must appear verbatim.

    A trailing period is stripped before the length test: an answer ending
    "...Ph.D. in Biological Oceanography, 2011." yields the token `2011.`,
    which never matches a document that writes `Ph.D., 2011`. That is sentence
    punctuation, not part of the figure.
    """
    tokens = (t.rstrip(".") for t in re.findall(r"\$?[\d][\d,]*\.?\d*%?", s or ""))
    return [t for t in tokens if len(t) >= 4]


def as_number(token: str):
    """'$807,485.77' -> 807485.77, '58.0%' -> 0.58, else None."""
    raw = token.strip().lstrip("$").replace(",", "")
    percent = raw.endswith("%")
    raw = raw.rstrip("%")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value / 100 if percent else value


def workbook_has(text: str, token: str) -> bool:
    """Is this figure in the workbook, allowing for display rounding?

    The key quotes figures as displayed (rounded to cents, '58.0%'); the
    workbook stores full precision ('807485.766', '0.58'). Comparing the
    strings says nothing, so compare the values — within half a cent, or a
    relative tolerance for rates.
    """
    want = as_number(token)
    if want is None:
        return token in text
    for candidate in re.findall(r"\d[\d,]*\.?\d*", text):
        got = as_number(candidate)
        if got is None:
            continue
        if abs(got - want) <= 0.005 or (want and abs(got - want) / abs(want) < 1e-6):
            return True
    return False


def pages_containing(doc: dict, needle: str) -> list[int]:
    """Every page whose text contains *needle*."""
    hits, start = [], 0
    text = doc["text"]
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            break
        p = page_for_offset(idx, doc["markers"])
        if p is not None and p not in hits:
            hits.append(p)
        start = idx + 1
    return hits


def load_documents(binaries: Path) -> dict:
    docs = {}
    # Extract once per document, keeping real page boundaries.
    for path in sorted((binaries / "pdf").glob("*.pdf")):
        text, markers = dr._pymupdf_extract_with_pages(str(path))
        docs[path.name] = {
            "text": text,
            "markers": markers,
            "norm": normalize_with_map(text),
            "pages": max((m["value"] for m in markers if m.get("kind") == "page"), default=0),
        }

    # The budget workbook is a cited source too. It lives in source/ and has
    # sheets rather than pages, so it needs its own load — otherwise the one
    # question that cites it is reported as a missing file and silently goes
    # unchecked.
    for path in sorted((binaries / "source").glob("*.xlsx")):
        text, markers = dr.extract_text_with_markers(str(path), "xlsx")
        docs[path.name] = {
            "text": text,
            "markers": markers,
            "norm": normalize_with_map(text),
            "pages": 0,          # sheets, not pages
            "sheets": [m["value"] for m in markers if m.get("kind") == "sheet"],
        }
    return docs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True,
                        help="directory holding ground_truth.json")
    parser.add_argument("--binaries", type=Path, required=True,
                        help="directory holding the unpacked release assets (pdf/, source/)")
    parser.add_argument("--allow-unverifiable", action="append", metavar="QID:FILE",
                        help="a (question, document) pair this pass cannot check beyond "
                             "the pinned KNOWN_UNVERIFIABLE set; repeatable")
    args = parser.parse_args()
    allowed_unverifiable = set(KNOWN_UNVERIFIABLE) | parse_allow_unverifiable(
        args.allow_unverifiable
    )

    questions = json.loads((args.keys / "ground_truth.json").read_text())["questions"]
    docs = load_documents(args.binaries)

    bad_page, wrong_page, not_found, missing_file, ok = [], [], [], [], 0
    # A reasoned answer ("No. Internal service-center charges are included in
    # MTDC...") is synthesised, so there is no distinctive figure to look for
    # and no verbatim quote to find. That is not a defect in the key, it is the
    # limit of matching strings — which is why validate_keys2.py exists. Kept
    # apart from `not_found` so this pass can fail on the real thing: an answer
    # that *does* quote a figure, which is then absent from the document cited.
    unverifiable = []

    for q in questions:
        # An answer's figures need to be *somewhere* in the sources the key
        # names — not on every one of them. A multi-source answer distributes
        # itself: Q013 takes its dollar amounts from the Budget Justification
        # and its rule from the Budget Policy, which quotes no figures at all.
        # So resolve per question: if no cited document carries any of the
        # figures, that is a real defect; if some document does, the ones that
        # don't are supporting prose and this pass has nothing to say.
        located_somewhere = False
        pending: list[tuple] = []

        for src in q.get("sources") or []:
            fname, page = src[0], src[1]
            doc = docs.get(fname)
            if doc is None:
                missing_file.append((q["id"], fname))
                continue
            if doc.get("sheets") is not None:
                # Workbook source: no page to check, so verify the answer's
                # figures are actually in the workbook rather than skipping it.
                if page is not None:
                    bad_page.append((q["id"], fname, page, "workbook has no pages"))
                    continue
                if not q.get("answerable", True):
                    ok += 1
                    continue
                answer = str(q.get("answer") or "")
                wanted = numeric_tokens(answer)
                missing = [t for t in wanted if not workbook_has(doc["text"], t)]
                if wanted and missing:
                    not_found.append((q["id"], fname, "workbook",
                                      f"figures absent: {', '.join(missing[:3])}"))
                else:
                    located_somewhere = located_somewhere or bool(wanted)
                    ok += 1
                continue

            if not isinstance(page, int) or not 1 <= page <= doc["pages"]:
                bad_page.append((q["id"], fname, page, doc["pages"]))
                continue

            if not q.get("answerable", True):
                ok += 1  # nothing to locate for an unanswerable item
                continue

            answer = str(q.get("answer") or "")
            tokens = numeric_tokens(answer)
            found_pages = []
            for tok in tokens:
                found_pages += pages_containing(doc, tok)
            if not tokens:
                off = find_quote_offset(doc["text"], answer[:60], doc["norm"])
                if off is not None:
                    p = page_for_offset(off, doc["markers"])
                    if p:
                        found_pages.append(p)

            if not found_pages:
                pending.append((q["id"], fname, page, answer[:48], bool(tokens)))
            elif page in found_pages:
                located_somewhere = True
                ok += 1
            else:
                located_somewhere = True
                wrong_page.append((q["id"], fname, page, sorted(set(found_pages)), answer[:40]))

        for qid, fname, page, excerpt, had_tokens in pending:
            if had_tokens and not located_somewhere:
                not_found.append((qid, fname, page, excerpt))
            else:
                unverifiable.append((qid, fname, page, excerpt))

    def section(title, rows, fmt):
        print(f"\n{title}: {len(rows)}")
        for r in rows:
            print("   " + fmt(r))

    print(f"documents: {len(docs)}   questions: {len(questions)}")
    print(f"citations verified on the cited page: {ok}")
    section("CITED PAGE OUT OF RANGE", bad_page,
            lambda r: f"{r[0]} {r[1]} cites p.{r[2]} but doc has {r[3]}pp")
    section("MISSING FILE", missing_file, lambda r: f"{r[0]} -> {r[1]}")
    section("ANSWER FOUND, BUT ON A DIFFERENT PAGE", wrong_page,
            lambda r: f"{r[0]} {r[1]} cites p.{r[2]}, found on p.{r[3]}  [{r[4]}]")
    section("QUOTED FIGURE NOT LOCATED IN CITED DOC", not_found,
            lambda r: f"{r[0]} {r[1]} p.{r[2]}  [{r[3]}]")
    new_unverifiable = [r for r in unverifiable
                        if (r[0], r[1]) not in allowed_unverifiable]
    section("NOT VERIFIABLE BY STRING MATCH — see validate_keys2.py", unverifiable,
            lambda r: ("known" if (r[0], r[1]) in allowed_unverifiable else "NEW  ")
                      + f" {r[0]} {r[1]} p.{r[2]}  [{r[3]}]")
    for qid, fname in sorted(allowed_unverifiable - {(r[0], r[1]) for r in unverifiable}):
        print(f"   note: {qid} {fname} is pinned unverifiable but no longer reaches "
              f"that list")

    if bad_page or wrong_page or not_found or missing_file or new_unverifiable:
        print("\nKEY VALIDATION: FAIL")
        if new_unverifiable:
            print(f"  {len(new_unverifiable)} citation(s) checked by neither this pass "
                  f"nor validate_keys2.py, and not pinned in KNOWN_UNVERIFIABLE")
        return 1
    print("\nKEY VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
