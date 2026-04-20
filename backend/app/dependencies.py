from functools import lru_cache

from fastapi import Cookie, Depends, Header, HTTPException, status

from app.config import Settings
from app.models.user import User
from app.utils.security import decode_token


@lru_cache
def get_settings() -> Settings:
    return Settings()


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    settings: Settings = Depends(get_settings),
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    payload = decode_token(access_token, settings)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    user = await User.find_one(User.user_id == payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    # Block locked demo users from all API access
    if user.is_demo_user and user.demo_status == "locked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DEMO_EXPIRED",
        )
    return user


async def get_api_key_user(
    x_api_key: str = Header(...),
) -> User:
    """Authenticate via x-api-key header (for external API integrations)."""
    import datetime

    from app.utils.security import hash_api_token

    user = await User.find_one(User.api_token_hash == hash_api_token(x_api_key))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    # Check token expiry — stored value may be naive (UTC assumed)
    expires = user.api_token_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        if expires < datetime.datetime.now(datetime.timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key expired",
            )
    # Block locked demo users from API key access too
    if user.is_demo_user and user.demo_status == "locked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DEMO_EXPIRED",
        )
    return user
