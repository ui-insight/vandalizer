"""Document-aware page-citation scoring, and a breakdown of what goes wrong.

A page-pooling scorer takes every source page for a question and asks whether
a cited number appears in that set. It never checks which *document* the model
named. On a packet where most documents have a page 1 and a page 2, that is
close to free marks: "p. 2" scores correct whenever any source sits on page 2.
It also punishes the reverse case — a correct page of a document the key lists
for a different question.

This resolves each citation to (document, page) where the model names one, and
classifies the outcome so failures can be counted rather than guessed at:

  exact         document and page both match a ground-truth source
  corroborating true citation to a page the canonical set doesn't enumerate --
                the category #628 showed was being punished. The key's
                `corroborating_sources` names these pages: they genuinely
                support the answer, they are just not the passage the key
                picked as canonical. Correct, but non-canonical.
  wrong_page    right document, wrong page        <- marker/attribution failure
  wrong_doc     page exists but in a document not cited for this question
  bare_page     no document named; page matches some source (the old metric)
  bare_miss     no document named; page matches nothing

Only `wrong_page` is unambiguously the failure this work is about. Separating
it from `wrong_doc` -- and both from `corroborating` -- is the point: they have
different fixes, and `corroborating` needs no fix at all.

The header prints how many corroborating pairs the key actually carries. A key
written before v0.4.0 has none, and would silently score as the old metric did;
a zero there says so out loud.

`raw.json` is a list of `{"id": ..., "got": ...}` rows — whatever the harness
got back for each question.

**Not valid for a composite-document run.** Page numbers here are scored
against the key's per-document `sources` and `corroborating_sources`, so they
only mean anything when the model was reading the packet as separate
documents. `run_benchmark_http.py --mode merged` concatenates the same packet
into one continuously paginated PDF, and a citation to page 30 of that PDF is
not page 30 of any document the key names — every number would be scored
against the wrong scale and the result would be confidently wrong rather than
obviously broken. Rows stamped `"mode": "merged"` are therefore refused with a
non-zero exit rather than scored.

Run: cd backend && uv run python \\
       ../benchmarks/corpus/CSU-NSF-001/tools/citation_accuracy.py \\
       --keys ../benchmarks/corpus/CSU-NSF-001 raw.json
"""
import argparse
import collections
import json
import re
from pathlib import Path

# Titles as the model tends to write them, mapped to the filename stem.
#
# v0.5.0 split the two combined personnel documents per person, so three of
# these titles now name two documents apiece. The generic alias resolves to the
# PI's file and the Co-PI's is reached by the longer alias below it — see
# `doc_for()` for how a longer alias starting at the same place wins.
ALIASES = {
    "fa rate agreement": "01", "rate agreement": "01", "f&a rate": "01",
    "budget policy": "02", "csu-rsp-204": "02",
    "project summary": "03",
    "project description": "04",
    "budget justification": "05",
    "data management": "06",
    "references cited": "07",
    "facilities": "08", "equipment": "08",
    "postdoc": "09", "mentoring plan": "09", "mentoring": "09",
    "biographical": "10", "biosketch": "10",
    "biographical sketch (co-pi)": "11", "biosketch (co-pi)": "11",
    "co-pi biosketch": "11", "co-pi biographical": "11",
    "current and pending": "12", "current & pending": "12", "c&p": "12",
    "current and pending (co-pi)": "13", "current & pending (co-pi)": "13",
    "co-pi current and pending": "13",
    "synergistic": "14", "synergistic activities (co-pi)": "15",
    "co-pi synergistic": "15",
    "infrastructure summary": "16", "research infrastructure": "16",
}

CITE = re.compile(r"(?:\bp\.?\s*|\bpage\s+)(\d{1,3})\b", re.I)


def doc_for(context: str) -> str | None:
    """Which document does this citation refer to, if the model said.

    `context` is the text immediately before the citation, so the document it
    belongs to is the *last* one named — not the first. An answer that walks
    through several documents names each one before citing it, and taking the
    earliest mention mis-attributes every citation after the first.
    """
    lowered = context.lower()
    # Compared by where each mention *ends*, not where it starts. Titles now
    # overlap: "the Co-PI biosketch" contains "biosketch", which starts later
    # and names a different document, and by start position the generic title
    # would win every time. On a tie the longer alias wins, which is how
    # "current and pending (co-pi)" beats the "current and pending" inside it.
    best, best_end, best_len = None, -1, 0
    # The extension is optional: self-identifying page markers carry the stem
    # alone (`[05_Budget_Justification p. 2]`) and models copy that form.
    for hit in re.finditer(r"(\d{2})_[a-z][a-z_]*(?:\.pdf)?", lowered):
        if hit.end() > best_end:
            best, best_end, best_len = hit.group(1), hit.end(), len(hit.group(0))
    for alias, stem in ALIASES.items():
        pos = lowered.rfind(alias)
        if pos < 0:
            continue
        end = pos + len(alias)
        if end > best_end or (end == best_end and len(alias) > best_len):
            best, best_end, best_len = stem, end, len(alias)
    return best


