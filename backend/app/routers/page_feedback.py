"""Questions and flags from a page's viewers to its owner (app.services.page_feedback)."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.page_feedback import PageFeedback
from app.models.user import User
from app.rate_limit import limiter
from app.routers.artifacts import authorized, public_doc
from app.services import page_feedback as service

router = APIRouter()


class FeedbackRequest(BaseModel):
    revision: str = Field(max_length=64)
    anchor: dict[str, Any] = Field(default_factory=dict)
    message: str = Field(max_length=service.MAX_MESSAGE + 100)
    kind: Literal["question", "flag"] = "question"


class PublicFeedbackRequest(BaseModel):
    anchor: dict[str, Any] = Field(default_factory=dict)
    message: str = Field(max_length=service.MAX_MESSAGE + 100)
    kind: Literal["question", "flag"] = "question"
    name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=254)
    # Left empty by people; filled by form-filling bots.
    website: str = Field(default="", max_length=200)


class AnswerRequest(BaseModel):
    text: str = Field(max_length=service.MAX_ANSWER + 100)
    on_page: bool = False


class StatusRequest(BaseModel):
    status: Literal["open", "answered", "resolved"]


def _raise(e: Exception) -> None:
    if isinstance(e, PermissionError):
        raise HTTPException(403, str(e)) from e
    raise HTTPException(422, str(e)) from e


async def _owned_feedback(uuid: str, feedback_uuid: str, user: User) -> tuple[dict, PageFeedback]:
    doc = await authorized(uuid, user, manage=True)
    fb = await PageFeedback.find_one({"uuid": feedback_uuid, "artifact_uuid": uuid})
    if not fb:
        raise HTTPException(404, "Question not found")
    return doc, fb


@router.get("/{uuid}/feedback", response_model=None)
async def list_feedback(uuid: str, revision: str = "", user: User = Depends(get_current_user)) -> dict:
    """Owner: every question. Team member: their own, plus answers shown on this version."""
    doc = await authorized(uuid, user)
    owner = doc["user_id"] == user.user_id
    if owner:
        return {"role": "owner", "items": await service.for_owner(doc), "settings": service.settings_of(doc),
                "shared_by": await service.shared_by(doc)}
    return {"role": "member", "items": await service.for_member(doc, user, revision), "shared_by": await service.shared_by(doc)}


@router.post("/{uuid}/feedback", response_model=None)
@limiter.limit("20/hour")
async def ask(request: Request, uuid: str, body: FeedbackRequest, user: User = Depends(get_current_user)) -> dict:
    """A team member's question or flag on a spot of the page."""
    doc = await authorized(uuid, user)
    try:
        fb = await service.submit(doc, revision=body.revision, anchor=body.anchor, message=body.message,
                                  kind=body.kind, author=user)
    except (ValueError, PermissionError) as e:
        _raise(e)
    return service.serialize(fb, for_owner=False)


@router.post("/{uuid}/feedback/{feedback_uuid}/answer", response_model=None)
async def answer(uuid: str, feedback_uuid: str, body: AnswerRequest, user: User = Depends(get_current_user)) -> dict:
    doc, fb = await _owned_feedback(uuid, feedback_uuid, user)
    try:
        fb = await service.answer(doc, fb, user, body.text, on_page=body.on_page)
    except ValueError as e:
        _raise(e)
    return service.serialize(fb, for_owner=True)


@router.post("/{uuid}/feedback/{feedback_uuid}/status", response_model=None)
async def set_status(uuid: str, feedback_uuid: str, body: StatusRequest, user: User = Depends(get_current_user)) -> dict:
    _doc, fb = await _owned_feedback(uuid, feedback_uuid, user)
    try:
        fb = await service.set_status(fb, body.status)
    except ValueError as e:
        _raise(e)
    return service.serialize(fb, for_owner=True)


@router.put("/{uuid}/feedback-settings", response_model=None)
async def update_settings(uuid: str, body: dict, user: User = Depends(get_current_user)) -> dict:
    """Owner: take questions from public-link viewers; the contact line shown on the page."""
    doc = await authorized(uuid, user, manage=True)
    try:
        settings = await service.update_settings(doc, body)
    except ValueError as e:
        _raise(e)
    doc["feedback"] = settings
    return {"settings": settings, "shared_by": await service.shared_by(doc)}


@router.get("/public/{token}/feedback", response_model=None)
async def public_feedback(token: str, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """Who shared the page, whether it takes questions, and answers shown on it."""
    # The request carries the signed-in viewer for a sign-in-only link.
    doc, rev = await public_doc(token, settings, request)
    return {
        "shared_by": await service.shared_by(doc),
        "public_questions": service.settings_of(doc)["public_questions"],
        "items": await service.for_public(doc, rev["uuid"]),
    }


@router.post("/public/{token}/feedback", response_model=None)
@limiter.limit("5/hour")
async def public_ask(request: Request, token: str, body: PublicFeedbackRequest, settings: Settings = Depends(get_settings)) -> dict:
    """A public-link viewer's question, when the owner allows them."""
    doc, rev = await public_doc(token, settings, request)
    if body.website.strip():
        # Pretend success to a bot; nothing is stored or sent.
        return {"ok": True}
    try:
        await service.submit(doc, revision=rev["uuid"], anchor=body.anchor, message=body.message, kind=body.kind,
                             public_token=token, name=body.name, email=body.email)
    except (ValueError, PermissionError) as e:
        _raise(e)
    return {"ok": True}
