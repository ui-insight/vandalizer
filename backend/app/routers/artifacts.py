"""Authenticated artifact drafts and explicitly published revision links."""
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
from app.schemas.artifact import ChatArtifactRequest, CreateArtifactRequest, PublishArtifactRequest, ReviseArtifactRequest, ShareArtifactRequest
from app.schemas.chat_export import ChatExportRequest
from app.services import access_control, artifacts
from app.services.chat_export import render_chat_export
from app.services.page_printing import render_page
from app.tasks import get_sync_db
from app.utils.content_disposition import content_disposition

router = APIRouter()


async def authorized_project(uuid, user):
    from app.services.project_service import get_authorized_project
    if uuid and not await get_authorized_project(uuid, user):
        raise HTTPException(404, "Project not found")


@router.get("/browse")
async def browse_artifacts(
    search: str = Query(default="", max_length=200),
    sort: Literal["updated", "newest", "title"] = "updated",
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=50),
    project_uuid: str | None = None,
    user: User = Depends(get_current_user),
):
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

    def query(db):
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


async def run(fn, *args):
    return await anyio.to_thread.run_sync(functools.partial(fn, get_sync_db(), *args))


async def authorized(uuid, user, manage=False):
    doc = await run(artifacts.get, uuid)
    if doc["user_id"] == user.user_id:
        return doc
    if not manage and access_control.can_view_team(doc.get("team_id"), await access_control.get_team_access_context(user)):
        return artifacts.team_view(doc)
    raise HTTPException(404, "Page not found")


def content_response(rev, download=False, *, version=1, view="content"):
    title = rev["title"].strip() or "Page"
    filename = title if title.lower().endswith(".html") else f"{title}.html"
    html, csp = render_page(rev, version, "content" if download else view)
    return HTMLResponse(html, headers={
        "Content-Security-Policy": csp, "X-Frame-Options": "SAMEORIGIN",
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow",
        **({"Content-Disposition": content_disposition(filename)} if download else {}),
    })


@router.get("")
async def list_artifacts(user: User = Depends(get_current_user)):
    result = await browse_artifacts(search="", sort="updated", page=1, page_size=100, project_uuid=None, user=user)
    return result["items"]


@router.post("")
@limiter.limit("20/minute")
async def create_artifact(request: Request, body: CreateArtifactRequest, user: User = Depends(get_current_user)):
    await authorized_project(body.project_uuid, user)
    return artifacts.metadata(await run(artifacts.create, user.user_id, body.title, body.html, body.request_id,
                                        {"kind": "editor", "project_uuid": body.project_uuid}), True)


@router.post("/from-chat")
@limiter.limit("20/minute")
async def chat_artifact(request: Request, body: ChatArtifactRequest, user: User = Depends(get_current_user)):
    await authorized_project(body.project_uuid, user)
    if body.conversation_uuid:
        from app.models.chat import ChatConversation
        if not await ChatConversation.find_one({"uuid": body.conversation_uuid, "user_id": user.user_id}):
            raise HTTPException(404, "Conversation not found")
    try:
        transcript = ChatExportRequest(format="html", messages=body.messages)
        html = await anyio.to_thread.run_sync(render_chat_export, transcript)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return artifacts.metadata(await run(artifacts.create, user.user_id, body.title, html.decode(), body.request_id,
                                        {"kind": "chat_export", "conversation_uuid": body.conversation_uuid,
                                         "project_uuid": body.project_uuid}), True)


@router.post("/from-workflow/{session_id}")
@limiter.limit("20/minute")
async def workflow_artifact(request: Request, session_id: str, step: str | None = None, user: User = Depends(get_current_user)):
    from app.services.workflow_service import _get_authorized_workflow_result
    result = await _get_authorized_workflow_result(session_id, user)
    if not result:
        raise HTTPException(404, "Workflow run not found")
    return artifacts.metadata(await run(artifacts.from_workflow, result.model_dump(), user.user_id, step), True)


async def public_doc(token, settings):
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


