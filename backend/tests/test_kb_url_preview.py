"""Previewing URLs before they enter a knowledge base — unit level.

The end-to-end flow (fetch, crawl, commit on a real database) is covered in
tests/integration/test_tier2_kb_url_preview.py; this file covers the verdicts
and the routes' guards, which run in every CI pass.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# A preview that is stuck says so (support ticket: "Fetching pages…" spun for
# 10+ minutes with no pages and no error, until the 2-hour TTL removed it).
# ---------------------------------------------------------------------------

import datetime as _dt

NOW = _dt.datetime(2026, 10, 20, 12, 0, tzinfo=_dt.timezone.utc)


def _running(created_ago, started_ago=None, progress_ago=None):
    # Naive, as Mongo hands them back.
    def at(ago):
        return None if ago is None else (NOW - _dt.timedelta(seconds=ago)).replace(tzinfo=None)

    return SimpleNamespace(
        uuid="pv-1", status="running", error_message=None,
        created_at=at(created_ago), started_at=at(started_ago), progress_at=at(progress_ago),
    )


class _FakeCollection:
    """The preview collection, as the atomic updates see it."""

    def __init__(self, doc=None):
        self.doc = doc
        self.updates = []

    async def find_one(self, query, projection=None):
        return self.doc

    async def update_one(self, query, update):
        self.updates.append((query, update))
        matched = self.doc is not None and all(
            self.doc.get(k) == v for k, v in query.items()
        )
        if matched:
            self.doc.update(update["$set"])
        return SimpleNamespace(modified_count=1 if matched else 0)


class TestStallDetection:
    @pytest.mark.asyncio
    async def test_a_preview_no_worker_has_picked_up_is_reported_after_a_minute(self):
        coll = _FakeCollection()
        with patch.object(kb_url_preview, "_collection", return_value=coll), \
             patch("app.services.worker_status.queue_has_worker", AsyncMock(return_value=True)):
            assert await kb_url_preview.check_progress(_running(30), now=NOW) is None
            msg = await kb_url_preview.check_progress(_running(61), now=NOW)
        assert msg == kb_url_preview.NOT_STARTED_MESSAGE

    @pytest.mark.asyncio
    async def test_a_queue_with_no_worker_says_so_instead_of_busy(self):
        coll = _FakeCollection()
        has_worker = AsyncMock(return_value=False)
        with patch.object(kb_url_preview, "_collection", return_value=coll), \
             patch("app.services.worker_status.queue_has_worker", has_worker):
            assert await kb_url_preview.check_progress(_running(30), now=NOW) is None
            msg = await kb_url_preview.check_progress(_running(61), now=NOW)
        assert msg == kb_url_preview.NO_WORKERS_MESSAGE
        # Asked about the queue the preview task is routed to, and only once
        # the minute was up.
        has_worker.assert_awaited_once_with("workflows")

    @pytest.mark.asyncio
    async def test_an_unanswerable_worker_check_falls_back_to_busy(self):
        coll = _FakeCollection()
        with patch.object(kb_url_preview, "_collection", return_value=coll), \
             patch("app.services.worker_status.queue_has_worker", AsyncMock(return_value=None)):
            msg = await kb_url_preview.check_progress(_running(61), now=NOW)
        assert msg == kb_url_preview.NOT_STARTED_MESSAGE

    @pytest.mark.asyncio
    async def test_a_started_preview_is_judged_by_its_last_page(self):
        coll = _FakeCollection()
        with patch.object(kb_url_preview, "_collection", return_value=coll):
            # Started long ago but a page just landed: fine.
            assert await kb_url_preview.check_progress(_running(600, 590, 10), now=NOW) is None
            msg = await kb_url_preview.check_progress(_running(600, 590, 91), now=NOW)
        assert msg == kb_url_preview.NO_PROGRESS_MESSAGE

    @pytest.mark.asyncio
    async def test_a_preview_past_the_task_limit_is_settled_as_failed(self):
        preview = _running(4000, 3990, 1900)
        coll = _FakeCollection({"uuid": "pv-1", "status": "running"})
        with patch.object(kb_url_preview, "_collection", return_value=coll):
            msg = await kb_url_preview.check_progress(preview, now=NOW)
        assert msg is None
        assert preview.status == "error"
        assert preview.error_message == kb_url_preview.DEAD_MESSAGE
        assert coll.doc["status"] == "error"

    @pytest.mark.asyncio
    async def test_a_finished_preview_is_never_stalled(self):
        preview = _running(4000)
        preview.status = "ready"
        coll = _FakeCollection()
        with patch.object(kb_url_preview, "_collection", return_value=coll):
            assert await kb_url_preview.check_progress(preview, now=NOW) is None
        assert coll.updates == []


class TestRunPreviewClaimAndCancel:
    @pytest.mark.asyncio
    async def test_a_preview_canceled_while_queued_is_not_fetched(self):
        coll = _FakeCollection({"uuid": "pv-1", "status": "canceled", "started_at": None})
        fetch = AsyncMock()
        with patch.object(kb_url_preview, "_collection", return_value=coll), \
             patch.object(kb_url_preview.ks, "fetch_source_page", fetch):
            await kb_url_preview.run_preview("pv-1")
        fetch.assert_not_called()
        assert coll.doc["status"] == "canceled"

    @pytest.mark.asyncio
    async def test_cancel_stops_before_the_next_page_and_is_not_overwritten(self):
        doc = {"uuid": "pv-1", "status": "running", "started_at": None}
        coll = _FakeCollection(doc)
        preview = SimpleNamespace(
            uuid="pv-1", knowledge_base_uuid="kb-1", crawl_enabled=False,
            urls=["https://example.gov/a", "https://example.gov/b"],
            expires_at=NOW,
        )
        fetched = []

        async def fetch(url):
            fetched.append(url)
            doc["status"] = "canceled"  # the user cancels during the first page
            raise RuntimeError("boom")

        recorded = []

        async def record(self, url, verdict, **fields):
            recorded.append((url, verdict))

        with patch.object(kb_url_preview, "_collection", return_value=coll), \
             patch.object(kb_url_preview, "KBUrlPreview", MagicMock(find_one=AsyncMock(return_value=preview))), \
             patch.object(kb_url_preview, "_url_in_kb", AsyncMock(return_value=False)), \
             patch.object(kb_url_preview._Recorder, "record", record), \
             patch.object(kb_url_preview.ks, "fetch_source_page", fetch):
            await kb_url_preview.run_preview("pv-1")
        assert fetched == ["https://example.gov/a"]
        assert doc["status"] == "canceled"

    @pytest.mark.asyncio
    async def test_cancel_only_stops_a_running_preview(self):
        coll = _FakeCollection({"uuid": "pv-1", "status": "ready"})
        with patch.object(kb_url_preview, "_collection", return_value=coll):
            assert await kb_url_preview.cancel_preview(SimpleNamespace(uuid="pv-1")) is False
        assert coll.doc["status"] == "ready"


class TestStallRoutes:
    @pytest.mark.asyncio
    async def test_poll_carries_the_stall_message(self, client):
        cookies, headers = _auth()
        _, patches = _routes()
        preview = SimpleNamespace(uuid="pv-1", status="running", error_message=None, crawl_enabled=False)
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "get_preview", AsyncMock(return_value=preview)), \
             patch.object(kb_url_preview, "check_progress",
                          AsyncMock(return_value=kb_url_preview.NOT_STARTED_MESSAGE)), \
             patch.object(kb_url_preview, "list_pages", AsyncMock(return_value=[])):
            resp = await client.get(
                "/api/knowledge/kb-uuid-1/add_urls/preview/pv-1", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["stalled"] is True
        assert body["stall_message"] == kb_url_preview.NOT_STARTED_MESSAGE
        assert body["workers_down"] is False

    @pytest.mark.asyncio
    async def test_poll_says_when_no_worker_can_run_it(self, client):
        cookies, headers = _auth()
        _, patches = _routes()
        preview = SimpleNamespace(uuid="pv-1", status="running", error_message=None, crawl_enabled=False)
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "get_preview", AsyncMock(return_value=preview)), \
             patch.object(kb_url_preview, "check_progress",
                          AsyncMock(return_value=kb_url_preview.NO_WORKERS_MESSAGE)), \
             patch.object(kb_url_preview, "list_pages", AsyncMock(return_value=[])):
            resp = await client.get(
                "/api/knowledge/kb-uuid-1/add_urls/preview/pv-1", cookies=cookies, headers=headers,
            )
        body = resp.json()
        assert body["stalled"] is True
        assert body["workers_down"] is True

    @pytest.mark.asyncio
    async def test_cancel_route_cancels_the_callers_preview(self, client):
        cookies, headers = _auth()
        _, patches = _routes()
        preview = SimpleNamespace(uuid="pv-1", status="running")
        cancel = AsyncMock(return_value=True)
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(kb_url_preview, "get_preview", AsyncMock(return_value=preview)), \
             patch.object(kb_url_preview, "cancel_preview", cancel):
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/add_urls/preview/pv-1/cancel", cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "canceled": True}
        cancel.assert_awaited_once_with(preview)
