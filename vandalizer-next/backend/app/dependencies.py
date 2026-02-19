from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException, status

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
