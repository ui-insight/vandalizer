"""Check each cited claim in a chat answer against the passage it cites.

A knowledge-base answer cites a passage after each claim, and the UI draws
the citation as a chip a reader trusts. The word-overlap check chat ran
before (``kb_answer_grounding.unsupported_citations``) cannot see a claim
that shares every word with its passage and says something else: "All
requests must be submitted at least 10 calendar days before …" cited to
"All requests for no-cost extensions should be submitted at least 10
calendar days before …", or a list item read as the opposite of the list's
lead-in.

Here every statement of the answer that carries a citation (split as a
workflow output is, by ``output_statements``) is checked against the
passages it cites — and only those:

1. one temperature-0 call per batch of claims, shown each claim, the
   user's question and its cited passages (with the lead-in of a list a
   passage holds items of), says whether the passages state it and copies
   the excerpt that does;
2. that excerpt must be in the cited passage, word for word (pieces joined
   by "…" in order, within one stretch), checked here;
3. every number and date in the claim must be in the excerpt, unless the
   user's question gave it; and the claim must not ask more or less than
   the excerpt — "must" for "should", "required" for "may" — nor turn a
   limit around, merge two limits, or drop the case a rule applies in.
   These are the workflow sourcing gates (``output_sourcing``), plus one
   chat needs: advice ("should") with a figure is still advice, while the
   workflow gate excuses any sentence that states a limit.

A claim that passes is ``verified`` with its excerpt; one that fails is
``unverified`` with the reason, and the UI marks its chip so. Nothing here
changes the answer. The check runs after the answer has streamed; it never
blocks it, and a call that fails or runs out of time leaves every claim
``unchecked`` rather than unverified.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from app.services import output_sourcing as osrc
from app.services.kb_grounding import match_source_index
from app.services.output_statements import Statement, markdown_statements

logger = logging.getLogger(__name__)

VERSION = 1
MAX_CLAIMS = 40            # cited claims checked per answer; the rest stay unchecked
BATCH_CLAIMS = 10          # claims per model call
VOTES = 3                  # readings of each batch, made at once; a majority decides
BATCH_CHARS = 14000        # passage text per model call
TIMEOUT_SECONDS = 25.0     # for the whole check
PASSAGE_CHARS = 5000       # of a passage shown to the checker

# The workflow judge's rules, said for a chat answer: a claim there applies
# a rule to the user's question ("beer at a lab party" under "alcoholic
# beverages"), which a report statement never does.
CHECK_INSTRUCTIONS = (
    "You check the claims in an AI assistant's chat answer against the knowledge-base passages each claim "
    "cites. You are given the user's question, then the passages, then each claim with the ids of the passages "
    "it cites and the headings or list items it sits under.\n\n"
    "For each claim decide whether its passages state it. A claim may restate a passage in other words, leave "
    "details out, name the source, and apply the passage's rule to the user's question when the question plainly "
    "falls under the rule's own words (beer is an alcoholic beverage).\n\n"
    "Answer supported: false when the claim\n"
    "- asks more or less than the passage: \"must\" or \"required\" where the passage says \"should\", \"may\" or "
    "\"is encouraged\", or the reverse;\n"
    "- turns a rule around: no approval needed where the passage requires approval, allowed where it is "
    "unallowable, a maximum read as a minimum;\n"
    "- has a number, date, amount, party or condition the passage does not give, or drops a condition the rule "
    "applies only under;\n"
    "- adds a fact, reason, exception or consequence the passage does not state, or draws a conclusion it does "
    "not state in so many words;\n"
    "- only shares words with the passage.\n\n"
    "Read a passage with its lead-in when one is shown: the list items under a lead-in are what the lead-in says "
    "they are (\"must request prior approval for the following: … (5) The transfer of funds …\" means the "
    "transfer needs prior approval). Read a claim the same way, with the headings and list items it sits under "
    "(\"under\"): under \"Prior approval is required when:\", the claim \"The extension changes the approved scope\" "
    "says that is a case requiring prior approval. A list item shown without its lead-in only says the item is on "
    "a list the passage does not show: it does not say the item is allowed, required or forbidden.\n\n"
    "When supported is true, give the passage id and copy the excerpt that states the claim: one run of that "
    "passage's text, copied character for character, at most 300 characters. When the claim rests on a lead-in "
    "and an item under it, copy both in the order they appear, joined by \" … \". When the claim puts together "
    "facts from several of its passages, give \"quotes\" instead: one excerpt per passage it rests on. Never "
    "correct spelling or spacing.\n\n"
    "Reply with JSON only: "
    '{"items": [{"id": 1, "supported": true, "passage": "P2", "quote": "..."}, '
    '{"id": 2, "supported": true, "quotes": [{"passage": "P1", "quote": "..."}, {"passage": "P3", "quote": "..."}]}, '
    '{"id": 3, "supported": false, "why": "a few words"}]}'
)

_BRACKET_RE = re.compile(r"\[([^\[\]\n]{3,400})\](?!\()")
_TRAILING_RE = re.compile(r"[\s.,;:!?*_)]*")
# Advice: "should", "encouraged", "recommended" — whatever figures it has.
_ADVISED_ONLY_RE = re.compile(r"\bshould\b|\bencourag(?:e|es|ed|ing)\b|\brecommend(?:s|ed)?\b", re.I)
_STRONG_RE = re.compile(r"\b(?:must|shall|required|requires?|mandatory)\b", re.I)


@dataclass
class Claim:
    statement: Statement
    citations: list[str]                   # the brackets' text, as written
    sources: list[int]                     # indexes into the answer's citations
    result: dict = field(default_factory=dict)


def _citation_targets(inner: str, sources: list[dict]) -> Optional[list[int]]:
    """The passages one bracket names, or None when any part names none."""
    parts = [p for p in re.split(r"\s*;\s*", inner) if p.strip()]
    if not parts:
        return None
    found: list[int] = []
    for p in parts:
        i = match_source_index(p, sources)
        if i is None:
            return None
        found.append(i)
    return found


def cited_claims(answer: str, sources: list[dict]) -> list[Claim]:
    """The statements of ``answer`` that cite a retrieved passage — inside
    the statement or right after it — with the passages they cite."""
    out: list[Claim] = []
    for st in markdown_statements(answer or ""):
        if st.kind != "claim" or st.start is None or st.end is None:
            continue
        brackets = [m for m in _BRACKET_RE.finditer(answer, st.start, st.end)]
        # The citations right after the statement: the splitter ends a
        # statement before them, and before the sentence's full stop.
        at = st.end
        while True:
            at = _TRAILING_RE.match(answer, at).end()
            m = _BRACKET_RE.match(answer, at)
            if not m:
                break
            brackets.append(m)
            at = m.end()
        cites: list[str] = []
        targets: list[int] = []
        for m in brackets:
            hit = _citation_targets(m.group(1), sources)
            if hit is None:
                continue
            cites.append(m.group(1))
            targets.extend(i for i in hit if i not in targets)
        if targets:
            out.append(Claim(st, cites, targets))
    return out


def _passage_text(source: dict) -> str:
    content = str(source.get("content") or source.get("content_preview") or "")[:PASSAGE_CHARS]
    lead = source.get("lead_in")
    return f"{lead}\n{content}" if lead else content


def _prompt(question: str, claims: list[tuple[int, Claim]], sources: list[dict]) -> tuple[str, dict[str, int]]:
    ids: dict[int, str] = {}
    parts = [f"USER QUESTION\n{question.strip()}", "PASSAGES"]
    for _, c in claims:
        for i in c.sources:
            if i not in ids:
                ids[i] = f"P{len(ids) + 1}"
                s = sources[i]
                lead = s.get("lead_in")
                body = str(s.get("content") or s.get("content_preview") or "")[:PASSAGE_CHARS]
                text = f"Lead-in (earlier in the same section): {lead}\n---\n{body}" if lead else body
                parts.append(f'<passage id="{ids[i]}" source="{s.get("label") or s.get("document_title") or ""}">\n'
                             f"{text.strip()}\n</passage>")
    parts.append("CLAIMS")
    for n, c in claims:
        item: dict = {"id": n, "claim": c.statement.text}
        if c.statement.label:
            item["label"] = c.statement.label
        if c.statement.context:
            item["under"] = " — ".join(c.statement.context)
        item["passages"] = [ids[i] for i in c.sources]
        parts.append(json.dumps(item, ensure_ascii=False))
    return "\n\n".join(parts), {v: k for k, v in ids.items()}


def _batches(claims: list[Claim], sources: list[dict]) -> list[list[Claim]]:
    out: list[list[Claim]] = []
    cur: list[Claim] = []
    seen: set[int] = set()
    chars = 0
    for c in claims:
        add = sum(len(_passage_text(sources[i])) for i in c.sources if i not in seen)
        if cur and (len(cur) >= BATCH_CLAIMS or chars + add > BATCH_CHARS):
            out.append(cur)
            cur, seen, chars = [], set(), 0
            add = sum(len(_passage_text(sources[i])) for i in c.sources)
        cur.append(c)
        seen.update(c.sources)
        chars += add
    if cur:
        out.append(cur)
    return out


def _advice_for_duty(claim: str, text: str) -> bool:
    """A claim that something must be done, from text that only advises it —
    figures or not: "should be submitted at least 10 calendar days before"
    is not "must be submitted …"."""
    return bool(_STRONG_RE.search(claim) and _ADVISED_ONLY_RE.search(text) and not _STRONG_RE.search(text))


# What a claim or a passage says of an action: forbidden, required, allowed
# (or not required), advised. Read in that order, each match removed, so
# "may not" is forbidden and "does not require" allowed.
_FORBID_RE = re.compile(
    r"\b(?:must|shall|may|can|will|should)\s+not\b|\bcannot\b|\bcan[’']t\b|\bunallowable\b|\bprohibit(?:s|ed|ing)?\b"
    r"|\bnot\s+(?:be\s+)?(?:permitted|allowed|allowable|authorized)\b",
    re.I,
)
_PERMIT_RE = re.compile(
    r"\b(?:does|do|did|is|are|be)\s+not\s+(?:be\s+)?(?:required|require|needed|need)\b|\bneed\s+not\b"
    r"|\bno\s+(?:prior\s+)?(?:approval|requirement)s?\b|\bwithout\s+(?:(?:prior|written|advance)\s+)*approval\b"
    r"|\b(?:allowable|permitted|allowed|authorized|optional)\b|\bpermits?\b|\ballows?\b"
    r"|(?<!\bin )(?<!\bof )(?<!\bby )(?<!\bon )(?<!\bto )\bmay\b(?!\s*\d)|\bcan\b",
    re.I,
)
_DUTY_RE = re.compile(r"\b(?:must|shall|required|requires?|requiring|mandatory)\b", re.I)
_ADVISE_RE = re.compile(r"\bshould\b|\bencourag(?:e|es|ed|ing)\b|\brecommend(?:s|ed)?\b", re.I)
_REG_REF_RE = re.compile(
    r"\b\d{1,2}\s*(?:C\.?F\.?R|U\.?S\.?C)\.?\s*(?:(?:part|§|section)\s*)?\d+(?:\.\d+)?(?:-\d+)?(?:\([0-9A-Za-z]{1,4}\))*"
    r"|§§?\s*\d+(?:\.\d+)?(?:-\d+)?(?:\([0-9A-Za-z]{1,4}\))*(?:\s*(?:and|through|to|-)\s*\d+(?:\.\d+)?)?"
    r"|\b(?:sub)?part\s+(?:\d{1,4}|[A-F])\b|\bparagraphs?\s+(?:\([0-9A-Za-z]{1,4}\))+",
    re.I,
)
_ITEM_START_RE = re.compile(r"^\s*(?:\([0-9A-Za-z]{1,5}\)|[0-9A-Za-z]{1,4}[.)])\s")


# "Cannot move them without prior approval" requires the approval.
_NOT_WITHOUT_RE = re.compile(
    r"\b(?:cannot|can[’']t|(?:may|must|shall)\s+not|not\s+(?:be\s+)?(?:allowed|permitted))\b[^.;\n]{0,80}?"
    r"\bwithout\s+(?:\w+\s+){0,2}approval\b",
    re.I,
)


# "This paragraph does not preclude the Federal agency from approving further
# no-cost extensions" leaves the agency free to.
_NOT_BARRED_RE = re.compile(
    r"\b(?:does|do|did|is|are|was|were|will|shall)\s+not\s+(?:be\s+)?(?:preclude[sd]?|prevent(?:s|ed)?|bar(?:s|red)?|prohibit(?:s|ed)?)\b",
    re.I,
)


_UNLESS_RE = re.compile(r"\bunless\b|\bexcept\s+(?:when|where|if)\b", re.I)
_ONLY_IF_RE = re.compile(r"\bonly\s+(?:if|when|where|with|to\s+the\s+extent)\b|\bunless\b", re.I)


def modality(text: str) -> set[str]:
    """What ``text`` says of an action: some of forbidden, permitted,
    required, advised."""
    out: set[str] = set()
    t = _NOT_WITHOUT_RE.sub(" requires approval ", text or "")
    t = _NOT_BARRED_RE.sub(" permits ", t)
    for name, rx in (("forbidden", _FORBID_RE), ("permitted", _PERMIT_RE), ("required", _DUTY_RE),
                     ("advised", _ADVISE_RE)):
        if rx.search(t):
            out.add(name)
            t = rx.sub(" ", t)
    # "Unallowable unless they have a programmatic purpose" is "allowable
    # only if they do", and the reverse.
    if "forbidden" in out and _UNLESS_RE.search(text or ""):
        out.add("permitted")
    if "permitted" in out and _ONLY_IF_RE.search(text or ""):
        out.add("forbidden")
    return out


def _find_pieces(src, quote: str) -> Optional[list[tuple[int, int]]]:
    """Where an excerpt cut with "…" sits: each piece of two words or more
    word for word, in order, anywhere in the passage (a chat passage is one
    chunk or section). A one-word piece ("(A) …") is the checker skipping
    words, not a claim's support, and is dropped."""
    parts = [p for p in osrc._INNER_ELLIPSIS_RE.split(quote) if len(osrc.fold(p)[0].split()) >= 2]
    if len(parts) < 2 or max(len(osrc.fold(p)[0].split()) for p in parts) < 3:
        return None
    at, spans = 0, []
    for p in parts:
        hits = osrc._find_all(src, p.strip(" ,;:"), at, len(src.text))
        if not hits:
            return None
        spans.append(hits[0])
        at = hits[0][1]
    return spans


