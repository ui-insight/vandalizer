"""Credentials service — payload encryption, OAuth client-credentials JWT exchange, bearer caching.

Runs in sync context (called from Celery workers / APICallNode). The router
layer uses the async wrappers at the bottom.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
import uuid
from typing import Any

import httpx
import jwt
import redis

from app.utils.encryption import decrypt_value, encrypt_value
from app.utils.url_validation import validate_outbound_url

logger = logging.getLogger(__name__)


CREDENTIAL_TYPES = ("static_header", "oauth_client_credentials")

# Encrypted-at-rest payload fields, per credential type. Anything in the
# payload that isn't listed here is stored as plaintext (URLs, scopes, etc.).
_ENCRYPTED_FIELDS: dict[str, tuple[str, ...]] = {
    "static_header": ("header_value",),
    "oauth_client_credentials": ("private_key", "client_secret"),
}

# Redis cache key prefix and skew window for bearer expiry.
_TOKEN_CACHE_PREFIX = "credentials:bearer:"
_BEARER_REFRESH_SKEW_SECONDS = 30


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class CredentialError(Exception):
    """Raised for malformed payloads, failed exchanges, etc."""


def validate_payload(credential_type: str, payload: dict) -> None:
    """Raise CredentialError if *payload* is missing required fields for *credential_type*."""
    if credential_type not in CREDENTIAL_TYPES:
        raise CredentialError(f"Unknown credential type: {credential_type!r}")

    if credential_type == "static_header":
        for field in ("header_name", "header_value"):
            if not payload.get(field):
                raise CredentialError(f"static_header credential is missing {field!r}")

    elif credential_type == "oauth_client_credentials":
        for field in ("client_id", "token_endpoint", "private_key"):
            if not payload.get(field):
                raise CredentialError(f"oauth_client_credentials credential is missing {field!r}")
        # token_endpoint must be a safe outbound URL
        try:
            validate_outbound_url(payload["token_endpoint"])
        except ValueError as e:
            raise CredentialError(f"token_endpoint rejected: {e}") from e


# ---------------------------------------------------------------------------
# Payload encryption (round-trip helpers)
# ---------------------------------------------------------------------------

def encrypt_payload(credential_type: str, payload: dict) -> dict:
    """Return a copy of *payload* with secret fields encrypted at rest."""
    encrypted = dict(payload)
    for field in _ENCRYPTED_FIELDS.get(credential_type, ()):
        value = encrypted.get(field)
        if value:
            encrypted[field] = encrypt_value(value)
    return encrypted


def decrypt_payload(credential_type: str, payload: dict) -> dict:
    """Return a copy of *payload* with secret fields decrypted."""
    decrypted = dict(payload)
    for field in _ENCRYPTED_FIELDS.get(credential_type, ()):
        value = decrypted.get(field)
        if value:
            decrypted[field] = decrypt_value(value)
    return decrypted


def metadata_view(credential_doc: dict) -> dict:
    """Strip secret payload fields, keeping only metadata safe to return to clients."""
    payload = credential_doc.get("payload", {}) or {}
    safe_payload: dict[str, Any] = {}
    encrypted_fields = set(_ENCRYPTED_FIELDS.get(credential_doc.get("type", ""), ()))
    for k, v in payload.items():
        if k in encrypted_fields:
            safe_payload[k] = "<set>" if v else ""
        else:
            safe_payload[k] = v
    return {
        "id": str(credential_doc["_id"]) if "_id" in credential_doc else credential_doc.get("id", ""),
        "name": credential_doc.get("name", ""),
        "type": credential_doc.get("type", ""),
        "description": credential_doc.get("description"),
        "team_id": credential_doc.get("team_id"),
        "user_id": credential_doc.get("user_id", ""),
        "payload": safe_payload,
        "created_at": credential_doc.get("created_at"),
        "updated_at": credential_doc.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# OAuth client_credentials JWT-assertion flow
# ---------------------------------------------------------------------------

def _redis_client() -> redis.Redis:
    redis_host = os.environ.get("redis_host", "localhost")
    return redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)


def _build_client_assertion(payload: dict) -> str:
    """Sign a short-lived JWT assertion for a client_credentials exchange.

    Uses RS256 by default; honors `algorithm` field on the payload if set.
    """
    now = int(time.time())
    claims = {
        "iss": payload["client_id"],
        "sub": payload["client_id"],
        "aud": payload.get("audience") or payload["token_endpoint"],
        "iat": now,
        "exp": now + 300,
        "jti": uuid.uuid4().hex,
    }
    algorithm = payload.get("algorithm") or "RS256"
    return jwt.encode(claims, payload["private_key"], algorithm=algorithm)


def _exchange_token(payload: dict) -> tuple[str, int]:
    """POST a signed assertion to the token endpoint. Return (bearer, expires_in_seconds)."""
    assertion = _build_client_assertion(payload)
    body: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": assertion,
        "client_id": payload["client_id"],
    }
    if payload.get("scope"):
        body["scope"] = payload["scope"]
    # Some servers expect client_secret even alongside JWT assertion; pass through
    # if configured (decrypted upstream).
    if payload.get("client_secret"):
        body["client_secret"] = payload["client_secret"]

    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            resp = client.post(
                payload["token_endpoint"],
                data=body,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise CredentialError(
            f"Token endpoint returned {e.response.status_code}: {e.response.text[:500]}"
        ) from e
    except httpx.RequestError as e:
        raise CredentialError(f"Token endpoint request failed: {e}") from e
    except ValueError as e:
        raise CredentialError(f"Token endpoint returned non-JSON response: {e}") from e

    bearer = data.get("access_token")
    if not bearer:
        raise CredentialError("Token endpoint response missing access_token")
    # expires_in is seconds-from-now per RFC 6749 §5.1; default to 5 minutes.
    expires_in = int(data.get("expires_in") or 300)
    return bearer, expires_in


def get_bearer_token(credential_id: str, decrypted_payload: dict) -> str:
    """Return a bearer token for *credential_id*, using Redis cache when fresh.

    Re-exchanges within `_BEARER_REFRESH_SKEW_SECONDS` of expiry.
    """
    cache_key = f"{_TOKEN_CACHE_PREFIX}{credential_id}"
    client = _redis_client()
    try:
        cached_raw: Any = client.get(cache_key)
        if cached_raw:
            try:
                cached = json.loads(cached_raw)
                if cached.get("expires_at", 0) - _BEARER_REFRESH_SKEW_SECONDS > int(time.time()):
                    return str(cached["token"])
            except (ValueError, KeyError):
                pass  # fall through to re-exchange
    except redis.RedisError as e:
        logger.warning("Redis unavailable for bearer cache read: %s", e)

    bearer, expires_in = _exchange_token(decrypted_payload)
    expires_at = int(time.time()) + expires_in

    try:
        client.set(
            cache_key,
            json.dumps({"token": bearer, "expires_at": expires_at}),
            ex=max(expires_in - _BEARER_REFRESH_SKEW_SECONDS, 30),
        )
    except redis.RedisError as e:
        logger.warning("Redis unavailable for bearer cache write: %s", e)

    return bearer


def invalidate_cached_token(credential_id: str) -> None:
    """Drop a cached bearer (e.g. after rotation or 401)."""
    try:
        client = _redis_client()
        client.delete(f"{_TOKEN_CACHE_PREFIX}{credential_id}")
    except redis.RedisError:
        pass


# ---------------------------------------------------------------------------
# Auth-header application (called from APICallNode)
# ---------------------------------------------------------------------------

def apply_auth(
    *,
    credential_doc: dict,
    headers: dict[str, str],
) -> dict[str, str]:
    """Mutate *headers* in place per the credential's auth strategy. Return headers.

    Raises CredentialError on configuration or token-exchange failures.
    """
    cred_type = credential_doc.get("type")
    payload = decrypt_payload(cred_type or "", credential_doc.get("payload", {}) or {})

    if cred_type == "static_header":
        name = payload.get("header_name") or ""
        value = payload.get("header_value") or ""
        if not name or not value:
            raise CredentialError("static_header credential is incomplete")
        headers[name] = value
        return headers

    if cred_type == "oauth_client_credentials":
        validate_payload(cred_type, payload)
        cred_id = str(credential_doc.get("_id") or credential_doc.get("id") or "")
        if not cred_id:
            raise CredentialError("Cannot apply OAuth credential without an id")
        bearer = get_bearer_token(cred_id, payload)
        headers["Authorization"] = f"Bearer {bearer}"
        return headers

    raise CredentialError(f"Unknown credential type: {cred_type!r}")


# ---------------------------------------------------------------------------
# Sync MongoDB lookup (for use inside Celery workers)
# ---------------------------------------------------------------------------

def fetch_credential_sync(db: Any, credential_id: str) -> dict | None:
    """Return the raw credential doc from a pymongo db handle, or None.

    `db` is a pymongo Database, matching the pattern in app/tasks/workflow_tasks.py.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        oid = ObjectId(credential_id)
    except (InvalidId, TypeError):
        return None
    result: dict | None = db.credential.find_one({"_id": oid})
    return result


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def generate_random_jti() -> str:
    """Exposed for tests."""
    return secrets.token_hex(16)
