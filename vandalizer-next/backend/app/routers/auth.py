import datetime
import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Cookie, status
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.system_config import SystemConfig
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services import auth_service
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter()


def _set_tokens(response: Response, user: User, settings: Settings) -> None:
    access = create_access_token(user.user_id, settings)
    refresh = create_refresh_token(user.user_id, settings)
    response.set_cookie(
        "access_token",
        access,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
        max_age=settings.jwt_access_expire_minutes * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
        max_age=settings.jwt_refresh_expire_days * 86400,
    )


async def _user_response(user: User) -> UserResponse:
    current_team_uuid = None
    if user.current_team:
        from app.models.team import Team

        team = await Team.get(user.current_team)
        if team:
            current_team_uuid = team.uuid
    return UserResponse(
        id=str(user.id),
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        is_admin=user.is_admin,
        current_team=str(user.current_team) if user.current_team else None,
        current_team_uuid=current_team_uuid,
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
):
    user = await auth_service.authenticate(body.user_id, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    _set_tokens(response, user, settings)
    return await _user_response(user)


@router.post("/register")
async def register(
    body: RegisterRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
):
    try:
        user = await auth_service.register(
            body.user_id or body.email, body.email, body.password, body.name
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    _set_tokens(response, user, settings)
    return await _user_response(user)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return await _user_response(user)


@router.post("/api-token/generate")
async def generate_api_token(user: User = Depends(get_current_user)):
    """Generate a new API token for the current user."""
    token = secrets.token_urlsafe(32)
    user.api_token = token
    user.api_token_created_at = datetime.datetime.now(datetime.timezone.utc)
    await user.save()
    return {"api_token": token, "created_at": user.api_token_created_at.isoformat()}


@router.post("/api-token/revoke")
async def revoke_api_token(user: User = Depends(get_current_user)):
    """Revoke the current user's API token."""
    user.api_token = None
    user.api_token_created_at = None
    await user.save()
    return {"ok": True}


@router.get("/api-token/status")
async def api_token_status(user: User = Depends(get_current_user)):
    """Check if the current user has an active API token."""
    return {
        "has_token": user.api_token is not None,
        "created_at": user.api_token_created_at.isoformat() if user.api_token_created_at else None,
    }


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    settings: Settings = Depends(get_settings),
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token"
        )
    payload = decode_token(refresh_token, settings)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    user = await User.find_one(User.user_id == payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    _set_tokens(response, user, settings)
    return await _user_response(user)


# ---------------------------------------------------------------------------
# Public auth config (no auth required)
# ---------------------------------------------------------------------------


def _get_azure_provider(config: SystemConfig) -> dict | None:
    """Extract the enabled Azure provider from config, or None."""
    for p in config.oauth_providers:
        if p.get("provider") == "azure" and p.get("enabled"):
            required = ("client_id", "client_secret", "tenant_id")
            if all(p.get(k) for k in required):
                return p
    return None


@router.get("/config")
async def auth_config():
    """Public endpoint — returns which auth methods are available."""
    config = await SystemConfig.get_config()
    providers = []
    if "oauth" in config.auth_methods:
        azure = _get_azure_provider(config)
        providers.append(
            {
                "provider": "azure",
                "display_name": azure.get("label", "Sign in with U of I")
                if azure
                else "Azure SSO",
                "configured": azure is not None,
            }
        )
    return {
        "auth_methods": config.auth_methods,
        "oauth_providers": providers,
    }


# ---------------------------------------------------------------------------
# Azure OAuth
# ---------------------------------------------------------------------------

_AZURE_AUTHORIZE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_AZURE_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_ME = "https://graph.microsoft.com/v1.0/me"


@router.get("/oauth/azure")
async def oauth_azure_login(settings: Settings = Depends(get_settings)):
    """Redirect the browser to Azure AD for authentication."""
    config = await SystemConfig.get_config()
    azure = _get_azure_provider(config)
    if not azure:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Azure OAuth not configured",
        )

    redirect_uri = f"{settings.frontend_url}/api/auth/oauth/azure/callback"
    params = {
        "client_id": azure["client_id"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email User.Read",
    }
    url = _AZURE_AUTHORIZE.format(tenant=azure["tenant_id"])
    return RedirectResponse(f"{url}?{urllib.parse.urlencode(params)}")


@router.get("/oauth/azure/callback")
async def oauth_azure_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    """Azure AD redirects here after the user authenticates."""
    landing = f"{settings.frontend_url}/landing"

    if error or not code:
        return RedirectResponse(f"{landing}?error=oauth_failed")

    config = await SystemConfig.get_config()
    azure = _get_azure_provider(config)
    if not azure:
        return RedirectResponse(f"{landing}?error=oauth_failed")

    redirect_uri = f"{settings.frontend_url}/api/auth/oauth/azure/callback"

    # Exchange code for token
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _AZURE_TOKEN.format(tenant=azure["tenant_id"]),
                data={
                    "client_id": azure["client_id"],
                    "client_secret": azure["client_secret"],
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()

            # Fetch user profile from Microsoft Graph
            me_resp = await client.get(
                _GRAPH_ME,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            me_resp.raise_for_status()
            profile = me_resp.json()
    except httpx.HTTPError:
        return RedirectResponse(f"{landing}?error=oauth_failed")

    upn = profile.get("userPrincipalName", "")
    mail = profile.get("mail") or profile.get("userPrincipalName")
    display_name = profile.get("displayName")

    user = await auth_service.resolve_oauth_user(upn, mail, display_name)

    response = RedirectResponse(f"{settings.frontend_url}/")
    _set_tokens(response, user, settings)
    return response
