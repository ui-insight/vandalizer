import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import Settings

MGMT_API_KEY_PREFIX = "vk_live_"
MGMT_API_KEY_DISPLAY_LEN = 12  # length of stored prefix shown in admin UI


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def hash_api_token(token: str) -> str:
    # SHA-256 (unsalted) is appropriate here: tokens are 256 bits of entropy
    # from secrets.token_urlsafe(32), so rainbow-table / dictionary attacks
    # are infeasible. Determinism lets us index and look up by hash.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_mgmt_api_key() -> tuple[str, str, str]:
    """Generate a management API key.

    Returns (full_token, display_prefix, sha256_hash). The full_token is
    shown to the issuer once and never recoverable; only the prefix and
    hash are persisted.
    """
    raw = secrets.token_urlsafe(32)
    full = f"{MGMT_API_KEY_PREFIX}{raw}"
    return full, full[:MGMT_API_KEY_DISPLAY_LEN], hash_api_token(full)


def create_access_token(
    user_id: str, settings: Settings, token_version: int = 0
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access", "ver": token_version},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    user_id: str, settings: Settings, token_version: int = 0
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_expire_days
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh", "ver": token_version},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, settings: Settings) -> dict | None:
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except InvalidTokenError:
        return None