@dataclass
class _Located:
    text: str                      # the passage as the checker read it
    cited: str                     # the excerpt (pieces joined by " … ")
    sentences: list[str]           # the sentence each piece is in
    pieced: bool
    lead: Optional[str]
    pieces: list[str] = field(default_factory=list)


def _locate(source: dict, quote: str) -> Optional[_Located]:
    quote = osrc.clean_quote(quote)
    if len(osrc.fold(quote)[0].split()) < 2:
        return None
    text = _passage_text(source)
    src = osrc._Source("kb", text, source)
    spans = osrc._find_all(src, quote, 0, len(text))[:1]
    pieced = False
    if not spans:
        spans = _find_pieces(src, quote) or []
        pieced = bool(spans)
    if not spans:
        return None
    # The sentence each piece is in; one that ends at its full stop is read
    # to there, not on into the next sentence.
    sentences = [osrc.sentence_around(text, a, b - 1 if text[b - 1:b] in ".;:" and b > a + 1 else b)
                 for a, b in spans]
    cited = " … ".join(text[a:b] for a, b in spans)
    return _Located(text, cited, sentences, pieced, source.get("lead_in"), [text[a:b] for a, b in spans])


def verify(claim: Claim, parts: list[tuple[dict, str]], question: str) -> tuple[bool, str, Optional[str]]:
    """``(verified, reason, excerpt)`` for the checker's excerpts, one per
    passage the claim rests on (``parts``: source, quote): each found in its
    passage, and the claim through the deterministic gates against them."""
    found: list[_Located] = []
    for source, quote in parts:
        loc = _locate(source, quote)
        if loc is None:
            return False, "quote_not_in_passage", None
        found.append(loc)
    cited = " … ".join(f.cited for f in found)
    st = claim.statement
    # A figure the user gave ("$1,240") is the question's, not the passage's;
    # a regulation the claim names ("Under the Uniform Guidance (2 CFR 200)",
    # "§ 200.308(f)(5)") says where it comes from, which the citation and
    # the checker judge. Only figures written in digits: "a single award",
    # "a one-time extension" name no number the passage must give.
    asked = {v.key for v in osrc.values_in(question or "")}
    values = [v for v in osrc.values_in(_REG_REF_RE.sub(" ", st.text))
              if v.key not in asked and re.search(r"\d", v.raw)]
    if not osrc._values_supported(values, cited, osrc.values_in(cited)):
        return False, "value_not_in_quote", cited
    sentences = [s for f in found for s in f.sentences]
    read = [cited, *[f.cited for f in found], *sentences]
    # How strongly is read where the claim is: an excerpt in pieces holds
    # other sentences ("However, the recipient must notify …" beside "does
    # not preclude the Federal agency from approving further no-cost
    # extensions"), so only the one sharing most of the claim's words counts.
    own = osrc.stems(st.text)
    strength = [t for f in found for t in (
        [f.cited, *f.sentences] if not f.pieced else [max(f.sentences, key=lambda s: len(osrc.stems(s) & own))]
    )]
    if any(osrc.obligation_differs(st.text, t) or _advice_for_duty(st.text, t) for t in strength):
        return False, "obligation_differs", cited
    # A limit is compared where it is the claim's own: "up to 12 months" is
    # not turned around by "at least 10 calendar days" in another sentence
    # of the excerpt.
    keys = {v.key for v in values}
    if any(osrc.limit_direction_differs(st.text, t) for t in read
           if keys & {v.key for v in osrc.values_in(t)}):
        return False, "limit_differs", cited
    # What the claim says of the action — required, allowed, forbidden,
    # advised — must be said where it rests. "Permits transferring
    # participant-support funds" was accepted from the bare list item "(5)
    # The transfer of funds budgeted for participant support costs to other
    # budget categories.", which says nothing of permission: its list's
    # lead-in says the transfer needs prior approval. A list item is read
    # with the lead-in the passage carries.
    governing = read + [f.lead for f in found if f.lead and any(_ITEM_START_RE.match(s) for s in f.sentences)]
    if not modality(st.text) <= set().union(*(modality(t) for t in governing)):
        return False, "modality_differs", cited
    # Two limits of one amount merged, compared across the passage's lines
    # and items: "(iv) … increase to the micro-purchase threshold up to
    # $50,000. The recipient … may self-certify a threshold up to $50,000 …"
    # is one limit, its heading and its rule.
    by_line = re.sub(r"(?<=[.!?])[ \t]+(?=[A-Z*_(\[\"'])", "; ", "\n".join(p for f in found for p in f.pieces))
    if osrc.values_merged(st.text, by_line):
        return False, "values_merged", cited
    if any(osrc.condition_dropped(st, f.cited, osrc.common_words(f.text)) for f in found):
        return False, "condition_dropped", cited
    if any(osrc.negation_differs(st, s) for s in sentences):
        return False, "subject_differs", cited
    return True, "ok", cited


