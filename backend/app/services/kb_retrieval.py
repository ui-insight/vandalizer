"""Precise knowledge-base retrieval: the right section for plain words, or
nothing.

Workflow grounding asked a knowledge base with a bi-encoder alone and always
handed over its top ``k`` chunks. Measured on 61 research-administration
queries over 2 CFR 200 and an institution's policy pages (plus 25 held out),
that found the right section for about three plain-language queries in four,
and handed the model about two wrong passages per query (four for a question
the base cannot answer). Section-number queries worked because a separate
lane finds the section by its heading. The misses had four causes, each
answered here:

* **Words the base never uses** ("IDC", "NCE", "beer"). The query is expanded
  with a research-administration glossary and the base's own "Long Form
  (ABBR)" definitions (:mod:`app.services.ra_glossary`).
* **Neighbouring text outranks the target** (Appendix VII's state-government
  rate rules over § 200.414). Candidates come from the vector search *and* a
  BM25 index over the chunks with their section headings, fused by rank; a
  local cross-encoder (:mod:`app.services.cross_encoder`) then reads each
  query-passage pair, and appendices written for other kinds of recipient
  are left out for an institution of higher education.
* **Headings cut away from their rules.** Every chunk is read under the
  heading path it sits under — by BM25, by the cross-encoder, and by a title
  index that routes "program income" to § 200.307 when the match is
  unambiguous. A source chunked by its structure
  (:mod:`app.services.kb_chunking`) stores that path on each chunk; one cut
  every 1,000 characters, where three chunks in four carry no heading, is
  rebuilt in order and its headings found again.
* **Every slot filled.** A passage is kept only if the cross-encoder scores it
  above an absolute cut and close to the best one; a passage from a different
  section than the best must be closer still. A query the base cannot answer
  gets no passage at all, which is what grounding wants: a wrong citation is
  worse than none.

The index is built from the chunks already stored — nothing written — and
cached per process until the base's chunks are written again (see
``INDEX_CHECK_S``). The cuts and the route thresholds below were set on the
development queries and checked on the held-out ones, for both kinds of
chunk (a lower cut gained on chunks cut by section but let a held-out
question the base cannot answer through); they are tied to the default
embedder (all-MiniLM-L6-v2) and to the cross-encoder revision pinned in
:mod:`app.services.cross_encoder`.

Everything here is optional: without a full-collection read on the store, or
without the cross-encoder, :func:`index_for` / :func:`ready` say so and the
caller keeps its previous ranking.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.services.kb_chunking import (
    DEFINITION_RE,
    HEADING_PATH_MAX_CHARS,
    Bound,
    heading_path,
    is_definitions,
    section_bounds,
    sub_headings,
    title_words,
)

logger = logging.getLogger(__name__)

# Candidates each lane (vector, BM25) contributes before rank fusion, and how
# many fused candidates the cross-encoder reads.
CANDIDATES_PER_LANE = 30
RERANK_POOL = 30
RRF_K = 60
# The relevance cut (cross-encoder logits). A passage is kept when it scores
# at least MIN_SCORE and within WITHIN_TOP of the best passage; one from a
# different section than the first passage must be within OTHER_SECTION_WITHIN.
MIN_SCORE = -3.0
WITHIN_TOP = 3.0
OTHER_SECTION_WITHIN = 1.5
# The cut for a passage scored against a paraphrase of the question in the
# base's own words (app.services.kb_paraphrase) rather than the question. A
# short search query is what the cross-encoder was trained on, and its scores
# run several points higher for the same passage, so its cut is higher too.
# On the development questions that keep nothing (2026-10-25), two
# paraphrases at 0.5 let a passage through for one question in seven the base
# cannot answer, and for answerable ones handed over a pool without the
# answer for every 2.4 that held it — answered from as if it did. Four
# paraphrases at 2.0 let none of the former through and halved the latter,
# for 5% of the pools that held the answer.
PARAPHRASE_MIN_SCORE = 2.0
# The same for one part of a compound question (kb_paraphrase.part_pools).
# A part is searched with one query, not four, so it has no others to make
# up for what a higher cut drops: at 2.0 it lost a quarter of the answer
# text the parts reached.
PART_MIN_SCORE = 1.5
# The fused candidates a paraphrase or part query has the cross-encoder read
# (RERANK_POOL for the question itself). Every passage those queries kept on
# the development questions was among their first 8; reading 30 tripled the
# cost of a turn that falls back on them.
RESCUE_RERANK_POOL = 8
# The cut for the chunk either side of a passage handed over, in the same
# section of the same source (kb_grounding.with_neighbours). The section has
# already cleared the relevance cut; its next lines often hold the rest of
# the answer or the exception to it. On the development questions this
# reached 5 points more of the answer text and 3 more of its governing
# context for 1.7 more passages per question; admitting every neighbour
# added 0.9 more passages for almost nothing.
NEIGHBOUR_MIN_SCORE = -5.0
# The passages of each base, best first, whose same-section chunks either side
# are handed over whatever they score and beyond any cap
# (kb_grounding.with_adjacent). On the KB accuracy eval (Phase 3 after-run,
# 2026-10-26) the answer text a pool missed sat one or two chunks from a passage
# it held, in the same section, in 47% of the turns that reached only part of
# their answer; the neighbour cut and the pool's cap kept it out about equally
# often. Beside the best two passages this reached all the answer text in 15
# more such turns for 1.2 more passages per turn; beside every passage, 16 for
# 2.7.
ADJACENT_PASSAGES = 2
# The section the chat model names first from the bases' table of contents
# (kb_sections) joins a turn's passages after every cap through its best
# chunks, at most SECTION_PICK_CHUNKS, each scoring at least SECTION_MIN_SCORE
# (kb_grounding.with_section) — unless a passage already comes from it, or the
# turn has none. On the KB accuracy eval (2026-10-27, offline over the Phase 3
# after-run's pools) this reached all the answer text in 36 of 155 turns whose
# passages held none of it, for 0.26 more passages per turn on questions
# answered right and 0.28 on questions the bases cannot answer; without the
# score cut 40, for 0.45 and 0.51. The chunks that held answer text scored a
# median -2.7, those added where there is no answer -7.5.
SECTION_PICK_CHUNKS = 2
SECTION_MIN_SCORE = -8.0
# Title routing: cosine of the expanded query to a section title, and its
# lead over the best title of any other section (all-MiniLM-L6-v2 scale).
ROUTE_MIN_SIMILARITY = 0.75
ROUTE_MIN_LEAD = 0.03
# A routed section is handed over through its best chunks, at most this many.
ROUTED_CHUNKS = 2
# Index lifetime. A cached index is used for INDEX_CHECK_S without asking the
# store; then it is kept while the base's revision — stamped on its collection
# by every chunk write (DocumentManager.KB_REVISION_KEY) — and its chunk count
# are the ones it was built from, and rebuilt when either changed. A re-chunk
# or refresh can keep the count; it cannot keep the revision. A base not
# written since revisions were stamped has only its count to go by, so its
# index is also rebuilt UNSTAMPED_MAX_AGE_S after it was built.
INDEX_CHECK_S = 30
UNSTAMPED_MAX_AGE_S = 1200
RESULT_CACHE_SIZE = 512

# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

# Cost-principle appendices of 2 CFR 200 written for recipients other than
# institutions of higher education (nonprofits, state and local governments,
# public assistance, hospitals). Their rate rules read like the IHE rules of
# Appendix III, and were the commonest wrong passage for an IHE's
# indirect-cost questions.
_NOT_FOR_IHE_RE = re.compile(r"^Appendix (?:IV|V|VI|VII|VIII|IX) to Part 200\b")


def _join(text: str, nxt: str) -> tuple[str, int]:
    """``text`` followed by the next chunk of its source with the splitter's
    repeated overlap removed, and where the next chunk starts in the result."""
    for n in range(min(len(text), len(nxt), 600), 11, -1):
        if text.endswith(nxt[:n]):
            return text + nxt[n:], len(text) - n
    return f"{text}\n\n{nxt}", len(text) + 2


_CHUNK_NO_RE = re.compile(r"_chunk_(\d+)$")


def _chunk_order(c: dict) -> int:
    meta = c.get("metadata") or {}
    idx = meta.get("chunk_index")
    if isinstance(idx, int):
        return idx
    m = _CHUNK_NO_RE.search(str(c.get("chunk_id") or ""))
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

_STOP = frozenset("""a an the of to in on for and or by with from at as is are be was were it its this that these
those which who what when where how can could may might must shall should will would do does did not no any all
each our we you your they their there here than then so if into about over under between per via vs versus""".split())
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:&[a-z0-9]+)?")


def _stem(word: str) -> str:
    if len(word) <= 3 or word.isdigit():
        return word
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "s" and word.endswith(("ss", "us", "is")):
                return word
            return word[: -len(suffix)] + repl
    return word


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in _TOKEN_RE.findall((text or "").lower()) if w not in _STOP and (len(w) > 1 or w.isdigit())]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.postings: dict[str, list[tuple[int, int]]] = {}
        self.lengths = np.zeros(self.n, dtype=np.float32)
        for i, doc in enumerate(docs):
            toks = tokens(doc)
            self.lengths[i] = len(toks)
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            for t, c in counts.items():
                self.postings.setdefault(t, []).append((i, c))
        self.avg = float(self.lengths.mean()) if self.n else 0.0

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        if not self.n:
            return out
        for t in set(tokens(query)):
            plist = self.postings.get(t)
            if not plist:
                continue
            idf = math.log(1 + (self.n - len(plist) + 0.5) / (len(plist) + 0.5))
            for i, tf in plist:
                norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avg or 1.0))
                out[i] += idf * tf * (self.k1 + 1) / norm
        return out


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

@dataclass
class Route:
    """A section a plain query names by its title. ``term`` is set when the
    match is a defined term (§ 200.1 "Program income means …")."""
    key: str
    title: str
    term: Optional[str]
    similarity: float
    lead: float

    @property
    def numbered(self) -> bool:
        return bool(re.fullmatch(r"\d{1,4}\.\d{1,4}(?:-\d{1,3})?[a-z]?", self.key))


@dataclass
class KbIndex:
    kb_uuid: str
    chunks: list[dict]
    keys: list[str]                    # section key per chunk
    prefixes: list[str]                # heading path per chunk
    excluded: set[int]                 # chunks in sections that do not apply
    bm25: BM25
    abbreviations: dict[str, str]
    section_titles: dict[str, str]     # key -> heading words
    titles: list[tuple[str, str, Optional[str]]] = field(default_factory=list)
    title_matrix: Optional[np.ndarray] = None
    embed: object = None               # the store's embedding function, for routing
    count: int = 0
    built_at: float = 0.0
    position: dict[str, int] = field(default_factory=dict)
    revision: Optional[str] = None     # the base's revision when it was read
    checked_at: float = 0.0            # last found current against the store

    def section_of(self, chunk_id) -> Optional[str]:
        i = self.position.get(str(chunk_id))
        return self.keys[i] if i is not None else None


def _is_default_embedder(ef) -> bool:
    # The route thresholds were measured on all-MiniLM-L6-v2 similarities.
    return type(ef).__name__ in ("ONNXMiniLM_L6_V2", "DefaultEmbeddingFunction")


Titles = list[tuple[str, str, Optional[str]]]


def _has_stored_section(c: dict) -> bool:
    key = (c.get("metadata") or {}).get("section_key")
    return isinstance(key, str) and bool(key)


def _stored_sections(group: list[dict], section_titles: dict[str, str], titles: Titles) -> list[tuple[str, str]]:
    """(section key, heading path) per chunk of a source chunked by its
    structure, read from the chunks (:mod:`app.services.kb_chunking`)."""
    out: list[tuple[str, str]] = []
    for c in group:
        meta = c.get("metadata") or {}
        key = str(meta["section_key"])
        title = str(meta.get("section_title") or "")
        content = c.get("content") or ""
        if not key.startswith("group:"):
            if title and key not in section_titles:
                section_titles[key] = title
                titles.append((key, title, None))
            if is_definitions(title):
                titles.extend((key, m.group("term"), m.group("term")) for m in DEFINITION_RE.finditer(content))
            titles.extend((key, sub, None) for _, sub in sub_headings(content))
        out.append((key, str(meta.get("heading_path") or "")))
    return out


def _rebuilt_sections(group: list[dict], name: str, section_titles: dict[str, str],
                      titles: Titles) -> list[tuple[str, str]]:
    """(section key, heading path) per chunk of a source cut by length: its
    text rebuilt in chunk order, the overlap removed, and its headings found
    again."""
    text, starts = "", []
    for c in group:
        content = c.get("content") or ""
        if not text:
            text, at = content, 0
        else:
            text, at = _join(text, content)
        starts.append(at)

    bounds = section_bounds(text, name)
    subs = sub_headings(text)

    def section_at(pos: int) -> Bound:
        return next((b for b in bounds if b.start <= pos < b.end), bounds[-1])

    for b in bounds:
        if b.group:
            continue
        words = title_words(b.heading)
        if not words:
            continue
        # The first heading of a key names it (a later contents line or
        # cross-reference cannot rename it).
        if b.key not in section_titles:
            section_titles[b.key] = words
            titles.append((b.key, words, None))
        if is_definitions(words):
            for m in DEFINITION_RE.finditer(text, b.start, b.end):
                titles.append((b.key, m.group("term"), m.group("term")))
    for at, sub in subs:
        b = section_at(at)
        if not b.group:
            titles.append((b.key, sub, None))

    out: list[tuple[str, str]] = []
    for c, start in zip(group, starts):
        end = start + len(c.get("content") or "")
        # A chunk belongs to the section holding most of its text, not the
        # one it starts in: chunks are cut by length, so one that opens on
        # the last lines of § 200.431 can be mostly § 200.432, and a
        # heading naming the wrong section misleads the reranker.
        spans = [(min(b.end, end) - max(b.start, start), b) for b in bounds
                 if min(b.end, end) > max(b.start, start) and not b.group]
        b = max(spans, key=lambda x: x[0])[1] if spans else section_at(start)
        sub = next((s for at, s in reversed(subs) if b.start <= at <= max(start, b.start) + 40), None)
        prefix = heading_path(b, sub=sub, content=c.get("content") or "")
        if b.key.startswith("source:") and name:
            prefix = name
        out.append((b.key, prefix))
    return out


def build_index(kb_uuid: str, chunks: list[dict], *, embedding_function=None, institution_type: str = "ihe",
                route_titles: Optional[bool] = None) -> Optional[KbIndex]:
    """The index over a base's stored chunks. None for an empty base.

    Titles are embedded for routing only with the embedder the route
    thresholds were measured on, unless ``route_titles`` says otherwise."""
    if not chunks:
        return None
    by_source: dict[str, list[dict]] = {}
    for c in chunks:
        meta = c.get("metadata") or {}
        sid = str(meta.get("source_id") or meta.get("document_id") or meta.get("source_name") or "")
        by_source.setdefault(sid, []).append(c)

    ordered: list[dict] = []
    keys: list[str] = []
    prefixes: list[str] = []
    excluded: set[int] = set()
    texts: list[str] = []
    section_titles: dict[str, str] = {}
    titles: Titles = []

    for group in by_source.values():
        group.sort(key=_chunk_order)
        name = str((group[0].get("metadata") or {}).get("source_name") or "")
        # A source whose chunks all say where they sit is read as stored; one
        # chunked before that (or only partly rewritten) is rebuilt.
        if all(_has_stored_section(c) for c in group):
            labelled = _stored_sections(group, section_titles, titles)
        else:
            labelled = _rebuilt_sections(group, name, section_titles, titles)
        for c, (key, prefix) in zip(group, labelled):
            i = len(ordered)
            ordered.append(c)
            keys.append(key)
            prefixes.append(prefix[:HEADING_PATH_MAX_CHARS])
            texts.append(f"{prefix}\n{c.get('content') or ''}")
            # The heading path opens with the section's heading line.
            if institution_type == "ihe" and _NOT_FOR_IHE_RE.match(re.sub(r"^\s*#{1,6}\s*", "", prefix)):
                excluded.add(i)

    from app.services.ra_glossary import corpus_abbreviations

    index = KbIndex(
        kb_uuid=kb_uuid, chunks=ordered, keys=keys, prefixes=prefixes, excluded=excluded,
        bm25=BM25(texts), abbreviations=corpus_abbreviations(c.get("content") or "" for c in ordered),
        section_titles=section_titles, titles=[t for t in titles if len(t[1]) >= 3],
        count=len(chunks), built_at=time.time(),
        position={str(c.get("chunk_id")): i for i, c in enumerate(ordered)},
    )
    routable = route_titles if route_titles is not None else _is_default_embedder(embedding_function)
    if embedding_function is not None and routable and index.titles:
        try:
            vectors = embedding_function([t[1] for t in index.titles])
            m = np.asarray([np.asarray(v, dtype=np.float32) for v in vectors])
            index.title_matrix = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
            index.embed = embedding_function
        except Exception as e:  # noqa: BLE001 — no routing, everything else stands
            logger.debug("Title index embedding failed for kb=%s: %s", kb_uuid, e)
    return index


_INDEXES: dict[str, KbIndex] = {}
_INDEX_LOCKS: dict[str, threading.Lock] = {}
_INDEX_GUARD = threading.Lock()


def _settings():
    from app.config import Settings

    return Settings()


def enabled() -> bool:
    try:
        return bool(_settings().kb_precise_retrieval)
    except Exception:  # noqa: BLE001
        return False


def index_for(dm, kb_uuid: str) -> Optional[KbIndex]:
    """The cached index for a base, rebuilt when the base changed (see
    INDEX_CHECK_S). None when precise retrieval is off or the store cannot
    list a base's chunks."""
    if not enabled() or not hasattr(dm, "get_kb_all_chunks"):
        return None
    current = _INDEXES.get(kb_uuid)
    if current is not None and time.time() - current.checked_at < INDEX_CHECK_S:
        return current
    with _INDEX_GUARD:
        lock = _INDEX_LOCKS.setdefault(kb_uuid, threading.Lock())
    with lock:
        now = time.time()
        current = _INDEXES.get(kb_uuid)
        if current is not None and now - current.checked_at < INDEX_CHECK_S:
            return current
        # Read before the chunks: a write landing between the two leaves an
        # index of new chunks under the old revision (rebuilt once more at
        # the next check), never one of old chunks under the new revision.
        signature = _signature(dm, kb_uuid)
        if current is not None and signature is not None and _still_current(current, signature, now):
            current.checked_at = now
            return current
        try:
            chunks = dm.get_kb_all_chunks(kb_uuid)
            if not isinstance(chunks, list):
                return None
            index = build_index(
                kb_uuid, chunks, embedding_function=getattr(dm, "embedding_function", None),
                institution_type=(_settings().kb_institution_type or "").strip().lower(),
            )
        except Exception as e:  # noqa: BLE001 — the caller keeps its vector ranking
            logger.warning("Knowledge-base index build failed for kb=%s: %s", kb_uuid, e)
            return None
        if index is None:
            _INDEXES.pop(kb_uuid, None)
            return None
        index.revision = signature[0] if signature is not None else None
        index.checked_at = now
        _INDEXES[kb_uuid] = index
        return index


