"""Unit tests for credentials_service.

Covers payload validation, encrypt/decrypt round-trips, JWT-assertion
construction, OAuth token exchange (mocked HTTP), Redis caching, and the
apply_auth dispatcher used by APICallNode.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
import redis
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import credentials_service
from app.services.credentials_service import (
    CredentialError,
    apply_auth,
    decrypt_payload,
    encrypt_payload,
    get_bearer_token,
    invalidate_cached_token,
    metadata_view,
    validate_payload,
    _build_client_assertion,
    _exchange_token,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rsa_private_pem() -> str:
    """Generate a fresh RSA private key for signing tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="module")
def rsa_public_pem(rsa_private_pem: str) -> str:
    private = serialization.load_pem_private_key(
        rsa_private_pem.encode(), password=None, backend=default_backend()
    )
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


@pytest.fixture
def fake_redis():
    """In-process dict-backed Redis fake covering the methods we use."""
    store: dict[str, tuple[str, float | None]] = {}

    def _get(key):
        item = store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.time() > expires_at:
            store.pop(key, None)
            return None
        return value

    def _set(key, value, ex=None):
        expires_at = time.time() + ex if ex else None
        store[key] = (value, expires_at)
        return True

    def _delete(key):
        store.pop(key, None)
        return 1

    client = MagicMock(spec=redis.Redis)
    client.get.side_effect = _get
    client.set.side_effect = _set
    client.delete.side_effect = _delete
    return client


# ---------------------------------------------------------------------------
# validate_payload
# ---------------------------------------------------------------------------

class TestValidatePayload:
    def test_unknown_type(self):
        with pytest.raises(CredentialError, match="Unknown credential type"):
            validate_payload("nope", {})

    def test_static_header_missing_field(self):
        with pytest.raises(CredentialError, match="header_value"):
            validate_payload("static_header", {"header_name": "X-Api-Key"})

    def test_static_header_ok(self):
        validate_payload("static_header", {"header_name": "X-Api-Key", "header_value": "secret"})

    def test_oauth_missing_field(self):
        with pytest.raises(CredentialError, match="private_key"):
            validate_payload("oauth_client_credentials", {
                "client_id": "abc",
                "token_endpoint": "https://example.com/token",
            })

    @patch("app.services.credentials_service.validate_outbound_url", return_value="ok")
    def test_oauth_ok(self, _mock_validate):
        validate_payload("oauth_client_credentials", {
            "client_id": "abc",
            "token_endpoint": "https://example.com/token",
            "private_key": "-----BEGIN-----",
        })

    @patch("app.services.credentials_service.validate_outbound_url", side_effect=ValueError("blocked"))
    def test_oauth_blocked_token_endpoint(self, _mock_validate):
        with pytest.raises(CredentialError, match="token_endpoint rejected"):
            validate_payload("oauth_client_credentials", {
                "client_id": "abc",
                "token_endpoint": "http://10.0.0.1/token",
                "private_key": "-----BEGIN-----",
            })


# ---------------------------------------------------------------------------
# Encrypt / decrypt round-trip
# ---------------------------------------------------------------------------

class TestPayloadEncryption:
    def test_static_header_round_trip(self):
        original = {"header_name": "X-Key", "header_value": "topsecret"}
        encrypted = encrypt_payload("static_header", original)
        # Header name not encrypted; value is (assuming key configured) — in
        # absence of a key the value passes through unchanged.
        assert encrypted["header_name"] == "X-Key"
        decrypted = decrypt_payload("static_header", encrypted)
        assert decrypted["header_value"] == "topsecret"

    def test_oauth_round_trip(self, rsa_private_pem):
        original = {
            "client_id": "abc",
            "token_endpoint": "https://example.com/token",
            "private_key": rsa_private_pem,
            "scope": "read write",
        }
        encrypted = encrypt_payload("oauth_client_credentials", original)
        assert encrypted["client_id"] == "abc"  # not a secret field
        assert encrypted["scope"] == "read write"  # not a secret field
        decrypted = decrypt_payload("oauth_client_credentials", encrypted)
        assert decrypted["private_key"] == rsa_private_pem


# ---------------------------------------------------------------------------
# metadata_view never leaks secrets
# ---------------------------------------------------------------------------

