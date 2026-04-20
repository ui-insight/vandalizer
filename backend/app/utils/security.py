import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import Settings


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def hash_api_token(token: str) -> str:
    # SHA-256 (unsalted) is appropriate here: tokens are 256 bits of entropy
    # from secrets.token_urlsafe(32), so rainbow-table / dictionary attacks
    # are infeasible. Determinism lets us index and look up by hash.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: str, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: str, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_expire_days
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
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
