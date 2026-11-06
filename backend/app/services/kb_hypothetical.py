"""Hypothetical-passage search: a chat question that keeps no knowledge-base
passage, even reworded and even after its best candidates were read, is
searched once more with the text the model expects the base to hold.

A question asked as a case ("a vendor bidding on our grant-funded contract
offered to take our buyer to dinner — is that okay?") shares almost no words
with the rule that answers it (gratuities, conflicts of interest, standards
of conduct for procurement). The paraphrase rescue (:mod:`kb_paraphrase`)
rewrites it as short search queries in the base's vocabulary and the empty-
pool check (:mod:`kb_empty_check`) has a model read the question's three
best candidates; on the final sweep of the shipped build (2026-11-05,
``runs/2026-11-05_sweep_18e58332``) 62 of 1,317 answerable turns still kept
nothing and were answered "not found", 38 of them plain-language questions,
the answer text in the base every time. The model's own draft of the answer
is a far better query for that text: on the retrieval misses of the live
configuration (2026-11-04, ``runs/2026-11-05_ab_second-retrieval_18e58332/study``)
searching with it reached the gold section for 34% of the misses against
16% for the question. Searching every turn that way cost 15 s and moved
answers both ways, so it did not ship.

So, only when the pool, the rescue and the check have all kept nothing: the
chat model writes, at temperature 0 and with thinking off, two texts the
regulation or policy would contain that decide the question — a two-to-four
sentence passage in that text's register, and the one or two lines its list,
definition or exception would state (a rule that decides a case is often a
list item: "(3) Costs of promotional items and memorabilia;", "(7) Costs of
memberships in civic and community organizations.") — with no figure, date,
section number or name the question does not hold (one written anyway is
struck out, as the rescue strikes them). The base's :data:`CANDIDATES` best
candidates for each text by cross-encoder score, taken together, are read by
the empty-pool check's model against the question exactly as that check
reads them, and a candidate is kept only when the model says it answers and
quotes the sentence that does (on six such questions, 2026-11-05, the check
kept the gold chunk for five when shown it; the sixth answers only by
exception). A kept passage is marked :data:`kb_empty_check.CHECKED` and
:data:`HYPOTHETICAL`. A turn whose first search kept something never waits
for this; one that kept nothing pays two model calls at once for the texts
and the check's reads, in parallel. Behind
``chat_config["kb_hypothetical_search_enabled"]`` (default False).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

CANDIDATES = 8                        # per text; the union is read (gold within 8 for 8 of 12 not-found questions, 11-05)
TIMEOUT_S = 20.0                      # a turn that kept nothing already waits; a late text keeps nothing
MAX_TOKENS = 240
MAX_CHARS = 700
MIN_CHARS = 40
CACHE_SIZE = 256

# Set on a passage this search kept (beside kb_empty_check.CHECKED).
HYPOTHETICAL = "hypothetical"

_COMMON = (
    "Keep names, acronyms and numbers exactly as the question writes them, and never spell out an acronym. "
    "Do not add figures, dates, thresholds, section numbers, or names of laws, agencies or institutions that "
    "are not in the question. No preamble, no heading, no citation."
)
PASSAGE_PROMPT = (
    "You write the passage a regulation or institutional policy on research administration would contain "
    "that answers a question. Write 2 to 4 sentences of such text, in its own register and vocabulary: the "
    "formal names of the costs, actions, roles, documents and procedures the question is about, stating the "
    "rule with the conditions and exceptions such text attaches. " + _COMMON + " Output only the passage."
)
LINES_PROMPT = (
    "You write the one or two lines a regulation or institutional policy on research administration would "
    "contain that decide a question: the specific cost, action, role, document or procedure the question is "
    "about and how the text treats it (allowable or unallowable, permitted, required, prohibited, exempt, or "
    "an exception), as the text's own list item, definition or exception would state it. Such text names the "
    "general category the question's case belongs to, not the case: 'memberships in civic and community "
    "organizations', not a named club; 'promotional items and memorabilia', not t-shirts; 'the basic least "
    "expensive unrestricted accommodations class', not a flight. Write 1 or 2 such lines, one per line, each "
    "under 30 words, in the text's vocabulary. " + _COMMON + " Output only the lines."
)
KINDS = (("passage", PASSAGE_PROMPT), ("lines", LINES_PROMPT))

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_LEAD_RE = re.compile(r"^\s*(?:[-*•]+|\d{1,2}[.)]|(?:passage|lines?)\s*[:.)-])\s*", re.IGNORECASE | re.MULTILINE)
_MARKUP_RE = re.compile(r"[*_`#>|]+")
_WS_RE = re.compile(r"\s+")


def enabled(sys_config_doc: Optional[dict]) -> bool:
    """Whether ``chat_config`` turns the search on (``kb_hypothetical_search_enabled``, default False)."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    return bool(cfg.get("kb_hypothetical_search_enabled", False))


