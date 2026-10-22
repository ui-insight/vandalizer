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
* **Headings cut away from their rules.** Chunks are cut every 1,000
  characters, so three in four carry no heading. The index rebuilds each
  source in order, finds its section headings, and gives every chunk the
  heading path it sits under — for BM25, for the cross-encoder, and for a
  title index that routes "program income" to § 200.307 when the match is
  unambiguous.
* **Every slot filled.** A passage is kept only if the cross-encoder scores it
  above an absolute cut and close to the best one; a passage from a different
  section than the best must be closer still. A query the base cannot answer
  gets no passage at all, which is what grounding wants: a wrong citation is
  worse than none.

The index is built from the chunks already stored — no re-ingest, nothing
written — and cached per process. The cuts and the route thresholds below
were set on the development queries and checked on the held-out ones; they
are tied to the default embedder (all-MiniLM-L6-v2) and to the cross-encoder
revision pinned in :mod:`app.services.cross_encoder`.

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
# Title routing: cosine of the expanded query to a section title, and its
# lead over the best title of any other section (all-MiniLM-L6-v2 scale).
ROUTE_MIN_SIMILARITY = 0.75
ROUTE_MIN_LEAD = 0.03
# A routed section is handed over through its best chunks, at most this many.
ROUTED_CHUNKS = 2
# Index lifetime: rebuilt after this when the base's chunk count changed, and
# after twice this regardless (a refreshed source can keep its count).
INDEX_TTL_S = 600
RESULT_CACHE_SIZE = 512

# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

_MD = r"[ \t]*(?:#{1,6}[ \t]+)?"
# "§ 200.414 Indirect costs.", FAR's "31.205-6 Compensation…".
_SECTION_RE = re.compile(
    rf"^{_MD}(?:§[ \t]*)?(?P<num>\d{{1,4}}\.\d{{1,4}}(?:-\d{{1,3}})?[a-z]?)(?![\d(\-–—]|\.\d)[ \t]+(?P<title>[A-Z\[][^\n]{{0,200}})$",
    re.MULTILINE,
)
# A numbered policy page: "45.10 - Facilities and Administrative (Indirect) Rate".
_POLICY_RE = re.compile(
    rf"^{_MD}(?P<num>\d{{1,3}}\.\d{{1,3}})[ \t]+[-–—][ \t]+(?P<title>[A-Z][^\n]{{0,200}})$",
    re.MULTILINE,
)
# "Appendix III to Part 200—Indirect (F&A) Costs Identification and …".
_APPENDIX_RE = re.compile(rf"^{_MD}(?P<num>Appendix [IVXLC]+)\b(?P<title>[^\n]{{0,240}})$", re.MULTILINE)
# "Subpart E—Cost Principles": a group boundary, not a section of its own.
_GROUP_RE = re.compile(rf"^{_MD}(?:Subpart|SUBPART|Part|PART)[ \t]+[\w.]+[ \t]*(?:[-—–:][^\n]*)?$", re.MULTILINE)
# Sub-headings inside a section: "C-1. Indirect rate.", "D. Policy.", "A. General".
_SUB_RE = re.compile(r"^(?P<label>[A-Z](?:-\d+)?(?:\.[a-z])?)\.[ \t]+(?P<text>[^\n]{2,160})", re.MULTILINE)
# A defined term: "Program income means …".
_DEFINITION_RE = re.compile(r"^(?P<term>[A-Z][^\n]{1,90}?) (?:means|is defined)\b", re.MULTILINE)
_NUMBER_IN_NAME_RE = re.compile(r"(?<![\d.])(\d{1,4}\.\d{1,4}(?:-\d{1,3})?)(?![\d])")

# Cost-principle appendices of 2 CFR 200 written for recipients other than
# institutions of higher education (nonprofits, state and local governments,
# public assistance, hospitals). Their rate rules read like the IHE rules of
# Appendix III, and were the commonest wrong passage for an IHE's
# indirect-cost questions.
_NOT_FOR_IHE_RE = re.compile(r"^Appendix (?:IV|V|VI|VII|VIII|IX) to Part 200\b")


def _short_title(text: str) -> str:
    """'C-2. Residual funds. Residual funds are …' -> 'Residual funds'."""
    m = re.match(r"([^.:\n]{2,90})[.:]", text)
    return (m.group(1) if m else text[:90]).strip()


def _title_words(heading: str) -> str:
    """The words of a heading without its number or trailing period."""
    text = re.sub(r"^\s*#{1,6}\s*", "", heading)
    text = re.sub(r"^§\s*", "", text)
    text = re.sub(r"^(?:\d{1,4}\.\d{1,4}(?:-\d{1,3})?[a-z]?|Appendix [IVXLC]+(?: to Part \d+)?)\s*[-–—:]?\s*", "", text)
    return text.strip().rstrip(".").strip()


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

    def section_of(self, chunk_id) -> Optional[str]:
        i = self.position.get(str(chunk_id))
        return self.keys[i] if i is not None else None


