"""Configurable web search for the agentic chat ``web_search`` tool.

A single service that normalizes three provider contracts into one shape so the
admin can point the deployment at whichever search backend they have:

- **tavily**  — LLM-optimized SaaS. ``POST`` JSON ``{api_key, query, ...}``.
- **searxng** — self-hostable metasearch. ``GET .../search?q=...&format=json``.
- **brave**   — Brave's independent index. ``GET`` with ``X-Subscription-Token``.

Configuration lives on :class:`SystemConfig` (``web_search_provider``,
``web_search_endpoint``, ``web_search_api_key``) and is passed in as the
``model_dump()`` dict via ``deps.system_config_doc`` so the tool never re-reads
the DB. The API key is stored encrypted; we decrypt it here.
"""

import logging
from typing import Optional

import httpx

from app.utils.encryption import decrypt_value
from app.utils.url_validation import validate_outbound_url

logger = logging.getLogger(__name__)

_TIMEOUT_S = 15.0
_MAX_SNIPPET_CHARS = 500
_DEFAULT_MAX_RESULTS = 5
_HARD_MAX_RESULTS = 10

# Tavily has a stable public endpoint; if the admin leaves the endpoint blank
# but selects "tavily", fall back to it so the common case needs only a key.
_TAVILY_DEFAULT_ENDPOINT = "https://api.tavily.com/search"

_USER_AGENT = "Vandalizer-Chat/1.0 (+research-admin agent)"


def is_configured(sys_config_doc: dict) -> bool:
    """Return True when web search has a provider and a usable endpoint.

    Tavily is usable with just a provider (it has a default endpoint); the
    others require an explicit endpoint.
    """
    provider = (sys_config_doc.get("web_search_provider") or "").strip().lower()
    endpoint = (sys_config_doc.get("web_search_endpoint") or "").strip()
    if not provider:
        return False
    if provider == "tavily":
        return True
    return bool(endpoint)


async def web_search(
    query: str,
    sys_config_doc: dict,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> dict:
    """Run a web search and return ``{results: [...], answer, provider}``.

    Returns ``{"configured": False, "error": ...}`` when web search isn't set
    up, and ``{"error": ...}`` on a request/parse failure — never raises, so the
    chat tool can degrade gracefully.
    """
    query = (query or "").strip()
    if not query:
        return {"error": "Empty search query.", "results": []}

    provider = (sys_config_doc.get("web_search_provider") or "").strip().lower()
    endpoint = (sys_config_doc.get("web_search_endpoint") or "").strip()
    api_key = decrypt_value(sys_config_doc.get("web_search_api_key") or "")

    if not provider:
        return {
            "configured": False,
            "error": "Web search is not configured for this deployment.",
            "results": [],
        }

    if provider == "tavily" and not endpoint:
        endpoint = _TAVILY_DEFAULT_ENDPOINT
    if not endpoint:
        return {
            "configured": False,
            "error": "Web search endpoint is not configured for this deployment.",
            "results": [],
        }

    n = max(1, min(int(max_results or _DEFAULT_MAX_RESULTS), _HARD_MAX_RESULTS))

    # SSRF guard — important for self-hosted SearXNG endpoints.
    try:
        validate_outbound_url(endpoint)
    except ValueError as e:
        return {"error": f"Web search endpoint rejected: {e}", "results": []}

    try:
        if provider == "tavily":
            payload = await _search_tavily(endpoint, api_key, query, n)
        elif provider == "searxng":
            payload = await _search_searxng(endpoint, api_key, query, n)
        elif provider == "brave":
            payload = await _search_brave(endpoint, api_key, query, n)
        else:
            return {
                "error": f"Unknown web search provider: {provider!r}.",
                "results": [],
            }
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        return {
            "error": f"Web search provider returned HTTP {status}.",
            "status_code": status,
            "results": [],
        }
    except httpx.TimeoutException:
        return {
            "error": f"Web search timed out after {int(_TIMEOUT_S)}s.",
            "results": [],
        }
    except Exception as e:  # network, DNS, TLS, JSON decode, shape errors
        logger.warning("Web search (%s) failed: %s", provider, e)
        return {"error": f"Web search failed: {e}", "results": []}

    payload["provider"] = provider
    payload["query"] = query
    return payload


def _clip(text: Optional[str]) -> str:
    return (text or "").strip()[:_MAX_SNIPPET_CHARS]


async def _search_tavily(endpoint: str, api_key: str, query: str, n: int) -> dict:
    body = {
        "query": query,
        "max_results": n,
        "include_answer": True,
        "search_depth": "basic",
    }
    # Tavily accepts the key in the body and (newer) as a bearer header; send both.
    headers = {"User-Agent": _USER_AGENT}
    if api_key:
        body["api_key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
        resp = await client.post(endpoint, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    results = [
        {
            "title": _clip(r.get("title")) or r.get("url", ""),
            "url": r.get("url", ""),
            "snippet": _clip(r.get("content")),
        }
        for r in (data.get("results") or [])
        if r.get("url")
    ][:n]
    answer = data.get("answer")
    return {"results": results, "answer": answer.strip() if isinstance(answer, str) else None}


async def _search_searxng(endpoint: str, api_key: str, query: str, n: int) -> dict:
    # SearXNG exposes results at <base>/search. Accept either a base URL or a
    # full .../search URL so the admin can paste whichever they have.
    url = endpoint if endpoint.rstrip("/").endswith("/search") else endpoint.rstrip("/") + "/search"
    params = {"q": query, "format": "json"}
    headers = {"User-Agent": _USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    results = [
        {
            "title": _clip(r.get("title")) or r.get("url", ""),
            "url": r.get("url", ""),
            "snippet": _clip(r.get("content")),
        }
        for r in (data.get("results") or [])
        if r.get("url")
    ][:n]
    return {"results": results, "answer": None}


async def _search_brave(endpoint: str, api_key: str, query: str, n: int) -> dict:
    params = {"q": query, "count": n}
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if api_key:
        headers["X-Subscription-Token"] = api_key

    async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
        resp = await client.get(endpoint, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    web = data.get("web") or {}
    results = [
        {
            "title": _clip(r.get("title")) or r.get("url", ""),
            "url": r.get("url", ""),
            "snippet": _clip(r.get("description")),
        }
        for r in (web.get("results") or [])
        if r.get("url")
    ][:n]
    return {"results": results, "answer": None}
