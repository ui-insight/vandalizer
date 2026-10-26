"""Knowledge-base grounding for workflow tasks.

Retrieval that belongs to the task that consumes it. A task that names one or
more knowledge bases, each with its own short retrieval queries, gets at run
time a block of passages retrieved *for that task's questions* — instead of
the one merged block a separate Knowledge Base Query step hands identically
to every task that follows it.

Grounding is a property of the task, not of the step: the step's data sources
(previous output, documents) are shared by every task in the step, while the
policy a budget task needs differs from what a red-flags task needs. So a
task's ``kb_grounding`` config is read on its own and its passages are
appended to whatever input the step gives it.

The pipeline, per task:

1. Render each base's queries (``{{ inputs.output }}`` templating is
   honoured, and a rendered query longer than :data:`CONDENSE_WORD_LIMIT`
   words is condensed into a search prompt rather than silently cut at the
   embedder's 256-token input cap).
2. For every (knowledge base, query) pair: each section the query names,
   found by its heading and handed over whole (heading to next heading,
   capped — see "Sections" below), then a lexical lookup for any other cited
   number or identifier (``NSF-24-117``) that a bi-encoder scores as
   near-noise, then the rest by relevance. Where it can run, that is precise
   retrieval (:mod:`app.services.kb_retrieval`): a plain query is expanded
   with research-administration vocabulary, routed to a section whose title
   it names, searched by vector and BM25 together, and reranked by a local
   cross-encoder whose cut hands over no passage rather than a wrong one.
   Otherwise it is an over-fetched vector search with a per-source diversity
   cap so one long page cannot fill every slot.
   The knowledge base's Autovalidate-tuned relevance floor applies to the
   vector candidates unless the task sets its own.
3. Round-robin the pools across a base's queries, then across bases, so each
   query and each base is represented before any contributes twice; dedupe
   on chunk id *and* on content, because a corpus that ingests both a whole
   regulation and each of its subparts embeds the same paragraph twice.
4. Trim to the task's passage cap and, when the caller knows the model's
   remaining input budget, to what actually fits — dropping the lowest-ranked
   passages first, never the document.
5. Render one framed text block with a source line above every passage and a
   citation list for the run's Sources panel.

No database access happens here: knowledge-base titles and tuned settings
arrive pre-resolved on the task data (``_kb_meta``, see
``workflow_tasks._preload_kb_meta``) the same way document texts do, so the
module stays pure and unit-testable with a fake ``DocumentManager``.

Deliberately not applied from a knowledge base's tuned config: LLM reranking
and query rewriting. Those tune a chat answer to one free-text question; a
grounded task issues several author-written retrieval queries per run, and an
LLM call per (base, query) pair inside a parallel step is the wrong trade.
The local cross-encoder costs well under a second per pair of base and query
on a CPU, and a task's queries are fixed, so its results are cached.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.services.kb_chunking import SECTION_TITLE_START
from app.services.kb_lead_in import attach_lead_ins, with_lead_in
from app.services.page_locator import (
    annotate_chunk_pages,
    cited_pages,
    format_page_range,
    locator_for_meta,
    page_breaks_of,
)

logger = logging.getLogger(__name__)

# The key under which a task stores its grounding, and the ``kind`` a Form
# Filler attribution entry carries for a value found in the passages.
GROUNDING_SOURCE = "kb_grounding"
# Section header the passages land under in a task's CONTEXT block.
GROUNDING_SECTION_LABEL = "Knowledge Base Passages"

DEFAULT_K = 4                 # passages per knowledge base per query
DEFAULT_MAX_PASSAGES = 8      # total after merge and dedupe
MAX_KNOWLEDGE_BASES = 5
MAX_QUERIES = 8               # per knowledge base
MAX_K = 20
MAX_MAX_PASSAGES = 40
OVERFETCH_MULTIPLIER = 3
# A rendered query longer than this is condensed before embedding. The default
# embedder keeps the first 256 tokens of its input, so a template that splices
# a whole upstream output into the query would otherwise search on its first
# paragraph — with no warning.
CONDENSE_WORD_LIMIT = 60
PIN_LIMIT_PER_TERM = 6
# A section the query names is handed over as one passage, from its heading
# to the next heading, at most this long (cut at a line break). Chunks are
# 1,000 characters, so this is three or four of them: the general rule of a
# section and its first paragraphs, not a 20,000-character compensation rule.
SECTION_MAX_CHARS = 4000
# Chunks read past the one holding the heading, enough to fill the cap.
SECTION_FOLLOW_CHUNKS = 6
# Below this, the heading is a table-of-contents line, not a section.
SECTION_MIN_BODY_CHARS = 40
SECTION_FETCH_POOL = 100
# Rough allowance for the prompt scaffolding around CONTEXT when a caller
# derives a token budget for the passages.
PROMPT_SCAFFOLD_TOKENS = 400
# How much of a passage's text a citation carries into the run record. It
# must hold a whole section passage: sourcing and the popover read this
# text, and it has to be exactly what the model saw.
CITATION_CONTENT_CHARS = SECTION_MAX_CHARS + 1000


KB_GROUNDING_HEADER = (
    "Reference knowledge-base passages for this task. These are partial "
    "excerpts retrieved from policy and guidance sources by similarity to the "
    "retrieval queries listed below. They are REFERENCE MATERIAL, not the "
    "document under review, and may be incomplete, off-topic, or "
    "contradictory: read each one before relying on it and ignore the "
    "irrelevant ones. Each passage starts with its tag, e.g. [KB2], and the "
    "source it comes from."
)

class GroundingConfigError(ValueError):
    """The task's grounding block cannot be used as configured.

    The message is written for the workflow author reading it on the step's
    error banner, not for a developer reading a stack trace.
    """


@dataclass
class KnowledgeBaseTarget:
    """One knowledge base a task reads, with the queries it is searched with."""

    kb_uuid: str
    queries: list[str] = field(default_factory=list)


@dataclass
class GroundingConfig:
    targets: list[KnowledgeBaseTarget]
    k: int = DEFAULT_K
    max_passages: int = DEFAULT_MAX_PASSAGES
    # 0 means "use each knowledge base's tuned floor, if it has one".
    min_similarity: float = 0.0

    @property
    def knowledge_bases(self) -> list[str]:
        return [t.kb_uuid for t in self.targets]

    @property
    def queries(self) -> list[str]:
        """Every distinct query template across the targets, in author order."""
        seen: list[str] = []
        for t in self.targets:
            for q in t.queries:
                if q not in seen:
                    seen.append(q)
        return seen


@dataclass
class GroundingResult:
    text: str
    sources: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    passages: list[dict] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.passages


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # One query per line in the editor.
        parts = re.split(r"[\n]", value)
        return [p.strip() for p in parts if p and p.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _as_int(value, default: int, *, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def grounding_targets(raw) -> list[KnowledgeBaseTarget]:
    """The (knowledge base, queries) pairs a raw ``kb_grounding`` block names.

    Three shapes are read, newest first:

    * per-base entries — ``knowledge_bases: [{"kb_uuid": ..., "queries": [...]}]``,
      optionally with a top-level ``queries`` list that fills in for an entry
      that has none;
    * the flat form — ``knowledge_bases: [uuid, ...]`` plus one shared
      ``queries`` list, every base searched with every query;
    * the legacy single ``kb_uuid`` / ``query`` of a Knowledge Base Query step.

    Duplicate bases are merged. Returns ``[]`` for anything that names no base.
    """
    if not isinstance(raw, dict):
        return []
    shared = _as_str_list(raw.get("queries")) or _as_str_list(raw.get("query"))
    entries = raw.get("knowledge_bases")
    if isinstance(entries, str):
        entries = _as_str_list(entries)
    if not isinstance(entries, (list, tuple)):
        entries = _as_str_list(raw.get("kb_uuid"))

    targets: list[KnowledgeBaseTarget] = []
    by_uuid: dict[str, KnowledgeBaseTarget] = {}
    for entry in entries:
        if isinstance(entry, dict):
            uuid = str(entry.get("kb_uuid") or entry.get("uuid") or "").strip()
            queries = _as_str_list(entry.get("queries")) or _as_str_list(entry.get("query")) or list(shared)
        else:
            uuid = str(entry or "").strip()
            queries = list(shared)
        if not uuid:
            continue
        if uuid in by_uuid:
            for q in queries:
                if q not in by_uuid[uuid].queries:
                    by_uuid[uuid].queries.append(q)
            continue
        target = KnowledgeBaseTarget(kb_uuid=uuid, queries=queries)
        by_uuid[uuid] = target
        targets.append(target)
    return targets


def has_grounding(raw) -> bool:
    """Whether a task's data carries a grounding block naming at least one base."""
    return bool(grounding_targets(raw))


