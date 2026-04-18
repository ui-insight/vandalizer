import datetime
import secrets
import urllib.parse
import logging

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Cookie, status
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.rate_limit import limiter
from app.models.system_config import SystemConfig
from app.utils.encryption import decrypt_value
from app.models.user import User
from app.schemas.auth import DeleteAccountRequest, ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest, UpdateProfileRequest, UserResponse
from app.services import auth_service, audit_service
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

logger = logging.getLogger(__name__)

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

    # Resolve support agent status from system config
    is_support_agent = False
    if user.is_admin:
        is_support_agent = True
    else:
        from app.models.system_config import SystemConfig
        config = await SystemConfig.get_config()
        contacts = config.support_contacts or []
        is_support_agent = any(c.get("user_id") == user.user_id for c in contacts)

    return UserResponse(
        id=str(user.id),
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        is_admin=user.is_admin,
        is_staff=user.is_staff,
        is_examiner=user.is_examiner,
        is_support_agent=is_support_agent,
        is_demo_user=user.is_demo_user,
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


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    settings: Settings = Depends(get_settings),
):
    """Send a password reset email. Always returns success to avoid email enumeration."""
    email = body.email.strip().lower()
    user = await User.find_one(User.email == email)
    if not user:
        user = await User.find_one(User.user_id == email)
    if not user or not user.password_hash:
        logger.info("Password reset: no matching user with password for %s", email)
        return {"ok": True}

    # Generate token, store in Redis with 1-hour TTL
    token = secrets.token_urlsafe(32)
    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        await r.set(f"pw_reset:{token}", user.user_id, ex=3600)
    finally:
        await r.aclose()

    from app.services.email_service import send_email, password_reset_email

    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    subject, html = password_reset_email(user.name or user.user_id, reset_url)
    sent = await send_email(user.email or email, subject, html, settings)
    logger.info("Password reset: user=%s, email=%s, sent=%s", user.user_id, user.email, sent)

    return {"ok": True}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    settings: Settings = Depends(get_settings),
):
    """Reset password using a token from the forgot-password email."""
    from app.utils.security import hash_password

    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        user_id = await r.get(f"pw_reset:{body.token}")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset link. Please request a new one.",
            )
        # Consume the token (one-time use)
        await r.delete(f"pw_reset:{body.token}")
    finally:
        await r.aclose()

    user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
    user = await User.find_one(User.user_id == user_id_str)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found.",
        )

    user.password_hash = hash_password(body.password)
    await user.save()

    return {"ok": True}


@router.get("/magic-login")
async def magic_login(
    token: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    """Consume a one-time magic login token and redirect to the app."""
    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        user_id = await r.get(f"magic_login:{token}")
        if not user_id:
            return RedirectResponse(url=f"{settings.frontend_url}/landing?error=invalid_link")
        await r.delete(f"magic_login:{token}")
    finally:
        await r.aclose()

    user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
    user = await User.find_one(User.user_id == user_id_str)
    if not user:
        return RedirectResponse(url=f"{settings.frontend_url}/landing?error=invalid_link")

    response = RedirectResponse(url=f"{settings.frontend_url}/")
    _set_tokens(response, user, settings)
    await audit_service.log_event(
        action="user.magic_login",
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=user.user_id,
    )
    return response


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


@router.get("/email-preferences")
async def get_email_preferences(user: User = Depends(get_current_user)):
    """Get the current user's email notification preferences."""
    return user.email_preferences or {"onboarding": True, "nudges": True}


@router.put("/email-preferences")
async def update_email_preferences(
    body: dict,
    user: User = Depends(get_current_user),
):
    """Update email notification preferences."""
    prefs = user.email_preferences or {}
    for key in ("onboarding", "nudges"):
        if key in body:
            prefs[key] = bool(body[key])
    user.email_preferences = prefs
    await user.save()
    return prefs


@router.post("/account/delete/preflight")
async def delete_account_preflight(user: User = Depends(get_current_user)):
    """Pre-flight check: returns data counts and blocking conditions."""
    from app.services.account_deletion_service import get_deletion_summary

    summary = await get_deletion_summary(user.user_id)
    summary["has_password"] = bool(user.password_hash)
    return summary


@router.post("/account/delete")
@limiter.limit("3/hour")
async def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    response: Response,
    user: User = Depends(get_current_user),
):
    """Permanently delete the current user's account and all data."""
    if body.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(status_code=400, detail="Confirmation text does not match.")

    if user.password_hash:
        if not body.password:
            raise HTTPException(status_code=400, detail="Password is required.")
        verified = await auth_service.authenticate(user.user_id, body.password)
        if not verified:
            raise HTTPException(status_code=401, detail="Incorrect password.")

    from app.services.account_deletion_service import get_deletion_summary, delete_user_account

    summary = await get_deletion_summary(user.user_id)
    if not summary["can_delete"]:
        raise HTTPException(status_code=409, detail=summary["blocking_reason"])

    await audit_service.log_event(
        action="user.account_deletion_initiated",
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=user.user_id,
        ip_address=request.client.host if request.client else None,
    )

    await delete_user_account(user.user_id)

    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