class TestMetadataView:
    def test_static_header_value_redacted(self):
        doc = {
            "_id": "abc123",
            "name": "key",
            "type": "static_header",
            "team_id": None,
            "user_id": "u1",
            "payload": {"header_name": "X-Key", "header_value": "enc:xxx"},
        }
        view = metadata_view(doc)
        assert view["payload"]["header_name"] == "X-Key"
        assert view["payload"]["header_value"] == "<set>"

    def test_oauth_secrets_redacted(self):
        doc = {
            "_id": "abc",
            "name": "lakehouse",
            "type": "oauth_client_credentials",
            "team_id": "team-1",
            "user_id": "u1",
            "payload": {
                "client_id": "client-abc",
                "token_endpoint": "https://example.com/token",
                "private_key": "enc:xxxx",
                "scope": "lakehouse.read",
            },
        }
        view = metadata_view(doc)
        assert view["payload"]["client_id"] == "client-abc"
        assert view["payload"]["token_endpoint"] == "https://example.com/token"
        assert view["payload"]["private_key"] == "<set>"
        assert view["payload"]["scope"] == "lakehouse.read"

    def test_empty_secret_marked_blank(self):
        doc = {
            "_id": "abc",
            "name": "x",
            "type": "static_header",
            "user_id": "u1",
            "payload": {"header_name": "X", "header_value": ""},
        }
        view = metadata_view(doc)
        assert view["payload"]["header_value"] == ""


# ---------------------------------------------------------------------------
# JWT assertion construction
# ---------------------------------------------------------------------------

class TestBuildClientAssertion:
    def test_assertion_is_signed_and_decodable(self, rsa_private_pem, rsa_public_pem):
        payload = {
            "client_id": "client-abc",
            "token_endpoint": "https://issuer/token",
            "private_key": rsa_private_pem,
        }
        token = _build_client_assertion(payload)
        decoded = jwt.decode(
            token,
            rsa_public_pem,
            algorithms=["RS256"],
            audience="https://issuer/token",
        )
        assert decoded["iss"] == "client-abc"
        assert decoded["sub"] == "client-abc"
        assert decoded["aud"] == "https://issuer/token"
        assert decoded["exp"] > decoded["iat"]

    def test_explicit_audience_used_when_provided(self, rsa_private_pem, rsa_public_pem):
        payload = {
            "client_id": "client-abc",
            "token_endpoint": "https://issuer/token",
            "audience": "https://api.lakehouse",
            "private_key": rsa_private_pem,
        }
        token = _build_client_assertion(payload)
        decoded = jwt.decode(
            token, rsa_public_pem, algorithms=["RS256"], audience="https://api.lakehouse"
        )
        assert decoded["aud"] == "https://api.lakehouse"


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

class TestExchangeToken:
    @patch("app.services.credentials_service.httpx.Client")
    def test_successful_exchange(self, mock_client_cls, rsa_private_pem):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"access_token": "abc123", "expires_in": 600}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        bearer, expires_in = _exchange_token({
            "client_id": "client-abc",
            "token_endpoint": "https://issuer/token",
            "private_key": rsa_private_pem,
            "scope": "read",
        })
        assert bearer == "abc123"
        assert expires_in == 600

        # Check body shape
        post_args = mock_client.post.call_args
        body = post_args[1]["data"]
        assert body["grant_type"] == "client_credentials"
        assert body["client_assertion_type"] == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        assert body["client_id"] == "client-abc"
        assert body["scope"] == "read"
        assert body["client_assertion"]  # signed JWT present

    @patch("app.services.credentials_service.httpx.Client")
    def test_missing_access_token_raises(self, mock_client_cls, rsa_private_pem):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"token_type": "bearer"}  # no access_token
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        with pytest.raises(CredentialError, match="missing access_token"):
            _exchange_token({
                "client_id": "abc",
                "token_endpoint": "https://issuer/token",
                "private_key": rsa_private_pem,
            })

    @patch("app.services.credentials_service.httpx.Client")
    def test_default_expires_in(self, mock_client_cls, rsa_private_pem):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok"}  # no expires_in
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        _, expires_in = _exchange_token({
            "client_id": "abc",
            "token_endpoint": "https://issuer/token",
            "private_key": rsa_private_pem,
        })
        assert expires_in == 300


# ---------------------------------------------------------------------------
# Bearer cache
# ---------------------------------------------------------------------------

