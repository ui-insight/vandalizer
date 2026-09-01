"""POST /api/extractions/search-sets/{uuid}/upload-template failure paths.

Attaching a PDF with no form fields used to be a dead end for the user: the
API answered 422 but the UI never surfaced it, and the file had already been
written over the previously attached template. Both halves are covered here —
the message has to be actionable, and nothing may touch disk before the PDF is
known to be usable.
"""

import secrets
from types import SimpleNamespace
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
    user.token_version = 0
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


def _reader_with_fields(fields):
    reader = MagicMock()
    reader.get_fields = MagicMock(return_value=fields)
    return MagicMock(return_value=reader)


async def _post_template(client, tmp_path, *, reader):
    """POST a PDF, with the upload dir pointed at tmp_path."""
    user = _make_user()
    cookies, headers = _auth()
    ss = MagicMock()
    ss.uuid = "ss-uuid-1"

    with (
        patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch("app.routers.extractions._get_search_set_or_404",
              new_callable=AsyncMock, return_value=ss),
        patch("app.config.Settings",
              MagicMock(return_value=SimpleNamespace(upload_dir=str(tmp_path)))),
        patch("PyPDF2.PdfReader", reader),
    ):
        MockUser.find_one = AsyncMock(return_value=user)
        return await client.post(
            "/api/extractions/search-sets/ss-uuid-1/upload-template",
            files={"file": ("form.pdf", b"%PDF-1.4 not-really-a-pdf", "application/pdf")},
            cookies=cookies,
            headers=headers,
        )


class TestUploadTemplateWithoutFormFields:
    @pytest.mark.asyncio
    async def test_explains_that_a_fillable_pdf_is_required(self, client, tmp_path):
        resp = await _post_template(client, tmp_path, reader=_reader_with_fields({}))

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "no form fields" in detail.lower()
        # Actionable: says what is needed, and names the other path on the same
        # screen that does work for a regular document.
        assert "fillable" in detail.lower()
        assert "From Document" in detail

    @pytest.mark.asyncio
    async def test_leaves_the_attached_template_untouched(self, client, tmp_path):
        existing = tmp_path / "ss-uuid-1_template.pdf"
        existing.write_bytes(b"%PDF-1.4 the-good-template")

        resp = await _post_template(client, tmp_path, reader=_reader_with_fields({}))

        assert resp.status_code == 422
        assert existing.read_bytes() == b"%PDF-1.4 the-good-template"

    @pytest.mark.asyncio
    async def test_unreadable_pdf_is_a_400_not_a_500(self, client, tmp_path):
        reader = MagicMock(side_effect=Exception("not a pdf"))

        resp = await _post_template(client, tmp_path, reader=reader)

        assert resp.status_code == 400
        assert "could not be read" in resp.json()["detail"].lower()
        assert list(tmp_path.iterdir()) == []
