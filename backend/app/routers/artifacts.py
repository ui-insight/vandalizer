"""Authenticated artifact drafts and explicitly published revision links."""
from collections.abc import Callable
from typing import Concatenate, ParamSpec, TypeVar
from pymongo.database import Database
import functools
import re
from datetime import timezone
from typing import Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response
from fastapi.responses import HTMLResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.artifact import PageAnswerRequest, PageFeedbackSettingsRequest, PageQuestionRequest, PublicPageQuestionRequest
from app.schemas.artifact import ChatArtifactRequest, CreateArtifactRequest, DuplicateArtifactRequest, PublishArtifactRequest, RenameArtifactRequest, ReviseArtifactRequest, ShareArtifactRequest
from app.services.page_links import prepare_page_links
from app.services import access_control, artifacts, page_feedback
from app.services import transcript_pages
from app.services.page_printing import render_page
from app.services.page_embedding import prepare_page_embed
from app.tasks import get_sync_db
from app.utils.content_disposition import content_disposition

router = APIRouter()


async def authorized_project(uuid: str | None, user: User) -> None:
    from app.services.project_service import get_authorized_project
    if uuid and not await get_authorized_project(uuid, user):
        raise HTTPException(404, "Project not found")


@router.get("/browse", response_model=None)
async def browse_artifacts(
    search: str = Query(default="", max_length=200),
    sort: Literal["updated", "newest", "title"] = "updated",
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=50),
    project_uuid: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    await authorized_project(project_uuid, user)
    access = await access_control.get_team_access_context(user)
    conditions = [{"deleted_at": None}, {"$or": [
        {"user_id": user.user_id}, {"team_id": {"$in": list(access.team_uuids | access.team_object_ids)}},
    ]}]
    if project_uuid:
        from app.models.project import ProjectPin
        pins = await ProjectPin.find({"project_uuid": project_uuid, "pin_type": "artifact"}).to_list()
        conditions.append({"$or": [{"project_uuid": project_uuid}, {"uuid": {"$in": [p.target_id for p in pins]}}]})
    order = {"updated": ("updated_at", -1), "newest": ("created_at", -1), "title": ("title", 1)}[sort]

    def query(db: Database[dict]) -> dict:
        # Match access first and remove HTML before sorting. Early pages without
        # a denormalized title remain searchable without a data migration.
        pipeline = [{"$match": {"$and": conditions}}, *artifacts.visible_metadata_stages(user.user_id)]
        if search.strip():
            pipeline.append({"$match": {"title": {"$regex": re.escape(search.strip()), "$options": "i"}}})
        pipeline.append({"$facet": {
            "items": [{"$sort": dict([order, ("uuid", 1)])}, {"$skip": (page - 1) * page_size}, {"$limit": page_size}],
            "total": [{"$count": "value"}],
        }})
        result = next(db.html_artifacts.aggregate(pipeline))
        return {"items": [artifacts.metadata(doc, doc["user_id"] == user.user_id) for doc in result["items"]],
                "total": result["total"][0]["value"] if result["total"] else 0, "page": page, "page_size": page_size}
    return await run(query)


P = ParamSpec('P')
R = TypeVar('R')


async def run(fn: Callable[Concatenate[Database[dict], P], R], *args: P.args, **kwargs: P.kwargs) -> R:
    return await anyio.to_thread.run_sync(functools.partial(fn, get_sync_db(), *args, **kwargs))


async def authorized(uuid: str, user: User, manage: bool=False) -> dict:
    doc = await run(artifacts.get, uuid)
    if doc["user_id"] == user.user_id:
        return doc
    if not manage and access_control.can_view_team(doc.get("team_id"), await access_control.get_team_access_context(user)):
        return artifacts.team_view(doc)
    raise HTTPException(404, "Page not found")


def content_response(rev: dict, download: bool=False, *, version: int=1, view: Literal["content", "full", "print", "embed"]="content", mark: str | None=None) -> HTMLResponse:
    title = rev["title"].strip() or "Page"
    if mark and not download:
        # A viewer's question points here: highlight it for the owner (rendering only).
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(rev["html"], "html.parser")
        page_feedback.mark(soup, mark)
        rev = {**rev, "html": str(soup)}
    filename = title if title.lower().endswith(".html") else f"{title}.html"
    html, csp = render_page(rev, version, "content" if download else view)
    html, csp = prepare_page_links(html, csp)
    if view == "embed" and not download:
        html, csp = prepare_page_embed(html, csp)
    return HTMLResponse(html, headers={
        "Content-Security-Policy": csp, "X-Frame-Options": "SAMEORIGIN",
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow",
        **({"Content-Disposition": content_disposition(filename)} if download else {}),
    })