def parse_grounding_config(raw, *, what: str = "Knowledge base grounding") -> GroundingConfig:
    """Validate a task's ``kb_grounding`` block.

    Raises :class:`GroundingConfigError` naming what the author has to fix. A
    base with no queries of its own is let through here — the retriever
    reports it by title, which this function cannot see — but a block whose
    bases all lack queries is refused outright.
    """
    if not isinstance(raw, dict):
        raise GroundingConfigError(
            f"{what} is not configured: choose at least one knowledge base "
            "and give it a retrieval query."
        )
    targets = grounding_targets(raw)
    if not targets:
        raise GroundingConfigError(
            f"{what} is not configured: no knowledge base selected."
        )
    if len(targets) > MAX_KNOWLEDGE_BASES:
        raise GroundingConfigError(
            f"{what} lists {len(targets)} knowledge bases; the limit is {MAX_KNOWLEDGE_BASES}."
        )
    if not any(t.queries for t in targets):
        raise GroundingConfigError(
            f"{what} is not configured: the retrieval query is empty."
        )
    for t in targets:
        if len(t.queries) > MAX_QUERIES:
            raise GroundingConfigError(
                f"{what} lists {len(t.queries)} retrieval queries for one "
                f"knowledge base; the limit is {MAX_QUERIES}."
            )
    k = _as_int(raw.get("k"), DEFAULT_K, lo=1, hi=MAX_K)
    max_passages = _as_int(
        raw.get("max_passages"), DEFAULT_MAX_PASSAGES, lo=1, hi=MAX_MAX_PASSAGES,
    )
    min_similarity = _as_float(raw.get("min_similarity"), 0.0)
    if min_similarity < 0:
        min_similarity = 0.0
    return GroundingConfig(
        targets=targets, k=k, max_passages=max_passages, min_similarity=min_similarity,
    )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def render_queries(templates: list[str], inputs: dict) -> tuple[list[str], list[str]]:
    """Fill ``{{ ... }}`` placeholders from the step input.

    Returns ``(queries, warnings)``. A template that renders to nothing is
    dropped with a warning (its upstream value was empty — a fact about the
    data, not a configuration error); a placeholder that cannot resolve is a
    configuration error and raises.
    """
    from app.utils import templating

    rendered: list[str] = []
    warnings: list[str] = []
    for template in templates:
        try:
            query = templating.render(template, inputs or {}, json_encode=False)
        except templating.TemplateError as e:
            raise GroundingConfigError(str(e)) from e
        query = (query or "").strip() if isinstance(query, str) else str(query or "").strip()
        if not query:
            warnings.append(
                f"Retrieval query skipped: {template!r} rendered to an empty string."
            )
            continue
        rendered.append(query)
    return rendered, warnings


def _word_count(text: str) -> int:
    return len(text.split())


def condense_query(
    query: str,
    *,
    model: Optional[str],
    system_config_doc: Optional[dict],
    usage_acc=None,
) -> tuple[str, Optional[str]]:
    """Shorten an over-long rendered query into a retrieval prompt.

    Returns ``(query, warning)``. Uses the same search-prompt rewriter the KB
    optimizer offers; without a model (or when the rewrite fails) falls back
    to the first :data:`CONDENSE_WORD_LIMIT` words and says so, which still
    beats letting the embedder truncate silently.
    """
    if _word_count(query) <= CONDENSE_WORD_LIMIT:
        return query, None
    if model:
        try:
            from app.services.llm_service import PROMPT_AGENT_SYSTEM_PROMPT, create_chat_agent

            agent = create_chat_agent(
                model, system_prompt=PROMPT_AGENT_SYSTEM_PROMPT,
                system_config_doc=system_config_doc,
            )
            run = agent.run_sync(
                "Generate a search prompt for this user question: "
                f"{query[:6000]}"
            )
            if usage_acc is not None:
                usage_acc.record(run)
            condensed = (run.output or "").strip()
            if condensed and _word_count(condensed) <= CONDENSE_WORD_LIMIT * 2:
                return condensed, None
        except Exception as e:  # noqa: BLE001 — degrade, never fail the step here
            logger.warning("Grounding query condense failed; truncating: %s", e)
    words = query.split()
    truncated = " ".join(words[:CONDENSE_WORD_LIMIT])
    return truncated, (
        f"A retrieval query was {len(words)} words long and was cut to the first "
        f"{CONDENSE_WORD_LIMIT}; the knowledge base only embeds the start of a "
        "long query. Prefer short, topic-specific queries."
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _pinned_hits(dm, kb_uuid: str, query: str, *, skip: frozenset = frozenset()) -> list[dict]:
    """Chunks that literally contain a section number or identifier the query
    names (``§ 200.414``), the way chat pins them: exact matches only, so a
    query about 200.1 does not pin 200.10. A failed lookup pins nothing.

    ``skip`` are sections already handed over whole (:func:`_section_passages`);
    their remaining hits only cross-reference them, so they pin nothing."""
    from app.services.chat_service import _extract_pin_terms, retrieve_pinned_chunks_sync

    terms = [
        t for t in _extract_pin_terms(query)
        if not any(s == t or s.startswith(f"{t}-") for s in skip)
    ]
    if not terms:
        return []
    try:
        return retrieve_pinned_chunks_sync(dm, kb_uuid, terms, limit_per_ref=PIN_LIMIT_PER_TERM)
    except Exception as e:  # noqa: BLE001 — vector retrieval still runs
        logger.debug("Lexical pin lookup failed for %r: %s", query, e)
        return []


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
#
# A query that names a section ("200.405 allocable costs") wants the section.
# Its number is literally in two kinds of chunk: the ones that cross-reference
# it ("see § 200.405(c)") and the one holding its heading — and a source chunked
# before chunks followed sections was cut every 1,000 characters, so that
# heading often closes its chunk while the rule sits in the next one (a section
# chunked by its structure starts its own chunk, but a long one still runs on
# into the chunks after it). Pinning hits by how often they
# name the number handed the model cross-references and a bare heading, and the
# citation check rightly refused every citation to them.
#
# So a section the query names is found by its heading and handed over as one
# passage: from the heading line, through the chunks that follow (their
# repeated overlap removed), to the next heading or SECTION_MAX_CHARS. It is
# labelled by the section ("Subpart E—Cost Principles · § 200.405") and built
# the same way whichever task asks for it, so one source line always means one
# text across a run.

# A section number in a query: "200.405", "§ 200.403(h)", FAR's "31.205-6".
_QUERY_SECTION_RE = re.compile(r"(?<![\d.])(\d{1,4}\.\d{1,4}(?:-\d{1,3}(?!\d|\.\d))?)(?!\d|\.\d)")
# A heading line: "§ 200.405 Allocable costs.", "31.205-6 Compensation for
# personal services.", "## 9904.401 …", "§ 734.8 “Technology” or …", a
# Subpart or Part title. Titles open as the chunker's do.
_ANY_HEADING_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]+)?(?:"
    r"(?:§[ \t]*)?\d{1,4}\.\d{1,4}(?:-\d{1,3})?[a-z]?(?![\d(\-–—]|\.\d)[ \t]+" + SECTION_TITLE_START +
    r"|(?:Subpart|SUBPART|Part|PART)[ \t]+[\w.]+[ \t]*(?:[-—–:]|$)"
    r")[^\n]{0,200}$",
    re.MULTILINE,
)
# A short title line with no number and no closing punctuation, last in a
# section: eCFR's undesignated centre headings ("Procurement Standards").
_CENTER_HEADING_TAIL_RE = re.compile(r"\n[ \t]*[A-Z][^\d\n]{0,78}[^\d\s.;:,)\]]\s*$")
_CHUNK_ID_RE = re.compile(r"^(.*)_chunk_(\d+)$")


