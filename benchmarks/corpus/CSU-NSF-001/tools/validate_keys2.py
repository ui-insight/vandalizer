"""Second pass: are prose answers actually *supported* by the page cited?

Pass 1 matched answer strings verbatim, which only works for figures and
quotes. Reasoned answers ("No. Internal service-center charges are included
in MTDC...") are synthesised, so string matching says nothing. Here we score
each citation by how many of the answer's distinctive content words appear on
the cited page, and — the part that matters — whether some *other* page in the
same document scores better, which is what a stale page mapping looks like.

A suspect is a prompt to look, not a proven defect: the key documents the ones
already adjudicated. Pass those with `--allow QID:FILE:PAGE` so a new suspect
is the only thing that fails the run.

Run: cd backend && uv run python \\
       ../benchmarks/corpus/CSU-NSF-001/tools/validate_keys2.py \\
       --keys ../benchmarks/corpus/CSU-NSF-001 --binaries DIR \\
       --allow Q021:04_Project_Description.pdf:11
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

STOP = set("""a an the and or but if then than that this these those of in on at to for from by with
as is are was were be been being it its no not yes any all each per may can will would should must
we our they their he she his her you your i more most some such only other same so if when while
which who whom whose what where how because about into over under between during before after above
below up down out off again further once here there both few nor own too very s t don now includes
included include applies apply project proposal amount total rate charges""".split())


def tokens(s: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}|\$?[\d][\d,]*\.?\d*%?", s or "")
    return {w.lower() for w in words if w.lower() not in STOP and len(w) > 2}


def parse_allow(values) -> set[tuple[str, str, int]]:
    allowed = set()
    for value in values or []:
        qid, fname, page = value.rsplit(":", 2)
        allowed.add((qid, fname, int(page)))
    return allowed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True,
                        help="directory holding ground_truth.json")
    parser.add_argument("--binaries", type=Path, required=True,
                        help="directory holding the unpacked release assets (pdf/)")
    parser.add_argument("--allow", action="append", metavar="QID:FILE:PAGE",
                        help="a suspect already adjudicated and documented in the key; "
                             "repeatable")
    args = parser.parse_args()
    allowed = parse_allow(args.allow)

    docs = {}
    for path in sorted((args.binaries / "pdf").glob("*.pdf")):
        with pymupdf.open(path) as d:
            docs[path.name] = [(pg.get_text("text") or "") for pg in d]

    questions = json.loads((args.keys / "ground_truth.json").read_text())["questions"]
    suspect, fine, unverifiable = [], 0, 0

    for q in questions:
        if not q.get("answerable", True):
            continue
        want = tokens(q.get("answer", ""))
        if len(want) < 3:
            unverifiable += 1
            continue
        # Pages this question already cites, per document. A multi-source answer
        # is synthesised across several pages, so each individual page only
        # carries part of it and scores low on the whole answer. If the "better"
        # page is one the key already points at, the mapping is right and the
        # score is an artefact of scoring each page against the full answer.
        cited_pages = {}
        for src in q.get("sources") or []:
            if isinstance(src[1], int):
                cited_pages.setdefault(src[0], set()).add(src[1])

        for src in q.get("sources") or []:
            fname, page = src[0], src[1]
            pages = docs.get(fname)
            if not pages or not isinstance(page, int) or not 1 <= page <= len(pages):
                continue
            scores = [len(want & tokens(t)) / len(want) for t in pages]
            cited = scores[page - 1]
            best = max(scores)
            best_page = scores.index(best) + 1
            if cited >= 0.5 or cited >= best - 0.05:
                fine += 1
            elif best_page in cited_pages.get(fname, set()):
                fine += 1  # the better page is also cited — key is complete
            else:
                suspect.append((q["id"], fname, page, round(cited, 2),
                                best_page, round(best, 2)))

    print(f"citations well-supported on the cited page : {fine}")
    print(f"answers too short to score                : {unverifiable}")
    print(f"\ncitations where ANOTHER page scores clearly better: {len(suspect)}")
    unexplained = []
    for r in sorted(suspect, key=lambda r: r[3] - r[5]):
        known = (r[0], r[1], r[2]) in allowed
        marker = "known" if known else "NEW  "
        print(f"   {marker} {r[0]} {r[1]:42} cites p.{r[2]} ({r[3]:.0%})  "
              f"better: p.{r[4]} ({r[5]:.0%})")
        if not known:
            unexplained.append(r)

    stale = allowed - {(r[0], r[1], r[2]) for r in suspect}
    for qid, fname, page in sorted(stale):
        print(f"   note: --allow {qid}:{fname}:{page} no longer matches any suspect")

    if unexplained:
        print(f"\nSUPPORT VALIDATION: FAIL ({len(unexplained)} unexplained suspect(s))")
        return 1
    print("\nSUPPORT VALIDATION: PASS (no unexplained suspects)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
