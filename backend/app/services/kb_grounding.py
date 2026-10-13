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
# How much of a passage's text a citation carries into the run record.
CITATION_CONTENT_CHARS = 2000


KB_GROUNDING_HEADER = (
    "Reference knowledge-base passages for this task. These are partial "
    "excerpts retrieved from policy and guidance sources by similarity to the "
    "retrieval queries listed below. They are REFERENCE MATERIAL, not the "
    "document under review, and may be incomplete, off-topic, or "
    "contradictory: read each one before relying on it and ignore the "
    "irrelevant ones. Each passage starts with its tag, e.g. [KB2], and the "
    "source it comes from."
)

# Appended to the INSTRUCTION of a task whose context carries its own
# knowledge-base passages. It cannot live in the passages header: the
# engine's grounded prompt tells the model that CONTEXT is data, never
# instructions, so a rule placed there is (correctly) ignored. The model
# cites a short tag ([KB2]) — copying a long source line is what models skip
# or abbreviate, and a bare number would mean a different passage in every
# task — and the engine replaces each tag with the passage's source line as
# soon as the reply arrives (resolve_passage_tags). The JSON clause is what
# lets a citation survive a task that emits a fragment for a later
# consolidation step to render.
CITATION_RULE = (
    "CITATIONS (required): the CONTEXT includes knowledge-base passages, each "
    "introduced by a tag in square brackets such as [KB2] followed by its "
    "source. Whenever a statement you write draws on a passage, follow that "
    "statement immediately with the passage's tag in square brackets — right "
    "after the sentence or value it supports, never gathered in a list at "
    "the end; cite two passages as [KB1][KB3]. Statements in the CONTEXT that "
    "already carry a citation in square brackets keep it, exactly as written, "
    "when you restate or reorganize them. If your output is JSON, this rule "
    "still applies and overrides any instruction to emit only the listed "
    "fields' bare values: end every string value that states a rule, "
    "requirement, threshold, or rationale drawn from a passage with the tag, "
    "inside the string — e.g. \"rationale\": \"Prior written approval is "
    "required for equipment purchases [KB2]\". Add no new fields. Never "
    "invent a tag, never attach one to a claim the passage does not support, "
    "and cite nothing for statements that come only from the document under "
    "review."
)