def section_terms(query: str) -> list[str]:
    """The section numbers a query names, in order, deduplicated."""
    return list(dict.fromkeys(m.group(1) for m in _QUERY_SECTION_RE.finditer(query or "")))


def _section_heading_re(section: str) -> re.Pattern:
    return re.compile(
        rf"^[ \t]*(?:#{{1,6}}[ \t]+)?(?:§[ \t]*)?{re.escape(section)}"
        rf"(?![\d(\-–—]|\.\d)[ \t]+{SECTION_TITLE_START}[^\n]{{0,200}}$",
        re.MULTILINE,
    )


def _join_chunk(text: str, nxt: str) -> str:
    """``text`` followed by the next chunk of its source, without the overlap
    the splitter repeats at the start of a chunk. Chunks are stripped at
    ingest, so the overlap is a suffix of one and a prefix of the next."""
    for n in range(min(len(text), len(nxt), 600), 11, -1):
        if text.endswith(nxt[:n]):
            return text + nxt[n:]
    # No overlap: the splitter broke at a blank line and started after it.
    return f"{text}\n\n{nxt}"


def _page_at(meta: dict, offset: int) -> Optional[int]:
    page = meta.get("page")
    if not isinstance(page, int) or isinstance(page, bool):
        return None
    for at, next_page in page_breaks_of(meta):
        if at > offset:
            break
        page = next_page
    return page


def _section_meta(pieces: list[tuple[int, dict]], start: int, end: int) -> dict:
    """Chunk-style metadata for the text ``[start, end)`` of chunks joined at
    the offsets in ``pieces`` — source, and for a paged source the page the
    section starts on, the page it ends on and the breaks between, so the
    page markers and the page range are those of the section itself."""
    first = pieces[0][1].get("metadata") or {}
    meta = {k: first[k] for k in ("source_id", "source_name", "chunk_index", "total_chunks") if k in first}

    def page(pos: int) -> Optional[int]:
        owner = next((p for p in reversed(pieces) if p[0] <= pos), pieces[0])
        return _page_at(owner[1].get("metadata") or {}, pos - owner[0])

    current = page(start)
    if current is None:
        return meta
    meta["page"] = current
    if any((p[1].get("metadata") or {}).get("page_approximate") for p in pieces):
        meta["page_approximate"] = True
    at: set[int] = set()
    for offset, chunk in pieces:
        at.add(offset)
        at.update(offset + o for o, _ in page_breaks_of(chunk.get("metadata") or {}))
    breaks: list[list[int]] = []
    for pos in sorted(p for p in at if start < p < end):
        here = page(pos)
        if here is not None and here != current:
            breaks.append([pos - start, here])
            current = here
    if breaks:
        meta["page_end"] = breaks[-1][1]
        meta["page_breaks"] = json.dumps(breaks)
    return meta


