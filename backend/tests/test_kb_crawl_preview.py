"""A crawl is previewed before it adds anything, and adds only what was ticked.

Support ticket: crawling ran blind — it followed links and embedded pages up
to the limit, and the user saw what it took only after it was in the KB
(news, navigation, junk, all paid for in embeddings). The preview walks the
same links with the same scope, budget and navigation check, creates no
sources, and the add step ingests only the pages the user chose.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult

START = "https://www.uidaho.edu/research/osp"
CONTENT = "Sponsored programs policy text. " * 40


def _page(url: str, links: list[str] = (), text: str = CONTENT, title: str = "") -> WebFetchResult:
    html = "".join(f'<a href="{link}">x</a>' for link in links)
    return WebFetchResult(
        url=url, title=title or url.rsplit("/", 1)[-1], text=text,
        raw_html=f"<html><body>{html}</body></html>", used_browser=False, status_code=200,
    )


SITE = {
    START: _page(START, [
        f"{START}/fa-rates", f"{START}/news", f"{START}/broken",
        f"{START}/already", "https://www.facebook.com/uidaho", f"{START}/cost-share",
    ], title="Office of Sponsored Programs"),
    f"{START}/fa-rates": _page(f"{START}/fa-rates", [f"{START}/fa-rates/history"], title="F&A rates"),
    f"{START}/news": _page(f"{START}/news", [f"{START}/news/2026"], text="NAV", title="News"),
    f"{START}/cost-share": _page(f"{START}/cost-share", title="Cost share"),
    f"{START}/fa-rates/history": _page(f"{START}/fa-rates/history", title="Rate history"),
    f"{START}/news/2026": _page(f"{START}/news/2026", title="2026 news"),
}


async def _fake_fetch(url, **_):
    if url.endswith("/broken"):
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))
    return SITE[url]


def _preview(**overrides):
    p = SimpleNamespace(
        uuid="pv-1", kb_uuid="kb-1", start_urls=[START], max_crawl_pages=5,
        allowed_domains="", status="running", error_message=None, pages=[],
        fetched=0, completed_at=None,
    )
    for k, v in overrides.items():
        setattr(p, k, v)
    p.save = AsyncMock()
    return p


async def _run(preview, in_kb=()):
    fetch = AsyncMock(side_effect=_fake_fetch)
    with patch("app.services.web_fetcher.fetch_url", fetch), \
         patch.object(knowledge_service, "get_kb_sources",
                      AsyncMock(return_value=[SimpleNamespace(url=u) for u in in_kb])), \
         patch("app.utils.page_quality.describe_low_value_page",
               lambda text, n, min_chars: "Mostly links" if text == "NAV" else None), \
         patch.object(knowledge_service, "_get_dm", side_effect=AssertionError("a preview embeds nothing")), \
         patch.object(knowledge_service, "_insert_source_unless_duplicate",
                      AsyncMock(side_effect=AssertionError("a preview creates no sources"))):
        await knowledge_service.run_crawl_preview(preview)
    return fetch


def _kinds(preview):
    return {p["url"].removeprefix(START) or "/": (p["kind"], p["in_kb"]) for p in preview.pages}


class TestPreviewFindsWhatACrawlWould:
    @pytest.mark.asyncio
    async def test_lists_every_page_and_adds_none(self):
        preview = _preview()
        await _run(preview, in_kb=[f"{START}/already"])

        assert _kinds(preview) == {
            "/": ("start", False),
            "/fa-rates": ("content", False),
            "/news": ("navigation", False),
            "/broken": ("failed", False),
            "/already": ("content", True),
            "/cost-share": ("content", False),
            "/fa-rates/history": ("content", False),
            "/news/2026": ("content", False),
        }
        assert preview.status == "complete"
        broken = next(p for p in preview.pages if p["url"].endswith("/broken"))
        assert "404" in (broken["note"] or "")

    @pytest.mark.asyncio
    async def test_stays_in_scope_and_skips_fetching_pages_already_in_the_kb(self):
        preview = _preview()
        fetch = await _run(preview, in_kb=[f"{START}/already"])
        fetched = [c.args[0] for c in fetch.await_args_list]
        assert "https://www.facebook.com/uidaho" not in fetched
        assert f"{START}/already" not in fetched
        assert preview.fetched == len(fetched)

    @pytest.mark.asyncio
    async def test_max_pages_counts_content_pages_not_navigation(self):
        preview = _preview(max_crawl_pages=2)
        await _run(preview)
        content = [p for p in preview.pages if p["kind"] == "content"]
        assert len(content) == 2
        # The navigation page met before the second content page is listed
        # and did not use up a slot.
        assert any(p["kind"] == "navigation" for p in preview.pages)

    @pytest.mark.asyncio
    async def test_an_unreachable_start_page_is_listed_and_not_followed(self):
        preview = _preview(start_urls=[f"{START}/broken"])
        await _run(preview)
        assert [(p["kind"], p["start_url"]) for p in preview.pages] == [("failed", f"{START}/broken")]

    @pytest.mark.asyncio
    async def test_progress_is_saved_as_pages_are_found(self):
        preview = _preview()
        await _run(preview)
        assert preview.save.await_count >= len(preview.pages) - 1


# --- Add only what was ticked -------------------------------------------------


def _source_cls():
    made = []

    def construct(**kwargs):
        src = SimpleNamespace(**{
            "uuid": f"src-{len(made)}", "status": "pending", "crawled_urls": None,
            "skipped_urls": None, "parent_source_uuid": None, **kwargs,
        })
        made.append(src)
        return src

    return MagicMock(side_effect=construct), made


async def _add(preview, urls):
    cls, made = _source_cls()
    ingest = AsyncMock(return_value=None)
    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_insert_source_unless_duplicate", AsyncMock(return_value=True)), \
         patch.object(knowledge_service, "_ingest_url_source", ingest), \
         patch.object(knowledge_service, "_save_unless_deleted", AsyncMock(return_value=True)), \
         patch.object(knowledge_service, "recalculate_stats", AsyncMock()) as recalc:
        added = await knowledge_service.add_crawl_selection(MagicMock(uuid="kb-1"), preview, urls)
    return added, made, ingest, recalc


@pytest.fixture
async def finished():
    preview = _preview()
    await _run(preview, in_kb=[f"{START}/already"])
    return preview


class TestAddOnlyTheTickedPages:
    @pytest.mark.asyncio
    async def test_unticked_pages_are_never_fetched_or_embedded(self, finished):
        added, made, ingest, recalc = await _add(finished, [START, f"{START}/fa-rates"])

        assert added == 2
        assert [s.url for s in made] == [START, f"{START}/fa-rates"]
        assert ingest.await_count == 2
        recalc.assert_awaited_once()
        assert finished.status == "added"

    @pytest.mark.asyncio
    async def test_children_hang_off_the_start_page_like_a_crawl(self, finished):
        _, made, _, _ = await _add(finished, [START, f"{START}/fa-rates", f"{START}/news"])
        parent, *children = made
        assert parent.crawl_enabled is True
        assert all(c.parent_source_uuid == parent.uuid for c in children)
        assert parent.crawled_urls == [f"{START}/fa-rates", f"{START}/news"]
        # A ticked navigation page is added — the user overrode the check —
        # and is not reported as skipped.
        assert parent.skipped_urls is None

    @pytest.mark.asyncio
    async def test_unticked_navigation_is_recorded_as_skipped(self, finished):
        _, made, _, _ = await _add(finished, [START, f"{START}/fa-rates"])
        assert made[0].skipped_urls == [f"{START}/news"]

    @pytest.mark.asyncio
    async def test_unticking_the_start_page_adds_the_rest_without_a_parent(self, finished):
        _, made, _, _ = await _add(finished, [f"{START}/cost-share"])
        assert [(s.url, s.parent_source_uuid) for s in made] == [(f"{START}/cost-share", None)]

    @pytest.mark.asyncio
    async def test_failed_in_kb_and_unknown_urls_are_ignored(self, finished):
        added, made, _, _ = await _add(finished, [
            f"{START}/broken", f"{START}/already", "https://evil.example/not-in-preview",
        ])
        assert added == 0
        assert made == []


# --- Routes -------------------------------------------------------------------

from tests.test_knowledge_routes import _auth, _make_user, _mock_kb  # noqa: E402


def _route_patches(kb, preview=None):
    return (
        patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
        patch("app.dependencies.User"),
        patch("app.routers.knowledge.svc"),
        patch("app.routers.knowledge.organization_service"),
        patch("app.models.knowledge.KBCrawlPreview.find_one", AsyncMock(return_value=preview)),
    )


async def _call(client, method, path, kb, preview=None, json=None, extra=()):
    cookies, headers = _auth()
    p_token, p_user, p_svc, p_org, p_find = _route_patches(kb, preview)
    with p_token, p_user as MockUser, p_svc as mock_svc, p_org as mock_org, p_find:
        stack = [e.__enter__() for e in extra]
        try:
            MockUser.find_one = AsyncMock(return_value=_make_user())
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            resp = await client.request(method, path, cookies=cookies, headers=headers, json=json)
        finally:
            for e in reversed(extra):
                e.__exit__(None, None, None)
    return resp, stack


class TestRoutes:
    @pytest.mark.asyncio
    async def test_starting_a_preview_queues_discovery_and_adds_nothing(self, client):
        kb = _mock_kb()
        inserted = []

        def construct(**kwargs):
            p = _preview(uuid="pv-new", **kwargs)
            p.insert = AsyncMock(side_effect=lambda: inserted.append(p))
            return p

        delay = patch("app.tasks.kb_validation_tasks.crawl_preview_task.delay")
        add_urls = patch("app.tasks.kb_validation_tasks.add_urls_task.delay")
        ins = patch("app.models.knowledge.KBCrawlPreview", MagicMock(side_effect=construct))
        resp, (mock_delay, mock_add, _) = await _call(
            client, "POST", "/api/knowledge/kb-uuid-1/crawl_previews", kb,
            json={"urls": [START, START, ""], "max_crawl_pages": 99},
            extra=(delay, add_urls, ins),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["start_urls"] == [START]
        assert body["max_crawl_pages"] == 50
        mock_delay.assert_called_once_with(body["uuid"])
        mock_add.assert_not_called()
        assert len(inserted) == 1

    @pytest.mark.asyncio
    async def test_add_claims_the_preview_and_sends_only_listed_pages(self, client):
        kb = _mock_kb()
        preview = _preview(status="complete", pages=[
            knowledge_service._preview_page(START, START, "start"),
            knowledge_service._preview_page(f"{START}/a", START, "content"),
            knowledge_service._preview_page(f"{START}/b", START, "failed"),
        ])
        delay = patch("app.tasks.kb_validation_tasks.add_crawl_selection_task.delay")
        resp, (mock_delay,) = await _call(
            client, "POST", "/api/knowledge/kb-uuid-1/crawl_previews/pv-1/add", kb, preview,
            json={"urls": [f"{START}/a", f"{START}/b", "https://evil.example/x"]},
            extra=(delay,),
        )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "added": 1}
        assert preview.status == "adding"
        mock_delay.assert_called_once_with(kb.uuid, "pv-1", [f"{START}/a"])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["running", "adding", "added"])
    async def test_add_is_refused_until_the_preview_is_complete_and_only_once(self, client, status):
        preview = _preview(status=status, pages=[knowledge_service._preview_page(START, START, "start")])
        delay = patch("app.tasks.kb_validation_tasks.add_crawl_selection_task.delay")
        resp, (mock_delay,) = await _call(
            client, "POST", "/api/knowledge/kb-uuid-1/crawl_previews/pv-1/add", _mock_kb(), preview,
            json={"urls": [START]}, extra=(delay,),
        )
        assert resp.status_code == 409
        mock_delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_expired_preview_says_so(self, client):
        resp, _ = await _call(client, "GET", "/api/knowledge/kb-uuid-1/crawl_previews/gone", _mock_kb())
        assert resp.status_code == 404
        assert "expired" in resp.json()["detail"]