@router.get("", response_model=None)
async def list_artifacts(user: User = Depends(get_current_user)) -> list[dict]:
    result = await browse_artifacts(search="", sort="updated", page=1, page_size=100, project_uuid=None, user=user)
    items: list[dict] = result["items"]
    return items


@router.post("", response_model=None)
@limiter.limit("20/minute")
async def create_artifact(request: Request, body: CreateArtifactRequest, user: User = Depends(get_current_user)) -> dict:
    await authorized_project(body.project_uuid, user)
    return artifacts.metadata(await run(artifacts.create, user.user_id, body.title, body.html, body.request_id,
                                        {"kind": "editor", "project_uuid": body.project_uuid}), True)


@router.post("/from-chat", response_model=None)
@limiter.limit("20/minute")
async def chat_artifact(request: Request, body: ChatArtifactRequest, user: User = Depends(get_current_user)) -> dict[str, object]:
    await authorized_project(body.project_uuid, user)
    conversation = None
    if body.conversation_uuid:
        from app.models.chat import ChatConversation
        conversation = await ChatConversation.find_one({"uuid": body.conversation_uuid, "user_id": user.user_id})
        if not conversation:
            raise HTTPException(404, "Conversation not found")
    try:
        saved, reused = await run(transcript_pages.save, user.user_id, body, getattr(conversation, 'title', None))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**artifacts.metadata(saved, True), 'reused': reused}


@router.post("/from-workflow/{session_id}", response_model=None)
@limiter.limit("20/minute")
async def workflow_artifact(request: Request, session_id: str, step: str | None = None, user: User = Depends(get_current_user)) -> dict:
    from app.services.workflow_service import _get_authorized_workflow_result
    result = await _get_authorized_workflow_result(session_id, user)
    if not result:
        raise HTTPException(404, "Workflow run not found")
    return artifacts.metadata(await run(artifacts.from_workflow, result.model_dump(), user.user_id, step, recreate_deleted=True), True)


async def public_doc(token: str, settings: Settings) -> tuple[dict, dict]:
    if not settings.artifact_public_sharing_enabled:
        raise HTTPException(404, "Page not found")
    doc = await run(lambda db: db.html_artifacts.find_one({
        "$or": [{"public_token": token}, {"publications.token": token}], "deleted_at": None,
    }))
    if not doc:
        raise HTTPException(404, "Page not found")
    selected = doc.get("published_revision") if doc.get("public_token") == token else next(
        (p["revision"] for p in doc.get("publications", []) if p["token"] == token), None)
    if not selected:
        raise HTTPException(404, "Page not found")
    return doc, artifacts.revision(doc, selected)


@router.get("/public/{token}", response_model=None)
async def get_public(token: str, response: Response, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    doc, rev = await public_doc(token, settings)
    # Mongo may return naive UTC datetimes. Never use the page's updated_at:
    # it advances when an owner saves a private draft.
    updated_at = rev["created_at"]
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    response.headers["Cache-Control"] = "no-store"
    return {"title": rev["title"], "revision": rev["uuid"],
            "version": next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == rev["uuid"]),
            "updated_at": updated_at,
            "shared_by": await run(page_feedback.shared_by, doc),
            "questions_enabled": bool(doc.get("public_questions")),
            "notes": await run(page_feedback.page_notes, doc["uuid"], rev["uuid"])}


@router.get("/public/{token}/content", response_model=None)
async def public_content(token: str, download: bool = False, revision: str | None = None,
                         view: Literal["content", "full", "print", "embed"] = "content", settings: Settings = Depends(get_settings)) -> HTMLResponse:
    doc, rev = await public_doc(token, settings)
    # Keep a viewer's version/date label matched to the HTML even if the owner
    # publishes again between the metadata request and the iframe request.
    if revision is not None and revision != rev["uuid"]:
        raise HTTPException(409, "The published page changed. Reload the page to view the current version.")
    version = next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == rev["uuid"])
    return content_response(rev, download, version=version, view=view)


@router.get("/{uuid}", response_model=None)
async def get_artifact(uuid: str, user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict[str, object]:
    doc = await authorized(uuid, user)
    owner = doc["user_id"] == user.user_id
    result = {**artifacts.metadata(doc, owner), "public_sharing_enabled": settings.artifact_public_sharing_enabled}
    if owner:
        result["public_questions"] = bool(doc.get("public_questions"))
        result["sharing_contact"] = doc.get("sharing_contact") or {}
        result["open_questions"] = await run(lambda db: db.page_feedback.count_documents(
            {"artifact_uuid": doc["uuid"], "status": "open"}))
    else:
        result["shared_by"] = await run(page_feedback.shared_by, doc)
    result["notes"] = await run(page_feedback.page_notes, doc["uuid"], artifacts.revision(doc)["uuid"])
    return result


@router.get("/{uuid}/revisions/{revision}/content", response_model=None)
async def private_content(uuid: str, revision: str, download: bool = False,
                          view: Literal["content", "full", "print", "embed"] = "content",
                          mark: str | None = Query(default=None, max_length=40),
                          user: User = Depends(get_current_user)) -> HTMLResponse:
    doc = await authorized(uuid, user)
    rev = artifacts.revision(doc, revision)
    version = rev.get("version") or next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == revision)
    return content_response(rev, download, version=version, view=view, mark=mark)


