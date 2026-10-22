"""Suggest web pages for a knowledge base from a described topic.

Building a KB from the web meant hunting down every link by hand and pasting
it into Add URLs (feature request). Here the user describes what they want —
"NSF proposal requirements" — and gets a short list of pages to approve; the
approved ones go through the ordinary add-URLs path, crawl options and all.

Every suggestion is a web-search result. The model only plans the searches
and picks among the numbered results; it never supplies a URL, so a
suggestion cannot be a link recalled from training data that 404s, moved
years ago, or never existed. Without a configured web search there are no
suggestions (``available: False``) rather than ungrounded ones.

Both model calls degrade instead of failing: no plan means the topic itself
is the query, and no ranking means the results come back in search order.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from pydantic_ai import Agent

logger = logging.getLogger(__name__)

METERING_FEATURE = "kb_source_suggest"

MAX_TOPIC_CHARS = 300
MAX_QUERIES = 3
RESULTS_PER_QUERY = 8
MAX_SUGGESTIONS = 12


class SearchPlan(BaseModel):
    queries: list[str] = Field(
        description=f"1-{MAX_QUERIES} web search queries that together find the authoritative pages on the topic.",
    )


class Pick(BaseModel):
    index: int = Field(description="The number of a candidate page from the list.")
    reason: str = Field(description="One short sentence: what this page covers that the topic needs.")


class Picks(BaseModel):
    picks: list[Pick] = Field(description="The relevant candidates, most useful first.")


_PLAN_PROMPT = f"""You plan web searches that find source pages for a research-administration knowledge base.

Given the topic a user wants covered, write 1-{MAX_QUERIES} search queries that together find the primary,
authoritative pages on it: the sponsor's or agency's own policy pages and guides, regulations (eCFR),
and the institution's own pages when the topic names one. Prefer the official source over articles or
summaries about it. Each query should look for a different part of the topic; don't repeat one query
in other words. Return queries only."""

_PICK_PROMPT = f"""You choose which web pages to add to a research-administration knowledge base.

You are given the topic the user wants covered and numbered candidate pages from a web search (title,
address, snippet). Return the candidates that belong in a knowledge base on that topic, most useful
first, at most {MAX_SUGGESTIONS}. Favor primary and official sources (the sponsor, agency, regulation,
or institution itself) over news, blogs, vendors, forums, and third-party summaries; leave out pages
that are off-topic, outdated by their own description, or duplicates of a better candidate. For each,
give one short sentence on what it covers. Use only the numbers in the list."""


def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _dedupe_key(url: str) -> str:
    """Same page, different spelling: scheme, ``www.``, trailing slash, fragment."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    path = parts.path.rstrip("/") or "/"
    return f"{_host(url)}{path}?{parts.query}" if parts.query else f"{_host(url)}{path}"


async def _sys_config_doc() -> dict:
    from app.models.system_config import SystemConfig

    cfg = await SystemConfig.get_config()
    return cfg.model_dump() if cfg else {}


async def is_available() -> bool:
    from app.services import web_search_service

    try:
        return web_search_service.is_configured(await _sys_config_doc())
    except Exception:
        logger.exception("Could not read web search configuration")
        return False


async def _agent(output_type: type[BaseModel], system_prompt: str, sys_config_doc: dict) -> Agent:
    from app.services.config_service import get_default_model_name
    from app.services.llm_service import get_agent_model

    model_name = await get_default_model_name() or "gpt-4o-mini"
    model = get_agent_model(model_name, system_config_doc=sys_config_doc)
    return Agent(model, system_prompt=system_prompt, output_type=output_type)


def _kb_context(kb: Any) -> str:
    parts = [f"Knowledge base: {getattr(kb, 'title', '') or 'Untitled'}"]
    if getattr(kb, "description", None):
        parts.append(f"Its description: {kb.description[:500]}")
    return "\n".join(parts)


