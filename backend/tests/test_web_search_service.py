"""Unit tests for the configurable web search service.

httpx is monkeypatched so no network is touched; we assert each provider's
response shape is normalized to ``{results: [{title, url, snippet}], answer}``
and that the not-configured / SSRF / error paths degrade gracefully.
"""

import pytest

from app.services import web_search_service


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Stand-in for httpx.AsyncClient that records the request and replays a payload."""

    def __init__(self, payload, capture):
        self._payload = payload
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        self._capture.update(method="GET", url=url, params=params, headers=headers)
        return _FakeResponse(self._payload)

    async def post(self, url, json=None, headers=None):
        self._capture.update(method="POST", url=url, json=json, headers=headers)
        return _FakeResponse(self._payload)


@pytest.fixture
def patch_httpx(monkeypatch):
    """Patch the service's httpx + SSRF guard. Returns a setter for the payload."""
    captured: dict = {}

    def _install(payload):
        monkeypatch.setattr(
            web_search_service.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeClient(payload, captured),
        )
        # Skip DNS resolution in validate_outbound_url for these unit tests.
        monkeypatch.setattr(web_search_service, "validate_outbound_url", lambda url: url)
        return captured

    return _install


@pytest.mark.asyncio
async def test_not_configured_returns_flag():
    result = await web_search_service.web_search("anything", {})
    assert result["configured"] is False
    assert "not configured" in result["error"].lower()
    assert result["results"] == []


@pytest.mark.asyncio
async def test_is_configured():
    assert web_search_service.is_configured({"web_search_provider": "tavily"}) is True
    # MindRouter has a default endpoint, so provider alone is enough.
    assert web_search_service.is_configured({"web_search_provider": "mindrouter"}) is True
    assert web_search_service.is_configured(
        {"web_search_provider": "searxng", "web_search_endpoint": "https://s.x/search"}
    ) is True
    # SearXNG without an endpoint is not usable.
    assert web_search_service.is_configured({"web_search_provider": "searxng"}) is False
    assert web_search_service.is_configured({}) is False


