"""Paraphrase recall: a question that keeps no knowledge-base passage is asked
again in the base's own words.

Precise retrieval (:mod:`app.services.kb_retrieval`) hands over a passage
only when a cross-encoder scores it above a cut. That model was trained on
short web-search queries, and a question asked the way people talk ("Our PI
ends up working way more hours on the project than she promised. Does that
extra time go into the university's F&A rate base?") is far from one: it
scores the right passage below the cut even where the vector and BM25 lanes
both rank it first. On the KB accuracy eval's development questions
(2026-10-24), one answerable question in five kept no passage — four
plain-language questions in five — and since a turn with no passage is
refused, every one of them came back "not found". In 27 of those 62 the
right chunk was the best candidate, in 27 more it was in the pool.

So when a question keeps nothing, the chat model rewrites it as two short
search queries in the vocabulary the regulation or policy itself uses, twice
and independently (two calls at once), and each of the four is searched and
scored on its own (:func:`app.services.kb_grounding.paraphrase_pool`). A
passage found this way must clear a higher cut
(``kb_retrieval.PARAPHRASE_MIN_SCORE``): a search query is what the
cross-encoder reads best, and it scores everything higher. The cut is what
keeps a near miss out — similar text of another rule, which an answer then
rests on as if it were the rule asked about — and four queries are what let
it be high: on the development questions (2026-10-25) one call's two queries
at the lower cut first used handed over a pool without the answer for every
2.4 that held it, and let a passage through for one question in seven the
base cannot answer; two calls' four at 2.0, one for every 5.2 and none. One
call asked for four queries took half as long again as a call for two, and
its four found less.

The model is told not to answer and not to add figures, section numbers or
names the question does not hold, and a section number or figure it adds
anyway is removed: one taken from memory would steer retrieval to the
section the model believes applies, which is the guess a cited answer must
not rest on.

Only chat asks: workflow grounding issues author-written queries in the
base's terms, several per run (see :mod:`app.services.kb_grounding`).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You turn a question about research administration into search queries for a knowledge base of "
    "regulations and institutional policies. Write 2 short search queries, one per line, each under 15 "
    "words, in the vocabulary the regulation or policy text itself would use for the topic: the formal "
    "names of the costs, actions, roles, documents and procedures the question is about. Keep names, "
    "acronyms and numbers exactly as the question writes them, and never spell out an acronym. Do not "
    "answer the question. Do not add figures, dates, thresholds, section numbers, or names of laws, "
    "agencies or institutions that are not in the question. Output only the queries."
)
MAX_PHRASES = 2
# Independent calls for paraphrases, asked at once: their queries differ
# more than those of one call asked for more.
CALLS = 2
MAX_WORDS = 20
TIMEOUT_S = 8.0
CACHE_SIZE = 256

# A section number ("200.313", "§ 31.205-6", "45.19") or a figure ("$5,000",
# "15%", "90 days" is a number) a paraphrase may carry.
_SECTION_RE = re.compile(r"(?:§+\s*)?(?<![\d.])\d{1,4}\.\d{1,4}(?:-\d{1,3})?(?:\([a-z0-9]{1,4}\))*")
_FIGURE_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|K|million|billion))?|\b\d[\d,]*(?:\.\d+)?\s?%|\b\d[\d,.]*\b")
_LIST_MARK_RE = re.compile(r"^\s*(?:[-*•]+|\d{1,2}[.)]|query\s*\d*\s*[:.)-])\s*", re.IGNORECASE)


def _digits(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", (text or "").replace(",", "")))


def parse(question: str, output: str, limit: int = MAX_PHRASES) -> list[str]:
    """The model's search queries, cleaned: list marks and quotes removed,
    and any section number or figure the question does not hold struck out;
    at most ``limit``, each at most :data:`MAX_WORDS` words."""
    asked = _digits(question)
    norm_q = " ".join((question or "").lower().split())
    out: list[str] = []
    for line in (output or "").splitlines():
        text = _LIST_MARK_RE.sub("", line).strip().strip("\"'“”‘’`").strip()

        def strike(m: re.Match) -> str:
            return m.group(0) if _digits(m.group(0)) <= asked else " "

        text = _SECTION_RE.sub(strike, text)
        text = _FIGURE_RE.sub(strike, text)
        text = " ".join(text.split()[:MAX_WORDS]).strip(" ,;:-")
        if len(text) < 3 or text.lower() == norm_q or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


_CACHE: "OrderedDict[tuple[str, str, str], list[str]]" = OrderedDict()
_PENDING: dict[tuple[str, str, str], asyncio.Future] = {}


async def _ask(kind: str, prompt: str, question: str, model_name: Optional[str], limit: int) -> list[str]:
    """``model_name``'s search queries for ``question`` under ``prompt``,
    cleaned by :func:`parse`; [] without a model or when the call fails or
    times out. One call per (kind, model, question): the knowledge bases of
    a turn share it."""
    question = (question or "").strip()
    if not question or not model_name:
        return []
    key = (kind, model_name, question)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return list(_CACHE[key])
    pending = _PENDING.get(key)
    if pending is not None:
        return list(await asyncio.shield(pending))
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _PENDING[key] = future
    phrases: list[str] = []
    try:
        from app.services.kb_validation_service import _get_or_build_agent

        agent = _get_or_build_agent(f"kb_{kind}", model_name, prompt)
        run = await asyncio.wait_for(agent.run(f"Question: {question}"), timeout=TIMEOUT_S)
        phrases = parse(question, str(run.output or ""), limit)
        _CACHE[key] = phrases
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    except Exception as e:  # noqa: BLE001 — retrieval goes on without them
        logger.warning("KB question %s failed: %s", kind, e)
    finally:
        _PENDING.pop(key, None)
        future.set_result(phrases)
    return list(phrases)


async def paraphrases(question: str, model_name: Optional[str]) -> list[str]:
    """Search queries for ``question`` in a knowledge base's own words, from
    :data:`CALLS` calls asked at once; a call that fails leaves the others'."""
    found = await asyncio.gather(*[
        _ask("paraphraser" if n == 0 else f"paraphraser_{n + 1}", SYSTEM_PROMPT, question, model_name, MAX_PHRASES)
        for n in range(CALLS)
    ])
    out: list[str] = []
    for phrase in (p for phrases in found for p in phrases):
        if phrase not in out:
            out.append(phrase)
    return out


