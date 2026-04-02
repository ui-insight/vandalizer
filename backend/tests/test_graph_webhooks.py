"""Tests for app.routers.graph_webhooks — Graph webhook endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestGraphWebhook:
    @pytest.mark.asyncio
    async def test_validation_handshake(self, client):
        resp = await client.post(
            "/api/webhooks/graph?validationToken=abc123",
            headers={"X-CSRF-Token": "test"},
        )
        assert resp.status_code == 200
        assert resp.text == "abc123"

    @pytest.mark.asyncio
    async def test_no_notifications(self, client):
        resp = await client.post(
            "/api/webhooks/graph",
            json={"value": []},
            headers={"X-CSRF-Token": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_notifications"

    @pytest.mark.asyncio
    async def test_invalid_client_state_skipped(self, client):
        with patch("app.celery_app.celery_app") as mock_celery:
            resp = await client.post(
                "/api/webhooks/graph",
                json={"value": [{"clientState": "invalid", "resource": "/me/messages/1", "changeType": "created"}]},
                headers={"X-CSRF-Token": "test"},
            )
        assert resp.status_code == 200
        assert resp.json()["dispatched"] == 0


class TestGraphLifecycle:
    @pytest.mark.asyncio
    async def test_validation_handshake(self, client):
        resp = await client.post(
            "/api/webhooks/graph/lifecycle?validationToken=xyz",
            headers={"X-CSRF-Token": "test"},
        )
        assert resp.status_code == 200
        assert resp.text == "xyz"

    @pytest.mark.asyncio
    async def test_lifecycle_events(self, client):
        resp = await client.post(
            "/api/webhooks/graph/lifecycle",
            json={"value": [
                {"lifecycleEvent": "reauthorizationRequired", "subscriptionId": "sub1"},
                {"lifecycleEvent": "subscriptionRemoved", "subscriptionId": "sub2"},
                {"lifecycleEvent": "missed", "subscriptionId": "sub3"},
            ]},
            headers={"X-CSRF-Token": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