@router.get("/{uuid}/revisions/{revision}/source", response_model=None)
async def revision_source(uuid: str, revision: str, user: User = Depends(get_current_user)) -> dict[str, object]:
    doc = await authorized(uuid, user, manage=True)
    rev = artifacts.revision(doc, revision)
    return {"title": (doc.get("title") or rev["title"]) if revision == doc["latest_revision"] else rev["title"], "html": rev["html"]}


@router.patch("/{uuid}", response_model=None)
async def rename_artifact(uuid: str, body: RenameArtifactRequest, user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user, manage=True)
    return artifacts.metadata(await run(artifacts.rename, doc, body.title), True)


@router.post("/{uuid}/duplicate", response_model=None)
@limiter.limit("20/minute")
async def duplicate_artifact(request: Request, uuid: str, body: DuplicateArtifactRequest, user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user)
    return artifacts.metadata(await run(artifacts.duplicate, doc, user.user_id, body.request_id), True)


@router.post("/{uuid}/revisions", response_model=None)
@limiter.limit("20/minute")
async def revise_artifact(request: Request, uuid: str, body: ReviseArtifactRequest, user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user, manage=True)
    return artifacts.metadata(await run(artifacts.revise, doc, body.title, body.html, body.base_revision), True)


@router.put("/{uuid}/team", response_model=None)
async def share_team(uuid: str, body: ShareArtifactRequest, user: User = Depends(get_current_user)) -> dict[str, object]:
    doc = await authorized(uuid, user, manage=True)
    if body.team_id and not access_control.can_view_team(body.team_id, await access_control.get_team_access_context(user)):
        raise HTTPException(404, "Team not found")
    await run(artifacts.share_team, doc, body.team_id, body.revision)
    return {"ok": True}


@router.put("/{uuid}/publication", response_model=None)
async def publish(uuid: str, body: PublishArtifactRequest, user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict:
    if not settings.artifact_public_sharing_enabled:
        raise HTTPException(403, "Public page sharing is disabled on this deployment.")
    doc = await authorized(uuid, user, manage=True)
    saved = await run(artifacts.publish_separate if body.separate_link else artifacts.publish, doc, body.revision)
    if not saved:
        raise HTTPException(404, "Page not found")
    return artifacts.metadata(saved, True)


@router.delete("/{uuid}/publication", response_model=None)
async def unpublish(uuid: str, revision: str | None = Query(default=None, min_length=1, max_length=64), user: User = Depends(get_current_user)) -> dict[str, object]:
    doc = await authorized(uuid, user, manage=True)
    if revision is not None:
        await run(artifacts.unpublish_separate, doc, revision)
    else:
        await run(artifacts.unpublish, doc)
    return {"ok": True}


@router.delete("/{uuid}", response_model=None)
async def delete_artifact(uuid: str, user: User = Depends(get_current_user)) -> dict[str, object]:
    from datetime import datetime, timezone
    await authorized(uuid, user, manage=True)
    await run(lambda db: db.html_artifacts.update_one({"uuid": uuid, "user_id": user.user_id}, {"$set": {
        "deleted_at": datetime.now(timezone.utc), "public_token": None, "published_revision": None, "publications": [], "revisions": [],
    }}))
    return {"ok": True}



# ---------------------------------------------------------------------------
# Questions and flags from viewers (support ticket: viewers couldn't ask the
# owner anything). See services/page_feedback.py.
# ---------------------------------------------------------------------------


def _question_link(uuid: str, question: str) -> str:
    return f"/pages/{uuid}?question={question}"


async def _notify_owner(doc: dict, item: dict, asker_label: str) -> None:
    from app.services.notification_service import create_notification

    about = f" · about {item['anchor_label']}" if item.get("anchor_label") else ""
    await create_notification(
        doc["user_id"], "page_question",
        f"Question on {item['page_title']}"[:200],
        body=f"{asker_label}{about}: {item['message'][:300]}",
        link=_question_link(doc["uuid"], item["uuid"]),
        item_kind="page", item_id=doc["uuid"], item_name=item["page_title"],
    )


@router.get("/{uuid}/questions/anchors", response_model=None)
async def question_anchors(uuid: str, revision: str | None = Query(default=None, max_length=64),
                           user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user)
    return {"anchors": page_feedback.anchors(artifacts.revision(doc, revision)["html"])}


@router.post("/{uuid}/questions", response_model=None)
@limiter.limit("20/minute")
async def ask_question(request: Request, uuid: str, body: PageQuestionRequest,
                       user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user)
    if doc["user_id"] == user.user_id:
        raise HTTPException(422, "This is your page. Use Request changes to change it.")
    # The version the viewer can see (team view), never one they can't.
    rev = artifacts.revision(doc, body.revision)
    name = (user.name or user.email or "A team member").strip()
    full = await run(artifacts.get, uuid)
    item = await run(page_feedback.create, full, rev, message=body.message, anchor_id=body.anchor_id,
                     asker={"kind": "user", "user_id": user.user_id, "name": name})
    await _notify_owner(full, item, name)
    return page_feedback.serialize(item)


@router.get("/{uuid}/questions/mine", response_model=None)
async def my_questions(uuid: str, user: User = Depends(get_current_user)) -> list[dict]:
    doc = await authorized(uuid, user)
    rows = await run(lambda db: list(db.page_feedback.find(
        {"artifact_uuid": doc["uuid"], "asker.user_id": user.user_id}).sort("created_at", -1).limit(50)))
    return [page_feedback.serialize(r) for r in rows]


@router.get("/{uuid}/questions", response_model=None)
async def list_questions(uuid: str, user: User = Depends(get_current_user)) -> list[dict]:
    doc = await authorized(uuid, user, manage=True)
    return await run(page_feedback.list_for_owner, doc["uuid"])


@router.post("/{uuid}/questions/{question}/answer", response_model=None)
async def answer_question(uuid: str, question: str, body: PageAnswerRequest,
                          user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)) -> dict:
    doc = await authorized(uuid, user, manage=True)
    item = await run(page_feedback.answer, doc, question, body.text, body.show_on_page)
    asker = item.get("asker") or {}
    title = item.get("page_title") or doc.get("title") or "your page"
    if asker.get("kind") == "user" and asker.get("user_id"):
        from app.services.notification_service import create_notification
        await create_notification(
            asker["user_id"], "page_question_answered", f"Answer about {title}"[:200],
            body=body.text[:300], link=_question_link(doc["uuid"], item["uuid"]),
            item_kind="page", item_id=doc["uuid"], item_name=title,
        )
    elif asker.get("kind") == "public" and asker.get("email"):
        from app.services.email_service import page_question_answered_email, send_email
        token = asker.get("token")
        url = f"{settings.frontend_url.rstrip('/')}/a/{token}" if token else None
        subject, html = page_question_answered_email(title, item["message"], body.text, url, item.get("anchor_label"))
        await send_email(asker["email"], subject, html, settings=settings, email_type="page_question")
    return page_feedback.serialize(item, owner=True)


