"""Tests for app.utils.security — password hashing and JWT tokens."""

from app.config import Settings
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

_TEST_SETTINGS = Settings(
    jwt_secret_key="test-secret-key",
    environment="development",
)


def test_password_hash_and_verify():
    hashed = hash_password("my-password")
    assert hashed != "my-password"
    assert verify_password("my-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip():
    token = create_access_token("user123", _TEST_SETTINGS)
    payload = decode_token(token, _TEST_SETTINGS)
    assert payload is not None
    assert payload["sub"] == "user123"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user456", _TEST_SETTINGS)
    payload = decode_token(token, _TEST_SETTINGS)
    assert payload is not None
    assert payload["sub"] == "user456"
    assert payload["type"] == "refresh"


def test_decode_invalid_token_returns_none():
    assert decode_token("not-a-real-token", _TEST_SETTINGS) is None


def test_decode_with_wrong_secret_returns_none():
    token = create_access_token("user123", _TEST_SETTINGS)
    wrong_settings = Settings(
        jwt_secret_key="different-secret",
        environment="development",
    )
    assert decode_token(token, wrong_settings) is None