Ask = Callable[[str, str], Awaitable[str]]


async def _reading(batch: list[Claim], sources: list[dict], question: str, ask: Ask,
                   vote: int) -> Optional[list[Optional[dict]]]:
    """One reading of a batch: per claim ``{ok, reason, source?, quote?,
    why?}`` (None where a gate could not run), or None when the call failed.
    Later readings see the claims in reverse, so no two read one claim
    beside the same neighbours in the same place."""
    order = batch if vote % 2 == 0 else batch[::-1]
    items = list(enumerate(order, 1))
    prompt, by_id = _prompt(question, items, sources)
    try:
        answers = osrc._parse(await ask(CHECK_INSTRUCTIONS, prompt))
    except Exception as e:  # noqa: BLE001 — unchecked, never unverified
        logger.warning("Chat claim check call failed: %s", e)
        return None
    out: dict[int, Optional[dict]] = {}
    for n, c in items:
        a = answers.get(n) or {}
        # One excerpt, or one per passage for a claim that rests on several.
        given = a.get("quotes") if isinstance(a.get("quotes"), list) and a.get("quotes") else [a]
        parts = [(by_id.get(str((g or {}).get("passage") or "").strip()), (g or {}).get("quote"))
                 for g in given if isinstance(g, dict)]
        if a.get("supported") is not True or not parts or any(i is None or i not in c.sources for i, _ in parts):
            why = a.get("why") if isinstance(a.get("why"), str) else None
            out[id(c)] = {"ok": False, "reason": "not_stated", **({"why": why[:200]} if why else {})}
            continue
        try:
            ok, reason, excerpt = verify(
                c, [(sources[i], q if isinstance(q, str) else "") for i, q in parts], question,
            )
        except Exception as e:  # noqa: BLE001 — a gate that cannot run settles nothing
            logger.warning("Chat claim verification failed: %s", e)
            out[id(c)] = None
            continue
        out[id(c)] = {"ok": ok, "reason": reason, "source": parts[0][0],
                      **({"quote": excerpt[:600]} if excerpt else {})}
    return [out.get(id(c)) for c in batch]