class TestGetBearerToken:
    @patch("app.services.credentials_service._exchange_token")
    @patch("app.services.credentials_service._redis_client")
    def test_cache_miss_then_hit(self, mock_redis_factory, mock_exchange, fake_redis, rsa_private_pem):
        mock_redis_factory.return_value = fake_redis
        mock_exchange.return_value = ("tok-1", 600)

        payload = {"client_id": "abc", "token_endpoint": "https://x/t", "private_key": rsa_private_pem}
        first = get_bearer_token("cred-1", payload)
        second = get_bearer_token("cred-1", payload)

        assert first == "tok-1"
        assert second == "tok-1"
        assert mock_exchange.call_count == 1  # second call served from cache

    @patch("app.services.credentials_service._exchange_token")
    @patch("app.services.credentials_service._redis_client")
    def test_cache_invalidate(self, mock_redis_factory, mock_exchange, fake_redis, rsa_private_pem):
        mock_redis_factory.return_value = fake_redis
        mock_exchange.side_effect = [("tok-1", 600), ("tok-2", 600)]

        payload = {"client_id": "abc", "token_endpoint": "https://x/t", "private_key": rsa_private_pem}
        first = get_bearer_token("cred-1", payload)
        invalidate_cached_token("cred-1")
        second = get_bearer_token("cred-1", payload)

        assert first == "tok-1"
        assert second == "tok-2"
        assert mock_exchange.call_count == 2

    @patch("app.services.credentials_service._exchange_token")
    @patch("app.services.credentials_service._redis_client")
    def test_expired_cache_re_exchanges(self, mock_redis_factory, mock_exchange, rsa_private_pem):
        # Pre-seed cache with an already-expired token.
        client = MagicMock(spec=redis.Redis)
        client.get.return_value = json.dumps({"token": "stale", "expires_at": int(time.time()) - 100})
        client.set.return_value = True
        client.delete.return_value = 1
        mock_redis_factory.return_value = client
        mock_exchange.return_value = ("fresh", 600)

        payload = {"client_id": "abc", "token_endpoint": "https://x/t", "private_key": rsa_private_pem}
        result = get_bearer_token("cred-1", payload)
        assert result == "fresh"
        mock_exchange.assert_called_once()

    @patch("app.services.credentials_service._exchange_token")
    @patch("app.services.credentials_service._redis_client")
    def test_redis_unavailable_still_exchanges(self, mock_redis_factory, mock_exchange, rsa_private_pem):
        client = MagicMock(spec=redis.Redis)
        client.get.side_effect = redis.RedisError("connection refused")
        client.set.side_effect = redis.RedisError("connection refused")
        mock_redis_factory.return_value = client
        mock_exchange.return_value = ("tok", 600)

        payload = {"client_id": "abc", "token_endpoint": "https://x/t", "private_key": rsa_private_pem}
        assert get_bearer_token("cred-1", payload) == "tok"


# ---------------------------------------------------------------------------
# apply_auth dispatcher
# ---------------------------------------------------------------------------

class TestApplyAuth:
    def test_static_header_applied(self):
        cred = {
            "_id": "abc123",
            "type": "static_header",
            "payload": {"header_name": "X-Key", "header_value": "secret"},
        }
        headers: dict[str, str] = {}
        apply_auth(credential_doc=cred, headers=headers)
        assert headers == {"X-Key": "secret"}

    def test_static_header_incomplete_raises(self):
        cred = {
            "_id": "abc",
            "type": "static_header",
            "payload": {"header_name": "X-Key"},
        }
        with pytest.raises(CredentialError, match="incomplete"):
            apply_auth(credential_doc=cred, headers={})

    @patch("app.services.credentials_service.get_bearer_token", return_value="tok-xyz")
    @patch("app.services.credentials_service.validate_outbound_url", return_value="ok")
    def test_oauth_applies_bearer(self, _mock_validate, _mock_token, rsa_private_pem):
        cred = {
            "_id": "abc123",
            "type": "oauth_client_credentials",
            "payload": {
                "client_id": "c",
                "token_endpoint": "https://issuer/token",
                "private_key": rsa_private_pem,
            },
        }
        headers: dict[str, str] = {}
        apply_auth(credential_doc=cred, headers=headers)
        assert headers == {"Authorization": "Bearer tok-xyz"}

    def test_unknown_type_raises(self):
        with pytest.raises(CredentialError, match="Unknown credential type"):
            apply_auth(credential_doc={"_id": "abc", "type": "weird", "payload": {}}, headers={})


# ---------------------------------------------------------------------------
# fetch_credential_sync
# ---------------------------------------------------------------------------

class TestFetchCredentialSync:
    def test_invalid_objectid_returns_none(self):
        db = MagicMock()
        result = credentials_service.fetch_credential_sync(db, "not-an-objectid")
        assert result is None
        db.credential.find_one.assert_not_called()

    def test_lookup_passes_objectid(self):
        db = MagicMock()
        db.credential.find_one.return_value = {"_id": "abc", "type": "static_header"}
        result = credentials_service.fetch_credential_sync(db, "507f1f77bcf86cd799439011")
        assert result == {"_id": "abc", "type": "static_header"}
        db.credential.find_one.assert_called_once()
