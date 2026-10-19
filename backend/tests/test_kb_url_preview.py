"""Previewing URLs before they enter a knowledge base — unit level.

The end-to-end flow (fetch, crawl, commit on a real database) is covered in
tests/integration/test_tier2_kb_url_preview.py; this file covers the verdicts
and the routes' guards, which run in every CI pass.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services import kb_url_preview
from app.services.web_fetcher import WebFetchResult
from tests.test_knowledge_routes import _auth, _make_user, _mock_kb


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

CONTENT = "Allowable costs under the award are described in this section. " * 60


def _result(text: str, links: int = 0) -> WebFetchResult:
    html = "".join(f'<a href="https://example.gov/p{i}">x</a>' for i in range(links))
    return WebFetchResult(
        url="https://example.gov/page", title="t", text=text, raw_html=f"<html>{html}</html>",
        used_browser=False, status_code=200,
    )


class TestQualityVerdicts:
    def test_real_content_has_no_reasons(self):
        assert kb_url_preview._low_quality_reasons(_result(CONTENT), is_seed=True) == []

    def test_a_thin_page_the_user_typed_is_flagged_not_dropped(self):
        reasons = kb_url_preview._low_quality_reasons(_result("Contact us."), is_seed=True)
        assert len(reasons) == 1 and "characters of content" in reasons[0]

    def test_a_link_index_the_user_typed_is_flagged(self):
        text = "Index " * 300  # long enough, but all links
        reasons = kb_url_preview._low_quality_reasons(_result(text, links=60), is_seed=True)
        assert any("Link index page" in r for r in reasons)

    def test_garbled_text_is_flagged(self):
        garbled = " " * 600
        reasons = kb_url_preview._low_quality_reasons(_result(garbled), is_seed=True)
        assert kb_url_preview.GARBLED_REASON in reasons

    def test_crawled_pages_are_not_judged_thin_here(self):
        # The crawl's navigation gate handles those before this runs.
        assert kb_url_preview._low_quality_reasons(_result("Contact us."), is_seed=False) == []

    def test_summary_carries_an_excerpt_not_the_whole_page(self):
        page = SimpleNamespace(
            page_id="p1", url="u", final_url=None, title="T", parent_url=None,
            verdict="low", reason="thin", text="x" * 5000, char_count=5000,
            chunk_count=6, truncated=False, warnings=[],
        )
        summary = kb_url_preview.page_summary(page)
        assert len(summary["excerpt"]) == kb_url_preview.EXCERPT_CHARS
        assert summary["addable"] is True
        page.verdict = "navigation"
        assert kb_url_preview.page_summary(page)["addable"] is False


def _routes(user_id="user1"):
    user = _make_user(user_id)
    return user, (
        patch("app.dependencies.decode_token", return_value={"sub": user_id, "type": "access"}),
        patch("app.dependencies.User", find_one=AsyncMock(return_value=user)),
        patch("app.routers.knowledge.svc", get_knowledge_base=AsyncMock(return_value=_mock_kb())),
        patch("app.routers.knowledge.organization_service",
              get_user_org_ancestry=AsyncMock(return_value=[])),
    )


class TestPreviewRoutes:
    @pytest.mark.asyncio
    async def test_preview_is_dispatched_and_adds_nothing(self, client):
        cookies, headers = _auth()
        _, patches = _routes()
        preview = SimpleNamespace(uuid="pv-1", status="running")
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "start_preview", AsyncMock(return_value=preview)), \
             patch("app.tasks.kb_validation_tasks.preview_urls_task.delay") as preview_delay, \
             patch("app.tasks.kb_validation_tasks.add_urls_task.delay") as add_delay:
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls/preview",
                json={"urls": ["https://example.gov/policy"]},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json()["preview_uuid"] == "pv-1"
        preview_delay.assert_called_once_with("pv-1")
        add_delay.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("crawl, count", [(False, 51), (True, 6)])
    async def test_a_preview_checks_a_handful_not_a_sitemap(self, client, crawl, count):
        # One worker task fetches every URL of a preview; a sitemap's worth
        # would be killed at the time limit with the rest never fetched. Large
        # adds take the batched add_urls path instead.
        cookies, headers = _auth()
        _, patches = _routes()
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "start_preview", AsyncMock()) as start, \
             patch("app.tasks.kb_validation_tasks.preview_urls_task.delay") as preview_delay:
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls/preview",
                json={"urls": [f"https://example.gov/p{i}" for i in range(count)], "crawl_enabled": crawl},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400
        assert "at most" in resp.json()["detail"]
        start.assert_not_called()
        preview_delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_someone_elses_preview_is_not_found(self, client):
        cookies, headers = _auth()
        _, patches = _routes()
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "get_preview", AsyncMock(return_value=None)):
            resp = await client.get(
                "/api/knowledge/kb-uuid-1/add_urls/preview/pv-1", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,claimed,expected", [
        ("running", False, 409),
        ("committed", False, 409),
        ("ready", True, 200),
    ])
    async def test_commit_only_a_finished_unclaimed_preview(self, client, status, claimed, expected):
        cookies, headers = _auth()
        _, patches = _routes()
        preview = SimpleNamespace(uuid="pv-1", status=status)
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "get_preview", AsyncMock(return_value=preview)), \
             patch.object(kb_url_preview, "claim_for_commit", AsyncMock(return_value=claimed)), \
             patch("app.tasks.kb_validation_tasks.commit_url_preview_task.delay") as commit_delay:
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls/preview/pv-1/commit",
                json={"page_ids": ["a", "b"]},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == expected
        if expected == 200:
            commit_delay.assert_called_once_with("pv-1", ["a", "b"])
        else:
            commit_delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_needs_a_selection(self, client):
        cookies, headers = _auth()
        _, patches = _routes()
        preview = SimpleNamespace(uuid="pv-1", status="ready")
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "get_preview", AsyncMock(return_value=preview)):
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls/preview/pv-1/commit",
                json={"page_ids": []},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 400