def candidate_count(sys_config_doc: Optional[dict]) -> int:
    """How many of each text's best candidates the check reads
    (``kb_hypothetical_search_candidates``, default :data:`CANDIDATES`)."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    try:
        return max(1, int(cfg.get("kb_hypothetical_search_candidates") or CANDIDATES))
    except (TypeError, ValueError):
        return CANDIDATES


def clean(question: str, output: str) -> str:
    """The model's text as a search query: thinking, list marks, quotes and
    markup removed, any section number or figure the question does not hold
    struck out, whitespace collapsed, at most :data:`MAX_CHARS` characters;
    "" when too little is left."""
    from app.services.kb_paraphrase import _FIGURE_RE, _SECTION_RE, _digits

    asked = _digits(question)
    text = _THINK_RE.sub(" ", output or "")
    text = _LEAD_RE.sub("", text)
    text = _MARKUP_RE.sub(" ", text).strip().strip("\"'“”‘’").strip()

    def strike(m: re.Match) -> str:
        return m.group(0) if _digits(m.group(0)) <= asked else " "

    text = _SECTION_RE.sub(strike, text)
    text = _FIGURE_RE.sub(strike, text)
    text = _WS_RE.sub(" ", text).strip(" ,;:-")
    if len(text) < MIN_CHARS:
        return ""
    return text[:MAX_CHARS]


_CACHE: "OrderedDict[tuple[str, str], list[str]]" = OrderedDict()
_PENDING: dict[tuple[str, str], asyncio.Future] = {}


async def _ask(kind: str, prompt: str, question: str, model_name: str) -> str:
    """One text of *kind* for ``question`` from ``model_name`` at temperature
    0 with thinking off, cleaned by :func:`clean`; "" when the call fails or
    is late."""
    try:
        from app.services.kb_empty_check import _system_config_doc
        from app.services.kb_validation_service import _get_or_build_agent
        from app.services.llm_service import build_thinking_model_settings

        doc = _system_config_doc()
        settings = dict(build_thinking_model_settings(model_name, False, doc) or {})
        settings.update(temperature=0.0, max_tokens=MAX_TOKENS)
        agent = _get_or_build_agent(f"kb_hypothetical_{kind}", model_name, prompt, model_settings=settings)
        run = await asyncio.wait_for(agent.run(f"Question: {question}"), timeout=TIMEOUT_S)
        return clean(question, str(run.output or ""))
    except Exception as e:  # noqa: BLE001 — retrieval goes on without it
        logger.warning("KB hypothetical %s failed: %s", kind, e)
        return ""


async def hypotheticals(question: str, model_name: Optional[str]) -> list[str]:
    """The texts ``model_name`` expects the base to hold for ``question``
    (:data:`KINDS`, asked at once), cleaned, the empty ones dropped; [] without
    a model. One set per (model, question): the knowledge bases of a turn
    share it."""
    question = (question or "").strip()
    if not question or not model_name:
        return []
    key = (model_name, question)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return list(_CACHE[key])
    pending = _PENDING.get(key)
    if pending is not None:
        return list(await asyncio.shield(pending))
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _PENDING[key] = future
    texts: list[str] = []
    try:
        found = await asyncio.gather(*[_ask(kind, prompt, question, model_name) for kind, prompt in KINDS])
        texts = [t for t in found if t]
        _CACHE[key] = texts
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    finally:
        _PENDING.pop(key, None)
        future.set_result(texts)
    return list(texts)


async def checked_pool(dm, kb_uuid: str, query: str, *, k: int, floor: float,
                       model_name: Optional[str]) -> list[dict]:
    """The passages among the base's best candidates for the hypothetical
    texts that the empty-pool check's model finds answer ``query``, best
    first and marked :data:`kb_empty_check.CHECKED` and :data:`HYPOTHETICAL`;
    [] when the search is off, there is no answering model, no text could be
    written, precise retrieval cannot run here, or nothing passes."""
    from app.services import chat_answer_repair, kb_empty_check, kb_grounding
    from app.services import kb_retrieval as kr

    doc = kb_empty_check._system_config_doc()
    question = (query or "").strip()
    if not enabled(doc) or not model_name or not question:
        return []
    cfg = (doc or {}).get("chat_config") or {}
    model = str(cfg.get("empty_pool_check_model") or kb_empty_check.DEFAULT_MODEL)
    texts = await hypotheticals(question, model_name)
    if not texts:
        return []
    n = candidate_count(doc)
    pools = await asyncio.gather(*[
        asyncio.to_thread(kb_grounding.best_candidates, dm, kb_uuid, text, n=n, floor=floor) for text in texts
    ])
    best: dict[str, dict] = {}
    for pool in pools:
        for r in pool or []:
            cid = str(r.get("chunk_id"))
            if cid not in best or (r.get("rerank_score") or 0) > (best[cid].get("rerank_score") or 0):
                best[cid] = r
    candidates = sorted(best.values(), key=lambda r: -(r.get("rerank_score") or 0))
    if not candidates:
        return []
    index = kr.index_for(dm, kb_uuid)

    def source(r: dict) -> str:
        pos = index.position.get(str(r.get("chunk_id"))) if index is not None else None
        return index.prefixes[pos] if pos is not None else ""

    ask = chat_answer_repair.model_ask(model_name, doc)
    keeps = await asyncio.gather(*[
        kb_empty_check._keeps(ask, model, question, source(r), r.get("content") or "") for r in candidates
    ])
    kept = [{**r, kb_empty_check.CHECKED: True, HYPOTHETICAL: True}
            for r, keep in zip(candidates, keeps) if keep][:k]
    logger.info("KB question kept no passage, even checked; the hypothetical search kept %d of %d candidates "
                "from %d texts", len(kept), len(candidates), len(texts))
    return kept
