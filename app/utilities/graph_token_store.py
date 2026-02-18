#!/usr/bin/env python3
"""Encrypted Microsoft Graph token storage and refresh.

Tokens are stored in MongoDB with Fernet encryption. Refresh uses MSAL
so it works inside Celery workers without an HTTP request context.
"""

import datetime
import os

import mongoengine as me
from cryptography.fernet import Fernet, InvalidToken

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class MSGraphTokenSet(me.Document):
    """Encrypted Graph API tokens for a single user."""

    user_id = me.StringField(required=True, unique=True, max_length=200)
    access_token_enc = me.BinaryField(required=True)
    refresh_token_enc = me.BinaryField(required=True)
    token_type = me.StringField(default="Bearer", max_length=20)
    expires_at = me.DateTimeField(required=True)
    scopes = me.ListField(me.StringField(), default=[])
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "ms_graph_tokens",
        "indexes": ["user_id", "expires_at"],
    }


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

# The Fernet key MUST be a 32-byte URL-safe base64-encoded value.
# Generate one with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_FERNET_KEY: str | None = os.environ.get("GRAPH_TOKEN_KEY")


def _fernet() -> Fernet:
    if not _FERNET_KEY:
        raise RuntimeError(
            "GRAPH_TOKEN_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(_FERNET_KEY.encode())


def _encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def _decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt token — GRAPH_TOKEN_KEY may have changed")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_token(user_id: str, token_response: dict) -> MSGraphTokenSet:
    """Encrypt and persist a Graph API token response.

    ``token_response`` is the dict returned by Flask-Dance / MSAL containing at
    least ``access_token``, ``refresh_token``, and ``expires_in`` (seconds).
    """
    access_token = token_response.get("access_token", "")
    refresh_token = token_response.get("refresh_token", "")
    expires_in = token_response.get("expires_in", 3600)
    scope_str = token_response.get("scope", "")
    scopes = scope_str.split() if isinstance(scope_str, str) else list(scope_str)

    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(seconds=int(expires_in))

    token_set = MSGraphTokenSet.objects(user_id=user_id).first()
    if token_set:
        token_set.access_token_enc = _encrypt(access_token)
        token_set.refresh_token_enc = _encrypt(refresh_token)
        token_set.expires_at = expires_at
        token_set.scopes = scopes
        token_set.updated_at = now
    else:
        token_set = MSGraphTokenSet(
            user_id=user_id,
            access_token_enc=_encrypt(access_token),
            refresh_token_enc=_encrypt(refresh_token),
            expires_at=expires_at,
            scopes=scopes,
            created_at=now,
            updated_at=now,
        )
    token_set.save()
    return token_set


def get_valid_token(user_id: str) -> str | None:
    """Return a valid access token for *user_id*, refreshing if needed.

    Returns ``None`` when no token is stored or refresh fails.
    """
    token_set = MSGraphTokenSet.objects(user_id=user_id).first()
    if not token_set:
        return None

    now = datetime.datetime.utcnow()
    # Use 5-minute buffer so we refresh before actual expiry
    if token_set.expires_at > now + datetime.timedelta(minutes=5):
        return _decrypt(token_set.access_token_enc)

    # Token expired or about to — attempt refresh
    return _refresh_token(token_set)


def revoke_token(user_id: str) -> None:
    """Delete stored tokens for *user_id*."""
    MSGraphTokenSet.objects(user_id=user_id).delete()


def has_valid_token(user_id: str) -> bool:
    """Check whether *user_id* has a stored (possibly expired) token set."""
    return MSGraphTokenSet.objects(user_id=user_id).count() > 0


# ---------------------------------------------------------------------------
# Refresh via MSAL
# ---------------------------------------------------------------------------


def _get_azure_config() -> dict | None:
    """Retrieve Azure AD app credentials from SystemConfig or env vars."""
    try:
        from app.utilities.config import get_oauth_provider_by_type

        azure_config = get_oauth_provider_by_type("azure")
        if azure_config:
            return {
                "client_id": azure_config.get("client_id"),
                "client_secret": azure_config.get("client_secret"),
                "tenant": azure_config.get("tenant_id") or azure_config.get("tenant"),
            }
    except Exception:
        pass

    # Fallback to env vars
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    tenant = os.environ.get("TENANT_NAME")
    if client_id and client_secret and tenant:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "tenant": tenant,
        }
    return None


def _refresh_token(token_set: MSGraphTokenSet) -> str | None:
    """Use MSAL to refresh an expired token set. Returns the new access token."""
    try:
        import msal
    except ImportError:
        return None

    azure = _get_azure_config()
    if not azure:
        return None

    authority = f"https://login.microsoftonline.com/{azure['tenant']}"
    cca = msal.ConfidentialClientApplication(
        azure["client_id"],
        authority=authority,
        client_credential=azure["client_secret"],
    )

    refresh_token = _decrypt(token_set.refresh_token_enc)
    result = cca.acquire_token_by_refresh_token(
        refresh_token,
        scopes=token_set.scopes or ["https://graph.microsoft.com/.default"],
    )

    if "access_token" not in result:
        # Refresh failed — token may have been revoked
        return None

    # Persist refreshed tokens
    now = datetime.datetime.utcnow()
    token_set.access_token_enc = _encrypt(result["access_token"])
    if result.get("refresh_token"):
        token_set.refresh_token_enc = _encrypt(result["refresh_token"])
    token_set.expires_at = now + datetime.timedelta(
        seconds=int(result.get("expires_in", 3600))
    )
    token_set.updated_at = now
    token_set.save()

    return result["access_token"]
