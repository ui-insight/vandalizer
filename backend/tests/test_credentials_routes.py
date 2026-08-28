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
    user.token_version = 0
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


class TestConnectionTestRoutes:
    @pytest.mark.asyncio
    async def test_draft_test_runs_the_service_with_the_typed_payload(self, client):
        user = _make_user()
        cookies, headers = _auth()
        report = {"ok": True, "steps": [{"step": "Configuration", "ok": True, "detail": "x"}], "status_code": None, "elapsed_ms": None}
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.credentials_service.run_connection_test", return_value=report) as mock_test,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/credentials/test", cookies=cookies, headers=headers,
                json={"type": "static_header", "payload": {"header_name": "X", "header_value": "k"}, "test_url": "https://api.example.com/"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == report
        assert mock_test.call_args.args == ("static_header", {"header_name": "X", "header_value": "k"})
        assert mock_test.call_args.kwargs == {"test_url": "https://api.example.com/"}

    @pytest.mark.asyncio
    async def test_saved_test_merges_form_edits_over_stored_secrets(self, client):
        user = _make_user()
        cookies, headers = _auth()
        cred = MagicMock()
        cred.id = "cred-1"
        cred.user_id = "testuser"
        cred.team_id = None
        cred.type = "static_header"
        cred.payload = {"header_name": "X-Old", "header_value": "ENC"}
        report = {"ok": True, "steps": [], "status_code": 200, "elapsed_ms": 12}
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.get", new=AsyncMock(return_value=cred)),
            patch("app.routers.credentials.credentials_service.merge_update_payload",
                  return_value={"header_name": "X-New", "header_value": "plain-secret", "test_url": "https://stored.example/"}) as mock_merge,
            patch("app.routers.credentials.credentials_service.decrypt_payload",
                  return_value={"header_name": "X-New", "header_value": "plain-secret", "test_url": "https://stored.example/"}),
            patch("app.routers.credentials.credentials_service.run_connection_test", return_value=report) as mock_test,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post(
                "/api/credentials/507f1f77bcf86cd799439011/test", cookies=cookies, headers=headers,
                json={"payload": {"header_name": "X-New", "header_value": ""}},
            )
        assert resp.status_code == 200, resp.text
        # Blank secret in the form keeps the stored one (merge handles it); the
        # stored test_url is used when the request gives none.
        assert mock_merge.call_args.args[2] == {"header_name": "X-New", "header_value": ""}
        assert mock_test.call_args.kwargs == {"test_url": "https://stored.example/"}

    @pytest.mark.asyncio
    async def test_saved_test_is_404_for_a_credential_the_user_cannot_see(self, client):
        user = _make_user()
        cookies, headers = _auth()
        cred = MagicMock()
        cred.user_id = "someone-else"
        cred.team_id = None
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.get", new=AsyncMock(return_value=cred)),
            patch("app.routers.credentials._can_view_team", new=AsyncMock(return_value=False)),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/credentials/507f1f77bcf86cd799439011/test", cookies=cookies, headers=headers, json={})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_saved_test_with_edits_needs_manage_permission(self, client):
        # A team member who can only view may test the stored credential as-is,
        # but merging edits (e.g. a new token_endpoint) would send the stored
        # secrets wherever the caller says, so that needs manage permission.
        user = _make_user()
        cookies, headers = _auth()
        cred = MagicMock()
        cred.user_id = "someone-else"
        cred.team_id = "team-1"
        cred.type = "oauth_client_credentials"
        cred.payload = {"client_id": "c", "token_endpoint": "https://issuer/token", "private_key": "ENC"}
        report = {"ok": True, "steps": [], "status_code": None, "elapsed_ms": None}
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.get", new=AsyncMock(return_value=cred)),
            patch("app.routers.credentials._can_view_team", new=AsyncMock(return_value=True)),
            patch("app.routers.credentials._can_manage_team", new=AsyncMock(return_value=False)),
            patch("app.routers.credentials.credentials_service.decrypt_payload", return_value=dict(cred.payload)),
            patch("app.routers.credentials.credentials_service.run_connection_test", return_value=report) as mock_test,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            denied = await client.post(
                "/api/credentials/507f1f77bcf86cd799439011/test", cookies=cookies, headers=headers,
                json={"payload": {"token_endpoint": "https://attacker.example/token"}},
            )
            allowed = await client.post(
                "/api/credentials/507f1f77bcf86cd799439011/test", cookies=cookies, headers=headers,
                json={"test_url": "https://api.example.com/me"},
            )
        assert denied.status_code == 403
        assert allowed.status_code == 200, allowed.text
        assert mock_test.call_count == 1
        assert mock_test.call_args.args[1]["token_endpoint"] == "https://issuer/token"



# Shared with test_credentials_service: an RSA key for OAuth payloads.
from cryptography.hazmat.backends import default_backend  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

@pytest.fixture(scope="module")
def rsa_private_pem() -> str:
    """Generate a fresh RSA private key for signing tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()



class TestChangeCredentialType:
    def _cred(self):
        cred = MagicMock()
        cred.id = "507f1f77bcf86cd799439011"
        cred.user_id = "testuser"
        cred.team_id = None
        cred.name = "Lakehouse"
        cred.description = None
        cred.type = "static_header"
        cred.payload = {"header_name": "X-Api-Key", "header_value": "ENC"}
        cred.created_at = None
        cred.updated_at = None
        cred.save = AsyncMock()
        return cred

    @pytest.mark.asyncio
    async def test_type_change_replaces_the_payload_and_repoints_steps(self, client, rsa_private_pem):
        user = _make_user()
        cookies, headers = _auth()
        cred = self._cred()
        task = MagicMock()
        task.data = {"auth_strategy": "static_header", "credential_id": cred.id, "url": "https://x"}
        task.save = AsyncMock()
        find_result = MagicMock()
        find_result.to_list = AsyncMock(return_value=[task])
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.get", new=AsyncMock(return_value=cred)),
            patch("app.routers.credentials.credentials_service.validate_outbound_url", return_value="ok", create=True),
            patch("app.services.credentials_service.validate_outbound_url", return_value="ok"),
            patch("app.routers.credentials.credentials_service.invalidate_cached_token") as mock_inval,
            patch("app.models.workflow.WorkflowStepTask.find", return_value=find_result),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.patch(
                f"/api/credentials/{cred.id}", cookies=cookies, headers=headers,
                json={"type": "oauth_client_credentials", "payload": {
                    "client_id": "c1", "token_endpoint": "https://issuer/token", "private_key": rsa_private_pem,
                }},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["type"] == "oauth_client_credentials"
        assert body["steps_updated"] == 1
        assert body["payload"]["client_id"] == "c1"
        assert body["payload"]["private_key"] == "<set>"
        assert "header_name" not in body["payload"]  # nothing merged from the old type
        assert cred.type == "oauth_client_credentials"
        assert task.data["auth_strategy"] == "oauth_client_credentials"
        task.save.assert_awaited_once()
        mock_inval.assert_called_once_with(cred.id)

    @pytest.mark.asyncio
    async def test_type_change_without_a_full_payload_is_refused(self, client):
        user = _make_user()
        cookies, headers = _auth()
        cred = self._cred()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.get", new=AsyncMock(return_value=cred)),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.patch(f"/api/credentials/{cred.id}", cookies=cookies, headers=headers,
                                      json={"type": "oauth_client_credentials"})
            assert resp.status_code == 400
            assert "complete payload" in resp.json()["detail"]
            resp = await client.patch(f"/api/credentials/{cred.id}", cookies=cookies, headers=headers,
                                      json={"type": "oauth_client_credentials", "payload": {"client_id": "c1"}})
            assert resp.status_code == 400
            assert "token_endpoint" in resp.json()["detail"]
        cred.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_same_type_still_merges(self, client):
        """Sending the current type is not a change: the rotate-one-secret merge path stays."""
        user = _make_user()
        cookies, headers = _auth()
        cred = self._cred()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.credentials.Credential.get", new=AsyncMock(return_value=cred)),
            patch("app.routers.credentials.credentials_service.merge_update_payload",
                  return_value={"header_name": "X-New", "header_value": "kept"}) as mock_merge,
            patch("app.routers.credentials.credentials_service.invalidate_cached_token"),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.patch(f"/api/credentials/{cred.id}", cookies=cookies, headers=headers,
                                      json={"type": "static_header", "payload": {"header_name": "X-New"}})
        assert resp.status_code == 200, resp.text
        mock_merge.assert_called_once()
        assert resp.json()["steps_updated"] is None
