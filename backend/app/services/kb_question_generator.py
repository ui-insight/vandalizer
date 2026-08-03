"""Auto-generate validation test queries from KB content using an LLM.

Mirrors the spirit of ``workflow_validator.PlanGenerator`` (an LLM inspects the
artefact and proposes validation cases) but is async (KB data lives in Beanie
and ChromaDB, not raw pymongo collections) and tuned to produce *discriminating*
questions whose answers require retrieval — so the analysis-mode lift metric
remains meaningful.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError

from app.models.kb_test_query import KBTestQuery
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.services.document_manager import DocumentManager
from app.services.llm_service import get_agent_model
from app.services.config_service import get_user_model_name
from app.services.workflow_validator import _extract_json

logger = logging.getLogger(__name__)

_dm: DocumentManager | None = None


def _get_dm() -> DocumentManager:
    global _dm
    if _dm is None:
        _dm = DocumentManager()
    return _dm


# Cap on how many sources we sample anchor chunks from — protects cost on huge KBs.
MAX_SAMPLED_SOURCES = 30
# Per-chunk character budget when stuffing into the generator prompt.
MAX_CHUNK_CHARS = 600


KB_QUESTION_GENERATION_SYSTEM_PROMPT = (
    "You generate validation questions for a knowledge base.\n\n"
    "You are given chunks from a knowledge base, each labelled with its source.\n"
    "Produce a set of questions whose canonical answers are grounded directly in\n"
    "the supplied chunks, plus an expected answer and the source label(s) the\n"
    "answer would cite.\n\n"
    "DISCRIMINATION (very important):\n"
    "Favour questions that *require* the knowledge base — questions whose\n"
    "answers depend on specific facts, named entities, numbers, dates, internal\n"
    "terminology, or details unlikely to appear in a generalist LLM's training\n"
    "data. Avoid questions that a model could answer plausibly from common\n"
    "knowledge alone (e.g. 'what is a budget?'). The point of these questions\n"
    "is to measure how much value the knowledge base adds over a no-KB answer.\n\n"
    "CATEGORIES (mix them):\n"
    "- factual:     a single specific fact lookup\n"
    "- summary:     synthesise a short summary across one source\n"
    "- enumeration: list multiple items (e.g. 'list the deadlines')\n"
    "- boundary:    edge / negative cases ('is X mentioned in the docs?')\n\n"
    "OUTPUT FORMAT — return ONLY JSON (no markdown, no extra text):\n"
    '{"questions": [\n'
    '  {"query": "...", "expected_answer": "1-3 sentence canonical answer grounded in the chunks",\n'
    '   "expected_source_labels": ["substring of one or more provided source names"],\n'
    '   "category": "factual|summary|enumeration|boundary",\n'
    '   "source_chunk_ids": ["chunk_id_1", ...]}\n'
    ']}\n\n'
    "RULES:\n"
    "- expected_answer must be directly supported by the supplied chunks. Do not invent.\n"
    "- expected_source_labels must be substrings of provided source names. Do not invent source names.\n"
    "- source_chunk_ids must be drawn from the provided chunk IDs.\n"
    "- Keep each expected_answer concise (1-3 sentences).\n"
    "- Questions must be SELF-CONTAINED. Never refer to 'the provided excerpt',\n"
    "  'this chunk', 'the passage above', or similar — at answer time the reader\n"
    "  searches the whole knowledge base and never sees your sample. Name the\n"
    "  document or topic instead ('the EBSCO article on X').\n"
    "- ABSENCE CLAIMS: you only see small truncated samples of each source, so\n"
    "  you cannot know that a fact is absent from the full document. Never write\n"
    "  an expected_answer asserting information is 'not specified' / 'not\n"
    "  mentioned' unless the fact would be entirely outside the knowledge\n"
    "  base's subject matter. For boundary questions, prefer topics clearly\n"
    "  foreign to the corpus over details that might appear in unsampled text.\n"
)


# Questions phrased against the generator's private sample ("the provided
# excerpt") are unanswerable as written at validation time — the RAG pipeline
# retrieves from the whole KB and the answering model reasonably reads "the
# excerpt" as its retrieved context.
_SAMPLE_SCOPED_QUERY_RE = re.compile(
    r"\b(?:(?:provided|supplied|given|above|this|the)\s+)?(?:excerpt|passage|chunk|snippet)s?\b",
    re.IGNORECASE,
)

# Expected answers claiming information is absent. Only these get the
# full-KB verification pass — positive facts are grounded in a chunk the
# generator actually saw.
_ABSENCE_ANSWER_RE = re.compile(
    r"not\s+(?:specified|stated|mentioned|provided|given|included|indicated)"
    r"|does\s+not\s+(?:specify|state|mention|say|provide|include|indicate|give)"
    r"|doesn'?t\s+(?:specify|state|mention|say|provide|include|indicate|give)"
    r"|no\s+(?:mention|information|reference)\b"
    r"|\bn/?a\b"
    r"|\bunknown\b",
    re.IGNORECASE,
)


KB_ABSENCE_VERIFICATION_SYSTEM_PROMPT = (
    "You check whether a knowledge base really lacks a piece of information.\n"
    "You are given a validation question, an expected answer claiming the\n"
    "information is absent / not specified, and passages retrieved from the\n"
    "FULL knowledge base for that question.\n\n"
    "Decide whether the retrieved passages DO contain the information the\n"
    "question asks about — which would make the expected answer wrong.\n\n"
    'Return ONLY JSON (no markdown): {"contradicted": true|false, "evidence": "short quote or empty"}\n'
    "- contradicted=true only when a passage explicitly provides the asked-for\n"
    "  information. Inference, adjacent facts, or partial hints do not count.\n"
)


class KBQuestionGenerator:
    """Generates KBTestQuery records by sampling chunks and asking an LLM."""

    COVERAGE_TARGETS = {"quick": 5, "standard": 10, "exhaustive": 25}

    async def generate(
        self,
        kb_uuid: str,
        user_id: str,
        coverage: str = "standard",
        persist: bool = True,
    ) -> list[KBTestQuery]:
        """Generate test queries for a KB.

        Returns the list of created KBTestQuery objects (persisted if persist=True).
        Raises ``ValueError`` for unknown KB or empty (un-indexed) KB.
        """
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_uuid}")

        target_count = self.COVERAGE_TARGETS.get(coverage, self.COVERAGE_TARGETS["standard"])

        sources = await KnowledgeBaseSource.find(
            KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
        ).to_list()
        sources_with_chunks = [s for s in sources if s.chunk_count and s.chunk_count > 0]
        if not sources_with_chunks:
            raise ValueError("KB has no indexed content")

        sampled = await asyncio.to_thread(
            self._sample_chunks, kb_uuid, sources_with_chunks, target_count,
        )
        if not sampled:
            raise ValueError("KB has no readable chunks to sample")

        prompt = self._build_user_prompt(target_count, sampled)

        # Resolve model + run generator agent (async). get_user_model_name
        # validates the user's stored selection against available_models and
        # falls back to the system default when it's stale — a raw read would
        # return a removed/renamed model whose endpoint can't be resolved,
        # routing the call to an unreachable public default host (the per-user
        # "Connection error." that broke generation while chat worked).
        model_name = await get_user_model_name(user_id)
        if not model_name:
            raise ValueError("No LLM model configured for question generation")

        # Load SystemConfig so per-model api_key/endpoint flow through to the
        # provider; without it get_agent_model falls back to "no-api-key" and
        # routes external models like openai/gpt-oss-120b at api.openai.com.
        from app.models.system_config import SystemConfig
        try:
            cfg = await SystemConfig.get_config()
            sys_config_doc = cfg.model_dump() if cfg else None
        except Exception as e:
            logger.warning("Could not load SystemConfig for question generation: %s", e)
            sys_config_doc = None

        model = get_agent_model(model_name, system_config_doc=sys_config_doc)
        agent = Agent(model, system_prompt=KB_QUESTION_GENERATION_SYSTEM_PROMPT)
        run = await self._run_agent_with_retries(agent, prompt)

        try:
            parsed = _extract_json(run.output or "")
        except Exception as e:
            logger.exception("Generator output was not valid JSON: %s", e)
            raise ValueError("Generator returned no parseable questions") from e

        valid_source_names = {s.url_title or s.url or s.document_uuid or "" for s in sources}
        valid_source_names = {n for n in valid_source_names if n}
        provided_chunk_ids = {c["chunk_id"] for c in sampled}
        questions = self._parse_questions(parsed, valid_source_names, provided_chunk_ids)

        # Cap to target_count to avoid runaway generators.
        questions = questions[:target_count]

        # The generator only saw truncated samples, so an "information is
        # absent" expected answer may be contradicted by unsampled text in the
        # same document (the ticket case: "Accepted: January 14, 2024" lived
        # past the 600-char sample cut). Check those claims against full-KB
        # retrieval and drop the ones that don't hold.
        questions = await self._filter_contradicted_absence_questions(
            kb_uuid, questions, model_name, model,
        )

        created: list[KBTestQuery] = []
        for q in questions:
            tq = KBTestQuery(
                knowledge_base_uuid=kb_uuid,
                query=q["query"],
                expected_answer=q.get("expected_answer"),
                expected_source_labels=q.get("expected_source_labels", []),
                category=q.get("category"),
                source_chunk_ids=q.get("source_chunk_ids", []),
                auto_generated=True,
                user_id=user_id,
            )
            if persist:
                await tq.insert()
            created.append(tq)
        return created

    # ----- internals -----

    async def _filter_contradicted_absence_questions(
        self,
        kb_uuid: str,
        questions: list[dict[str, Any]],
        model_name: str,
        model: Any,
    ) -> list[dict[str, Any]]:
        """Drop questions whose 'not specified' expected answer is contradicted
        by full-KB retrieval.

        Keeps a question on any retrieval/LLM failure — verification is a
        quality filter, and an infra blip must not gut generation.
        """
        flagged = [q for q in questions if _ABSENCE_ANSWER_RE.search(q["expected_answer"])]
        if not flagged:
            return questions

        # Lazy import: kb_validation_service pulls in the whole RAG stack.
        from app.services.kb_validation_service import retrieve_kb_chunks

        checker = Agent(model, system_prompt=KB_ABSENCE_VERIFICATION_SYSTEM_PROMPT)
        dropped: set[int] = set()
        for q in flagged:
            try:
                results, _cfg, _tokens = await retrieve_kb_chunks(
                    kb_uuid, q["query"], model_name,
                )
                context = "\n\n".join(
                    ((r.get("metadata") or {}).get("source_name", "Unknown") + ":\n" + (r.get("content") or ""))
                    for r in results
                    if isinstance(r, dict) and r.get("content")
                )
                if not context:
                    continue
                run = await checker.run(
                    f"Question:\n{q['query']}\n\n"
                    f"Expected answer (claims absence):\n{q['expected_answer']}\n\n"
                    f"Retrieved passages:\n{context[:12000]}"
                )
                verdict = _extract_json(run.output or "")
                if isinstance(verdict, dict) and verdict.get("contradicted") is True:
                    dropped.add(id(q))
                    logger.info(
                        "Dropping absence question contradicted by full-KB retrieval: "
                        "%r (evidence: %r)",
                        q["query"][:120], str(verdict.get("evidence", ""))[:200],
                    )
            except Exception as e:
                logger.warning(
                    "Absence verification failed for %r — keeping question: %s",
                    q["query"][:120], e,
                )
        if not dropped:
            return questions
        return [q for q in questions if id(q) not in dropped]

    # Transient errors worth retrying on the inline LLM call. The Celery path
    # gets this via ``autoretry_for=TRANSIENT_EXCEPTIONS``; the synchronous
    # route call (used by the UI) has no such safety net, so mirror it here so a
    # single provider/network blip doesn't surface as a 502.
    #
    # ModelAPIError is pydantic-ai's wrapper for connection/transport failures
    # (e.g. openai.APIConnectionError -> "Connection error."). On oauthdev the
    # API container intermittently can't open an outbound socket to the model
    # endpoint, so this is exactly the blip a retry should absorb. HTTP *status*
    # errors surface as ModelHTTPError instead and are deliberately not retried
    # (a 4xx won't get better on a retry).
    _TRANSIENT = (ConnectionError, TimeoutError, OSError, ModelAPIError)
    _MAX_LLM_ATTEMPTS = 3

    async def _run_agent_with_retries(self, agent: Agent, prompt: str) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self._MAX_LLM_ATTEMPTS + 1):
            try:
                return await agent.run(prompt)
            except self._TRANSIENT as e:
                last_exc = e
                logger.warning(
                    "Question-generation LLM call failed (attempt %d/%d): %s",
                    attempt, self._MAX_LLM_ATTEMPTS, e,
                )
                if attempt < self._MAX_LLM_ATTEMPTS:
                    await asyncio.sleep(2 * attempt)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _sample_chunks(
        kb_uuid: str,
        sources_with_chunks: list[KnowledgeBaseSource],
        target_count: int,
    ) -> list[dict[str, Any]]:
        """Stratified sampling: one anchor chunk per source (capped), plus
        random extras. Returns a list of {chunk_id, source_id, source_name, content}.
        """
        # Stratify by chunk_count: bigger sources get pulled first.
        ranked = sorted(sources_with_chunks, key=lambda s: -(s.chunk_count or 0))
        ranked = ranked[:MAX_SAMPLED_SOURCES]

        dm = _get_dm()
        collection = dm.get_kb_collection(kb_uuid)

        sampled: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # Anchor chunks: one per source.
        for source in ranked:
            try:
                got = collection.get(where={"source_id": source.uuid}, limit=1)
            except Exception as e:
                logger.debug("Failed to fetch anchor chunk for source %s: %s", source.uuid, e)
                continue
            ids = (got or {}).get("ids") or []
            docs = (got or {}).get("documents") or []
            metas = (got or {}).get("metadatas") or []
            for cid, doc, meta in zip(ids, docs, metas):
                if cid in seen_ids or not doc:
                    continue
                seen_ids.add(cid)
                sampled.append({
                    "chunk_id": cid,
                    "source_id": (meta or {}).get("source_id") or source.uuid,
                    "source_name": (meta or {}).get("source_name") or source.url_title or source.url or source.document_uuid or "Unknown",
                    "content": (doc or "")[:MAX_CHUNK_CHARS],
                })

        # Random extras: up to target_count more, drawn across the whole collection.
        extras_needed = max(0, target_count - len(sampled))
        if extras_needed > 0:
            try:
                all_got = collection.get(limit=max(extras_needed * 4, 20))
            except Exception as e:
                logger.debug("Failed to fetch extra chunks: %s", e)
                all_got = {}
            ids = (all_got or {}).get("ids") or []
            docs = (all_got or {}).get("documents") or []
            metas = (all_got or {}).get("metadatas") or []
            pool = []
            for cid, doc, meta in zip(ids, docs, metas):
                if cid in seen_ids or not doc:
                    continue
                pool.append((cid, doc, meta or {}))
            random.shuffle(pool)
            for cid, doc, meta in pool[:extras_needed]:
                seen_ids.add(cid)
                sampled.append({
                    "chunk_id": cid,
                    "source_id": meta.get("source_id", ""),
                    "source_name": meta.get("source_name", "Unknown"),
                    "content": doc[:MAX_CHUNK_CHARS],
                })
        return sampled

    @staticmethod
    def _build_user_prompt(target_count: int, chunks: list[dict[str, Any]]) -> str:
        lines = [
            f"Generate {target_count} validation questions from the following knowledge base chunks.",
            "Mix categories. Favour questions that require retrieval (specific facts, names, numbers, dates).",
            "",
            "CHUNKS:",
        ]
        for c in chunks:
            lines.append(
                f"[CHUNK_ID: {c['chunk_id']} | SOURCE: {c['source_name']}]\n{c['content']}\n"
            )
        return "\n".join(lines)

    @staticmethod
    def _parse_questions(
        raw: Any,
        valid_source_names: set[str],
        provided_chunk_ids: set[str],
    ) -> list[dict[str, Any]]:
        """Normalise generator output. Filters out invented source names and chunk ids."""
        items: list[Any] = []
        if isinstance(raw, dict):
            items = raw.get("questions", []) or []
            if isinstance(items, dict):
                items = [items]
        elif isinstance(raw, list):
            items = raw

        out: list[dict[str, Any]] = []
        valid_categories = {"factual", "summary", "enumeration", "boundary"}
        for item in items:
            if not isinstance(item, dict):
                continue
            query = str(item.get("query", "")).strip()
            expected_answer = str(item.get("expected_answer", "")).strip()
            if not query or not expected_answer:
                continue
            if _SAMPLE_SCOPED_QUERY_RE.search(query):
                logger.info("Dropping sample-scoped generated question: %s", query[:120])
                continue

            raw_labels = item.get("expected_source_labels", []) or []
            labels: list[str] = []
            if isinstance(raw_labels, list):
                for lbl in raw_labels:
                    s = str(lbl).strip()
                    if not s:
                        continue
                    # Keep label only if it's a substring of some real source name.
                    if any(s.lower() in name.lower() for name in valid_source_names):
                        labels.append(s)

            raw_chunks = item.get("source_chunk_ids", []) or []
            chunk_ids: list[str] = []
            if isinstance(raw_chunks, list):
                for c in raw_chunks:
                    s = str(c).strip()
                    if s and s in provided_chunk_ids:
                        chunk_ids.append(s)

            category = str(item.get("category", "factual")).lower().strip()
            if category not in valid_categories:
                category = "factual"

            out.append({
                "query": query,
                "expected_answer": expected_answer,
                "expected_source_labels": labels,
                "source_chunk_ids": chunk_ids,
                "category": category,
            })
        return out
