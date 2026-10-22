"""Which queues have a live worker — and what /api/health says about it."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services import worker_status

ALL = worker_status.expected_queues()


@pytest.fixture(autouse=True)
def _fresh_cache():
    worker_status._cache = None
    yield
    worker_status._cache = None


class TestRouting:
    def test_the_preview_task_runs_on_the_workflows_queue(self):
        assert worker_status.queue_for("tasks.kb.preview_urls") == "workflows"

    def test_an_unrouted_task_runs_on_the_default_queue(self):
        assert worker_status.queue_for("tasks.nothing_routes_this") == "default"

    def test_every_routed_queue_is_expected(self):
        assert {"documents", "workflows", "uploads", "passive", "default"} <= ALL


class TestConsumingQueues:
    @pytest.mark.asyncio
    async def test_queues_come_from_the_workers_that_answered(self):
        with patch.object(worker_status, "_inspect_queues", return_value=frozenset({"documents"})):
            assert await worker_status.consuming_queues() == {"documents"}
            assert await worker_status.queue_has_worker("documents") is True
            assert await worker_status.queue_has_worker("workflows") is False

    @pytest.mark.asyncio
    async def test_a_broker_that_cannot_be_asked_is_unknown_not_down(self):
        with patch.object(worker_status, "_inspect_queues", side_effect=ConnectionError("refused")):
            assert await worker_status.consuming_queues() is None
            assert await worker_status.queue_has_worker("workflows") is None
            assert (await worker_status.worker_summary())["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_one_broadcast_serves_every_poll_within_the_cache_window(self):
        with patch.object(worker_status, "_inspect_queues", return_value=ALL) as inspect:
            for _ in range(5):
                await worker_status.consuming_queues()
        assert inspect.call_count == 1


class TestSummary:
    @pytest.mark.asyncio
    async def test_no_worker_answering_is_down_with_every_queue_missing(self):
        with patch.object(worker_status, "_inspect_queues", return_value=frozenset()):
            summary = await worker_status.worker_summary()
        assert summary["status"] == "down"
        assert set(summary["missing_queues"]) == ALL

    @pytest.mark.asyncio
    async def test_an_unserved_queue_is_down(self):
        with patch.object(worker_status, "_inspect_queues", return_value=ALL - {"workflows"}):
            summary = await worker_status.worker_summary()
        assert summary["status"] == "down"
        assert summary["missing_queues"] == ["workflows"]

    @pytest.mark.asyncio
    async def test_every_queue_served_is_ok(self):
        with patch.object(worker_status, "_inspect_queues", return_value=ALL):
            summary = await worker_status.worker_summary()
        assert summary == {"status": "ok", "queues": sorted(ALL), "missing_queues": []}


class TestHealthEndpoint:
    @pytest.fixture
    async def client(self):
        with patch("app.main.init_db", new_callable=AsyncMock):
            from app.main import app

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_dead_workers_are_reported_without_failing_the_api_probe(self, client):
        # Every dependency up, no worker: still 200, or a dead worker would get
        # a working API restarted.
        with patch("app.database.get_client") as get_client, \
             patch("redis.asyncio.Redis") as redis_cls, \
             patch("app.services.document_manager.get_chroma_client"), \
             patch.object(worker_status, "_inspect_queues", return_value=frozenset()):
            get_client.return_value.__getitem__.return_value.command = AsyncMock()
            redis_cls.return_value.ping = AsyncMock()
            redis_cls.return_value.aclose = AsyncMock()
            resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["workers"]["status"] == "down"
        assert "workflows" in body["workers"]["missing_queues"]

    @pytest.mark.asyncio
    async def test_workers_are_not_asked_about_when_redis_is_down(self, client):
        with patch("redis.asyncio.Redis") as redis_cls, \
             patch.object(worker_status, "_inspect_queues") as inspect:
            redis_cls.return_value.ping = AsyncMock(side_effect=ConnectionError("refused"))
            resp = await client.get("/api/health")
        body = resp.json()
        assert body["checks"]["redis"].startswith("error")
        assert body["workers"]["status"] == "unknown"
        inspect.assert_not_called()