@pytest.mark.asyncio
async def test_tavily_normalizes_and_includes_answer(patch_httpx):
    captured = patch_httpx({
        "answer": "  The current version is 24-1.  ",
        "results": [
            {"title": "PAPPG", "url": "https://nsf.gov/pappg", "content": "x" * 999},
            {"title": "No URL", "content": "skip me"},  # dropped — no url
        ],
    })
    cfg = {"web_search_provider": "tavily", "web_search_api_key": "secret"}
    result = await web_search_service.web_search("nsf pappg version", cfg, max_results=5)

    assert result["provider"] == "tavily"
    assert result["answer"] == "The current version is 24-1."
    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r == {
        "title": "PAPPG",
        "url": "https://nsf.gov/pappg",
        "snippet": "x" * web_search_service._MAX_SNIPPET_CHARS,
    }
    # Default endpoint + key sent in body and header.
    assert captured["method"] == "POST"
    assert captured["url"] == web_search_service._TAVILY_DEFAULT_ENDPOINT
    assert captured["json"]["api_key"] == "secret"
    assert captured["headers"]["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_searxng_appends_search_path(patch_httpx):
    captured = patch_httpx({
        "results": [{"title": "Hit", "url": "https://ex.org/a", "content": "snippet"}]
    })
    cfg = {
        "web_search_provider": "searxng",
        "web_search_endpoint": "https://searx.uidaho.edu",
    }
    result = await web_search_service.web_search("indirect costs", cfg)

    assert result["answer"] is None
    assert result["results"][0]["url"] == "https://ex.org/a"
    assert captured["method"] == "GET"
    assert captured["url"] == "https://searx.uidaho.edu/search"
    assert captured["params"] == {"q": "indirect costs", "format": "json"}


@pytest.mark.asyncio
async def test_brave_reads_web_results_and_token_header(patch_httpx):
    captured = patch_httpx({
        "web": {"results": [
            {"title": "Brave hit", "url": "https://ex.org/b", "description": "desc"},
        ]}
    })
    cfg = {
        "web_search_provider": "brave",
        "web_search_endpoint": "https://api.search.brave.com/res/v1/web/search",
        "web_search_api_key": "tok",
    }
    result = await web_search_service.web_search("sponsor policy", cfg, max_results=2)

    assert result["results"] == [
        {"title": "Brave hit", "url": "https://ex.org/b", "snippet": "desc"}
    ]
    assert captured["headers"]["X-Subscription-Token"] == "tok"
    assert captured["params"]["count"] == 2


@pytest.mark.asyncio
async def test_mindrouter_posts_bearer_and_strips_html(patch_httpx):
    captured = patch_httpx({
        "provider": "Brave Search",
        "total_results": 2,
        "results": [
            {
                "title": "ORED | <strong>University</strong> of Idaho",
                "url": "https://www.uidaho.edu/research",
                "snippet": "Connects businesses with <strong>university researchers</strong> &amp; industry.",
                "published": None,
            },
            {"title": "No URL", "snippet": "skip me"},  # dropped — no url
        ],
    })
    cfg = {"web_search_provider": "mindrouter", "web_search_api_key": "mr2_key"}
    result = await web_search_service.web_search("research administration", cfg, max_results=3)

    assert result["provider"] == "mindrouter"
    assert result["answer"] is None
    assert result["results"] == [
        {
            "title": "ORED | University of Idaho",
            "url": "https://www.uidaho.edu/research",
            "snippet": "Connects businesses with university researchers & industry.",
        }
    ]
    # Default endpoint, POST body, and Bearer auth.
    assert captured["method"] == "POST"
    assert captured["url"] == web_search_service._MINDROUTER_DEFAULT_ENDPOINT
    assert captured["json"] == {"query": "research administration", "max_results": 3}
    assert captured["headers"]["Authorization"] == "Bearer mr2_key"


@pytest.mark.asyncio
async def test_mindrouter_appends_v1_search_to_base_url(patch_httpx):
    captured = patch_httpx({"results": []})
    cfg = {
        "web_search_provider": "mindrouter",
        "web_search_endpoint": "https://mindrouter.uidaho.edu",
    }
    await web_search_service.web_search("q", cfg)
    assert captured["url"] == "https://mindrouter.uidaho.edu/v1/search"


@pytest.mark.asyncio
async def test_unknown_provider_errors(patch_httpx):
    patch_httpx({})  # patches the SSRF guard so we reach the provider switch
    cfg = {"web_search_provider": "duckduckgo", "web_search_endpoint": "https://x.y"}
    result = await web_search_service.web_search("q", cfg)
    assert "unknown web search provider" in result["error"].lower()


@pytest.mark.asyncio
async def test_ssrf_rejection(monkeypatch):
    def _reject(url):
        raise ValueError("URL resolves to blocked IP range: 127.0.0.1")

    monkeypatch.setattr(web_search_service, "validate_outbound_url", _reject)
    cfg = {"web_search_provider": "searxng", "web_search_endpoint": "http://localhost/search"}
    result = await web_search_service.web_search("q", cfg)
    assert "rejected" in result["error"].lower()
    assert result["results"] == []


@pytest.mark.asyncio
async def test_max_results_capped(patch_httpx):
    captured = patch_httpx({
        "results": [
            {"title": f"r{i}", "url": f"https://ex.org/{i}", "content": "c"}
            for i in range(50)
        ]
    })
    cfg = {"web_search_provider": "tavily"}
    result = await web_search_service.web_search("q", cfg, max_results=999)
    # Hard cap enforced regardless of requested max.
    assert len(result["results"]) == web_search_service._HARD_MAX_RESULTS
    assert captured["json"]["max_results"] == web_search_service._HARD_MAX_RESULTS
