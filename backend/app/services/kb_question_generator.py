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
from typing import Any

from pydantic_ai import Agent

from app.models.kb_test_query import KBTestQuery
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.services.document_manager import DocumentManager
from app.services.llm_service import get_agent_model
from app.services.workflow_validator import _extract_json, _resolve_model_name

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

        # Resolve model + run generator agent (async).
        model_name = await asyncio.to_thread(_resolve_model_name, user_id)
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

    # Transient errors worth retrying on the inline LLM call. The Celery path
    # gets this via ``autoretry_for=TRANSIENT_EXCEPTIONS``; the synchronous
    # route call (used by the UI) has no such safety net, so mirror it here so a
    # single provider/network blip doesn't surface as a 502.
    _TRANSIENT = (ConnectionError, TimeoutError, OSError)
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