async def _check_batch(batch: list[Claim], sources: list[dict], question: str, ask: Ask) -> None:
    """``VOTES`` readings of a batch at once; a claim is verified when most
    readings that settled it found its excerpt and it passed every gate. A
    single reading flipped about one claim in eight between runs."""
    readings = [r for r in await asyncio.gather(*[
        _reading(batch, sources, question, ask, v) for v in range(VOTES)
    ]) if r is not None]
    for k, c in enumerate(batch):
        settled = [r[k] for r in readings if r[k] is not None]
        if not settled:
            c.result = {"status": "unchecked", "reason": "check_failed"}
            continue
        passed = [s for s in settled if s["ok"]]
        if 2 * len(passed) > len(settled):
            best = passed[0]
            c.result = {"status": "verified", "reason": "ok", "source": best["source"],
                        **({"quote": best["quote"]} if best.get("quote") else {})}
            continue
        failed = [s for s in settled if not s["ok"]]
        # The gate most readings failed on, and what the checker said.
        reason = max({s["reason"] for s in failed}, key=lambda r: sum(s["reason"] == r for s in failed))
        first = next(s for s in failed if s["reason"] == reason)
        c.result = {"status": "unverified", **{k2: v for k2, v in first.items() if k2 != "ok"},
                    "votes": f"{len(passed)}/{len(settled)}"}


