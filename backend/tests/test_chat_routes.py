"""Integration tests for chat router (/api/chat).

All tests mock the database layer so they can run without MongoDB.
"""

import datetime
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.demo_status = None
    return user


def _auth(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestChatAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self, client):
        """Unauthenticated GET /api/chat/conversations returns 401."""
        resp = await client.get("/api/chat/conversations")
        assert resp.status_code == 401


class TestListConversations:
    @pytest.mark.asyncio
    async def test_returns_conversation_list(self, client):
        """GET /api/chat/conversations returns the user's conversations."""
        user = _make_user()
        cookies, headers = _auth()

        mock_conv = MagicMock()
        mock_conv.uuid = "conv-uuid-1"
        mock_conv.title = "My Chat"
        mock_conv.messages = ["msg1", "msg2"]
        mock_conv.created_at = datetime.datetime(2025, 1, 1, 12, 0, 0)
        mock_conv.updated_at = datetime.datetime(2025, 1, 2, 12, 0, 0)

        # Build the chained query mock: .find().sort().limit().to_list()
        chain = MagicMock()
        chain.to_list = AsyncMock(return_value=[mock_conv])
        sort_mock = MagicMock(return_value=chain)
        sort_mock.limit = MagicMock(return_value=chain)
        chain.limit = MagicMock(return_value=chain)

        find_result = MagicMock()
        find_result.sort = MagicMock(return_value=chain)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.chat.ChatConversation") as MockConv:
            MockUser.find_one = AsyncMock(return_value=user)
            MockConv.find = MagicMock(return_value=find_result)
            MockConv.user_id = "user_id"
            MockConv.updated_at = MagicMock()  # supports unary negation in sort()

            resp = await client.get(
                "/api/chat/conversations",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["uuid"] == "conv-uuid-1"
        assert data[0]["title"] == "My Chat"
        assert data[0]["message_count"] == 2


class TestChatActivityAuthz:
    @pytest.mark.asyncio
    async def test_chat_rejects_foreign_activity_id(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.chat.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.chat.activity_service.get_activity", new_callable=AsyncMock) as mock_get_activity:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_team_access.return_value = MagicMock()
            mock_get_activity.return_value = None

            resp = await client.post(
                "/api/chat",
                json={
                    "message": "resume this",
                    "activity_id": "507f1f77bcf86cd799439011",
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Activity not found"

    @pytest.mark.asyncio
    async def test_add_link_rejects_foreign_activity_id(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.chat.activity_service.get_activity", new_callable=AsyncMock) as mock_get_activity:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_activity.return_value = None

            resp = await client.post(
                "/api/chat/add-link",
                json={
                    "link": "https://example.com",
                    "current_activity_id": "507f1f77bcf86cd799439011",
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Activity not found"

    @pytest.mark.asyncio
    async def test_add_document_rejects_foreign_activity_id(self, client):
        user = _make_user("user1")
        cookies, headers = _auth("user1")

        with patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.chat.activity_service.get_activity", new_callable=AsyncMock) as mock_get_activity:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_activity.return_value = None

            resp = await client.post(
                "/api/chat/add-document",
                data={"current_activity_id": "507f1f77bcf86cd799439011"},
                files={"files": ("note.txt", b"hello", "text/plain")},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Activity not found"