async def _plan_queries(topic: str, kb: Any, sys_config_doc: dict) -> list[str]:
    try:
        agent = await _agent(SearchPlan, _PLAN_PROMPT, sys_config_doc)
        result = await agent.run(f"{_kb_context(kb)}\n\nTopic to cover: {topic}")
        queries = [q.strip() for q in result.output.queries if q and q.strip()]
    except Exception as e:
        from app.exceptions import TrialSpendBlockedError

        if isinstance(e, TrialSpendBlockedError):
            raise
        logger.warning("Search planning failed; searching the topic as written: %s", e)
        queries = []
    # The topic as written always runs too: it is the user's own words, and
    # a plan that drifted from them still leaves the direct search.
    return list(dict.fromkeys([topic, *queries]))[: MAX_QUERIES + 1]


async def _pick(topic: str, kb: Any, candidates: list[dict], sys_config_doc: dict) -> list[dict]:
    listing = "\n".join(
        f"{i}. {c['title']}\n   {c['url']}\n   {c['snippet'][:300]}" for i, c in enumerate(candidates, 1)
    )
    try:
        agent = await _agent(Picks, _PICK_PROMPT, sys_config_doc)
        result = await agent.run(f"{_kb_context(kb)}\n\nTopic to cover: {topic}\n\nCandidates:\n{listing}")
    except Exception as e:
        from app.exceptions import TrialSpendBlockedError

        if isinstance(e, TrialSpendBlockedError):
            raise
        logger.warning("Ranking source suggestions failed; returning search order: %s", e)
        return [{**c, "reason": None} for c in candidates[:MAX_SUGGESTIONS]]

    picked: list[dict] = []
    seen: set[int] = set()
    for pick in result.output.picks:
        # The model can only point at a candidate; a number outside the list
        # (or a repeat) is dropped, never turned into a page.
        if not 1 <= pick.index <= len(candidates) or pick.index in seen:
            continue
        seen.add(pick.index)
        picked.append({**candidates[pick.index - 1], "reason": (pick.reason or "").strip()[:300] or None})
        if len(picked) >= MAX_SUGGESTIONS:
            break
    return picked


async def suggest_sources(kb: Any, topic: str, *, user_id: str | None = None) -> dict:
    """Search the web for pages on ``topic`` and return the ones worth adding.

    Returns ``{available, queries, suggestions, already_in_kb, error}``. Each
    suggestion is ``{url, title, snippet, host, reason}``. Pages the KB
    already holds are left out and counted in ``already_in_kb``.
    """
    from app.services import knowledge_service, web_search_service
    from app.services.metering import metered_async

    topic = " ".join((topic or "").split())[:MAX_TOPIC_CHARS]
    sys_config_doc = await _sys_config_doc()
    if not web_search_service.is_configured(sys_config_doc):
        return {"available": False, "queries": [], "suggestions": [], "already_in_kb": 0, "error": None}

    async with metered_async(METERING_FEATURE, user_id=user_id, team_id=getattr(kb, "team_id", None)):
        queries = await _plan_queries(topic, kb, sys_config_doc)
        searches = await asyncio.gather(*(
            web_search_service.web_search(q, sys_config_doc, max_results=RESULTS_PER_QUERY) for q in queries
        ))

        candidates: list[dict] = []
        seen: set[str] = set()
        errors: list[str] = []
        for search in searches:
            if search.get("error") and not search.get("results"):
                errors.append(search["error"])
            for r in search.get("results") or []:
                url = (r.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                key = _dedupe_key(url)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "url": url,
                    "title": (r.get("title") or "").strip() or url,
                    "snippet": (r.get("snippet") or "").strip(),
                    "host": _host(url),
                })

        if not candidates:
            error = errors[0] if errors else None
            return {"available": True, "queries": queries, "suggestions": [], "already_in_kb": 0, "error": error}

        _, present = await knowledge_service.partition_new_urls(kb, [c["url"] for c in candidates])
        present_set = set(present)
        fresh = [c for c in candidates if knowledge_service._normalize_url(c["url"]) not in present_set]
        suggestions = await _pick(topic, kb, fresh, sys_config_doc) if fresh else []

    return {
        "available": True,
        "queries": queries,
        "suggestions": suggestions,
        "already_in_kb": len(candidates) - len(fresh),
        "error": None,
    }
