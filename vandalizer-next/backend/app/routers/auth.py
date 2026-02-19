from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, status

from app.config import Settings
from app.dependencies import get_current_user, get_settings
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
            body.user_id, body.email, body.password, body.name
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
