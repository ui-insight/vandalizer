"""Integration tests for the graph_webhooks router (app.routers.graph_webhooks).

Verifies validation token echo, clientState validation, and task dispatch.
"""

import secrets
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


class TestValidationTokenHandshake:
    @pytest.mark.asyncio
    async def test_validation_token_echoed(self, client):
        """POST with validationToken query param echoes the token as text/plain."""
        # The CSRF middleware exempts /api/webhooks/ prefixes
        resp = await client.post(
            "/api/webhooks/graph?validationToken=test-token-12345",
        )

        assert resp.status_code == 200
        assert resp.text == "test-token-12345"
        assert "text/plain" in resp.headers["content-type"]


class TestNotificationDispatch:
    @pytest.mark.asyncio
    async def test_valid_client_state_dispatches_task(self, client):
        """POST with valid clientState dispatches a Celery task."""
        # Use IDs that are 24-36 chars (valid ObjectId/UUID length)
        user_id = "aabbccdd11223344aabbccdd"  # 24 chars
        config_id = "aabbccdd11223344aabbccdd"  # 24 chars

        body = {
            "value": [
                {
                    "clientState": f"vandalizer:{user_id}:{config_id}",
                    "resource": "me/messages/abc123",
                    "changeType": "created",
                }
            ]
        }

        with patch("app.celery_app.celery_app") as mock_celery:
            resp = await client.post(
                "/api/webhooks/graph",
                json=body,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dispatched"] == 1
        mock_celery.send_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_client_state_format_skipped(self, client):
        """POST with invalid clientState format skips the notification."""
        body = {
            "value": [
                {
                    "clientState": "badformat",
                    "resource": "me/messages/abc123",
                    "changeType": "created",
                }
            ]
        }

        with patch("app.celery_app.celery_app") as mock_celery:
            resp = await client.post(
                "/api/webhooks/graph",
                json=body,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dispatched"] == 0
        mock_celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_short_ids_skipped(self, client):
        """POST with clientState where IDs are too short is skipped."""
        # IDs must be 24-36 chars; these are only 8 chars but match [a-f0-9]
        body = {
            "value": [
                {
                    "clientState": "vandalizer:aabb0011:ccdd2233",
                    "resource": "me/messages/abc123",
                    "changeType": "created",
                }
            ]
        }

        with patch("app.celery_app.celery_app") as mock_celery:
            resp = await client.post(
                "/api/webhooks/graph",
                json=body,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dispatched"] == 0
        mock_celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_drive_item_resource_dispatched(self, client):
        """Drive item resource dispatches ingest_drive_item task."""
        user_id = "aabbccdd11223344aabbccdd"
        config_id = "aabbccdd11223344aabbccdd"

        body = {
            "value": [
                {
                    "clientState": f"vandalizer:{user_id}:{config_id}",
                    "resource": "me/drive/items/abc123",
                    "changeType": "updated",
                }
            ]
        }

        with patch("app.celery_app.celery_app") as mock_celery:
            resp = await client.post(
                "/api/webhooks/graph",
                json=body,
            )

        assert resp.status_code == 200
        assert resp.json()["dispatched"] == 1
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "tasks.passive.ingest_drive_item"


class TestMalformedBody:
    @pytest.mark.asyncio
    async def test_malformed_json_returns_400(self, client):
        """POST with malformed JSON body returns 400."""
        resp = await client.post(
            "/api/webhooks/graph",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )

        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["detail"]