def _signature(dm, kb_uuid: str) -> Optional[tuple[Optional[str], int]]:
    """A base's revision (None when it has none) and chunk count — the
    collection's metadata and its count, no chunk read; None when the store
    cannot say."""
    from app.services.document_manager import KB_REVISION_KEY

    try:
        collection = dm.get_kb_collection_readonly(kb_uuid)
        if collection is None:
            return None, 0
        meta = collection.metadata
        revision = meta.get(KB_REVISION_KEY) if isinstance(meta, dict) else None
        return (revision if isinstance(revision, str) else None), collection.count()
    except Exception:  # noqa: BLE001
        return None


def _still_current(index: KbIndex, signature: tuple[Optional[str], int], now: float) -> bool:
    revision, count = signature
    if revision != index.revision or count != index.count:
        return False
    # Without a revision only the count speaks, and a rewrite can keep it.
    return revision is not None or now - index.built_at < UNSTAMPED_MAX_AGE_S


def ready() -> bool:
    """Whether the cross-encoder is available (fetching it on first ask)."""
    from app.services.cross_encoder import get_cross_encoder

    return enabled() and get_cross_encoder() is not None


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def expand(index: Optional[KbIndex], query: str) -> str:
    from app.services.ra_glossary import expand_query

    return expand_query(query, index.abbreviations if index else None)


