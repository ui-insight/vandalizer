"""Authorization and catalog coverage for verification routes."""

import json
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(
    user_id: str = "testuser",
    *,
    is_admin: bool = False,
    is_examiner: bool = False,
    current_team=None,
):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = is_examiner
    user.current_team = current_team
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


class TestVerificationRouteAuthz:
    @pytest.mark.asyncio
    async def test_queue_requires_examiner_access(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.verification.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/verification/queue", cookies=cookies, headers=headers)

        assert resp.status_code == 403
        mock_svc.list_queue.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_rejects_unauthorized_workflow(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.verification.access_control.get_authorized_workflow",
                new_callable=AsyncMock,
            ) as mock_get_workflow,
            patch("app.routers.verification.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_workflow.return_value = None

            resp = await client.post(
                "/api/verification/submit",
                json={"item_kind": "workflow", "item_id": "wf-1"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Item not found"
        mock_svc.submit_for_verification.assert_not_called()

    @pytest.mark.asyncio
    async def test_regular_user_cannot_view_other_users_request(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.verification.svc.get_request", new_callable=AsyncMock) as mock_get_request,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_request.return_value = {
                "uuid": "req-1",
                "submitter_user_id": "owner",
            }

            resp = await client.get("/api/verification/req-1", cookies=cookies, headers=headers)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submitter_can_view_own_request(self, client):
        user = _make_user("owner")
        cookies, headers = _auth("owner")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "owner", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.verification.svc.get_request", new_callable=AsyncMock) as mock_get_request,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_request.return_value = {
                "uuid": "req-1",
                "submitter_user_id": "owner",
            }

            resp = await client.get("/api/verification/req-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["uuid"] == "req-1"

    @pytest.mark.asyncio
    async def test_remove_from_collection_requires_examiner_access(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.verification.svc") as mock_svc,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.delete(
                "/api/verification/collections/507f1f77bcf86cd799439011/items/item-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        mock_svc.remove_from_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_verified_metadata_requires_item_visibility(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.verification.access_control.get_authorized_search_set_by_id",
                new_callable=AsyncMock,
            ) as mock_get_search_set,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_search_set.return_value = None

            resp = await client.get(
                "/api/verification/verified/search_set/507f1f77bcf86cd799439011/metadata",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


class TestCatalogRoutes:
    @pytest.mark.asyncio
    async def test_examiner_can_preview_catalog_import(self, client):
        user = _make_user("reviewer", is_examiner=True)
        cookies, headers = _auth("reviewer")
        payload = {
            "vandalizer_export": True,
            "schema_version": 1,
            "export_type": "catalog",
            "items": [
                {
                    "item_kind": "workflow",
                    "metadata": {"display_name": "Admissions Intake", "description": "Review workflow"},
                    "definition": {"name": "Admissions Intake"},
                }
            ],
        }

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "reviewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/verification/catalog/preview-import",
                files={"file": ("catalog.json", json.dumps(payload), "application/json")},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["items"] == [
            {
                "index": 0,
                "item_kind": "workflow",
                "name": "Admissions Intake",
                "description": "Review workflow",
                "quality_tier": None,
                "quality_grade": None,
            }
        ]

    @pytest.mark.asyncio
    async def test_catalog_import_uses_selected_indices_and_optional_space(self, client):
        user = _make_user("reviewer", is_examiner=True)
        cookies, headers = _auth("reviewer")
        payload = {
            "vandalizer_export": True,
            "schema_version": 1,
            "export_type": "catalog",
            "items": [{"item_kind": "workflow", "metadata": {}, "definition": {"name": "Flow"}}],
        }

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "reviewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.services.export_import_service.import_catalog_items",
                new_callable=AsyncMock,
            ) as mock_import_catalog,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_import_catalog.return_value = [{"kind": "workflow", "id": "wf-1", "name": "Flow"}]

            resp = await client.post(
                "/api/verification/catalog/import",
                files={"file": ("catalog.json", json.dumps(payload), "application/json")},
                data={"selected_indices": "[0]"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["imported"] == [{"kind": "workflow", "id": "wf-1", "name": "Flow"}]
        assert mock_import_catalog.await_count == 1
        assert mock_import_catalog.await_args.args[1] == [0]
        assert mock_import_catalog.await_args.args[2] == "reviewer"
        assert mock_import_catalog.await_args.kwargs == {"space": None, "team_id": None}

    @pytest.mark.asyncio
    async def test_catalog_export_requires_examiner_access(self, client):
        user = _make_user("viewer")
        cookies, headers = _auth("viewer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "viewer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/verification/catalog/export", cookies=cookies, headers=headers)

        assert resp.status_code == 403