def _record(c: Claim) -> dict:
    st = c.statement
    return {
        "claim": st.text,
        # Where the claim sits in the stored answer, and the citations it
        # carries as written: the UI finds the chip by them.
        "start": st.start, "end": st.end,
        "citations": c.citations,
        "cites": c.sources,
        **c.result,
    }


async def check_claims(answer: str, sources: list[dict], question: str, ask: Ask,
                       *, timeout: float = TIMEOUT_SECONDS) -> Optional[dict]:
    """The check of every cited claim in ``answer``, or None when it cites
    no retrieved passage. ``sources`` is the turn's citation list (each
    with ``label`` and ``content``); ``cites`` in a result indexes it."""
    claims = cited_claims(answer, sources)
    if not claims:
        return None
    checked, skipped = claims[:MAX_CLAIMS], claims[MAX_CLAIMS:]
    for c in skipped:
        c.result = {"status": "unchecked", "reason": "too_many_claims"}
    try:
        await asyncio.wait_for(
            asyncio.gather(*[_check_batch(b, sources, question, ask) for b in _batches(checked, sources)]),
            timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Chat claim check ran out of time after %.0f s", timeout)
    for c in checked:
        if not c.result:
            c.result = {"status": "unchecked", "reason": "timed_out"}
    rows = [_record(c) for c in claims]
    return {
        "version": VERSION,
        "claims": rows,
        "summary": {s: sum(r["status"] == s for r in rows) for s in ("verified", "unverified", "unchecked")},
    }


def model_ask(model: str, system_config_doc: Optional[dict]) -> Ask:
    """One temperature-0 call to ``model`` with dedicated instructions, as the
    workflow sourcing judge makes it, awaited on the chat's event loop."""
    async def ask(instructions: str, prompt: str) -> str:
        from pydantic_ai import Agent

        from app.services.llm_service import build_thinking_model_settings, get_agent_model

        agent_model = get_agent_model(model, system_config_doc=system_config_doc)
        settings = dict(build_thinking_model_settings(model, None, system_config_doc) or {})
        settings["temperature"] = 0.0
        result = await Agent(agent_model, instructions=instructions, model_settings=settings).run(prompt)
        return result.output or ""

    return ask
