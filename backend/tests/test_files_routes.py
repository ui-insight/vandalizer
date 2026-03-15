"""Integration tests for files router endpoints.

Verifies ownership checks, path traversal protection, and auth enforcement.
"""

import secrets
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser", **overrides):
    defaults = {
        "id": "fake-id",
        "user_id": user_id,
        "email": f"{user_id}@example.com",
        "name": "Test User",
        "is_admin": False,
        "is_examiner": False,
        "current_team": None,
        "is_demo_user": False,
        "demo_status": None,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _auth_cookies(user_id="testuser"):
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


class TestFileDownloadAuth:
    @pytest.mark.asyncio
    async def test_download_unauthenticated(self, client):
        resp = await client.get("/api/files/download?docid=test-uuid")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_download_calls_service_with_user_id(self, client):
        """Verify that user_id is passed to file_service.download_document."""
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.download_document = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/files/download?docid=test-uuid",
                cookies=cookies,
                headers=headers,
            )

        # Should call download_document with user_id kwarg
        mock_svc.download_document.assert_called_once()
        call_kwargs = mock_svc.download_document.call_args
        assert call_kwargs.kwargs.get("user_id") == "testuser"

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.download_document = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/files/download?docid=nonexistent",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404


class TestFileDeleteAuth:
    @pytest.mark.asyncio
    async def test_delete_calls_service_with_user_id(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_document = AsyncMock(return_value=True)

            resp = await client.delete(
                "/api/files/test-uuid",
                cookies=cookies,
                headers=headers,
            )

        mock_svc.delete_document.assert_called_once()
        call_kwargs = mock_svc.delete_document.call_args
        assert call_kwargs.kwargs.get("user_id") == "testuser"

    @pytest.mark.asyncio
    async def test_delete_unauthenticated(self, client):
        resp = await client.delete("/api/files/test-uuid")
        # CSRF middleware runs before auth, so unauthenticated DELETE
        # gets 403 (CSRF) rather than 401 (auth)
        assert resp.status_code in (401, 403)


class TestBulkDownloadAuth:
    @pytest.mark.asyncio
    async def test_bulk_download_passes_user_id(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.download_document = AsyncMock(return_value=None)

            resp = await client.post(
                "/api/files/download-bulk",
                json={"doc_ids": ["uuid-1", "uuid-2"]},
                cookies=cookies,
                headers=headers,
            )

        # Should have been called for each doc with user_id
        assert mock_svc.download_document.call_count == 2
        for call in mock_svc.download_document.call_args_list:
            assert call.kwargs.get("user_id") == "testuser"


class TestPathTraversal:
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self):
        """_safe_resolve rejects paths that escape the upload directory."""
        from app.services.file_service import _safe_resolve

        settings = Settings(upload_dir="/tmp/test-uploads")
        assert _safe_resolve(settings, "../../../etc/passwd") is None
        assert _safe_resolve(settings, "../../secret.txt") is None

    @pytest.mark.asyncio
    async def test_normal_path_allowed(self, tmp_path):
        from app.services.file_service import _safe_resolve

        # Create a real file to resolve
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        test_file = upload_dir / "user1" / "doc.pdf"
        test_file.parent.mkdir()
        test_file.write_text("test")

        settings = Settings(upload_dir=str(upload_dir))
        result = _safe_resolve(settings, "user1/doc.pdf")
        assert result is not None
        assert result.exists()
