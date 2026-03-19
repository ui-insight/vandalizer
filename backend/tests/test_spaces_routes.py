"""Authorization tests for legacy spaces routes."""

import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id: str = "testuser"):
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


def _auth(user_id: str = "testuser"):
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


class _UserField:
    def __eq__(self, other):
        return ("user_eq", other)


class TestSpacesRouteAuthz:
    @pytest.mark.asyncio
    async def test_list_spaces_filters_to_current_user(self, client):
        user = _make_user("alice")
        cookies, headers = _auth("alice")
        query = MagicMock()
        query.to_list = AsyncMock(return_value=[SimpleNamespace(id="1", uuid="space-1", title="Alice", user="alice")])

        class MockSpaceModel:
            user = _UserField()

            @staticmethod
            def find(arg):
                assert arg == ("user_eq", "alice")
                return query

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "alice", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.services.space_service.Space", MockSpaceModel),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/spaces/", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json() == [{"id": "1", "uuid": "space-1", "title": "Alice", "user": "alice"}]

    @pytest.mark.asyncio
    async def test_update_other_users_space_returns_404(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        space = SimpleNamespace(uuid="space-1", title="Owner Space", user="owner", save=AsyncMock())

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.services.space_service.Space") as MockSpace,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockSpace.find_one = AsyncMock(return_value=space)

            resp = await client.patch(
                "/api/spaces/space-1",
                json={"title": "Renamed"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        space.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_other_users_space_returns_404(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")
        space = SimpleNamespace(uuid="space-1", title="Owner Space", user="owner", delete=AsyncMock())

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.services.space_service.Space") as MockSpace,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockSpace.find_one = AsyncMock(return_value=space)

            resp = await client.delete(
                "/api/spaces/space-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        space.delete.assert_not_awaited()
