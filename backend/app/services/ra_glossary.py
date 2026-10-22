"""Research-administration vocabulary for knowledge-base retrieval.

A research administrator writes "IDC rate", "NCE request" or "can we buy
beer"; the regulation says "indirect (F&A) costs", "one-time extension of the
period of performance" and "alcoholic beverages". None of the left-hand words
occurs in 2 CFR 200 or the institution's policy pages, so neither a lexical
match nor the small embedder can bridge them, and the cross-encoder scores
the right passage as unrelated (-9 for "NCE request" against § 200.308(g)).

So a query is expanded before it is searched and scored: the terms below are
written from general RA practice, not from any one knowledge base, and the
knowledge base's own "Long Form (ABBR)" definitions and acronym tables are
added to them. An expansion only ever appends words in parentheses; the
query itself is unchanged, so an exact phrase still matches exactly.
"""

from __future__ import annotations

import re

# trigger (regex) -> words appended to the query. A trigger written with two
# or more capitals is an acronym and matches case-sensitively ("PI", not
# "pi"); a lower-case trigger matches any case.
RA_GLOSSARY: dict[str, str] = {
    r"\bIDC\b": "indirect costs",
    r"\bF&A\b": "facilities and administrative indirect costs",
    r"\boverhead\b": "indirect costs",
    r"\bMTDC\b": "modified total direct costs",
    r"\bTDC\b": "total direct costs",
    r"\bNCE\b": "no-cost extension one-time extension of the period of performance",
    r"\bno[- ]cost extension\b": "one-time extension of the period of performance",
    r"\bPoP\b": "period of performance",
    r"\bco-?PIs?\b": "co-principal investigator",
    r"\bPIs?\b": "principal investigator project director",
    r"\bPD\b": "project director",
    r"\bcost[- ]share\b": "cost sharing matching",
    r"\bmatch(ing)?\b": "cost sharing",
    r"\brebudget\w*": "revision of budget and program plans",
    r"\bpre-?award (spending|costs?)\b": "pre-award costs",
    r"\bsole[- ]source\b": "noncompetitive procurement",
    r"\bPSC\b": "participant support costs",
    r"\b(laptop|computer|tablet|iPad)s?\b": "computing devices",
    r"\b(beer|wine|liquor|alcohol)\b": "alcoholic beverages",
    r"\b(drone|UAV)s?\b": "unmanned aircraft systems UAS",
    r"\bsubcontract\w*": "subaward",
    r"\bsub-?recipient\w*": "subaward",
    r"\bNOA\b": "notice of award",
    r"\b(NOFO|FOA|RFA|RFP)\b": "notice of funding opportunity",
    r"\bIRB\b": "institutional review board human subjects",
    r"\bIACUC\b": "institutional animal care and use committee",
    r"\bRCR\b": "responsible conduct of research",
    r"\bFCOI\b": "financial conflict of interest",
    r"\bCOI\b": "conflict of interest",
    r"\bDMP\b": "data management plan",
    r"\bfringe\b": "fringe benefits",
    r"\bG&A\b": "general and administrative",
    r"\bEPAFs?\b": "electronic personnel action form",
    r"\bsingle audit\b": "audit requirements",
    r"\bstipends?\b": "participant support",
    r"\bcarry ?(over|forward)\b": "unobligated balances",
    r"\bdrawdowns?\b": "payment",
    r"\beffort cert\w*": "effort reporting",
    r"\b(foreign national|non-?US)\b": "non-US person",
    r"\bconsultants?\b": "professional service costs",
    r"\bsummer salary\b": "periods outside the academic year",
    r"\bdues\b": "memberships",
}

_COMPILED = [
    (re.compile(pat, 0 if re.search(r"[A-Z]{2}", pat) else re.IGNORECASE), words)
    for pat, words in RA_GLOSSARY.items()
]

# "Modified Total Direct Cost (MTDC)": up to seven capitalised words, then
# the abbreviation in parentheses.
_DEFINED_ABBR_RE = re.compile(r"((?:[A-Z][\w&-]*[ ]){1,6}[A-Z][\w&-]*)\s*\(([A-Z][A-Za-z&]{1,7})\)")
# An acronym table line, as 2 CFR 200.0 prints it: "(c) F&A Facilities and Administration".
_ACRONYM_LINE_RE = re.compile(r"^\([a-z]{1,3}\) ([A-Z][A-Za-z&]{1,7}) ([A-Z][^\n(]{3,80})$", re.MULTILINE)


def corpus_abbreviations(texts) -> dict[str, str]:
    """Abbreviations a knowledge base defines for itself, abbreviation ->
    long form. Only pairs whose initials fit are kept, so a parenthesised
    code after an unrelated phrase is not taken for a definition."""
    pairs: dict[str, str] = {}
    for text in texts:
        for m in _DEFINED_ABBR_RE.finditer(text or ""):
            long, abbr = m.group(1).strip(), m.group(2)
            initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", long)).upper()
            if abbr.replace("&", "").upper() in initials or initials.startswith(abbr[0]):
                pairs.setdefault(abbr, long)
        for m in _ACRONYM_LINE_RE.finditer(text or ""):
            pairs.setdefault(m.group(1), m.group(2).strip())
    return pairs


def expand_query(query: str, abbreviations: dict[str, str] | None = None) -> str:
    """``query`` with the long forms of the RA terms and abbreviations it
    uses appended in parentheses; unchanged when it uses none."""
    lowered = query.lower()
    add: list[str] = []
    for rx, words in _COMPILED:
        if rx.search(query) and words.lower() not in lowered and words not in add:
            add.append(words)
    for abbr, long in (abbreviations or {}).items():
        if re.search(rf"(?<![\w&]){re.escape(abbr)}(?![\w&])", query) and long.lower() not in lowered and long not in add:
            add.append(long)
    return f"{query} ({'; '.join(add)})" if add else query