# Outcomes worth printing a line about. `exact` and `corroborating` are both
# correct, so neither belongs here.
FAILURE_OUTCOMES = frozenset({"wrong_page", "wrong_doc", "bare_miss"})


def page_pairs(sources) -> set[tuple[str, int]]:
    """(document stem, page) for every source that actually names a page.

    Workbook rows carry a null page — `["CSU_NSF_001_Budget.xlsx", null, ...]` —
    because a spreadsheet has no pagination. They support the answer, but there
    is no page number for a citation to match, so they drop out here rather than
    contaminating the page sets with a `None`.
    """
    return {(s[0][:2], s[1]) for s in (sources or []) if isinstance(s[1], int)}


def classify(doc: str | None, page: int,
             pairs: set[tuple[str, int]],
             pairs_corr: set[tuple[str, int]]) -> str:
    """Which outcome is this one citation? See the module docstring.

    `pairs` is the question's canonical (document, page) set and `pairs_corr`
    its corroborating one. A corroborating hit is deliberately its own outcome
    rather than being folded into `exact`: it is correct, but it is not the
    passage the key chose, and collapsing the two would quietly loosen the
    strict metric.
    """
    if doc is None:
        # No document named, so the page is all there is to go on — and a
        # corroborating page is as true as a canonical one.
        cited_pages = {p for _, p in pairs} | {p for _, p in pairs_corr}
        return "bare_page" if page in cited_pages else "bare_miss"
    if (doc, page) in pairs:
        return "exact"
    if (doc, page) in pairs_corr:
        return "corroborating"
    if doc in {d for d, _ in pairs}:
        return "wrong_page"
    return "wrong_doc"


def refuse_merged(rows: list) -> str | None:
    """The reason this row set must not be citation-scored, or None.

    A composite run paginates the whole packet 1..N continuously, so a cited
    page cannot be resolved to a page of any document the key lists. There is
    no ground truth for that mapping in the shipped key — the harness that
    produced the published results derived it from the deployment's own stored
    page markers, which are not on any HTTP response. Rather than emit numbers
    that look fine and are not, this refuses.
    """
    modes = {row.get("mode") for row in rows if isinstance(row, dict)}
    if "merged" in modes:
        return ("this raw file contains rows from --mode merged, whose page "
                "numbers run 1..N across the whole composite PDF and do not "
                "correspond to the per-document pages in ground_truth.json. "
                "Citation scoring would be confidently wrong. Score attach or "
                "kb rows instead.")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True,
                        help="directory holding ground_truth.json")
    parser.add_argument("raw", type=Path,
                        help="harness output: a JSON list of {id, got} rows")
    args = parser.parse_args(argv)

    rows = json.loads(args.raw.read_text())
    refusal = refuse_merged(rows)
    if refusal:
        print(f"refusing to score: {refusal}")
        return 2
    gt = {q["id"]: q
          for q in json.loads((args.keys / "ground_truth.json").read_text())["questions"]}

    tally = collections.Counter()
    failures = []
    cited_questions = 0
    corroborating_in_key = sum(
        len(page_pairs(q.get("corroborating_sources"))) for q in gt.values()
    )

    for row in rows:
        question = gt[row["id"]]
        pairs = page_pairs(question.get("sources"))
        # Pages that also support the answer but are not the canonical passage.
        pairs_corr = page_pairs(question.get("corroborating_sources"))
        if not pairs:
            continue
        pages = {int(m.group(1)) for m in CITE.finditer(row["got"])}
        if not pages:
            continue
        cited_questions += 1

        for match in CITE.finditer(row["got"]):
            page = int(match.group(1))
            # Look back a little for the document this citation belongs to.
            doc = doc_for(row["got"][max(0, match.start() - 160):match.start()])
            outcome = classify(doc, page, pairs, pairs_corr)
            tally[outcome] += 1
            if outcome in FAILURE_OUTCOMES:
                failures.append((row["id"], outcome, doc, page, sorted(pairs)))

    total = sum(tally.values())
    print(f"corroborating pairs in key: {corroborating_in_key}")
    print(f"questions citing a page : {cited_questions}")
    print(f"citations               : {total}")
    print()
    for key in ("exact", "corroborating", "bare_page", "wrong_page", "wrong_doc", "bare_miss"):
        n = tally[key]
        print(f"  {key:13} {n:4}  {n / total:5.0%}" if total else "")
    good = tally["exact"] + tally["corroborating"] + tally["bare_page"]
    print()
    print(f"defensible (document+page canonical or corroborating, or page with "
          f"no document named): "
          f"{good}/{total} = {good / total:.0%}" if total else "")
    print(f"strict (document named AND both correct): "
          f"{tally['exact']}/{total} = {tally['exact'] / total:.0%}" if total else "")

    if failures:
        print("\nfailures:")
        for qid, kind, doc, page, pairs in failures:
            print(f"  {qid} {kind:10} cited {doc or '??'} p.{page}  truth {pairs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
