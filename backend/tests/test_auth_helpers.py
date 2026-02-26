"""Tests for auth router helper functions — cookie security and OAuth gating."""

from fastapi import Response

from app.config import Settings
from app.routers.auth import _get_azure_provider, _set_tokens


def _make_mock_user():
    """Create a minimal object that looks like a User for _set_tokens."""

    class FakeUser:
        user_id = "test-user-123"

    return FakeUser()


class TestSetTokensCookieSecurity:
    """Verify that _set_tokens sets cookies with correct security attributes."""

    def _get_cookie_headers(self, response: Response) -> list[str]:
        return [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]

    def test_cookies_are_httponly(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        for header in self._get_cookie_headers(response):
            assert "httponly" in header.lower()

    def test_secure_flag_in_production(self):
        settings = Settings(jwt_secret_key="real-secret", environment="production")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        for header in self._get_cookie_headers(response):
            assert "secure" in header.lower()

    def test_no_secure_flag_in_development(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        for header in self._get_cookie_headers(response):
            assert "secure" not in header.lower()

    def test_samesite_lax(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        for header in self._get_cookie_headers(response):
            assert "samesite=lax" in header.lower()

    def test_both_token_cookies_set(self):
        settings = Settings(environment="development")
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        headers = self._get_cookie_headers(response)
        cookie_names = [h.split("=")[0] for h in headers]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names

    def test_max_age_matches_settings(self):
        settings = Settings(
            environment="development",
            jwt_access_expire_minutes=15,
            jwt_refresh_expire_days=7,
        )
        response = Response()
        _set_tokens(response, _make_mock_user(), settings)

        headers = self._get_cookie_headers(response)
        for header in headers:
            if header.startswith("access_token="):
                assert "max-age=900" in header.lower()  # 15 * 60
            elif header.startswith("refresh_token="):
                assert "max-age=604800" in header.lower()  # 7 * 86400


class TestGetAzureProvider:
    """Verify the OAuth gate only returns fully configured providers.

    SystemConfig is a Beanie Document and requires DB init to construct,
    so we create a simple mock with an oauth_providers attribute instead.
    """

    def _make_config(self, providers: list[dict]):
        class FakeConfig:
            oauth_providers = providers
        return FakeConfig()

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
            "client_secret": "",
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

    def test_missing_client_id_returns_none(self):
        cfg = self._make_config([{
            "provider": "azure",
            "enabled": True,
            "client_id": "",
            "client_secret": "secret",
            "tenant_id": "tenant",
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
