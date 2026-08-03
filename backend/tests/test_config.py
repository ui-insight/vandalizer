"""Tests for app.config — JWT secret validation and defaults."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_jwt_secret_allowed_in_development():
    """In development mode, the default 'change-me' secret should be accepted."""
    s = Settings(jwt_secret_key="change-me", environment="development")
    assert s.jwt_secret_key == "change-me"


def test_default_jwt_secret_rejected_in_production():
    """In production, the default secret must raise a validation error."""
    with pytest.raises(ValidationError, match="jwt_secret_key must be changed"):
        Settings(
            jwt_secret_key="change-me",
            environment="production",
        )


def test_default_jwt_secret_rejected_in_staging():
    """In staging, the default secret must also be rejected."""
    with pytest.raises(ValidationError, match="jwt_secret_key must be changed"):
        Settings(
            jwt_secret_key="change-me",
            environment="staging",
        )


def test_custom_jwt_secret_accepted_in_production():
    """A non-default secret should pass validation in production."""
    s = Settings(
        jwt_secret_key="a-real-secret-key-here",
        environment="production",
    )
    assert s.jwt_secret_key == "a-real-secret-key-here"


def test_insight_endpoint_defaults_to_empty():
    """insight_endpoint should default to empty string, not a hardcoded URL."""
    s = Settings(environment="development")
    assert s.insight_endpoint == ""


def test_is_production_property():
    s_prod = Settings(
        jwt_secret_key="secret",
        environment="production",
    )
    s_dev = Settings(environment="development")
    assert s_prod.is_production is True
    assert s_dev.is_production is False


class TestUseSecureCookies:
    """Secure-flag resolution: explicit COOKIE_SECURE wins, else derived from
    environment + frontend_url scheme."""

    def test_production_https_is_secure(self):
        s = Settings(
            jwt_secret_key="secret",
            environment="production",
            frontend_url="https://vandalizer.example.edu",
        )
        assert s.use_secure_cookies is True

    def test_production_plain_http_is_not_secure(self):
        """The 'vandalizer in a box' case: production served over plain HTTP.

        Secure cookies are silently dropped by the browser on HTTP, so login
        would succeed but every following request would 401.
        """
        s = Settings(
            jwt_secret_key="secret",
            environment="production",
            frontend_url="http://localhost",
        )
        assert s.use_secure_cookies is False

    def test_development_is_not_secure(self):
        s = Settings(
            environment="development",
            frontend_url="http://localhost:5173",
        )
        assert s.use_secure_cookies is False

    def test_explicit_override_wins_both_ways(self):
        forced_on = Settings(
            jwt_secret_key="secret",
            environment="production",
            frontend_url="http://localhost",
            cookie_secure=True,
        )
        forced_off = Settings(
            jwt_secret_key="secret",
            environment="production",
            frontend_url="https://vandalizer.example.edu",
            cookie_secure=False,
        )
        assert forced_on.use_secure_cookies is True
        assert forced_off.use_secure_cookies is False
