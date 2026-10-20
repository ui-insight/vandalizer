"""Check every knowledge-base citation in a task's output against its passage.

A grounded task cites passages by tag, and the engine turns each tag into
the passage's source line — so a chip always opens the passage the model
named. Whether that passage actually supports the statement is a separate
question, and models get it wrong: told to cite, they attach a citation on
"§ 200.421 Advertising" to a period-of-performance finding that comes from
the award document. A citation that does not hold up is worse than none —
it is a false assurance in a compliance determination.

So each cited statement is checked, in one model call per task output, for
two things:

1. the passage itself states the rule, requirement, definition or fact the
   statement relies on, and
2. the excerpt that says so, copied from the passage, is really in it —
   checked here character for character (after normalizing whitespace,
   dashes and quotes), not taken on the model's word.

A citation that fails either test is removed from the output. One that
passes keeps its chip, and its excerpt rides on the source (``quotes``) so
the run UI can highlight the exact place in the passage the claim rests on.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable

from app.services.kb_grounding import _CITATION_RE, looks_like_citation, match_source_index

logger = logging.getLogger(__name__)

MAX_ITEMS = 40          # citations checked per output; the rest are removed
MAX_QUOTE_CHARS = 400
MIN_QUOTE_CHARS = 12

CHECK_INSTRUCTIONS = (
    "You check the citations in an AI-written finding against the "
    "knowledge-base passages they cite. For each item decide whether the "
    "cited PASSAGE itself states the rule, requirement, definition or fact "
    "that the STATEMENT applies or relies on. The statement may combine that "
    "rule with facts from the document under review (dates, amounts, award "
    "terms, what a record contains) — that is fine as long as the passage "
    "supplies the rule. Answer false when the passage is only on a related "
    "topic, says something different, or when nothing in the statement "
    "depends on it. When true, copy the shortest excerpt (one or two "
    "sentences, at most 300 characters) of the passage that supports the "
    "statement, character for character — do not paraphrase, shorten words, "
    "fix typos or leave words out with an ellipsis. Some items list "
    "earlier_verified_statements: that citation was already checked for "
    "those statements in an earlier step. Then also answer true when the "
    "statement is a restatement or summary of one of them (the same finding "
    "about the same cost), and quote the excerpt that supports it. Reply "
    "with JSON only, no prose: "
    '{"items": [{"id": 1, "supported": true, "quote": "..."}, '
    '{"id": 2, "supported": false, "quote": ""}]}'
)


@dataclass
class CitationCheck:
    text: str
    sources: list[dict]
    kept: int = 0
    removed: list[str] = field(default_factory=list)   # the statements that lost a citation
    failed: bool = False                               # the check itself could not run


@dataclass
class _Cite:
    start: int
    end: int
    index: int
    claim: str


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[‐‑‒–—―]", "-", t)
    t = re.sub(r"[“”„\"]", '"', t)
    t = re.sub(r"[‘’']", "'", t)
    t = t.replace("…", "...")
    return re.sub(r"\s+", " ", t).strip()


def quote_fragments(quote: str, passage: str) -> list[str] | None:
    """The pieces of ``quote`` (split at an ellipsis — a model abbreviates a
    long excerpt with "…") when every piece is in ``passage`` verbatim and in
    order, else None. Pieces are compared after normalizing case, whitespace,
    dashes and quotes; one at least must be a real excerpt, not a word."""
    pieces = [p.strip(" \t\n;,:") for p in re.split(r"\.\.\.|…", quote or "")]
    pieces = [p for p in pieces if len(_norm(p)) >= 4]
    if not pieces or max(len(_norm(p)) for p in pieces) < MIN_QUOTE_CHARS:
        return None
    hay = _norm(passage)
    pos = 0
    for p in pieces:
        at = hay.find(_norm(p), pos)
        if at < 0:
            return None
        pos = at + len(_norm(p))
    return pieces


# After a citation: more citations, a closing mark, then the quote that ends
# a JSON string value — the citation is the last thing in the value.
_CLOSES_VALUE_RE = re.compile(r'(?:\s*\[[^\[\]\n]{3,300}\])*\s*[.;:!?]?\s*"')


def _opening_quote(s: str) -> int:
    """Index of the unescaped double quote that opens the string ``s`` ends
    inside, or -1."""
    i = s.rfind('"')
    while i >= 0:
        slashes = len(s[:i]) - len(s[:i].rstrip("\\"))
        if slashes % 2 == 0:
            return i
        i = s.rfind('"', 0, i)
    return -1


def _claim_before(text: str, start: int, floor: int, *, closes_value: bool = False) -> str:
    """The statement a citation at ``start`` supports: the sentence (or list
    item) it closes — or, when it closes a JSON string value, the whole
    value. The citation rule tells a model emitting JSON to end each value
    that draws on a passage with the tag, so the tag answers for the value:
    judged on its last sentence alone ("Without such evidence, allocability
    cannot be confirmed"), a rationale loses the very rule it states."""
    s = text[floor:start].rstrip()
    s = s[:-1] if s.endswith((".", ":", ";", ",")) else s
    if closes_value:
        opened = _opening_quote(s)
        claim = s[opened + 1:].strip(" \t-*•–—:;") if opened >= 0 else ""
        if len(claim) >= 15:
            return claim[-1200:]
    cut = max(s.rfind("\n"), s.rfind('"'), s.rfind(". "), s.rfind("? "), s.rfind("! "))
    claim = s[cut + 1:].strip(" \t-*•–—:;")
    if len(claim) < 15:
        claim = s[-300:].strip(" \t-*•–—:;")
    return claim[-500:]


def find_citations(text: str, sources: list[dict]) -> list[_Cite]:
    """Each bracketed citation in ``text`` that resolves to a passage, with
    the statement it closes. Adjacent citations share a statement."""
    found: list[_Cite] = []
    prev_end = 0
    prev_claim = ""
    for m in _CITATION_RE.finditer(text or ""):
        label = m.group(1)
        if not looks_like_citation(label):
            continue
        idx = match_source_index(label, sources)
        if idx is None:
            continue
        between = text[prev_end:m.start()]
        closes_value = bool(_CLOSES_VALUE_RE.match(text, m.end()))
        claim = (
            prev_claim if found and not between.strip()
            else _claim_before(text, m.start(), prev_end, closes_value=closes_value)
        )
        found.append(_Cite(m.start(), m.end(), idx, claim))
        prev_end, prev_claim = m.end(), claim
    return found


def _prompt(cites: list[_Cite], sources: list[dict]) -> str:
    passages: dict[int, int] = {}
    for c in cites:
        passages.setdefault(c.index, len(passages) + 1)
    parts = ["PASSAGES"]
    for idx, pid in passages.items():
        parts.append(f"<passage id=\"P{pid}\">\n{sources[idx].get('content') or ''}\n</passage>")
    parts.append("ITEMS")
    for n, c in enumerate(cites, 1):
        item = {"id": n, "passage": f"P{passages[c.index]}", "statement": c.claim}
        # A citation kept from an earlier step was already checked there; the
        # question here is whether this line restates that finding.
        earlier = [q.get("claim") for q in (sources[c.index].get("quotes") or []) if q.get("claim")]
        if earlier:
            item["earlier_verified_statements"] = earlier[:3]
        parts.append(json.dumps(item, ensure_ascii=False))
    return "\n\n".join(parts)


def _parse(reply: str) -> dict[int, dict]:
    from app.services.workflow_validator import _extract_json

    data = _extract_json(reply)
    items = data.get("items") if isinstance(data, dict) else data
    out: dict[int, dict] = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and isinstance(it.get("id"), int):
            out[it["id"]] = it
    return out


def check_citations(
    text: str, sources: list[dict], *, ask: Callable[[str, str], str],
) -> CitationCheck:
    """Keep only the citations in ``text`` whose passage supports them.

    ``ask(instructions, prompt)`` runs the model and returns its reply. A
    citation that names no retrieved passage is left alone here (the step
    already flags it as unmatched). If the check cannot run, every citation
    is removed: an unchecked citation must not look like a verified one.
    """
    if not isinstance(text, str) or not text or not sources:
        return CitationCheck(text=text, sources=list(sources or []))
    cites = find_citations(text, sources)
    if not cites:
        return CitationCheck(text=text, sources=list(sources))

    checked = cites[:MAX_ITEMS]
    verdicts: dict[int, dict] = {}
    failed = False
    try:
        verdicts = _parse(ask(CHECK_INSTRUCTIONS, _prompt(checked, sources)))
    except Exception as e:  # noqa: BLE001 — a failed check removes, never keeps
        logger.warning("Citation check failed; removing the unchecked citations: %s", e)
        failed = True

    out_sources = [dict(s) for s in sources]
    keep: set[int] = set()
    for n, c in enumerate(checked, 1):
        v = verdicts.get(n) or {}
        quote = v.get("quote") if isinstance(v.get("quote"), str) else ""
        quote = quote.strip()[:MAX_QUOTE_CHARS]
        pieces = quote_fragments(quote, sources[c.index].get("content") or "")
        if v.get("supported") is True and pieces:
            keep.add(n)
            entry = {"claim": c.claim, "quote": " … ".join(pieces)}
            quotes = out_sources[c.index].setdefault("quotes", [])
            if entry not in quotes:
                quotes.append(entry)

    removed_claims: list[str] = []
    new_text = text
    for n in range(len(cites), 0, -1):   # back to front, so offsets stay valid
        if n in keep:
            continue
        c = cites[n - 1]
        start = c.start - 1 if c.start > 0 and new_text[c.start - 1] == " " else c.start
        new_text = new_text[:start] + new_text[c.end:]
        if c.claim not in removed_claims:
            removed_claims.insert(0, c.claim)
    return CitationCheck(
        text=new_text, sources=out_sources, kept=len(keep),
        removed=removed_claims, failed=failed,
    )
