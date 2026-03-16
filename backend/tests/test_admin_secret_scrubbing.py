"""Tests for admin config secret sanitization.

Verifies _sanitize_providers, _sanitize_models, and the GET /api/admin/config endpoint.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.routers.admin import _sanitize_models, _sanitize_providers
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(**overrides):
    defaults = {
        "id": "fake-id",
        "user_id": "admin1",
        "email": "admin@example.com",
        "name": "Admin User",
        "is_admin": True,
        "current_team": None,
        "organization_id": None,
        "is_demo_user": False,
        "demo_status": None,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    user.save = AsyncMock()
    return user


def _auth(user_id="admin1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


class TestSanitizeProviders:
    def test_replaces_client_secret(self):
        """client_secret is replaced with '***'."""
        providers = [
            {"name": "azure", "client_id": "abc123", "client_secret": "super-secret-value"},
        ]
        result = _sanitize_providers(providers)
        assert result[0]["client_secret"] == "***"
        assert result[0]["client_id"] == "abc123"
        assert result[0]["name"] == "azure"

    def test_leaves_other_fields_intact(self):
        """Fields other than client_secret are not modified."""
        providers = [
            {"name": "google", "client_id": "goog123", "redirect_uri": "https://example.com/callback"},
        ]
        result = _sanitize_providers(providers)
        assert result[0]["name"] == "google"
        assert result[0]["client_id"] == "goog123"
        assert result[0]["redirect_uri"] == "https://example.com/callback"

    def test_empty_secret_unchanged(self):
        """Empty client_secret is not replaced (falsy check)."""
        providers = [
            {"name": "azure", "client_id": "abc", "client_secret": ""},
        ]
        result = _sanitize_providers(providers)
        assert result[0]["client_secret"] == ""

    def test_no_secret_field(self):
        """Provider without client_secret key is unchanged."""
        providers = [
            {"name": "saml", "idp_url": "https://idp.example.com"},
        ]
        result = _sanitize_providers(providers)
        assert "client_secret" not in result[0]
        assert result[0]["name"] == "saml"

    def test_multiple_providers(self):
        """Multiple providers are all sanitized."""
        providers = [
            {"name": "a", "client_secret": "secret1"},
            {"name": "b", "client_secret": "secret2"},
        ]
        result = _sanitize_providers(providers)
        assert all(p["client_secret"] == "***" for p in result)

    def test_does_not_mutate_original(self):
        """Original list is not modified."""
        providers = [{"name": "x", "client_secret": "original"}]
        _sanitize_providers(providers)
        assert providers[0]["client_secret"] == "original"


class TestSanitizeModels:
    def test_replaces_api_key(self):
        """api_key is replaced with '***'."""
        models = [
            {"name": "gpt-4", "api_key": "sk-real-key-12345", "endpoint": "https://api.openai.com"},
        ]
        result = _sanitize_models(models)
        assert result[0]["api_key"] == "***"
        assert result[0]["name"] == "gpt-4"

    def test_leaves_other_fields_intact(self):
        """Fields other than api_key are not modified."""
        models = [
            {"name": "claude", "endpoint": "https://api.anthropic.com", "tier": "premium"},
        ]
        result = _sanitize_models(models)
        assert result[0]["name"] == "claude"
        assert result[0]["endpoint"] == "https://api.anthropic.com"
        assert result[0]["tier"] == "premium"

    def test_empty_api_key_unchanged(self):
        """Empty api_key is not replaced (falsy check)."""
        models = [
            {"name": "local", "api_key": ""},
        ]
        result = _sanitize_models(models)
        assert result[0]["api_key"] == ""

    def test_no_api_key_field(self):
        """Model without api_key key is unchanged."""
        models = [
            {"name": "ollama", "endpoint": "http://localhost:11434"},
        ]
        result = _sanitize_models(models)
        assert "api_key" not in result[0]

    def test_does_not_mutate_original(self):
        """Original list is not modified."""
        models = [{"name": "x", "api_key": "original"}]
        _sanitize_models(models)
        assert models[0]["api_key"] == "original"


class TestAdminConfigEndpoint:
    @pytest.fixture
    async def client(self):
        with patch("app.main.init_db", new_callable=AsyncMock):
            from app.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_config_scrubs_secrets(self, client):
        """GET /api/admin/config does not leak real client_secret or api_key values."""
        user = _make_user(is_admin=True)
        cookies, headers = _auth()

        mock_config = MagicMock()
        mock_config.get_extraction_config.return_value = {}
        mock_config.get_quality_config.return_value = {}
        mock_config.auth_methods = ["password", "oauth"]
        mock_config.oauth_providers = [
            {"name": "azure", "client_id": "id1", "client_secret": "real-secret-value"},
        ]
        mock_config.available_models = [
            {"name": "gpt-4o", "api_key": "sk-real-key-abcdef"},
        ]
        mock_config.ocr_endpoint = ""
        mock_config.llm_endpoint = ""
        mock_config.highlight_color = "#eab308"
        mock_config.ui_radius = "12px"

        with patch("app.dependencies.decode_token", return_value={"sub": "admin1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.admin.SystemConfig") as MockSysConfig:
            MockUser.find_one = AsyncMock(return_value=user)
            MockSysConfig.get_config = AsyncMock(return_value=mock_config)

            resp = await client.get(
                "/api/admin/config",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()

        # Verify secrets are scrubbed
        assert data["oauth_providers"][0]["client_secret"] == "***"
        assert data["oauth_providers"][0]["client_id"] == "id1"
        assert data["available_models"][0]["api_key"] == "***"
        assert data["available_models"][0]["name"] == "gpt-4o"

        # Verify real secrets are not present anywhere in the response text
        resp_text = resp.text
        assert "real-secret-value" not in resp_text
        assert "sk-real-key-abcdef" not in resp_text