def _is_default_embedder(ef) -> bool:
    # The route thresholds were measured on all-MiniLM-L6-v2 similarities.
    return type(ef).__name__ in ("ONNXMiniLM_L6_V2", "DefaultEmbeddingFunction")


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
    titles: list[tuple[str, str, Optional[str]]] = []

    for group in by_source.values():
        group.sort(key=_chunk_order)
        name = str((group[0].get("metadata") or {}).get("source_name") or "")
        text, starts = "", []
        for c in group:
            content = c.get("content") or ""
            if not text:
                text, at = content, 0
            else:
                text, at = _join(text, content)
            starts.append(at)

        # Section marks: (offset, key, heading line). The source's own name
        # stands for whatever precedes its first heading.
        marks: list[tuple[int, str, str]] = []
        for rx in (_SECTION_RE, _POLICY_RE, _APPENDIX_RE):
            for m in rx.finditer(text):
                marks.append((m.start(), m.group("num"), m.group(0).strip()))
        for m in _GROUP_RE.finditer(text):
            if not any(abs(m.start() - at) < 3 for at, _, _ in marks):
                marks.append((m.start(), f"group:{m.group(0).strip()[:60]}", m.group(0).strip()))
        marks.sort()
        # A contents list names each section on a line of its own: a heading
        # with nothing but the next heading after it is a contents line, not
        # the section (a one-sentence section such as "See § 200.425." stays).
        marks = [mk for i, mk in enumerate(marks)
                 if i + 1 >= len(marks) or mk[1].startswith("group:")
                 or len(text[mk[0]:marks[i + 1][0]].strip()) > len(mk[2]) + 2]
        if not marks or marks[0][0] > 0:
            m = _NUMBER_IN_NAME_RE.search(name)
            marks.insert(0, (0, m.group(1) if m else f"source:{name[:60]}", name))
        bounds = [(at, marks[i + 1][0] if i + 1 < len(marks) else len(text), key, head)
                  for i, (at, key, head) in enumerate(marks)]
        subs = [(m.start(), _short_title(m.group("text"))) for m in _SUB_RE.finditer(text)]

        def section_at(pos: int):
            for b in bounds:
                if b[0] <= pos < b[1]:
                    return b
            return bounds[-1]

        for at, end, key, head in bounds:
            if key.startswith("group:"):
                continue
            words = _title_words(head)
            if not words:
                continue
            # The first heading of a key names it (a later contents line or
            # cross-reference cannot rename it).
            if key not in section_titles:
                section_titles[key] = words
                titles.append((key, words, None))
            if re.search(r"\bdefinitions\b", words, re.IGNORECASE):
                for m in _DEFINITION_RE.finditer(text, at, end):
                    titles.append((key, m.group("term"), m.group("term")))
        for at, sub in subs:
            key = section_at(at)[2]
            if not key.startswith("group:"):
                titles.append((key, sub, None))

        for c, start in zip(group, starts):
            end = start + len(c.get("content") or "")
            # A chunk belongs to the section holding most of its text, not the
            # one it starts in: chunks are cut by length, so one that opens on
            # the last lines of § 200.431 can be mostly § 200.432, and a
            # heading naming the wrong section misleads the reranker.
            spans = [(min(e, end) - max(s, start), (s, e, k, h)) for s, e, k, h in bounds
                     if min(e, end) > max(s, start) and not k.startswith("group:")]
            b = max(spans, key=lambda x: x[0])[1] if spans else section_at(start)
            key, head = b[2], b[3]
            sub = next((s for at, s in reversed(subs) if b[0] <= at <= max(start, b[0]) + 40), None)
            prefix = re.sub(r"\s+", " ", head).strip()
            if sub:
                prefix += f" — {sub}"
            if re.search(r"\bdefinitions\b", head, re.IGNORECASE):
                terms = [m.group("term") for m in _DEFINITION_RE.finditer(c.get("content") or "")][:6]
                if terms:
                    prefix += " — " + "; ".join(terms)
            if key.startswith("source:") and name:
                prefix = name
            i = len(ordered)
            ordered.append(c)
            keys.append(key)
            prefixes.append(prefix[:300])
            texts.append(f"{prefix}\n{c.get('content') or ''}")
            if institution_type == "ihe" and _NOT_FOR_IHE_RE.match(re.sub(r"^\s*#{1,6}\s*", "", head)):
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
    """The cached index for a base, rebuilt when it may be stale. None when
    precise retrieval is off or the store cannot list a base's chunks."""
    if not enabled() or not hasattr(dm, "get_kb_all_chunks"):
        return None
    now = time.time()
    current = _INDEXES.get(kb_uuid)
    if current is not None and now - current.built_at < INDEX_TTL_S:
        return current
    with _INDEX_GUARD:
        lock = _INDEX_LOCKS.setdefault(kb_uuid, threading.Lock())
    with lock:
        current = _INDEXES.get(kb_uuid)
        if current is not None and now - current.built_at < INDEX_TTL_S:
            return current
        if current is not None and now - current.built_at < 2 * INDEX_TTL_S:
            count = _count(dm, kb_uuid)
            if count is not None and count == current.count:
                current.built_at = now
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
        _INDEXES[kb_uuid] = index
        return index


def _count(dm, kb_uuid: str) -> Optional[int]:
    try:
        collection = dm.get_kb_collection_readonly(kb_uuid)
        return collection.count() if collection is not None else 0
    except Exception:  # noqa: BLE001
        return None


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


def keep(scored: list[dict], *, anchor_section: Optional[str], index: KbIndex, top: Optional[float] = None) -> list[dict]:
    """The relevance cut over reranked results (best first)."""
    if not scored:
        return []
    top = scored[0]["rerank_score"] if top is None else top
    kept = [r for r in scored if r["rerank_score"] >= MIN_SCORE and r["rerank_score"] >= top - WITHIN_TOP]
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
