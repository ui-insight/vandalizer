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
    async def test_download_calls_service_with_user(self, client):
        """Verify that the current user is passed to file_service.download_document."""
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

        # Should call download_document with user kwarg
        mock_svc.download_document.assert_called_once()
        call_kwargs = mock_svc.download_document.call_args
        assert call_kwargs.kwargs.get("user") is user

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


class TestFileDownloadRangeAndInline:
    """Cover the progressive-loading additions to /api/files/download."""

    @pytest.mark.asyncio
    async def test_download_advertises_accept_ranges_and_attachment(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        from app.services.file_service import DownloadResult

        result = DownloadResult(data=b"A" * 1024, extension="pdf", title="big.pdf")
        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.download_document = AsyncMock(return_value=result)

            resp = await client.get(
                "/api/files/download?docid=u",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.headers["accept-ranges"] == "bytes"
        # Default disposition stays `attachment` so the Download button still
        # triggers a save dialog.
        assert resp.headers["content-disposition"].startswith("attachment;")

    @pytest.mark.asyncio
    async def test_download_inline_query_param(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        from app.services.file_service import DownloadResult

        result = DownloadResult(data=b"%PDF-1.4\n", extension="pdf", title="x.pdf")
        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.download_document = AsyncMock(return_value=result)

            resp = await client.get(
                "/api/files/download?docid=u&inline=1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.headers["content-disposition"].startswith("inline;")

    @pytest.mark.asyncio
    async def test_download_range_request_returns_206(self, client):
        user = _make_user()
        cookies, headers = _auth_cookies()
        from app.services.file_service import DownloadResult

        body = bytes(range(256))  # 0..255
        result = DownloadResult(data=body, extension="pdf", title="x.pdf")
        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.download_document = AsyncMock(return_value=result)

            resp = await client.get(
                "/api/files/download?docid=u&inline=1",
                cookies=cookies,
                headers={**headers, "Range": "bytes=10-19"},
            )

        assert resp.status_code == 206
        assert resp.content == body[10:20]
        assert resp.headers["content-range"] == "bytes 10-19/256"
        assert resp.headers["accept-ranges"] == "bytes"


class TestRangeHeaderParser:
    """Unit tests for the `Range` header parser used by the download route."""

    def _parse(self, header: str, total: int):
        from app.routers.files import _parse_range_header
        return _parse_range_header(header, total)

    def test_basic_range(self):
        assert self._parse("bytes=0-99", 1000) == (0, 99)

    def test_open_ended_range(self):
        assert self._parse("bytes=500-", 1000) == (500, 999)

    def test_suffix_range(self):
        assert self._parse("bytes=-100", 1000) == (900, 999)

    def test_clamps_to_total(self):
        assert self._parse("bytes=100-9999", 1000) == (100, 999)

    def test_rejects_multi_range(self):
        # Multi-range responses aren't worth the complexity; fall back to 200.
        assert self._parse("bytes=0-99,200-299", 1000) is None

    def test_rejects_invalid(self):
        assert self._parse("bytes=abc", 1000) is None
        assert self._parse("bytes=-", 1000) is None
        assert self._parse("", 1000) is None
        assert self._parse("bytes=1000-2000", 1000) is None  # start beyond total


class TestFileDeleteAuth:
    @pytest.mark.asyncio
    async def test_delete_calls_service_with_user(self, client):
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
        assert call_kwargs.kwargs.get("user") is user

    @pytest.mark.asyncio
    async def test_delete_unauthenticated(self, client):
        resp = await client.delete("/api/files/test-uuid")
        # CSRF middleware runs before auth, so unauthenticated DELETE
        # gets 403 (CSRF) rather than 401 (auth)
        assert resp.status_code in (401, 403)


class TestBulkDownloadAuth:
    @pytest.mark.asyncio
    async def test_bulk_download_passes_user(self, client):
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

        # Should have been called for each doc with user
        assert mock_svc.download_document.call_count == 2
        for call in mock_svc.download_document.call_args_list:
            assert call.kwargs.get("user") is user


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