def _build_section(dm, kb_uuid: str, section: str, chunk: dict, heading: re.Match) -> Optional[dict]:
    """The passage for ``section``, whose heading ``chunk`` holds at
    ``heading``: the heading line through the text before the next heading,
    reading on into the chunks that follow. None for a heading with no body
    (a table of contents)."""
    combined = chunk.get("content") or ""
    pieces: list[tuple[int, dict]] = [(0, chunk)]
    start = heading.start()
    body_from = heading.end()

    def section_end() -> Optional[int]:
        m = _ANY_HEADING_RE.search(combined, body_from)
        return m.start() if m else None

    end = section_end()
    m = _CHUNK_ID_RE.match(str(chunk.get("chunk_id") or ""))
    if end is None and len(combined) - start < SECTION_MAX_CHARS and m and hasattr(dm, "get_kb_chunks_by_ids"):
        prefix, n = m.group(1), int(m.group(2))
        wanted = [f"{prefix}_chunk_{n + i}" for i in range(1, SECTION_FOLLOW_CHUNKS + 1)]
        try:
            following = dm.get_kb_chunks_by_ids(kb_uuid, wanted)
        except Exception as e:  # noqa: BLE001 — the section is cut short, not lost
            logger.debug("Section continuation read failed for %s: %s", section, e)
            following = []
        for expected, nxt in zip(wanted, following):
            if nxt.get("chunk_id") != expected:
                break   # the source ends (or has a gap) here
            text = nxt.get("content") or ""
            combined = _join_chunk(combined, text)
            pieces.append((len(combined) - len(text), nxt))
            end = section_end()
            if end is not None or len(combined) - start >= SECTION_MAX_CHARS:
                break
    if end is None or end - start > SECTION_MAX_CHARS:
        end = min(len(combined), start + SECTION_MAX_CHARS)
        if end < len(combined):
            cut = combined.rfind("\n", start + SECTION_MAX_CHARS // 2, end)
            if cut < 0:
                cut = combined.rfind(" ", start + SECTION_MAX_CHARS // 2, end)
            end = cut if cut > 0 else end
        content = combined[start:end].rstrip()
    else:
        content = combined[start:end].rstrip()
        # The regulation's unnumbered group heading ("Property Standards")
        # stands just before the next section, not at the end of this one.
        while (tail := _CENTER_HEADING_TAIL_RE.search(content)) and tail.start() > heading.end() - start:
            content = content[:tail.start()].rstrip()
    end = start + len(content)
    if len(combined[body_from:end].strip()) < SECTION_MIN_BODY_CHARS:
        return None

    covers = {
        str(c.get("chunk_id")) for offset, c in pieces
        if c.get("chunk_id") is not None
        and start <= offset and offset + len(c.get("content") or "") <= end
    }
    base = str(m.group(1)) if m else str(chunk.get("chunk_id") or "")
    return {
        "content": content,
        "metadata": _section_meta(pieces, start, end),
        "chunk_id": f"{base}_section_{section}",
        "score": chunk.get("score"),
        "similarity": chunk.get("similarity"),
        "_section": section,
        # Chunks whose whole text the passage holds: never shown beside it.
        "_covers": covers,
    }


def _section_passages(dm, kb_uuid: str, query: str) -> list[dict]:
    """One passage per section the query names (per source holding it). Each
    carries in ``_replaces`` the chunks it stands in for in this query's pool:
    every chunk holding its heading, and every chunk wholly inside it. A
    section whose heading is not found is left to the pins and the vector
    search."""
    out: list[dict] = []
    for section in section_terms(query):
        try:
            candidates = dm.get_kb_chunks_containing(kb_uuid, section, SECTION_FETCH_POOL)
        except Exception as e:  # noqa: BLE001 — pins and vector search still run
            logger.debug("Section lookup failed for %s: %s", section, e)
            continue
        heading_re = _section_heading_re(section)
        by_source: dict[str, list[tuple[int, dict, re.Match]]] = {}
        for c in candidates:
            m = _CHUNK_ID_RE.match(str(c.get("chunk_id") or ""))
            source = m.group(1) if m else str(c.get("chunk_id"))
            # A contents list names the heading too, often in the same chunk
            # as the section itself: every occurrence is a candidate.
            for heading in heading_re.finditer(c.get("content") or ""):
                by_source.setdefault(source, []).append((int(m.group(2)) if m else 0, c, heading))
        for holders in by_source.values():
            holders.sort(key=lambda h: (h[0], h[2].start()))
            for _, chunk, heading in holders:
                built = _build_section(dm, kb_uuid, section, chunk, heading)
                if built is None:
                    continue
                replaces = {str(h[1].get("chunk_id")) for h in holders} | built["_covers"]
                # A corpus holding the regulation whole and by subpart has
                # the section twice: one passage stands in for both.
                twin = next((p for p in out if _content_key(p["content"]) == _content_key(built["content"])), None)
                if twin is not None:
                    twin["_replaces"] |= replaces
                    twin["_covers"] |= built["_covers"]
                else:
                    built["_replaces"] = replaces
                    out.append(built)
                break
    return out


def _diverse(results: list[dict], k: int) -> list[dict]:
    """Relevance order, no source taking more than half the slots."""
    from app.services.chat_service import _select_diverse_chunks

    return _select_diverse_chunks(results, k, max(2, -(-k // 2)))


def _round_robin(pools: list[list[dict]]) -> list[dict]:
    """Interleave pools so each contributes before any contributes twice."""
    import itertools

    merged: list[dict] = []
    seen: set = set()
    for tier in itertools.zip_longest(*pools):
        for r in tier:
            if r is None:
                continue
            cid = r.get("chunk_id")
            if cid is not None and cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            merged.append(r)
    return merged


def _content_key(content: str) -> str:
    normalized = re.sub(r"\s+", " ", (content or "").lower()).strip()[:300]
    return hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()


def dedupe_passages(passages: list[dict]) -> list[dict]:
    """Drop repeats by chunk id and by (normalized) content.

    Content dedupe is what collapses a corpus that ingested a whole regulation
    *and* each of its subparts: identical paragraphs, different chunk ids.
    """
    out: list[dict] = []
    seen_ids: set = set()
    seen_content: set = set()
    for r in passages:
        cid = r.get("chunk_id")
        if cid is not None and cid in seen_ids:
            continue
        ckey = _content_key(r.get("content") or "")
        if ckey in seen_content:
            continue
        if cid is not None:
            seen_ids.add(cid)
        seen_content.add(ckey)
        out.append(r)
    return out


def _precise_pool(dm, kb_uuid: str, query: str, *, k: int, floor: float) -> Optional[list[dict]]:
    """One (knowledge base, query) pool through precise retrieval (see
    :mod:`app.services.kb_retrieval`), or None when it cannot run here — the
    store cannot list the base, the reranker is unavailable, or it is turned
    off — so the caller keeps the vector ranking.

    The lanes, in the order their passages are handed over:

    1. Each section the query names by number, from its heading (as before);
       a plain query whose words match one section's title unambiguously is
       routed to that section the same way.
    2. Literal identifiers that are not sections of this base (``NSF-24-117``).
    3. A named or routed section's best chunks by the query's words: past the
       cap of a long section's passage (§ 200.308(g) on one-time extensions),
       or the section itself where the heading lane cannot build it (a policy
       page headed "45.13 - Program Income").
    4. Hybrid candidates reranked by the cross-encoder, kept only above the
       relevance cut — so a query the base cannot answer hands over nothing.
    """
    from app.services import kb_retrieval as kr

    index = kr.index_for(dm, kb_uuid)
    if index is None or not kr.ready():
        return None
    cache_key = (kb_uuid, index.revision, index.count, index.built_at, query, k, floor)
    hit = kr.cached(cache_key)
    if hit is not None:
        return hit

    expanded = kr.expand(index, query)
    half = max(1, -(-k // 2))
    named = section_terms(query)
    routed = kr.route(index, query) if not named else None

    section_query = f"{routed.key} {query}" if routed and routed.numbered and not routed.term else query
    sections = _section_passages(dm, kb_uuid, section_query)[:half]
    built = {s["_section"] for s in sections}
    pinned = _pinned_hits(dm, kb_uuid, query, skip=frozenset(built | set(index.section_titles)))

    final: list[dict] = []
    seen: set = set().union(*(s["_replaces"] for s in sections)) if sections else set()
    for r in sections + pinned:
        if len(final) >= half:
            break
        cid = r.get("chunk_id")
        if cid is not None and cid in seen:
            continue
        if cid is not None:
            seen.add(cid)
        final.append(r)

    scoped: list[tuple[str, Optional[str], bool]] = [(s, None, True) for s in named if s in index.section_titles]
    if routed and (routed.term or routed.key not in built):
        scoped.append((routed.key, routed.term, False))
    anchor = next(iter(built), None) or (scoped[0][0] if scoped else None)
    for key, term, asked in scoped:
        lane = [c for c in kr.candidates(dm, index, kb_uuid, expanded, floor=0.0, within=key, containing=term)
                if c.get("chunk_id") not in seen]
        scored = kr.rerank(index, expanded, lane)
        # A section the author named is theirs to have: its best chunk (or
        # two, when no passage stands for it). A routed one is inferred, so
        # its chunks must also clear the cut.
        take = scored[: (1 if key in built else kr.ROUTED_CHUNKS)] if asked else \
            kr.keep(scored, anchor_section=key, index=index)[: kr.ROUTED_CHUNKS]
        for r in take:
            seen.add(r.get("chunk_id"))
            final.append(r)

    general = [c for c in kr.candidates(dm, index, kb_uuid, expanded, floor=floor) if c.get("chunk_id") not in seen]
    for r in kr.keep(kr.rerank(index, expanded, general), anchor_section=anchor, index=index):
        if len(final) >= k:
            break
        if r.get("chunk_id") in seen:
            continue
        seen.add(r.get("chunk_id"))
        final.append(r)
    pool = attach_lead_ins(dm, kb_uuid, final[:k])
    kr.remember(cache_key, pool)
    return pool


def paraphrase_pool(dm, kb_uuid: str, query: str, phrases: list[str], *, k: int,
                    floor: float, min_score: Optional[float] = None) -> Optional[list[dict]]:
    """The passages a question that kept nothing finds through paraphrases of
    it in the base's own words (:mod:`app.services.kb_paraphrase`), or None
    when precise retrieval cannot run here.

    Each paraphrase is searched like the general lane of :func:`_precise_pool`
    and its passages are scored against the paraphrase, so they must clear
    the paraphrase cut (``min_score``, by default ``PARAPHRASE_MIN_SCORE``),
    not the question's; a short query in the base's words ranks what it
    finds near the top, so only its first ``RESCUE_RERANK_POOL`` candidates
    are scored. A passage several paraphrases find keeps its best score; the
    best ``k`` are handed over."""
    from app.services import kb_retrieval as kr

    index = kr.index_for(dm, kb_uuid)
    if index is None or not kr.ready():
        return None
    cut = kr.PARAPHRASE_MIN_SCORE if min_score is None else min_score
    cache_key = (kb_uuid, index.revision, index.count, index.built_at, ("paraphrase", query, tuple(phrases), cut),
                 k, floor)
    hit = kr.cached(cache_key)
    if hit is not None:
        return hit
    found: dict[str, dict] = {}
    for phrase in phrases:
        expanded = kr.expand(index, phrase)
        lane = kr.candidates(dm, index, kb_uuid, expanded, floor=floor)[: kr.RESCUE_RERANK_POOL]
        scored = kr.rerank(index, expanded, lane)
        for r in kr.keep(scored, anchor_section=None, index=index, min_score=cut):
            cid = str(r.get("chunk_id"))
            if cid not in found or r["rerank_score"] > found[cid]["rerank_score"]:
                found[cid] = r
    best = sorted(found.values(), key=lambda r: -r["rerank_score"])[:k]
    pool = attach_lead_ins(dm, kb_uuid, best)
    kr.remember(cache_key, pool)
    return pool


def with_neighbours(dm, kb_uuid: str, query: str, pool: list[dict], *, k: int) -> list[dict]:
    """``pool`` followed by the chunks either side of its passages — same
    source, same section, not already handed over — that the cross-encoder
    scores at least ``NEIGHBOUR_MIN_SCORE`` against ``query``, best first,
    up to ``k`` passages in all.

    A rule is often cut across chunks: the answer's last clause, the
    exception after it or the list it introduces sits in the next chunk,
    which scores below the relevance cut on its own. Its section has already
    cleared that cut, so its neighbours are held to a lower one."""
    from app.services import kb_retrieval as kr

    if not pool or len(pool) >= k:
        return pool
    index = kr.index_for(dm, kb_uuid)
    if index is None or not kr.ready():
        return pool
    held: set[int] = set()
    for r in pool:
        for cid in (str(r.get("chunk_id")), *(r.get("_covers") or ())):
            if cid in index.position:
                held.add(index.position[cid])

    def source(i: int):
        return (index.chunks[i].get("metadata") or {}).get("source_id")

    near: list[int] = []
    for r in pool:
        i = index.position.get(str(r.get("chunk_id")))
        if i is None:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(index.chunks) and j not in held and j not in near \
                    and index.keys[j] == index.keys[i] and source(j) == source(i) and j not in index.excluded:
                near.append(j)
    if not near:
        return pool
    scored = kr.rerank(index, kr.expand(index, query), [kr._chunk_result(index, j) for j in near])
    added = [r for r in scored if r["rerank_score"] >= kr.NEIGHBOUR_MIN_SCORE][: k - len(pool)]
    return pool + attach_lead_ins(dm, kb_uuid, added) if added else pool


def precise_cut(dm, kb_uuid: str, query: str, results: list[dict]) -> Optional[list[dict]]:
    """Chunks another lane found — a source the message names, a passage
    that amends one retrieved — scored by the cross-encoder against
    ``query`` and kept only above the relevance cut precise retrieval
    applies to its own, best first; None when precise retrieval cannot run
    here. A vector hit is the nearest text, relevant or not."""
    from app.services import kb_retrieval as kr

    if not results:
        return []
    index = kr.index_for(dm, kb_uuid)
    if index is None or not kr.ready():
        return None
    scored = kr.rerank(index, kr.expand(index, query), results)
    return [r for r in scored if r["rerank_score"] >= kr.MIN_SCORE]


def _retrieve_pool(
    dm, kb_uuid: str, query: str, *, k: int, floor: float,
) -> list[dict]:
    """One (knowledge base, query) pool: precise retrieval when it can run
    (:func:`_precise_pool`); otherwise the sections the query names, then
    pinned lexical hits, then the over-fetched vector search, diversified and
    cut to ``k``."""
    precise = _precise_pool(dm, kb_uuid, query, k=k, floor=floor)
    if precise is not None:
        return precise
    vector = dm.query_kb(kb_uuid, query, k * OVERFETCH_MULTIPLIER, floor)
    if floor > 0:
        # Belt and braces: the store applies the floor too, but a fake or an
        # older store that ignores it must not leak junk past the gate.
        vector = [
            r for r in vector
            if not isinstance(r.get("similarity"), (int, float)) or r["similarity"] >= floor
        ]

    half = max(1, -(-k // 2))
    sections = _section_passages(dm, kb_uuid, query)[:half]
    pinned = _pinned_hits(dm, kb_uuid, query, skip=frozenset(s["_section"] for s in sections))

    final: list[dict] = []
    # A section passage stands in for the chunks it was built from.
    seen: set = set().union(*(s["_replaces"] for s in sections)) if sections else set()
    for r in sections + pinned:
        if len(final) >= half:
            break
        cid = r.get("chunk_id")
        if cid is not None and cid in seen:
            continue
        if cid is not None:
            seen.add(cid)
        final.append(r)
    remaining = [r for r in vector if r.get("chunk_id") is None or r.get("chunk_id") not in seen]
    final.extend(_diverse(remaining, k - len(final)))
    return attach_lead_ins(dm, kb_uuid, final[:k])


def merge_pools(per_kb: list[list[list[dict]]], max_passages: int) -> list[dict]:
    """``per_kb[i][j]`` is knowledge base *i*'s pool for its query *j*.

    Round-robin within a base across its queries, then across bases, dedupe,
    and cut to the cap — so every base and every query is represented before
    any of them contributes a second passage. A chunk another query retrieved
    whose whole text a section passage holds is dropped as a repeat.
    """
    per_kb_merged = [_round_robin(pools) for pools in per_kb if pools]
    merged = _round_robin(per_kb_merged) if len(per_kb_merged) > 1 else (per_kb_merged[0] if per_kb_merged else [])
    covered: set = set().union(*(r.get("_covers") or () for r in merged)) if merged else set()
    merged = [r for r in merged if r.get("chunk_id") is None or r.get("chunk_id") not in covered]
    return dedupe_passages(merged)[:max_passages]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _citation_safe(label: str) -> str:
    label = label.replace("[", "(").replace("]", ")").replace(";", ",")
    label = label.replace('"', "'").replace("\\", "/")
    return re.sub(r"\s+", " ", label).strip()


_SECTION_NUMBER_RE = re.compile(r"\d{1,4}\.\d{1,4}(?:-\d{1,3})?[a-z]?")


def _chunk_locator(meta: dict, source_name: str, chunk_id) -> Optional[str]:
    """Where a pageless chunk sits: "§ 200.307 · part 2" — the second chunk
    of § 200.307 — or "§ 200.423" for a section held in one chunk, from the
    section a structure-aware chunk records; "part N" (its position in the
    source) for a chunk with no section, one whose source is named after
    its section ("APM 45.13 …"), or one chunked before sections were
    recorded."""
    key = meta.get("section_key")
    if (isinstance(key, str) and key and not key.startswith(("source:", "group:"))
            and not re.search(rf"(?<![\w.]){re.escape(key)}(?!\w)", source_name)):
        locator = f"§ {key}" if _SECTION_NUMBER_RE.fullmatch(key) else key
        part, parts = meta.get("section_part"), meta.get("section_parts")
        if isinstance(part, int) and isinstance(parts, int) and parts > 1:
            locator += f" · part {part}"
        return locator
    m = re.search(r"_chunk_(\d+)$", str(chunk_id or ""))
    return f"part {int(m.group(1)) + 1}" if m else None


def _passage_label(r: dict, *, kb_title: Optional[str], query: str) -> tuple[str, dict]:
    meta = r.get("metadata") or {}
    content = r.get("content") or ""
    source_name = meta.get("source_name", "Unknown source")
    sheet = meta.get("sheet")
    section = r.get("_section")
    if section:
        # A section passage is named by its section, and its pages are the
        # whole section's — not narrowed to the query, so it reads the same
        # in every task that retrieves it.
        page, page_end = meta.get("page"), meta.get("page_end")
        approximate = bool(meta.get("page_approximate"))
        locator = f"§ {section}"
    else:
        cited = cited_pages(meta, content, query)
        page, page_end, approximate = cited["page"], cited["page_end"], cited["page_approximate"]
        locator = format_page_range(page, page_end, approximate) if page is not None else locator_for_meta(meta)
    if not locator:
        # A web page or eCFR subpart has no pages, so every passage from it
        # would share one source line and a citation could not say which it
        # means. Where it sits tells them apart, the same in every task that
        # retrieves it: its section and part of it, or its position.
        locator = _chunk_locator(meta, source_name, r.get("chunk_id"))
    label = f"{source_name} · {locator}" if locator else source_name
    if kb_title:
        label = f"{kb_title} — {label}"
    # A source line rides inside brackets and JSON strings, and ";" separates
    # citations in one bracket: keep it free of all of them.
    label = _citation_safe(label)
    source = {
        "document_id": meta.get("source_id"),
        "document_title": source_name,
        "page": page,
        "page_end": page_end,
        "page_approximate": approximate,
        "sheet": sheet if isinstance(sheet, str) else None,
        "chunk_id": r.get("chunk_id"),
        "score": r.get("score"),
        "similarity": r.get("similarity"),
        "content_preview": content[:240],
        # The exact source line the model was told to copy when it cites this
        # passage, and the passage itself: the run UI turns a citation in the
        # output into an inline chip and shows the passage on click, so a
        # reader can check the claim against the text it rests on without
        # opening the knowledge base. Chunks are ~1,000 characters; the cap
        # only guards against an oversized ingest.
        "label": label,
        "content": content[:CITATION_CONTENT_CHARS],
        # The sentence that says what a list is, for a passage that holds
        # only items of it (see kb_lead_in): shown above the passage.
        "lead_in": r.get("lead_in"),
        "kb_uuid": r.get("kb_uuid"),
        "kb_title": r.get("kb_title"),
    }
    return label, source


def render_passages(
    passages: list[dict],
    *,
    queries: list[str],
    header: str = KB_GROUNDING_HEADER,
    label_kb: bool = True,
    show_queries: bool = True,
    queries_note: Optional[str] = None,
    tagged: bool = True,
) -> tuple[str, list[dict]]:
    """The framed text block and its citation list.

    ``tagged`` heads each passage with a tag the model cites ([KB2], resolved
    by :func:`resolve_passage_tags`, so it only suits a task that cites in its
    own reply); otherwise each passage sits under its source line in brackets,
    for text that flows into a later step as it is (a Knowledge Base Query
    step). ``label_kb`` prefixes each source line with the knowledge base it
    came from; a single-base lookup reads as it always has without it. Each
    passage is cited against the query that retrieved it (``_query``),
    falling back to the first query. How to cite an estimated (``p. ~N``)
    page is an instruction, so the engine adds it to the task's instruction
    rather than to this block, which the model reads as data.
    """
    parts: list[str] = []
    sources: list[dict] = []
    fallback_query = queries[0] if queries else ""
    for i, r in enumerate(passages, 1):
        query = r.get("_query") or fallback_query
        label, source = _passage_label(
            r, kb_title=(r.get("kb_title") if label_kb else None), query=query,
        )
        heading = f"[KB{i}] {label}" if tagged else f"[{label}]"
        body = annotate_chunk_pages(r.get("content") or "", r.get("metadata") or {})
        parts.append(f"{heading}\n{with_lead_in(body, r.get('lead_in'))}")
        sources.append(source)
    if not parts:
        return "", []
    lines = [header]
    if show_queries and (queries_note or queries):
        lines.append(queries_note or ("Retrieval queries: " + "; ".join(f"{q!r}" for q in queries)))
    text = "\n\n".join(lines) + "\n\n" + "\n\n---\n\n".join(parts)
    return text, sources


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

def grounding_token_budget(
    model: Optional[str], system_config_doc: Optional[dict], *texts: str,
) -> Optional[int]:
    """Input tokens left for passages once ``texts`` (the instruction and the
    task's other context) are in the prompt. ``None`` when the model is not
    known, which means "do not trim"."""
    if not model:
        return None
    try:
        from app.services.context_budget import count_tokens, input_budget_for
        from app.services.llm_service import _get_model_config_sync

        model_config = _get_model_config_sync(model, system_config_doc)
        budget = input_budget_for(model, model_config)
        used = PROMPT_SCAFFOLD_TOKENS + sum(
            count_tokens(t, model, model_config) for t in texts if t
        )
        return max(0, budget - used)
    except Exception as e:  # noqa: BLE001
        logger.debug("Grounding budget estimate unavailable for %s: %s", model, e)
        return None


def trim_to_budget(
    passages: list[dict], token_budget: Optional[int], *,
    model: Optional[str], system_config_doc: Optional[dict],
) -> tuple[list[dict], Optional[str]]:
    """Keep passages, in rank order, while they fit the budget."""
    if token_budget is None or not passages:
        return passages, None
    try:
        from app.services.context_budget import count_tokens
        from app.services.llm_service import _get_model_config_sync

        model_config = _get_model_config_sync(model, system_config_doc) if model else None
        kept: list[dict] = []
        used = 0
        for r in passages:
            cost = count_tokens((r.get("content") or "") + "\n[0] label\n", model or "", model_config) + 8
            if used + cost > token_budget:
                break
            kept.append(r)
            used += cost
    except Exception as e:  # noqa: BLE001
        logger.debug("Grounding budget trim skipped: %s", e)
        return passages, None
    if len(kept) == len(passages):
        return passages, None
    dropped = len(passages) - len(kept)
    if not kept:
        return [], (
            "Knowledge-base passages were left out: the task's other input "
            "already fills the model's context window. Use a model with a "
            "larger window, or point this task at less input."
        )
    return kept, (
        f"{dropped} lower-ranked knowledge-base passage{'s were' if dropped != 1 else ' was'} "
        "left out to fit the model's context window."
    )


# ---------------------------------------------------------------------------
# Citations in output
# ---------------------------------------------------------------------------

def merge_sources(*groups) -> list[dict]:
    """Concatenate citation lists, keeping the first copy of each passage.

    A step that keeps its input's citations carries that input's passages
    forward, and the run aggregates every step's list — so the same chunk
    would otherwise appear once per step that mentioned it, and the numbered
    chips would count it several times.
    """
    out: list[dict] = []
    seen: dict = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for s in group:
            if not isinstance(s, dict):
                continue
            key = s.get("chunk_id") or (
                s.get("document_id"), s.get("page"), (s.get("content_preview") or "")[:80],
            )
            if key in seen:
                # The same passage verified for another statement elsewhere in
                # the run: keep every verified quote, so the popover can show
                # the exact place each claim rests on.
                extra = [q for q in (s.get("quotes") or []) if q not in (out[seen[key]].get("quotes") or [])]
                if extra:
                    kept = dict(out[seen[key]])
                    kept["quotes"] = list(kept.get("quotes") or []) + extra
                    out[seen[key]] = kept
                continue
            seen[key] = len(out)
            out.append(s)
    return out


def match_source_index(citation: str, sources: list[dict]) -> Optional[int]:
    """The index of the passage a bracketed citation names, or None — the
    same loose match the run UI uses to place a chip: the source line as
    shown, else the document named with the page or part the passage is."""
    n = _norm_citation(citation)
    if len(n) < 3:
        return None
    for i, s in enumerate(sources):
        if isinstance(s, dict) and s.get("label") and _norm_citation(str(s["label"])) == n:
            return i
    page = re.search(r"\bp\. (\d+)", n)
    # "part 12", "§ 200.405" or "§ 200.405 · part 2" ends a pageless source
    # line; only the passage that is that part or that section answers to it.
    tail = _locator(n)
    title_only = _strip_locator(n)
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            continue
        title = _norm_citation(str(s.get("document_title") or ""))
        if len(title) < 4 or not (title in n or (len(title_only) >= 4 and title_only in title)):
            continue
        if page and s.get("page") is not None:
            lo, hi = s["page"], s.get("page_end") or s["page"]
            if not lo <= int(page.group(1)) <= hi:
                continue
        elif page:
            continue
        if tail and _locator(_norm_citation(str(s.get("label") or ""))) != tail:
            continue
        return i
    return None


# A section number as _norm_citation leaves it ("31.205-6" → "31.205 - 6").
_NORM_SECTION = r"\d{1,4}\.\d{1,4}(?: - \d{1,3})?[a-z]?"
# Where a pageless passage sits, at the end of a normalized source line: its
# section ("§ 200.405", "appendix iii"), part of a section ("§ 200.405 ·
# part 2"), or position in the source ("part 12").
_LOCATOR = r"(?:(?:§ ?" + _NORM_SECTION + r"|(?<=· )appendix [ivxlc]+)(?: · part \d+)?|\bpart \d+)"
_LOCATOR_RE = re.compile(_LOCATOR + r"\s*$")


def _locator(normalized: str) -> Optional[str]:
    m = _LOCATOR_RE.search(normalized)
    return re.sub(r"§\s*", "§ ", m.group(0).strip()) if m else None


def _strip_locator(normalized: str) -> str:
    """A normalized source line without its trailing page, part or section."""
    return re.sub(r"\s*·?\s*(?:p\. \d+(\s*-\s*\d+)?|" + _LOCATOR + r")\s*$", "", normalized).strip()


_CITATION_RE = re.compile(r"\[([^\[\]\n]{3,300})\]")
_PAGE_RE = re.compile(r"\bp\.\s*~?\s*\d")
_PAGE_WORD_RE = re.compile(r"\bpage\s+\d")


def _norm_citation(text: str) -> str:
    """Loose form of a citation for comparison; mirrors the run UI's matcher.
    Chat's "Source: " prefix is not part of the label."""
    t = re.sub(r"^\s*source\s*:\s*", "", text or "", flags=re.IGNORECASE).lower()
    t = re.sub(r"[‐‑‒–—―]", "-", t)
    t = re.sub(r"\s*--+\s*", " - ", t)
    t = re.sub(r"[·•|,]", "·", t)
    t = re.sub(r"\bpages?\s+", "p. ", t)
    t = re.sub(r"\bpp?\.\s*~?\s*", "p. ", t)
    t = re.sub(r"\s*·\s*", " · ", t)
    t = re.sub(r"\s*-\s*", " - ", t)
    t = re.sub(r"[\"'“”]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def looks_like_citation(text: str) -> bool:
    """Whether a bracketed string is shaped like a source line, as opposed to
    ordinary bracketed prose such as [N/A] or [see above]. A passage tag left
    unresolved ([KB9] past the last passage) counts, so it is reported."""
    t = text or ""
    return ("·" in t or "—" in t or " -- " in t
            or bool(_PAGE_RE.search(t)) or bool(_PAGE_WORD_RE.search(t))
            or bool(_TAG_ONLY_RE.fullmatch(t.strip())))


# A passage tag as the model cites it: [KB2], [KB1, KB3], [KB1; 3], and the
# (KB2) a model sometimes writes instead.
_PASSAGE_TAG_RE = re.compile(
    r"[\[(【]\s*(?:†\s*)?KB\s*[-‐‑‒–—]?\s*(\d{1,3})((?:\s*[,;†]\s*(?:KB\s*[-‐‑‒–—]?\s*)?\d{1,3})*)[^\])】\n]{0,40}?[\])】]",
    re.IGNORECASE,
)
_TAG_ONLY_RE = re.compile(r"KB\s*[-‐‑‒–—]?\s*\d{1,3}", re.IGNORECASE)
_EMPTY_NATIVE_CITE_RE = re.compile(r"\s*【[\s†]*】")


def resolve_passage_tags(text: str, sources: list[dict]) -> str:
    """Replace every passage tag in ``text`` with that passage's source line.

    ``sources`` is the task's passage list in the order the tags number it
    ([KB1] is ``sources[0]``). Run right after the model replies, so the
    output, every later step that reads it, and the run UI see the exact
    source line rather than a number that means a different passage in each
    task. A tag that names no passage — past the last one, or in a task
    with none — is removed: tags exist only between the engine and the
    model, and an unresolved one is an invented citation.
    """
    if not text or not isinstance(text, str):
        return text
    # Some models (gpt-oss) emit their own 【…】 citation marks, often empty
    # when there was nothing to cite: an empty one is dropped, a 【KB2】 is
    # resolved below like [KB2].
    text = _EMPTY_NATIVE_CITE_RE.sub("", text)
    sources = sources or []

    def sub(m: re.Match) -> str:
        nums = [int(m.group(1))] + [int(n) for n in re.findall(r"\d{1,3}", m.group(2) or "")]
        labels: list[str] = []
        for n in nums:
            label = sources[n - 1].get("label") if 1 <= n <= len(sources) else None
            if label and label not in labels:
                labels.append(label)
        # "\0" marks a removed tag, so the space before it goes too.
        return "".join(f"[{label}]" for label in labels) or "\0"

    return re.sub(r"[ \t]*\0", "", _PASSAGE_TAG_RE.sub(sub, text))


def cites_any(text: str, sources: list[dict], *, sections: bool = True) -> bool:
    """Whether ``text`` carries at least one citation that resolves to a
    retrieved passage: a bracketed source line, or (with ``sections``) a
    regulation section number a passage literally contains (what the run UI
    links). The retry asks for ``sections=False``: a task whose output
    template fixes a section anchor ("regulation_anchor": "2 CFR 200.404")
    names it whether or not it used a passage."""
    if not text or not sources:
        return False
    for m in _CITATION_RE.finditer(text):
        for part in re.split(r"\s*;\s*", m.group(1)):
            if looks_like_citation(part) and not unmatched_citations(f"[{part}]", sources):
                return True
    if not sections:
        return False
    contents = [str(s.get("content") or "") for s in sources if isinstance(s, dict)]
    for m in _SECTION_REF_RE.finditer(text):
        sec = re.escape(m.group(1))
        # Bare, "52.5" may be a figure: only a passage that writes "§ 52.5"
        # makes it a section. The run UI applies the same rule.
        marker = r"§\s*" if m.group(0).startswith(m.group(1)) else r"(?:§\s*|\b)"
        if any(re.search(rf"{marker}{sec}(?!\d)", c) for c in contents):
            return True
    return False


# A section named in text: "§ 200.407", "2 CFR 200.403(h)", or a bare
# "200.407". Mirrors the run UI's SECTION_RE (CitedMarkdown.tsx).
_SECTION_REF_RE = re.compile(
    r"(?:§\s*|\b\d{1,2}\s*CFR\s*(?:part\s*)?)?\b(\d{2,4}\.\d{1,4})\b", re.IGNORECASE,
)


def unmatched_citations(text: str, sources: list[dict]) -> list[str]:
    """Citation-shaped brackets in ``text`` that name no retrieved passage.

    The run UI links a citation to a passage by the same loose match; what
    it cannot link it leaves as plain text. Reporting those here on the step
    is what stops an invented source from passing as a verified one.
    """
    if not text or not sources:
        return []
    labels: set[str] = set()
    titles: list[str] = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        if s.get("label"):
            labels.add(_norm_citation(str(s["label"])))
        title = _norm_citation(str(s.get("document_title") or ""))
        if len(title) >= 4:
            titles.append(title)
    bad: list[str] = []
    for m in _CITATION_RE.finditer(text):
        for part in re.split(r"\s*;\s*", m.group(1)):
            part = part.strip()
            if not part or not looks_like_citation(part):
                continue
            n = _norm_citation(part)
            if n in labels:
                continue
            title_only = _strip_locator(n)
            if any(t in n or (len(title_only) >= 4 and title_only in t) for t in titles):
                continue
            if part not in bad:
                bad.append(part)
    return bad


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def retrieve_grounding(
    cfg: GroundingConfig,
    inputs: dict,
    *,
    kb_meta: Optional[dict] = None,
    model: Optional[str] = None,
    system_config_doc: Optional[dict] = None,
    usage_acc=None,
    token_budget: Optional[int] = None,
    dm=None,
    header: str = KB_GROUNDING_HEADER,
    label_kb: Optional[bool] = None,
    show_queries: bool = True,
    tagged: bool = True,
    progress: Optional[Callable[[str], None]] = None,
) -> GroundingResult:
    """Run the grounding pipeline for one task.

    Each target base is searched with its own queries. ``kb_meta`` maps a
    base's uuid to ``{"title", "rag_config_override", "exists"}`` as
    pre-resolved by the task loader. When it is supplied and a configured base
    is missing from it, that base no longer exists — a configuration error
    that fails the step, like a Knowledge Base Query step with no base
    selected. Without ``kb_meta`` (unit tests, a caller that did not
    pre-load it) bases are queried as given.

    Retrieval failures raise; the caller turns them into a step error so the
    failure text never flows downstream as if it were retrieved content.
    """
    kb_meta = kb_meta or {}

    def title_of(uuid: str) -> str:
        return (kb_meta.get(uuid) or {}).get("title") or uuid

    if kb_meta:
        missing = [u for u in cfg.knowledge_bases if u not in kb_meta or not kb_meta[u].get("exists", True)]
        if missing:
            raise GroundingConfigError(
                f"Knowledge base not found: {', '.join(title_of(u) for u in missing)}. "
                "It may have been deleted — pick another knowledge base for this step."
            )
    unqueried = [t for t in cfg.targets if not t.queries]
    if unqueried:
        names = ", ".join(title_of(t.kb_uuid) for t in unqueried)
        raise GroundingConfigError(
            f"Knowledge base grounding is not configured: no retrieval query "
            f"for {names}. Give every selected knowledge base at least one query."
        )

    warnings: list[str] = []
    # (target, rendered queries) — a base whose every query rendered empty is
    # skipped with a warning; the run continues on the others.
    prepared: list[tuple[KnowledgeBaseTarget, list[str]]] = []
    for target in cfg.targets:
        rendered, render_warnings = render_queries(target.queries, inputs)
        warnings.extend(render_warnings)
        condensed: list[str] = []
        for q in rendered:
            q2, warning = condense_query(
                q, model=model, system_config_doc=system_config_doc, usage_acc=usage_acc,
            )
            condensed.append(q2)
            if warning:
                warnings.append(warning)
        if not condensed:
            warnings.append(
                f"Knowledge base {title_of(target.kb_uuid)} was skipped: every "
                "retrieval query rendered to an empty string."
            )
            continue
        prepared.append((target, condensed))

    all_queries: list[str] = []
    for _, qs in prepared:
        for q in qs:
            if q not in all_queries:
                all_queries.append(q)
    if not prepared:
        warnings.append(
            "Knowledge base grounding skipped: every retrieval query rendered "
            "to an empty string."
        )
        return GroundingResult(text="", warnings=warnings)

    if dm is None:
        # The process-wide instance, as chat uses: a grounded task per thread
        # in a parallel step must not open a vector-store client each.
        from app.services.document_manager import get_document_manager

        dm = get_document_manager()

    if progress:
        progress("Retrieving knowledge-base passages…")

    per_kb: list[list[list[dict]]] = []
    for target, queries in prepared:
        meta = kb_meta.get(target.kb_uuid) or {}
        floor = cfg.min_similarity
        if floor <= 0:
            tuned = meta.get("rag_config_override") or {}
            floor = _as_float(tuned.get("min_similarity"), 0.0) if isinstance(tuned, dict) else 0.0
        pools: list[list[dict]] = []
        for q in queries:
            pool = _retrieve_pool(dm, target.kb_uuid, q, k=cfg.k, floor=floor)
            for r in pool:
                r["kb_uuid"] = target.kb_uuid
                r["kb_title"] = meta.get("title")
                r["_query"] = q
            pools.append(pool)
        per_kb.append(pools)

    passages = merge_pools(per_kb, cfg.max_passages)
    passages, budget_warning = trim_to_budget(
        passages, token_budget, model=model, system_config_doc=system_config_doc,
    )
    if budget_warning:
        warnings.append(budget_warning)

    if not passages:
        if progress:
            progress("No matching passages found")
        if not budget_warning:
            shown = "; ".join(f"{q!r}" for q in all_queries)
            warnings.append(
                f"The knowledge base returned no matching passages for the query: {shown}."
                if len(prepared) == 1 and len(all_queries) == 1
                else f"No knowledge-base passages matched the retrieval queries: {shown}."
            )
        return GroundingResult(text="", warnings=warnings, queries=all_queries)

    if label_kb is None:
        label_kb = len(cfg.targets) > 1 or any(
            (kb_meta.get(u) or {}).get("title") for u in cfg.knowledge_bases
        )
    # Say which base each query was aimed at when they differ; a single base
    # (or one shared list) keeps the plain form.
    queries_note: Optional[str] = None
    if show_queries and len(prepared) > 1 and any(qs != prepared[0][1] for _, qs in prepared):
        queries_note = "Retrieval queries — " + " | ".join(
            f"{title_of(t.kb_uuid)}: " + "; ".join(f"{q!r}" for q in qs) for t, qs in prepared
        )
    text, sources = render_passages(
        passages, queries=all_queries, header=header, label_kb=label_kb,
        show_queries=show_queries, queries_note=queries_note, tagged=tagged,
    )
    return GroundingResult(
        text=text, sources=sources, warnings=warnings, queries=all_queries, passages=passages,
    )
