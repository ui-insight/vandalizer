"""Triage answer correctness for a harness run against the shipped key.

`raw.json` is a list of rows carrying, per question, what the key expects and
what the system under test actually said. `run_benchmark_http.py` writes rows in
this shape; any harness can:

    {"id": "Q001", "type": "exact_extraction", "answerable": true,
     "question": "...", "expected": "$1,184,398.51", "got": "..."}

**This tool triages; it does not adjudicate.** It auto-marks a row PASS only
when the decisive content is unambiguously present by a mechanical test, FAIL
only when a mechanical test is decisive against it, and defers everything else
to REVIEW for a human. On the published v0.5.0 run it deferred 327 of 900 rows,
and every one of those was read by a person before any number was published.
A REVIEW count is not a failure count and must never be reported as one.

The adjudication rubric, stated so a reader can argue with it
------------------------------------------------------------
    **Decisive content** is the minimal set of assertions that answers the
    question *as asked*. Supporting breakdowns that appear in the key but that
    the question did not request are **not** required. A row **PASSes** iff
    every decisive element is present and correct and nothing in the answer
    contradicts it. A row **FAILs** otherwise. For the unanswerable items a row
    PASSes iff it states that the information is absent **and** invents no
    specific; inventing a specific is a hard fail regardless of the rest of the
    answer.

Two halves of that rubric are not mechanically checkable and are therefore left
to the human pass rather than guessed at here:

* *"nothing in the answer contradicts it"* — a prose claim can be wrong beside
  a correct figure. Rows whose decisive content is prose land in REVIEW.
* *"invents no specific"* — **nothing here checks for fabrication.** An answer
  that states the absence and then invents a specific auto-PASSes as a correct
  abstention, and that is a known limitation rather than an oversight: deciding
  whether a named specific is invented needs the world, not the key.

  Measured on the published run, so the limitation is stated with the rows that
  demonstrate it. Four rows have exactly that shape — all Q018, all
  knowledge-base mode: each declines ("*the specific model … is not stated in
  the retrieved documents*") and then, under an explicit *beyond the retrieved
  sources* heading, names real instrument brands as examples of the kind of
  name the documents do not carry. One of those names appears to be invented
  outright. All four PASS here, and the human adjudication passed them too,
  because none of them asserts the proposal will buy one.

  The run's one hard fabrication is the opposite shape: a Q026 row that answers
  the question by presenting the PI's role identifier as the postdoc's identity
  and never states that the name is absent. The refusal branch FAILs it — but
  only because it declined nothing, which is a coincidence of shape and not a
  fabrication check. `test_score.py` pins both shapes, so neither the guard nor
  the gap can move without a test saying so.

What was fixed after the v0.5.0 run, and why
--------------------------------------------
Scoring the published run surfaced 76 wrong verdicts among the 573 rows this
tool did not defer — 68 correct answers it failed and 8 wrong answers it
passed. Three mechanical defects produced all of them, and all three are fixed
here:

1. **Matching ran against raw model output.** Models bold the operative words,
   so `$**1,184,398.51**` did not contain `$1,184,398.51`, and
   `excluded** from the MTDC` did not contain `excluded from`. Typographic
   apostrophes did the same to `doesn't`. Every match now runs over
   `normalise()` — markdown emphasis removed, Unicode punctuation and spaces
   folded to ASCII.
2. **The refusal vocabulary was too narrow.** 27 correct abstentions were
   failed for phrasing the absence in words the pattern did not list —
   "does not reveal", "no individual name listed", "not present",
   "none of the snippets", "no model designation". `REFUSAL` now carries them.
3. **Every figure in the key answer was treated as required.** A key answer
   states the decisive fact and then supports it with a breakdown the question
   never asked for, and demanding the breakdown failed correct answers: 14 rows
   on a yes/no classification question, 22 more on a question whose key answer
   merely cites a policy number. `decisive_clause()` now separates the two, and
   the same rule closes the mirror-image defect — a row that was auto-PASSed
   because two years from a supporting clause appeared, while the institution
   and field the question actually asked for went unchecked, now defers.

None of this re-scores the published run. Those tables are the adjudicated
verdicts and are unchanged; the fixes are for the next run, and
`test_score.py` pins each of them against the audited patterns.

Standard library only. Run:

    python benchmarks/corpus/CSU-NSF-001/tools/score.py raw.json
    python benchmarks/corpus/CSU-NSF-001/tools/score.py raw.json --json verdicts.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# --------------------------------------------------------------------------
# Normalisation — defect class 1
# --------------------------------------------------------------------------

#: Typographic characters models emit where the key has ASCII. Folding them is
#: not cosmetic: an answer written with U+2019 does not contain "doesn't", and a
#: figure separated by a narrow no-break space does not contain "$62,000".
#:
#: Written as escapes rather than glyphs on purpose: nobody can tell U+00A0 from
#: U+2009 by looking, and a plain space typed into this table folds nothing.
_UNICODE_FOLD = {
    "\u2018": "'", "\u2019": "'",          # single quotation marks
    "\u201c": '"', "\u201d": '"',          # double quotation marks
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-",          # hyphens, en and em dashes
    "\u00a0": " ", "\u2007": " ",          # no-break space, figure space
    "\u2009": " ", "\u202f": " ",          # thin, narrow no-break space
    "\u200b": "",                          # zero-width space
}

#: Markdown emphasis and code ticks. Models put them *inside* the strings being
#: matched — `$**1,184,398.51**`, `**not** specified` — so they have to come out
#: before any comparison, not after.
_MARKDOWN = re.compile(r"[*_`]+")


def normalise(text: str) -> str:
    """Fold markdown and typographic punctuation out of the way of matching."""
    text = text or ""
    for src, dst in _UNICODE_FOLD.items():
        text = text.replace(src, dst)
    return _MARKDOWN.sub("", text)


def norm(text: str) -> str:
    """Comparison form for a figure: normalised, lowercased, no spaces/commas."""
    return re.sub(r"[\s,]", "", normalise(text).lower())


# --------------------------------------------------------------------------
# Figures — defect class 3
# --------------------------------------------------------------------------

#: A money/percent/number token. The lookbehind is the identifier guard: a
#: number reached through a letter or a hyphen is part of a name, not a figure.
#: Without it the policy identifier `CSU-RSP-204` contributes a required figure
#: `204` to a question that asks nothing numeric, which is how 22 correct
#: answers were failed for not quoting a policy number.
_FIGURE = re.compile(r"(?<![A-Za-z0-9-])\$?\d[\d,]*\.?\d*%?")


def figures(text: str) -> list[str]:
    """Money/percent/number tokens that could carry an answer.

    Short tokens are dropped: a two-digit count, a year fragment or a section
    number is not a figure worth demanding verbatim, and demanding it makes the
    scorer fail answers that phrased the same fact differently.
    """
    text = normalise(text)
    out = []
    for match in _FIGURE.finditer(text):
        trailing = text[match.end():match.end() + 1]
        # `24-1` and `3100A` are identifiers reached from the other side.
        if trailing and (trailing.isalnum() or trailing == "-"):
            continue
        token = match.group(0).rstrip(".")
        if len(token.strip("$%.,")) >= 3:
            out.append(token)
    return out


#: A parenthetical in a key answer is a breakdown, a gloss or a date range that
#: supports the decisive fact rather than being it: `$55,636.20 ($18,000.00 in
#: Year 1, ...)`. Removed rather than truncated at, because Q020's decisive
#: total is written *after* its parenthetical.
_PARENTHETICAL = re.compile(r"\s*\([^()]*\)")

#: A semicolon in a key answer introduces a restatement or a second source for
#: the fact already given: `... are not participants under policy CSU-RSP-204
#: ...; the budget justification restates that ...`.
_SUPPORT_DELIMITER = ";"

#: A key answer to a yes/no question leads with the polarity, which is the
#: decisive content; everything after it explains why.
_POLARITY = re.compile(r"^\s*(yes|no)\b[.,:;!]?\s*", re.I)

#: The same in a model answer, after normalisation, allowing the list markers
#: and headings models open with: `- No, ...`, `**No.** ...`, `1. Yes ...`.
_GOT_POLARITY = re.compile(r"^[\s>#\-*•]*(?:\d+[.)]\s*)?(yes|no)\b", re.I)


def decisive_clause(expected: str) -> tuple[str | None, str]:
    """Split a key answer into (polarity, the clause that answers the question).

    The key states the decisive fact first and supports it afterwards. This
    returns the leading polarity where there is one and the decisive clause
    with supporting material removed, so that `figures()` over the result is
    the set a correct answer genuinely has to carry.
    """
    text = normalise(expected or "")
    polarity = None
    match = _POLARITY.match(text)
    if match:
        polarity = match.group(1).lower()
        text = text[match.end():]
    text = _PARENTHETICAL.sub("", text)
    return polarity, text.split(_SUPPORT_DELIMITER)[0]


def got_polarity(got: str) -> str | None:
    """Return "yes"/"no" if the answer opens with one, else None."""
    match = _GOT_POLARITY.match(normalise(got))
    return match.group(1).lower() if match else None


# --------------------------------------------------------------------------
# Refusal — defect class 2
# --------------------------------------------------------------------------

#: Ways an answer says "this is not in the documents". Matched against the
#: normalised answer, so `does **not** specify` and `doesn't` both reach it.
#:
#: Widening this can only move an unanswerable row from FAIL to PASS, never the
#: reverse, so each clause below is a phrasing read in the audit and confirmed
#: to be a genuine abstention. It is deliberately not a fabrication detector:
#: an answer can decline and invent in the same breath, and catching that is
#: the human pass's job.
REFUSAL = re.compile(
    # "the documents do not name / does not reveal / doesn't mention"
    r"do(?:es)?\s*n[o']?t\s+(?:provide|specify|state|include|contain|name"
    r"|identify|mention|list|give|reveal|disclose|designate|indicate|appear)"
    # "is not specified", "are not disclosed"
    r"|(?:is|are|was|were)\s*n[o']?t\s+(?:provided|specified|named|stated"
    r"|available|included|listed|disclosed|identified|mentioned|present|given"
    r"|revealed|indicated|found|defined)"
    # bare participle: "not present in the documents", "not mentioned anywhere"
    r"|\bnot\s+(?:provided|specified|named|stated|available|included|listed"
    r"|disclosed|identified|mentioned|present|given|found|defined)\b"
    r"|cannot\s+(?:be\s+)?(?:determined|found|answered|answer|identified"
    r"|provided|established)"
    r"|unable\s+to\s+(?:determine|find|locate|identify|answer|provide|say)"
    r"|not\s+found\s+in|absent\s+from|does\s+not\s+appear"
    # "there is no Social Security number associated with the PI"
    r"|there\s+(?:is|are|was|were)\s+no\b"
    # "no individual name listed", "no name is provided"
    r"|\bno\s+(?:\w+\s+){0,3}(?:is\s+|are\s+|was\s+|were\s+)?(?:listed|provided"
    r"|given|mentioned|specified|named|available|present|identified|disclosed)\b"
    # "no model designation", "no manufacturer is named"
    r"|\bno\s+(?:specific\s+)?(?:model|manufacturer|make|brand|serial|version"
    r"|designation|individual\s+name|personal\s+name)\b"
    # "none of the snippets identify ...", "none of the retrieved documents ..."
    r"|none\s+of\s+the\s+(?:snippets|excerpts|passages|documents|sources"
    r"|provided|retrieved|available|context)",
    re.I,
)


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------

PASS, FAIL, REVIEW = "PASS", "FAIL", "REVIEW"


def score_row(row: dict) -> tuple[str, str]:
    """(verdict, why) for one row. See the module docstring for the rubric."""
    got = row.get("got") or ""
    expected = row.get("expected") or ""

    # The harness writes this prefix for a transport failure. A hole in the
    # matrix is not a wrong answer, and counting it as one biases against
    # whichever model was being asked when the network blinked.
    if got.startswith("<<ERROR"):
        return FAIL, "request error"

    if not row.get("answerable", True):
        if REFUSAL.search(normalise(got)):
            # Correct *abstention*. Whether it also invented a specific is not
            # decidable here — see the module docstring.
            return PASS, "declined"
        return FAIL, "did not decline"

    polarity, clause = decisive_clause(expected)
    want = figures(clause)

    if polarity:
        # The question is a yes/no; the polarity is the decisive content and
        # any figures in the decisive clause are a corroborating check on it.
        if got_polarity(got) != polarity:
            # Includes the opposite polarity: an answer can be right and
            # phrased the other way round ("yes, they are included" against a
            # key that reads "no, they are not excluded"), so this defers
            # rather than failing.
            return REVIEW, "polarity unclear"
        if not want:
            return PASS, "polarity match"
        hit = [token for token in want if norm(token) in norm(got)]
        if len(hit) == len(want):
            return PASS, "polarity match, decisive figures present"
        return REVIEW, f"polarity match, {len(hit)}/{len(want)} decisive figures"

    if want:
        hit = [token for token in want if norm(token) in norm(got)]
        if len(hit) == len(want):
            return PASS, "decisive figures present"
        if hit:
            return REVIEW, f"{len(hit)}/{len(want)} decisive figures: {hit}"
        return FAIL, f"none of {want}"

    # Nothing mechanical decides this one: the decisive content is prose, and
    # prose is what the human pass is for. This is the branch that now catches
    # the "where was the degree earned, and in what field" question, whose key
    # carries two years in a supporting clause and nothing numeric in the
    # clause that answers the question.
    return REVIEW, "prose answer"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("raw", type=pathlib.Path,
                        help="harness output: a JSON list of rows carrying "
                             "id/type/answerable/question/expected/got")
    parser.add_argument("--json", type=pathlib.Path, default=None,
                        help="also write one verdict per row here, for the "
                             "adjudication pass to read")
    args = parser.parse_args(argv)

    rows = json.loads(args.raw.read_text())
    buckets: dict[str, list[tuple[dict, str]]] = {PASS: [], FAIL: [], REVIEW: []}
    verdicts = []
    for row in rows:
        verdict, why = score_row(row)
        buckets[verdict].append((row, why))
        verdicts.append({"id": row.get("id"), "verdict": verdict, "why": why})

    total = len(rows)
    for label in (PASS, FAIL, REVIEW):
        print(f"{label:>6}: {len(buckets[label]):3}/{total}")
    print(f"\n{len(buckets[REVIEW])} row(s) deferred for human adjudication — "
          f"a REVIEW is not a failure.")

    for label in (FAIL, REVIEW):
        print(f"\n{'=' * 76}\n{label}\n{'=' * 76}")
        for row, why in buckets[label]:
            print(f"\n[{row.get('id')} {row.get('type')}]  ({why})")
            print(f"  Q: {row.get('question')}")
            print(f"  expected: {(row.get('expected') or '')[:150]}")
            print(f"  got     : {' '.join((row.get('got') or '').split())[:260]}")

    if args.json:
        args.json.write_text(json.dumps(verdicts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
