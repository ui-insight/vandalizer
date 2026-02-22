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
    return user


async def get_api_key_user(
    x_api_key: str = Header(...),
) -> User:
    """Authenticate via x-api-key header (for external API integrations)."""
    user = await User.find_one(User.api_token == x_api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return user
