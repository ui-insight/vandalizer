"""Empty-pool check: a chat question that keeps no knowledge-base passage,
even reworded, has its best few candidates read by a model.

Precise retrieval (:mod:`app.services.kb_retrieval`) hands over a passage
only when a cross-encoder scores it above an absolute cut, and the
paraphrase rescue (:mod:`app.services.kb_paraphrase`) only what a reworded
search scores higher still. A question asked as a case scores low across the
board, so the right chunk is often the best candidate and still under the
cut. On the KB accuracy eval (the 10-28 A/B), 299 of 2,633 answerable turns
came back with no passage and were answered "not found", the answer text in
the index every time. Lowering the cut reaches it, but hands the questions
the bases cannot answer about as many passages as it gains: at −8, answer
text for 147 of those turns and passages for 135 of the 183 such questions
refused today.

So when a pool and the rescue both keep nothing, and
``chat_config["empty_pool_check_enabled"]`` is on (it is off by default),
the base's :data:`CANDIDATES` best candidates by cross-encoder score are each
shown to a model at once (qwen3.5-122b with thinking off, temperature 0)
with the question. It labels each passage answers / partial / no and copies
the sentence that answers; a passage is kept only when it answers and that
sentence is in it. Offline over the same turns (2026-10-29, the prompt below
word for word, written once; records reports/empty-pool-check-2026-10-29),
this handed over answer text for 123 of the 299 and passages for none of the
183, the same in two passes and on held-out questions as on development
ones. Taking "partial" too reached 164 but handed passages to 15. A call
took 0.73 s median (p90 1.07 s), and only a turn with an empty pool waits
for one; a failed, late or unreadable call keeps nothing. The candidates'
scores are the pool's own, not computed again (``best_candidates``).

The probe showed each passage under its knowledge base's short name and
heading path; here it is the heading path alone. A passage kept this way is
marked :data:`CHECKED`, which the prompt does not show: a model has read it
against the question, unlike a reworded search's find (``RESCUED``).

Only chat asks: workflow grounding issues author-written queries in the
base's terms (see :mod:`app.services.kb_grounding`).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen/qwen3.5-122b"   # chat_answer_repair's checker, as the probe ran it
CANDIDATES = 3
CHECK_SECONDS = 6.0                   # per candidate, a retry included: 0.73 s median, 2.1 s max in the probe
MAX_TOKENS = 600
PASSAGE_CHARS = 8000                  # of a passage shown to the model (chunks are far shorter)
QUOTE_MIN_CHARS = 12
QUOTE_COVERAGE = 0.8
CACHE_SIZE = 512

# Set on a passage this check kept.
CHECKED = "checked"

# The probe's prompt (empty_check.py), word for word but for the passage's
# source line and the earlier question it showed a follow-up with; chat
# searches a follow-up with a standalone query.
SYSTEM_PROMPT = ("You decide whether a passage from a knowledge base answers a user's question. Judge only by what "
                 "the passage itself says, not by what you know. Reply with one JSON object and nothing else.")
PROMPT = """Question: {question}

Passage ({source}):
\"\"\"
{text}
\"\"\"

Does this passage answer the question?
- "answers": it states the answer, or the rule that decides it, for the case the question asks about.
- "partial": it states part of the answer, or a rule the answer depends on, but not enough to answer alone.
- "no": it is about another topic, program, agency or case, or it is background that does not decide the question.

Reply as {{"label": "answers" | "partial" | "no", "quote": "the sentence of the passage that answers it, copied \
exactly, or an empty string for no"}}"""
RETRY_NOTE = "\n\nReply with the JSON object only."


def check_model(sys_config_doc: Optional[dict]) -> Optional[str]:
    """The model that checks an empty pool, or None when the check is off.

    Keys of ``chat_config``: ``empty_pool_check_enabled`` (default False) and
    ``empty_pool_check_model`` (default qwen3.5-122b)."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    if not bool(cfg.get("empty_pool_check_enabled", False)):
        return None
    return str(cfg.get("empty_pool_check_model") or DEFAULT_MODEL)


def _system_config_doc() -> Optional[dict]:
    """The turn's System Config snapshot, loaded before retrieval runs."""
    from app.services.kb_validation_service import _active_system_config_doc

    return _active_system_config_doc.get()