@router.get("/public/{token}")
async def get_public(token: str, response: Response, settings: Settings = Depends(get_settings)):
    doc, rev = await public_doc(token, settings)
    # Mongo may return naive UTC datetimes. Never use the page's updated_at:
    # it advances when an owner saves a private draft.
    updated_at = rev["created_at"]
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    response.headers["Cache-Control"] = "no-store"
    return {"title": rev["title"], "revision": rev["uuid"],
            "version": next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == rev["uuid"]),
            "updated_at": updated_at}


@router.get("/public/{token}/content")
async def public_content(token: str, download: bool = False, revision: str | None = None,
                         view: Literal["content", "full", "print"] = "content", settings: Settings = Depends(get_settings)):
    doc, rev = await public_doc(token, settings)
    # Keep a viewer's version/date label matched to the HTML even if the owner
    # publishes again between the metadata request and the iframe request.
    if revision is not None and revision != rev["uuid"]:
        raise HTTPException(409, "The published page changed. Reload the page to view the current version.")
    version = next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == rev["uuid"])
    return content_response(rev, download, version=version, view=view)


@router.get("/{uuid}")
async def get_artifact(uuid: str, user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    doc = await authorized(uuid, user)
    return {**artifacts.metadata(doc, doc["user_id"] == user.user_id), "public_sharing_enabled": settings.artifact_public_sharing_enabled}


@router.get("/{uuid}/revisions/{revision}/content")
async def private_content(uuid: str, revision: str, download: bool = False,
                          view: Literal["content", "full", "print"] = "content", user: User = Depends(get_current_user)):
    doc = await authorized(uuid, user)
    rev = artifacts.revision(doc, revision)
    version = rev.get("version") or next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == revision)
    return content_response(rev, download, version=version, view=view)


@router.get("/{uuid}/revisions/{revision}/source")
async def revision_source(uuid: str, revision: str, user: User = Depends(get_current_user)):
    rev = artifacts.revision(await authorized(uuid, user, manage=True), revision)
    return {"title": rev["title"], "html": rev["html"]}


@router.post("/{uuid}/revisions")
@limiter.limit("20/minute")
async def revise_artifact(request: Request, uuid: str, body: ReviseArtifactRequest, user: User = Depends(get_current_user)):
    doc = await authorized(uuid, user, manage=True)
    return artifacts.metadata(await run(artifacts.revise, doc, body.title, body.html, body.base_revision), True)


@router.put("/{uuid}/team")
async def share_team(uuid: str, body: ShareArtifactRequest, user: User = Depends(get_current_user)):
    doc = await authorized(uuid, user, manage=True)
    if body.team_id and not access_control.can_view_team(body.team_id, await access_control.get_team_access_context(user)):
        raise HTTPException(404, "Team not found")
    await run(artifacts.share_team, doc, body.team_id, body.revision)
    return {"ok": True}


@router.put("/{uuid}/publication")
async def publish(uuid: str, body: PublishArtifactRequest, user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    if not settings.artifact_public_sharing_enabled:
        raise HTTPException(403, "Public page sharing is disabled on this deployment.")
    doc = await authorized(uuid, user, manage=True)
    saved = await run(artifacts.publish_separate if body.separate_link else artifacts.publish, doc, body.revision)
    if not saved:
        raise HTTPException(404, "Page not found")
    return artifacts.metadata(saved, True)


@router.delete("/{uuid}/publication")
async def unpublish(uuid: str, revision: str | None = Query(default=None, min_length=1, max_length=64), user: User = Depends(get_current_user)):
    doc = await authorized(uuid, user, manage=True)
    if revision is not None:
        await run(artifacts.unpublish_separate, doc, revision)
    else:
        await run(artifacts.unpublish, doc)
    return {"ok": True}


@router.delete("/{uuid}")
async def delete_artifact(uuid: str, user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    await authorized(uuid, user, manage=True)
    await run(lambda db: db.html_artifacts.update_one({"uuid": uuid, "user_id": user.user_id}, {"$set": {
        "deleted_at": datetime.now(timezone.utc), "public_token": None, "published_revision": None, "publications": [], "revisions": [],
    }}))
    return {"ok": True}