def route(index: KbIndex, query: str) -> Optional[Route]:
    """The section a plain query names by its title, when the match is
    unambiguous; else None."""
    if index.title_matrix is None or index.embed is None:
        return None
    try:
        qv = np.asarray(index.embed([expand(index, query)])[0], dtype=np.float32)
    except Exception as e:  # noqa: BLE001
        logger.debug("Route embedding failed: %s", e)
        return None
    qv = qv / max(float(np.linalg.norm(qv)), 1e-9)
    sims = index.title_matrix @ qv
    order = [int(i) for i in np.argsort(-sims)]
    best = order[0]
    # A section title beats a defined term of (nearly) the same score:
    # "Cost sharing" is § 200.306's title and a § 200.1 definition.
    if index.titles[best][2]:
        title = next((i for i in order[1:6] if not index.titles[i][2] and sims[best] - sims[i] <= 0.03), None)
        if title is not None:
            best = title
    key, text, term = index.titles[best]
    norm = text.lower().strip()
    runner = next((float(sims[i]) for i in order if i != best and index.titles[i][0] != key
                   and index.titles[i][1].lower().strip() != norm), 0.0)
    sim = float(sims[best])
    if sim < ROUTE_MIN_SIMILARITY or sim - runner < ROUTE_MIN_LEAD:
        return None
    return Route(key=key, title=index.section_titles.get(key, text), term=term, similarity=sim, lead=sim - runner)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def _chunk_result(index: KbIndex, i: int) -> dict:
    c = index.chunks[i]
    return {
        "content": c.get("content") or "", "metadata": dict(c.get("metadata") or {}),
        "chunk_id": c.get("chunk_id"), "score": None, "similarity": None,
    }


