"""Tests for auth router helper functions — cookie security and OAuth gating."""

from fastapi import Response

from app.config import Settings
from app.routers.auth import _get_azure_provider, _set_tokens
from app.models.system_config import SystemConfig


def _make_mock_user():
    """Create a minimal object that looks like a User for _set_tokens."""

    class FakeUser:
        user_id = "test-user-123"

    return FakeUser()


class TestSetTokensCookieSecurity:
    """Verify that _set_tokens sets cookies with correct security attributes."""

    def test_cookies_are_httponly(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        cookies = {c.key: c for c in response.raw_headers if c[0] == b"set-cookie"}
        raw_headers = dict(response.headers)

        # Check that both cookies appear in the response headers
        header_text = str(response.headers.getlist("set-cookie") if hasattr(response.headers, "getlist") else "")
        # Use the response body to inspect cookies
        cookie_headers = [
            v.decode() for k, v in response.raw_headers if k == b"set-cookie"
        ]
        assert len(cookie_headers) == 2
        for header in cookie_headers:
            assert "httponly" in header.lower()

    def test_secure_flag_in_production(self):
        settings = Settings(jwt_secret_key="real-secret", environment="production")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        cookie_headers = [
            v.decode() for k, v in response.raw_headers if k == b"set-cookie"
        ]
        for header in cookie_headers:
            assert "secure" in header.lower()

    def test_no_secure_flag_in_development(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        cookie_headers = [
            v.decode() for k, v in response.raw_headers if k == b"set-cookie"
        ]
        for header in cookie_headers:
            # In dev mode, secure should NOT be set
            assert "secure" not in header.lower()

    def test_samesite_lax(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        cookie_headers = [
            v.decode() for k, v in response.raw_headers if k == b"set-cookie"
        ]
        for header in cookie_headers:
            assert "samesite=lax" in header.lower()

    def test_both_token_cookies_set(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        cookie_headers = [
            v.decode() for k, v in response.raw_headers if k == b"set-cookie"
        ]
        cookie_names = [h.split("=")[0] for h in cookie_headers]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names


class TestGetAzureProvider:
    """Verify the OAuth gate only returns fully configured providers."""

    def _make_config(self, providers: list[dict]) -> SystemConfig:
        """Build a SystemConfig with the given oauth_providers (no DB needed)."""
        cfg = SystemConfig()
        cfg.oauth_providers = providers
        return cfg

    def test_no_providers_returns_none(self):
        cfg = self._make_config([])
        assert _get_azure_provider(cfg) is None

    def test_disabled_provider_returns_none(self):
        cfg = self._make_config([{
            "provider": "azure",
            "enabled": False,
            "client_id": "id",
            "client_secret": "secret",
            "tenant_id": "tenant",
        }])
        assert _get_azure_provider(cfg) is None

    def test_missing_client_secret_returns_none(self):
        cfg = self._make_config([{
            "provider": "azure",
            "enabled": True,
            "client_id": "id",
            "client_secret": "",  # empty = not configured
            "tenant_id": "tenant",
        }])
        assert _get_azure_provider(cfg) is None

    def test_missing_tenant_id_returns_none(self):
        cfg = self._make_config([{
            "provider": "azure",
            "enabled": True,
            "client_id": "id",
            "client_secret": "secret",
            "tenant_id": "",
        }])
        assert _get_azure_provider(cfg) is None

    def test_fully_configured_returns_provider(self):
        provider = {
            "provider": "azure",
            "enabled": True,
            "client_id": "my-client-id",
            "client_secret": "my-secret",
            "tenant_id": "my-tenant",
        }
        cfg = self._make_config([provider])
        result = _get_azure_provider(cfg)
        assert result is not None
        assert result["client_id"] == "my-client-id"

    def test_non_azure_provider_ignored(self):
        cfg = self._make_config([{
            "provider": "google",
            "enabled": True,
            "client_id": "id",
            "client_secret": "secret",
            "tenant_id": "tenant",
        }])
        assert _get_azure_provider(cfg) is None

    def test_multiple_providers_returns_correct_one(self):
        cfg = self._make_config([
            {"provider": "google", "enabled": True, "client_id": "g", "client_secret": "gs", "tenant_id": "gt"},
            {"provider": "azure", "enabled": True, "client_id": "az-id", "client_secret": "az-secret", "tenant_id": "az-tenant"},
        ])
        result = _get_azure_provider(cfg)
        assert result is not None
        assert result["client_id"] == "az-id"