def quote_in(quote: str, text: str, n: int = 6) -> bool:
    """Whether ``quote`` is in ``text``: whole, after the eval's normalisation,
    or at least :data:`QUOTE_COVERAGE` of its words inside runs of ``n`` words
    found there verbatim. A quote shorter than :data:`QUOTE_MIN_CHARS` is
    not."""
    from app.services.chat_answer_repair import _norm

    q, hay = _norm(quote), _norm(text)
    if len(q) < QUOTE_MIN_CHARS or not hay:
        return False
    if q in hay:
        return True
    w = q.split(" ")
    if len(w) <= n:
        return False
    covered = [False] * len(w)
    for i in range(len(w) - n + 1):
        if " ".join(w[i:i + n]) in hay:
            for j in range(i, i + n):
                covered[j] = True
    return sum(covered) / len(w) >= QUOTE_COVERAGE


def prompt(question: str, source: str, text: str) -> str:
    return PROMPT.format(question=question, source=source or "knowledge base", text=(text or "")[:PASSAGE_CHARS])


def verdict(reply: str, text: str) -> tuple[str, bool]:
    """The label of a reply, and whether it keeps the passage: "answers" with
    a quote that is in ``text``. Raises ValueError when no JSON is found."""
    from app.services.chat_answer_repair import parse_json

    obj = parse_json(reply)
    if not isinstance(obj, dict):
        raise ValueError("reply is not a JSON object")
    label = str(obj.get("label") or "").strip().lower()
    return label, label == "answers" and quote_in(str(obj.get("quote") or ""), text)


_CACHE: "OrderedDict[tuple[str, str, str], bool]" = OrderedDict()


async def _keeps(ask, model: str, question: str, source: str, text: str) -> bool:
    """Whether ``model`` finds that the passage answers ``question``; False when
    the call fails, is late, or its reply cannot be read even when asked once
    more. One call per (model, question, passage text)."""
    key = (model, question, hashlib.sha256(text.encode("utf-8")).hexdigest())
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    asked = prompt(question, source, text)

    async def run() -> bool:
        reply = await ask(model, SYSTEM_PROMPT, asked, MAX_TOKENS)
        try:
            return verdict(reply, text)[1]
        except ValueError:
            return verdict(await ask(model, SYSTEM_PROMPT, asked + RETRY_NOTE, MAX_TOKENS), text)[1]

    try:
        keep = await asyncio.wait_for(run(), timeout=CHECK_SECONDS)
    except Exception as e:  # noqa: BLE001 — a failed check keeps nothing
        logger.warning("KB empty-pool check by %s failed: %s", model, e)
        return False
    _CACHE[key] = keep
    while len(_CACHE) > CACHE_SIZE:
        _CACHE.popitem(last=False)
    return keep


async def checked_pool(dm, kb_uuid: str, query: str, *, k: int, floor: float,
                       model_name: Optional[str]) -> list[dict]:
    """The passages among the base's :data:`CANDIDATES` best candidates for
    ``query`` that the check finds answer it, best first and marked
    :data:`CHECKED`; [] when the check is off, there is no answering model
    (whose endpoint a checker not in System Config is called on), precise
    retrieval cannot run here, or nothing passes."""
    from app.services import chat_answer_repair, kb_grounding
    from app.services import kb_retrieval as kr

    doc = _system_config_doc()
    model = check_model(doc)
    question = (query or "").strip()
    if not model or not model_name or not question:
        return []
    # The query as the pool searched it, so the pool's scores are reused.
    best = await asyncio.to_thread(kb_grounding.best_candidates, dm, kb_uuid, query, n=CANDIDATES, floor=floor)
    if not best:
        return []
    index = kr.index_for(dm, kb_uuid)

    def source(r: dict) -> str:
        pos = index.position.get(str(r.get("chunk_id"))) if index is not None else None
        return index.prefixes[pos] if pos is not None else ""

    ask = chat_answer_repair.model_ask(model_name, doc)
    keeps = await asyncio.gather(*[_keeps(ask, model, question, source(r), r.get("content") or "") for r in best])
    kept = [{**r, CHECKED: True} for r, keep in zip(best, keeps) if keep][:k]
    logger.info("KB question kept no passage, even reworded; the check kept %d of %d candidates",
                len(kept), len(best))
    return kept
