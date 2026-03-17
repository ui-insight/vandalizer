import datetime
import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Cookie, status
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.rate_limit import limiter
from app.models.system_config import SystemConfig
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UpdateProfileRequest, UserResponse
from app.services import auth_service, audit_service
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
        is_examiner=user.is_examiner,
        current_team=str(user.current_team) if user.current_team else None,
        current_team_uuid=current_team_uuid,
    )


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
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
    await audit_service.log_event(
        action="user.login",
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=user.user_id,
        ip_address=request.client.host if request.client else None,
    )
    user_resp = await _user_response(user)
    result = user_resp.model_dump()

    # If demo user is locked, include demo_expired flag so frontend can redirect
    if user.is_demo_user and user.demo_status == "locked":
        from app.models.demo import DemoApplication

        demo_app = await DemoApplication.find_one(
            DemoApplication.user_id == user.user_id
        )
        result["demo_expired"] = True
        result["demo_uuid"] = demo_app.uuid if demo_app else None
        result["demo_feedback_token"] = (
            demo_app.post_questionnaire_token if demo_app else None
        )

    return result


@router.post("/register")
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
):
    try:
        user = await auth_service.register(
            body.user_id or body.email, body.email, body.password, body.name
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please check your details and try again.",
        )
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


@router.put("/profile")
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
):
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = body.email
    await user.save()
    return await _user_response(user)


_API_TOKEN_EXPIRY_DAYS = 365


@router.post("/api-token/generate")
async def generate_api_token(user: User = Depends(get_current_user)):
    """Generate a new API token for the current user (expires in 365 days)."""
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    user.api_token = token
    user.api_token_created_at = now
    user.api_token_expires_at = now + datetime.timedelta(days=_API_TOKEN_EXPIRY_DAYS)
    await user.save()
    return {
        "api_token": token,
        "created_at": user.api_token_created_at.isoformat(),
        "expires_at": user.api_token_expires_at.isoformat(),
    }


@router.post("/api-token/revoke")
async def revoke_api_token(user: User = Depends(get_current_user)):
    """Revoke the current user's API token."""
    user.api_token = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    await user.save()
    return {"ok": True}


@router.get("/api-token/status")
async def api_token_status(user: User = Depends(get_current_user)):
    """Check if the current user has an active API token."""
    now = datetime.datetime.now(datetime.timezone.utc)
    expired = (
        user.api_token_expires_at is not None
        and user.api_token_expires_at < now
    )
    return {
        "has_token": user.api_token is not None,
        "created_at": user.api_token_created_at.isoformat() if user.api_token_created_at else None,
        "expires_at": user.api_token_expires_at.isoformat() if user.api_token_expires_at else None,
        "expired": expired,
    }


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh(
    request: Request,
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
    """Public endpoint  - returns which auth methods are available."""
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


# ---------------------------------------------------------------------------
# SAML SSO
# ---------------------------------------------------------------------------

@router.get("/saml/login")
async def saml_login(request: Request, settings: Settings = Depends(get_settings)):
    """Initiate SAML login — redirects to IdP."""
    config = await SystemConfig.get_config()
    saml_provider = None
    for p in config.oauth_providers:
        if p.get("provider") == "saml":
            saml_provider = p
            break

    if not saml_provider:
        raise HTTPException(status_code=400, detail="SAML not configured")

    from app.services.saml_service import build_authn_request
    redirect_url = build_authn_request(saml_provider, request)
    return RedirectResponse(redirect_url)


@router.post("/saml/acs")
async def saml_acs(request: Request, settings: Settings = Depends(get_settings)):
    """SAML Assertion Consumer Service — receives IdP response."""
    config = await SystemConfig.get_config()
    saml_provider = None
    for p in config.oauth_providers:
        if p.get("provider") == "saml":
            saml_provider = p
            break

    if not saml_provider:
        raise HTTPException(status_code=400, detail="SAML not configured")

    form_data = await request.form()
    post_data = dict(form_data)

    from app.services.saml_service import process_saml_response
    try:
        attrs = process_saml_response(saml_provider, request, post_data)
    except ValueError as e:
        landing = saml_provider.get("error_redirect", settings.frontend_url + "/login")
        return RedirectResponse(f"{landing}?error=saml_failed&detail={e}")

    user = await auth_service.resolve_saml_user(
        uid=attrs["uid"],
        email=attrs["email"],
        display_name=attrs["display_name"],
        department=attrs.get("department"),
    )

    await audit_service.log_event(
        action="user.login",
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=user.user_id,
        detail={"method": "saml"},
        ip_address=request.client.host if request.client else None,
    )

    response = RedirectResponse(f"{settings.frontend_url}/")
    _set_tokens(response, user, settings)
    return response


@router.get("/saml/metadata")
async def saml_metadata(request: Request):
    """Return SP metadata XML for IdP configuration."""
    config = await SystemConfig.get_config()
    saml_provider = None
    for p in config.oauth_providers:
        if p.get("provider") == "saml":
            saml_provider = p
            break

    if not saml_provider:
        raise HTTPException(status_code=400, detail="SAML not configured")

    from app.services.saml_service import get_sp_metadata
    metadata_xml = get_sp_metadata(saml_provider, request)
    return Response(content=metadata_xml, media_type="application/xml")
