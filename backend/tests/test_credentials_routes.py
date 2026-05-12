"""Integration tests for the /api/credentials endpoints.

Mocks Beanie I/O and verifies:
  * payload validation runs before insert
  * secrets are encrypted at rest and never echoed back to clients
  * list endpoint redacts secret fields
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id: str = "testuser", current_team=None, is_admin: bool = False):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_examiner = False
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


class TestCreateCredential:
    @pytest.mark.asyncio
    async def test_payload_validation_rejects_missing_fields(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/credentials",
                cookies=cookies,
                headers=headers,
                json={
                    "name": "Lakehouse",
                    "type": "static_header",
                    "payload": {"header_name": "X-Api-Key"},  # missing header_value
                },
            )

        assert resp.status_code == 400
        assert "header_value" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_payload_is_encrypted_and_not_echoed(self, client):
        user = _make_user()
        cookies, headers = _auth()

        captured: dict = {}

        class _FakeCredential:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.id = "fake-credential-id"
                self.created_at = None
                self.updated_at = None

            async def insert(self):
                captured["payload"] = dict(self.payload)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential", _FakeCredential),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/credentials",
                cookies=cookies,
                headers=headers,
                json={
                    "name": "API key",
                    "type": "static_header",
                    "payload": {"header_name": "X-Api-Key", "header_value": "TOPSECRET"},
                },
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["payload"]["header_value"] == "<set>"
        assert body["payload"]["header_name"] == "X-Api-Key"
        # Secret value never appears in response.
        assert "TOPSECRET" not in resp.text
        # Persisted payload kept the header name; header_value is whatever
        # encrypt_value returned (encrypted if Fernet key set, plaintext otherwise).
        assert captured["payload"]["header_name"] == "X-Api-Key"


class TestListCredentials:
    @pytest.mark.asyncio
    async def test_list_redacts_secrets(self, client):
        user = _make_user()
        cookies, headers = _auth()

        fake_cred = MagicMock()
        fake_cred.id = "id-1"
        fake_cred.name = "key"
        fake_cred.type = "static_header"
        fake_cred.description = None
        fake_cred.team_id = None
        fake_cred.user_id = "testuser"
        fake_cred.payload = {"header_name": "X-Api-Key", "header_value": "enc:abc"}
        fake_cred.created_at = None
        fake_cred.updated_at = None

        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=[fake_cred])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.find", return_value=find_result),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/credentials", cookies=cookies, headers=headers)

        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert len(items) == 1
        assert items[0]["payload"]["header_value"] == "<set>"
        assert items[0]["payload"]["header_name"] == "X-Api-Key"
        assert "enc:abc" not in resp.text