# The same rule for a task with no passages of its own that reads cited text
# (or a Knowledge Base Query step's passages) from the previous step: the
# citations there are already source lines, so they are kept as written.
CARRY_CITATION_RULE = (
    "CITATIONS (required): statements in the CONTEXT carry knowledge-base "
    "citations in square brackets, such as [OMB Uniform Guidance (2 CFR 200) "
    "— Subpart E—Cost Principles · part 12], and knowledge-base passages may "
    "appear under such a citation. When you restate, reorganize or summarize "
    "a cited statement, keep its citation with it, copied exactly — right "
    "after the sentence or value it supports, never gathered in a list at "
    "the end. When you draw on a passage shown under a citation, follow your "
    "statement with that citation, copied exactly. If your output is JSON, "
    "this rule still applies and overrides any instruction to emit only the "
    "listed fields' bare values: keep each citation inside the string value "
    "it supports. Add no new fields. Never invent a citation, and cite "
    "nothing for statements that come only from the document under review."
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

def _pinned_hits(dm, kb_uuid: str, query: str) -> list[dict]:
    """Chunks that literally contain a section number or identifier the query
    names (``§ 200.414``), the way chat pins them: exact matches only, so a
    query about 200.1 does not pin 200.10. A failed lookup pins nothing."""
    from app.services.chat_service import _extract_pin_terms, retrieve_pinned_chunks_sync

    try:
        return retrieve_pinned_chunks_sync(
            dm, kb_uuid, _extract_pin_terms(query), limit_per_ref=PIN_LIMIT_PER_TERM,
        )
    except Exception as e:  # noqa: BLE001 — vector retrieval still runs
        logger.debug("Lexical pin lookup failed for %r: %s", query, e)
        return []


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

    pinned = _pinned_hits(dm, kb_uuid, query)

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

def _citation_safe(label: str) -> str:
    label = label.replace("[", "(").replace("]", ")").replace(";", ",")
    label = label.replace('"', "'").replace("\\", "/")
    return re.sub(r"\s+", " ", label).strip()


def _passage_label(r: dict, *, kb_title: Optional[str], query: str) -> tuple[str, dict]:
    meta = r.get("metadata") or {}
    content = r.get("content") or ""
    source_name = meta.get("source_name", "Unknown source")
    sheet = meta.get("sheet")
    cited = cited_pages(meta, content, query)
    page, page_end, approximate = cited["page"], cited["page_end"], cited["page_approximate"]
    locator = format_page_range(page, page_end, approximate) if page is not None else locator_for_meta(meta)
    if not locator:
        # A web page or eCFR subpart has no pages, so every passage from it
        # would share one source line and a citation could not say which it
        # means. Its position in the source tells them apart, the same in
        # every task that retrieves it.
        m = re.search(r"_chunk_(\d+)$", str(r.get("chunk_id") or ""))
        locator = f"part {int(m.group(1)) + 1}" if m else None
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
        parts.append(f"{heading}\n{annotate_chunk_pages(r.get('content') or '', r.get('metadata') or {})}")
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
    seen: set = set()
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
                continue
            seen.add(key)
            out.append(s)
    return out


_CITATION_RE = re.compile(r"\[([^\[\]\n]{3,300})\]")
_PAGE_RE = re.compile(r"\bp\.\s*~?\s*\d")
_PAGE_WORD_RE = re.compile(r"\bpage\s+\d")


def _norm_citation(text: str) -> str:
    """Loose form of a citation for comparison; mirrors the run UI's matcher."""
    t = (text or "").lower()
    t = re.sub(r"[‒–—―]", "-", t)
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
    r"[\[(【]\s*(?:†\s*)?KB\s*(\d{1,3})((?:\s*[,;†]\s*(?:KB\s*)?\d{1,3})*)[^\])】\n]{0,40}?[\])】]",
    re.IGNORECASE,
)
_TAG_ONLY_RE = re.compile(r"KB\s*\d{1,3}", re.IGNORECASE)
_EMPTY_NATIVE_CITE_RE = re.compile(r"\s*【[\s†]*】")


def resolve_passage_tags(text: str, sources: list[dict]) -> str:
    """Replace every passage tag in ``text`` with that passage's source line.

    ``sources`` is the task's passage list in the order the tags number it
    ([KB1] is ``sources[0]``). Run right after the model replies, so the
    output, every later step that reads it, and the run UI see the exact
    source line rather than a number that means a different passage in each
    task. A tag past the last passage is left as written (and reported as
    an unmatched citation).
    """
    if not text or not isinstance(text, str):
        return text
    # Some models (gpt-oss) emit their own 【…】 citation marks, often empty
    # when there was nothing to cite: an empty one is dropped, a 【KB2】 is
    # resolved below like [KB2].
    text = _EMPTY_NATIVE_CITE_RE.sub("", text)
    if not sources:
        return text

    def sub(m: re.Match) -> str:
        nums = [int(m.group(1))] + [int(n) for n in re.findall(r"\d{1,3}", m.group(2) or "")]
        labels: list[str] = []
        for n in nums:
            label = sources[n - 1].get("label") if 1 <= n <= len(sources) else None
            if not label:
                return m.group(0)
            if label not in labels:
                labels.append(label)
        return "".join(f"[{label}]" for label in labels)

    return _PASSAGE_TAG_RE.sub(sub, text)


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


CITATION_RETRY_NUDGE = (
    "Your previous reply used the knowledge-base passages but did not cite "
    "them. Reply again with the same content and, after every statement or "
    "value that rests on a passage, that passage's tag in square brackets "
    "(e.g. [KB2]) — inside the string value when the output is JSON."
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
            title_only = re.sub(r"\s*·?\s*(?:p\. \d+(\s*-\s*\d+)?|part \d+)\s*$", "", n).strip()
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
