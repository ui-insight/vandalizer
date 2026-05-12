import datetime
from functools import lru_cache
from typing import Callable, Coroutine

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from app.config import Settings
from app.models.api_key import ApiKey
from app.models.user import User
from app.services import audit_service
from app.utils.security import decode_token, hash_api_token

# All scopes recognized by the /api/mgmt/v1 surface. Endpoints request a
# scope via require_mgmt_scope; keys must hold it (or "*") to authorize.
MGMT_SCOPES: frozenset[str] = frozenset({
    # Read scopes
    "metrics:read",
    "users:read",
    "teams:read",
    "workflows:read",
    "documents:read",
    "activity:read",
    "audit:read",
    "config:read",
    "validation:read",
    # Write scopes (validation setup only — no user/config mutation surface)
    "validation:write",
    # Action scopes — spend tokens / kick off work
    "validation:run",
    "workflows:run",
    "extractions:run",
})


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


def require_mgmt_scope(
    required: str,
) -> Callable[..., Coroutine[None, None, ApiKey]]:
    """Factory: returns a FastAPI dep that authorizes a management API call.

    Verifies the X-API-Key header against an ApiKey record, checks the key
    is not revoked or expired, confirms the key holds the required scope
    (or "*"), updates last_used metadata, and writes an audit log entry.
    """
    if required not in MGMT_SCOPES:
        raise ValueError(f"Unknown mgmt scope: {required}")

    async def _dep(
        request: Request,
        x_api_key: str = Header(..., alias="X-API-Key"),
    ) -> ApiKey:
        key = await ApiKey.find_one(ApiKey.key_hash == hash_api_token(x_api_key))
        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        if key.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key revoked",
            )
        expires = key.expires_at
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            if expires < now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key expired",
                )
        if required not in key.scopes and "*" not in key.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope: {required}",
            )

        ip = request.client.host if request.client else None
        key.last_used_at = now
        key.last_used_ip = ip
        await key.save()

        await audit_service.log_event(
            action=f"mgmt.{required}",
            actor_user_id=str(key.id),
            actor_type="api_key",
            resource_type="mgmt_api",
            resource_id=request.url.path,
            detail={"method": request.method, "key_name": key.name},
            ip_address=ip,
        )
        return key

    return _dep


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
