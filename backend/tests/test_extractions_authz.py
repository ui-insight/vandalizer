"""Authorization tests for extraction routes."""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")
_ACTIVITY_ID = "507f1f77bcf86cd799439011"


def _make_user(user_id="user1"):
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
    from app.utils.security import hash_api_token

    user.api_token_hash = hash_api_token("test-api-key")
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
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


class TestSearchSetRouteAuthz:
    @pytest.mark.asyncio
    async def test_get_other_users_search_set_returns_404(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.extractions.access_control.get_authorized_search_set",
                new_callable=AsyncMock,
            ) as mock_get_search_set,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_search_set.return_value = None

            resp = await client.get("/api/extractions/search-sets/ss-1", cookies=cookies, headers=headers)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_sync_rejects_unauthorized_document(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        search_set = MagicMock()
        search_set.title = "Shared Extraction"

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.extractions.access_control.get_authorized_search_set",
                new_callable=AsyncMock,
            ) as mock_get_search_set,
            patch(
                "app.routers.extractions.access_control.get_team_access_context",
                new_callable=AsyncMock,
            ) as mock_team_access,
            patch(
                "app.routers.extractions.access_control.get_authorized_document",
                new_callable=AsyncMock,
            ) as mock_get_document,
            patch("app.routers.extractions.activity_service") as mock_activity,
            patch("app.routers.extractions.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_search_set.return_value = search_set
            mock_team_access.return_value = MagicMock()
            mock_get_document.return_value = None

            resp = await client.post(
                "/api/extractions/run-sync",
                json={
                    "search_set_uuid": "ss-1",
                    "document_uuids": ["doc-1"],
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert "document not found" in resp.json()["detail"].lower()
        mock_activity.activity_start.assert_not_called()
        mock_svc.run_extraction_sync.assert_not_called()


class TestExtractionStatusAuthz:
    @pytest.mark.asyncio
    async def test_status_uses_object_id_lookup_for_owned_activity(self, client):
        user = _make_user("api-user")
        activity = MagicMock()
        activity.status = "completed"
        activity.title = "Extraction Run"
        activity.started_at = None
        activity.finished_at = None
        activity.error = None
        activity.documents_touched = 2
        activity.result_snapshot = {"rows": 2}

        with (
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.activity_service.get_activity", new_callable=AsyncMock) as mock_get_activity,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_activity.return_value = activity

            resp = await client.get(
                f"/api/extractions/status/{_ACTIVITY_ID}",
                headers={"x-api-key": "test-api-key"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        lookup_id, lookup_user_id = mock_get_activity.await_args.args
        assert lookup_id == PydanticObjectId(_ACTIVITY_ID)
        assert lookup_user_id == "api-user"

    @pytest.mark.asyncio
    async def test_status_rejects_invalid_activity_id(self, client):
        user = _make_user("api-user")

        with (
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.extractions.activity_service.get_activity", new_callable=AsyncMock) as mock_get_activity,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get(
                "/api/extractions/status/not-an-object-id",
                headers={"x-api-key": "test-api-key"},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Activity not found"
        mock_get_activity.assert_not_awaited()