def candidates(dm, index: KbIndex, kb_uuid: str, expanded: str, *, floor: float,
               within: Optional[str] = None, containing: Optional[str] = None) -> list[dict]:
    """Vector and BM25 candidates fused by reciprocal rank. ``within`` keeps
    one section's chunks only (a section the query named or was routed to),
    and ``containing`` those of them that define a term ("X means")."""
    lane_vector: list[dict] = []
    if within is None:
        lane_vector = dm.query_kb(kb_uuid, expanded, CANDIDATES_PER_LANE, floor)
        if floor > 0:
            lane_vector = [r for r in lane_vector
                           if not isinstance(r.get("similarity"), (int, float)) or r["similarity"] >= floor]
    bm = index.bm25.scores(expanded)
    if within is not None:
        allowed = [i for i, k in enumerate(index.keys) if k == within
                   and (not containing or f"{containing} means" in (index.chunks[i].get("content") or ""))]
        if not allowed:
            return []
        order = sorted(allowed, key=lambda i: -bm[i])
    else:
        order = [int(i) for i in np.argsort(-bm)[:CANDIDATES_PER_LANE] if bm[i] > 0]

    fused: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for rank, r in enumerate(lane_vector):
        cid = str(r.get("chunk_id"))
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        rows[cid] = r
    for rank, i in enumerate(order[:CANDIDATES_PER_LANE]):
        cid = str(index.chunks[i].get("chunk_id"))
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        rows.setdefault(cid, _chunk_result(index, i))
    ranked = sorted(fused, key=lambda cid: -fused[cid])
    out = []
    for cid in ranked:
        pos = index.position.get(cid)
        if pos is not None and pos in index.excluded:
            continue
        out.append(rows[cid])
        if len(out) >= RERANK_POOL:
            break
    return out


