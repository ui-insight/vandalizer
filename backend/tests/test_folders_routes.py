"""Integration tests for folders router (/api/folders).

All tests mock the database layer so they can run without MongoDB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser", current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = current_team
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


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_create_folder(self, client):
        """POST /api/folders/create creates a new folder."""
        user = _make_user()
        cookies, headers = _auth()

        mock_folder = MagicMock()
        mock_folder.id = "folder-id"
        mock_folder.uuid = "folder-uuid"
        mock_folder.title = "New Folder"
        mock_folder.parent_id = "0"
        mock_folder.is_shared_team_root = False
        mock_folder.team_id = None

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.folders.folder_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.create_folder = AsyncMock(return_value=mock_folder)

            resp = await client.post(
                "/api/folders/create",
                json={"name": "New Folder", "parent_id": "0", "space": "default"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New Folder"
        assert data["uuid"] == "folder-uuid"
        assert data["parent_id"] == "0"


class TestRenameFolder:
    @pytest.mark.asyncio
    async def test_rename_folder(self, client):
        """PATCH /api/folders/rename renames a folder."""
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.folders.folder_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.rename_folder = AsyncMock(return_value=True)

            resp = await client.patch(
                "/api/folders/rename",
                json={"uuid": "folder-uuid", "newName": "Renamed Folder"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_svc.rename_folder.assert_called_once_with("folder-uuid", "Renamed Folder")

    @pytest.mark.asyncio
    async def test_rename_nonexistent_folder(self, client):
        """PATCH /api/folders/rename for missing folder returns 404."""
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.folders.folder_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.rename_folder = AsyncMock(return_value=False)

            resp = await client.patch(
                "/api/folders/rename",
                json={"uuid": "nonexistent", "newName": "Whatever"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


class TestDeleteFolder:
    @pytest.mark.asyncio
    async def test_delete_folder(self, client):
        """DELETE /api/folders/{uuid} deletes a folder."""
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.folders.folder_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_folder = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/folders/folder-uuid-123",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_svc.delete_folder.assert_called_once_with("folder-uuid-123")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_folder(self, client):
        """DELETE /api/folders/{uuid} for missing folder returns 404."""
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.folders.folder_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_folder = AsyncMock(return_value=False)

            resp = await client.delete(
                "/api/folders/nonexistent",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_folder_unauthenticated(self, client):
        """DELETE /api/folders/{uuid} without auth returns 401 or 403 (CSRF)."""
        resp = await client.delete("/api/folders/some-uuid")
        assert resp.status_code in (401, 403)