# ---------------------------------------------------------------------------
# Compound questions
# ---------------------------------------------------------------------------
#
# A question that asks two things ("What form does a university use for its
# CAS disclosure statement, and where do the copies go?") is searched as one,
# and its passages are those of the part that scores best: the relevance cut
# keeps a passage from another section only when it scores nearly as well.
# On the eval's development questions, 21 of 47 compound questions and 11 of
# 20 that span knowledge bases reached only part of their answer text. Such a
# question is split by the model into standalone search queries, one per
# part, and each part is searched on its own (:func:`part_pools`), at the
# paraphrase cut, beside the question itself.

PARTS_PROMPT = (
    "You split a question about research administration into the separate things it asks, to search a "
    "knowledge base of regulations and institutional policies. If it asks two or more separate things, "
    "write one short search query for each, one per line, each under 15 words, standalone (name the "
    "subject each part is about) and in the vocabulary the regulation or policy text itself would use. "
    "If it asks only one thing, write only: ONE. Keep names, acronyms and numbers exactly as the "
    "question writes them, and never spell out an acronym. Do not answer the question. Do not add "
    "figures, dates, thresholds, section numbers, or names of laws, agencies or institutions that are "
    "not in the question. Output only the queries."
)
MAX_PARTS = 3
_ASKS = (r"(?:who|whom|whose|what|when|where|which|why|how|is|are|was|were|does|do|did|can|could|may|must"
         r"|should|will|would|has|have|if)")
# ", and where do the copies go", "; or is the 90-day window …", or a second
# sentence after a question mark.
_COMPOUND_RE = re.compile(rf"[,;]\s*(?:and|or|but)\s+(?:then\s+)?{_ASKS}\b|\?\s+\S", re.IGNORECASE)


def looks_compound(question: str) -> bool:
    """Whether ``question`` reads as asking more than one thing."""
    return bool(_COMPOUND_RE.search(question or ""))


async def parts(question: str, model_name: Optional[str]) -> list[str]:
    """One standalone search query per thing ``question`` asks; [] when it
    asks one thing (or the model cannot say)."""
    found = await _ask("decomposer", PARTS_PROMPT, question, model_name, MAX_PARTS)
    found = [p for p in found if p.strip(" .").upper() != "ONE"]
    return found if len(found) >= 2 else []


async def part_pools(dm, kb_uuid: str, query: str, queries: list[str], *, k: int,
                     floor: float) -> list[list[dict]]:
    """One pool per part of a compound question: what the part's search query
    finds, held to the part cut (``kb_retrieval.PART_MIN_SCORE``) as
    :func:`kb_grounding.paraphrase_pool` searches it. [] when precise
    retrieval cannot run here."""
    from app.services import kb_grounding, kb_retrieval

    pools = await asyncio.gather(*[
        asyncio.to_thread(kb_grounding.paraphrase_pool, dm, kb_uuid, query, [q], k=k, floor=floor,
                          min_score=kb_retrieval.PART_MIN_SCORE)
        for q in queries
    ])
    return [p for p in pools if p is not None]


async def precise_pool(dm, kb_uuid: str, query: str, *, k: int, floor: float,
                       model_name: Optional[str]) -> Optional[list[dict]]:
    """The precise pool for ``query`` (:func:`kb_grounding._precise_pool`);
    when it keeps nothing, the passages paraphrases of ``query`` find. Either
    way followed by its passages' neighbours in their sections
    (:func:`kb_grounding.with_neighbours`). None when precise retrieval
    cannot run here."""
    from app.services import kb_grounding

    pool = await asyncio.to_thread(kb_grounding._precise_pool, dm, kb_uuid, query, k=k, floor=floor)
    if pool is None:
        return None
    if not pool and model_name:
        phrases = await paraphrases(query, model_name)
        if phrases:
            found = await asyncio.to_thread(
                kb_grounding.paraphrase_pool, dm, kb_uuid, query, phrases, k=k, floor=floor,
            )
            logger.info("KB question kept no passage; %d found through %d paraphrases",
                        len(found or []), len(phrases))
            pool = found if found is not None else pool
    if pool:
        pool = await asyncio.to_thread(kb_grounding.with_neighbours, dm, kb_uuid, query, pool, k=k)
    return pool
