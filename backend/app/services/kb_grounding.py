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
2. For every (knowledge base, query) pair: an over-fetched vector search plus
   a lexical lookup for any cited section number or identifier in the query
   (``§ 200.414``, ``NSF-24-117``) that a bi-encoder scores as near-noise,
   then a per-source diversity cap so one long page cannot fill every slot.
   The knowledge base's Autovalidate-tuned relevance floor applies unless the
   task sets its own.
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
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.services.page_locator import (
    annotate_chunk_pages,
    cited_pages,
    format_page_range,
    locator_for_meta,
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
# Rough allowance for the prompt scaffolding around CONTEXT when a caller
# derives a token budget for the passages.
PROMPT_SCAFFOLD_TOKENS = 400


KB_GROUNDING_HEADER = (
    "Reference knowledge-base passages for this task. These are partial "
    "excerpts retrieved from policy and guidance sources by similarity to the "
    "retrieval queries listed below. They are REFERENCE MATERIAL, not the "
    "document under review, and may be incomplete, off-topic, or "
    "contradictory: read each one before relying on it and ignore the "
    "irrelevant ones. When you use a passage, cite the source line shown "
    "above it (e.g. [OMB Uniform Guidance — Subpart E · p. 12]), copying it "
    "exactly, and never attribute a claim to a passage that does not support "
    "it."
)

KB_APPROXIMATE_PAGE_RULE = (
    "A page written as `p. ~N` is an estimate: that source was scanned, so "
    "page positions were interpolated rather than read. Keep the tilde when "
    "you cite it and describe the location as approximate; never restate such "
    "a page as exact."
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

def _pin_terms(query: str) -> list[str]:
    try:
        from app.services.chat_service import _extract_pin_terms
    except Exception:  # pragma: no cover — chat module unavailable in a stripped worker
        return []
    try:
        return _extract_pin_terms(query)
    except Exception:  # noqa: BLE001
        return []


def _rank_lexical_hits(chunks: list[dict], term: str) -> list[dict]:
    pattern = re.compile(re.escape(term), re.IGNORECASE)

    def key(item: dict) -> tuple:
        content = item.get("content") or ""
        starts = [m.start() for m in pattern.finditer(content)]
        return (-len(starts), starts[0] if starts else len(content))

    return sorted(chunks, key=key)


def _diverse(results: list[dict], k: int) -> list[dict]:
    """Relevance order with a per-source cap; see chat's ``_select_diverse_chunks``."""
    max_per_source = max(2, -(-k // 2))
    selected: list[dict] = []
    overflow: list[dict] = []
    counts: dict = {}
    for r in results:
        meta = r.get("metadata") or {}
        src = meta.get("source_id") or meta.get("source_name")
        if counts.get(src, 0) < max_per_source:
            selected.append(r)
            counts[src] = counts.get(src, 0) + 1
        else:
            overflow.append(r)
        if len(selected) >= k:
            break
    if len(selected) < k:
        selected.extend(overflow[: k - len(selected)])
    return selected[:k]


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
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


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


def _retrieve_pool(
    dm, kb_uuid: str, query: str, *, k: int, floor: float,
) -> list[dict]:
    """One (knowledge base, query) pool: pinned lexical hits, then the
    over-fetched vector search, diversified and cut to ``k``."""
    vector = dm.query_kb(kb_uuid, query, k * OVERFETCH_MULTIPLIER, floor)
    if floor > 0:
        # Belt and braces: the store applies the floor too, but a fake or an
        # older store that ignores it must not leak junk past the gate.
        vector = [
            r for r in vector
            if not isinstance(r.get("similarity"), (int, float)) or r["similarity"] >= floor
        ]

    pinned: list[dict] = []
    for term in _pin_terms(query):
        try:
            hits = dm.get_kb_chunks_containing(kb_uuid, term, limit=PIN_LIMIT_PER_TERM)
        except Exception as e:  # noqa: BLE001
            logger.debug("Lexical pin lookup failed for %r: %s", term, e)
            continue
        pinned.extend(_rank_lexical_hits(hits, term))

    half = max(1, -(-k // 2))
    final: list[dict] = []
    seen: set = set()
    for r in pinned:
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
    return final[:k]


def merge_pools(per_kb: list[list[list[dict]]], max_passages: int) -> list[dict]:
    """``per_kb[i][j]`` is knowledge base *i*'s pool for its query *j*.

    Round-robin within a base across its queries, then across bases, dedupe,
    and cut to the cap — so every base and every query is represented before
    any of them contributes a second passage.
    """
    per_kb_merged = [_round_robin(pools) for pools in per_kb if pools]
    merged = _round_robin(per_kb_merged) if len(per_kb_merged) > 1 else (per_kb_merged[0] if per_kb_merged else [])
    return dedupe_passages(merged)[:max_passages]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _passage_label(r: dict, *, kb_title: Optional[str], query: str) -> tuple[str, dict]:
    meta = r.get("metadata") or {}
    content = r.get("content") or ""
    source_name = meta.get("source_name", "Unknown source")
    sheet = meta.get("sheet")
    cited = cited_pages(meta, content, query)
    page, page_end, approximate = cited["page"], cited["page_end"], cited["page_approximate"]
    locator = format_page_range(page, page_end, approximate) if page is not None else locator_for_meta(meta)
    label = f"{source_name} · {locator}" if locator else source_name
    if kb_title:
        label = f"{kb_title} — {label}"
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
) -> tuple[str, list[dict], bool]:
    """The framed text block and its citation list.

    Returns ``(text, sources, any_approximate)``. ``label_kb`` prefixes each
    source line with the knowledge base it came from; a single-base lookup
    reads as it always has without it. Each passage is cited against the
    query that retrieved it (``_query``), falling back to the first query.
    """
    parts: list[str] = []
    sources: list[dict] = []
    any_approximate = False
    fallback_query = queries[0] if queries else ""
    for i, r in enumerate(passages, 1):
        query = r.get("_query") or fallback_query
        label, source = _passage_label(
            r, kb_title=(r.get("kb_title") if label_kb else None), query=query,
        )
        any_approximate = any_approximate or bool(source.get("page_approximate"))
        parts.append(f"[{i}] {label}\n{annotate_chunk_pages(r.get('content') or '', r.get('metadata') or {})}")
        sources.append(source)
    if not parts:
        return "", [], False
    lines = [header]
    if any_approximate:
        lines.append(KB_APPROXIMATE_PAGE_RULE)
    if show_queries and (queries_note or queries):
        lines.append(queries_note or ("Retrieval queries: " + "; ".join(f"{q!r}" for q in queries)))
    text = "\n\n".join(lines) + "\n\n" + "\n\n---\n\n".join(parts)
    return text, sources, any_approximate


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
    progress: Optional[Callable[[str], None]] = None,
) -> GroundingResult:
    """Run the grounding pipeline for one task.

    Each target base is searched with its own queries. ``kb_meta`` maps a
    base's uuid to ``{"title", "rag_config_override", "exists"}`` as
    pre-resolved by the task loader. When it is supplied and a configured base
    is missing from it, that base no longer exists — a configuration error
    that fails the step, like a Knowledge Base Query step with no base
    selected. Without ``kb_meta`` (Test Step on an unsaved config, unit
    tests) bases are queried as given.

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
                "It may have been deleted or is no longer shared with you — pick "
                "another knowledge base for this step."
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
        from app.services.document_manager import DocumentManager

        dm = DocumentManager()

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
    text, sources, _ = render_passages(
        passages, queries=all_queries, header=header, label_kb=label_kb,
        show_queries=show_queries, queries_note=queries_note,
    )
    return GroundingResult(
        text=text, sources=sources, warnings=warnings, queries=all_queries, passages=passages,
    )