_API_TOKEN_EXPIRY_DAYS = 365


@router.post("/api-token/generate")
async def generate_api_token(user: User = Depends(get_current_user)):
    """Generate a new API token for the current user (expires in 365 days)."""
    try:
        token = secrets.token_urlsafe(32)
        now = datetime.datetime.now(datetime.timezone.utc)
        user.api_token = token
        user.api_token_created_at = now
        user.api_token_expires_at = now + datetime.timedelta(days=_API_TOKEN_EXPIRY_DAYS)
        await user.save()
        logger.info(f"API token generated for user: {user.user_id}")
        return {
            "api_token": token,
            "created_at": user.api_token_created_at.isoformat(),
            "expires_at": user.api_token_expires_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error generating API token for user {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate API token: {str(e)}"
        )


@router.post("/api-token/revoke")
async def revoke_api_token(user: User = Depends(get_current_user)):
    """Revoke the current user's API token."""
    try:
        user.api_token = None
        user.api_token_created_at = None
        user.api_token_expires_at = None
        await user.save()
        logger.info(f"API token revoked for user: {user.user_id}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error revoking API token for user {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke API token: {str(e)}"
        )


@router.get("/api-token/status")
async def api_token_status(user: User = Depends(get_current_user)):
    """Check if the current user has an active API token."""
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = user.api_token_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        expired = expires is not None and expires < now
        return {
            "has_token": user.api_token is not None,
            "created_at": user.api_token_created_at.isoformat() if user.api_token_created_at else None,
            "expires_at": user.api_token_expires_at.isoformat() if user.api_token_expires_at else None,
            "expired": expired,
        }
    except Exception as e:
        logger.error(f"Error checking API token status for user {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check API token status: {str(e)}"
        )


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

    # Trial system is off by default for self-hosters
    settings = get_settings()
    demo_login_enabled = False
    if settings.enable_trial_system:
        from app.models.demo import DemoApplication

        demo_login_enabled = await DemoApplication.find(
            {"status": {"$in": ["active", "completed"]}},
        ).count() > 0

    return {
        "auth_methods": config.auth_methods,
        "oauth_providers": providers,
        "demo_login_enabled": demo_login_enabled,
        "trial_system_enabled": settings.enable_trial_system,
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

    # Generate CSRF state token and store in Redis with 10-minute TTL
    state = secrets.token_urlsafe(32)
    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        await r.set(f"oauth_state:{state}", "1", ex=600)
    finally:
        await r.aclose()

    redirect_uri = azure.get("redirect_uri") or f"{settings.frontend_url}/api/auth/oauth/azure/callback"
    params = {
        "client_id": azure["client_id"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email User.Read",
        "state": state,
    }
    url = _AZURE_AUTHORIZE.format(tenant=azure["tenant_id"])
    return RedirectResponse(f"{url}?{urllib.parse.urlencode(params)}")


@router.get("/oauth/azure/callback")
async def oauth_azure_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    """Azure AD redirects here after the user authenticates."""
    landing = f"{settings.frontend_url}/landing"

    # Validate OAuth state token to prevent CSRF
    if not state:
        return RedirectResponse(f"{landing}?error=oauth_state_invalid")
    r = aioredis.from_url(f"redis://{settings.redis_host}:6379")
    try:
        stored = await r.get(f"oauth_state:{state}")
        if not stored:
            return RedirectResponse(f"{landing}?error=oauth_state_invalid")
        # Delete after validation (one-time use)
        await r.delete(f"oauth_state:{state}")
    finally:
        await r.aclose()

    if error or not code:
        return RedirectResponse(f"{landing}?error=oauth_failed")

    config = await SystemConfig.get_config()
    azure = _get_azure_provider(config)
    if not azure:
        return RedirectResponse(f"{landing}?error=oauth_failed")

    redirect_uri = azure.get("redirect_uri") or f"{settings.frontend_url}/api/auth/oauth/azure/callback"

    # Exchange code for token
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _AZURE_TOKEN.format(tenant=azure["tenant_id"]),
                data={
                    "client_id": azure["client_id"],
                    "client_secret": decrypt_value(azure["client_secret"]),
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