def rerank(index: KbIndex, expanded: str, results: list[dict]) -> list[dict]:
    """``results`` scored by the cross-encoder (``rerank_score``), best first.
    Each passage is read under its heading path."""
    from app.services.cross_encoder import get_cross_encoder

    scorer = get_cross_encoder()
    if scorer is None or not results:
        return []
    texts = []
    for r in results:
        pos = index.position.get(str(r.get("chunk_id")))
        prefix = index.prefixes[pos] if pos is not None else ""
        texts.append(f"{prefix}\n{r.get('content') or ''}" if prefix else (r.get("content") or ""))
    for r, s in zip(results, scorer.scores(expanded, texts)):
        r["rerank_score"] = s
    return sorted(results, key=lambda r: -r["rerank_score"])


def keep(scored: list[dict], *, anchor_section: Optional[str], index: KbIndex, top: Optional[float] = None,
         min_score: float = MIN_SCORE) -> list[dict]:
    """The relevance cut over reranked results (best first)."""
    if not scored:
        return []
    top = scored[0]["rerank_score"] if top is None else top
    kept = [r for r in scored if r["rerank_score"] >= min_score and r["rerank_score"] >= top - WITHIN_TOP]
    if not kept:
        return []
    # The section of the first passage handed over (a section the query named
    # or was routed to, else the best-scoring one) anchors the rest.
    anchor = anchor_section or index.section_of(kept[0].get("chunk_id"))
    return [r for r in kept
            if index.section_of(r.get("chunk_id")) == anchor or r["rerank_score"] >= top - OTHER_SECTION_WITHIN]


_RESULTS: "OrderedDict[tuple, list[dict]]" = OrderedDict()
_RESULTS_LOCK = threading.Lock()


def cached(key: tuple):
    with _RESULTS_LOCK:
        hit = _RESULTS.get(key)
        if hit is not None:
            _RESULTS.move_to_end(key)
            return [dict(r) for r in hit]
    return None


def remember(key: tuple, pool: list[dict]) -> None:
    with _RESULTS_LOCK:
        _RESULTS[key] = [dict(r) for r in pool]
        _RESULTS.move_to_end(key)
        while len(_RESULTS) > RESULT_CACHE_SIZE:
            _RESULTS.popitem(last=False)
