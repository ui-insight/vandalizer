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