@router.post("/{uuid}/questions/{question}/close", response_model=None)
async def close_question(uuid: str, question: str, user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user, manage=True)
    await run(page_feedback.close, doc, question)
    return {"ok": True}


@router.patch("/{uuid}/question-settings", response_model=None)
async def question_settings(uuid: str, body: PageFeedbackSettingsRequest,
                            user: User = Depends(get_current_user)) -> dict:
    doc = await authorized(uuid, user, manage=True)
    fresh = await run(page_feedback.update_settings, doc, body.public_questions, body.hide_owner_name, body.contact_label)
    return {"public_questions": bool(fresh.get("public_questions")), "sharing_contact": fresh.get("sharing_contact") or {},
            "shared_by": await run(page_feedback.shared_by, fresh)}


@router.get("/public/{token}/questions/anchors", response_model=None)
async def public_question_anchors(token: str, settings: Settings = Depends(get_settings)) -> dict:
    doc, rev = await public_doc(token, settings)
    if not doc.get("public_questions"):
        raise HTTPException(404, "Questions aren't open for this page.")
    return {"anchors": page_feedback.anchors(rev["html"])}


@router.post("/public/{token}/questions", response_model=None)
@limiter.limit("5/hour")
async def public_ask_question(request: Request, token: str, body: PublicPageQuestionRequest,
                              settings: Settings = Depends(get_settings)) -> dict:
    doc, rev = await public_doc(token, settings)
    if not doc.get("public_questions"):
        raise HTTPException(404, "Questions aren't open for this page.")
    if body.website:
        # A filled honeypot is a bot: look accepted, store nothing.
        return {"ok": True}
    if not page_feedback.valid_email(body.email):
        raise HTTPException(422, "Enter an email address so the owner can answer you.")
    from slowapi.util import get_remote_address
    name = (body.name or "").strip()[:120] or None
    email = body.email.strip()
    item = await run(page_feedback.create, doc, rev, message=body.message, anchor_id=body.anchor_id,
                     asker={"kind": "public", "email": email, "name": name, "token": token,
                            "ip": page_feedback.ip_key(get_remote_address(request))})
    await _notify_owner(doc, item, f"{name} <{email}>" if name else email)
    return {"ok": True}
