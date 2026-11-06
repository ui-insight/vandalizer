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
from app.schemas.artifact import ChatArtifactRequest, CreateArtifactRequest, DuplicateArtifactRequest, PageTextEditsRequest, PublicLinkSettingsRequest, PublishArtifactRequest, RenameArtifactRequest, ReviseArtifactRequest, ShareArtifactRequest
from app.services import public_page_access
from app.services.page_links import prepare_page_links
from app.services import access_control, artifacts
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


def content_response(rev: dict, download: bool=False, *, version: int=1, view: Literal["content", "full", "print", "embed"]="content") -> HTMLResponse:
    title = rev["title"].strip() or "Page"
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


@router.get("/public-links", response_model=None)
async def list_public_links(user: User = Depends(get_current_user)) -> dict[str, object]:
    """All of the caller's live public links, expired and soonest-to-expire first."""
    return {"links": await run(public_page_access.live_links, user.user_id)}


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


async def optional_user(request: Request, settings: Settings) -> User | None:
    """The signed-in viewer of a public link, or None; never an error."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return await get_current_user(access_token=token, settings=settings)
    except HTTPException:
        return None


async def public_doc(token: str, settings: Settings, request: Request | None, *, count_view: bool = False) -> tuple[dict, dict]:
    if not settings.artifact_public_sharing_enabled:
        raise HTTPException(404, "Page not found")
    doc = await run(lambda db: db.html_artifacts.find_one({
        "$or": [{"public_token": token}, {"publications.token": token}], "deleted_at": None,
    }))
    if not doc:
        raise HTTPException(404, "Page not found")
    found = public_page_access.link_for_token(doc, token)
    if not found:
        raise HTTPException(404, "Page not found")
    selected, link, kind = found
    # Expiry and audience apply to the HTML as well as the metadata, so the
    # content URL can't be opened around them.
    viewer = await optional_user(request, settings) if request is not None and link["audience"] == "signed_in" else None
    public_page_access.check(link, viewer)
    if count_view:
        # Who opened it is recorded only for links that require signing in:
        # a visitor to an anyone-with-the-link page is anonymous to its owner.
        await run(public_page_access.record_view, doc, token, kind, viewer)
    return doc, artifacts.revision(doc, selected)


@router.get("/public/{token}", response_model=None)
async def get_public(token: str, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    # One opening of the link = one metadata request (the viewer then loads
    # the HTML once per view mode, which is not counted again).
    doc, rev = await public_doc(token, settings, request, count_view=True)
    found = public_page_access.link_for_token(doc, token)
    expires = found[1]["expires_at"] if found else None
    audience = found[1]["audience"] if found else "anyone"
    # Mongo may return naive UTC datetimes. Never use the page's updated_at:
    # it advances when an owner saves a private draft.
    updated_at = rev["created_at"]
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    response.headers["Cache-Control"] = "no-store"
    return {"title": rev["title"], "revision": rev["uuid"],
            "version": next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == rev["uuid"]),
            "updated_at": updated_at, "expires_at": expires, "audience": audience}


@router.get("/public/{token}/content", response_model=None)
async def public_content(token: str, request: Request, download: bool = False, revision: str | None = None,
                         view: Literal["content", "full", "print", "embed"] = "content", settings: Settings = Depends(get_settings)) -> HTMLResponse:
    doc, rev = await public_doc(token, settings, request)
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
        result["public_links"] = await run(public_page_access.describe, doc)
    return result


@router.put("/{uuid}/publication/settings", response_model=None)
async def public_link_settings(uuid: str, body: PublicLinkSettingsRequest, user: User = Depends(get_current_user)) -> dict:
    """Extend, shorten or restrict an existing public link."""
    doc = await authorized(uuid, user, manage=True)
    link = public_page_access.normalize(body.expires_at, body.audience, body.emails)
    if body.revision is None:
        if not doc.get("public_token") or not doc.get("published_revision"):
            raise HTTPException(404, "This page has no main public link.")
        await run(public_page_access.apply_main, doc, link)
    else:
        if not any(p["revision"] == body.revision for p in doc.get("publications") or []):
            raise HTTPException(404, "That version has no public link.")
        await run(public_page_access.apply_version, doc, body.revision, link)
    return artifacts.metadata(await run(artifacts.get, uuid), True)


@router.get("/{uuid}/revisions/{revision}/content", response_model=None)
async def private_content(uuid: str, revision: str, download: bool = False,
                          view: Literal["content", "full", "print", "embed"] = "content", user: User = Depends(get_current_user)) -> HTMLResponse:
    doc = await authorized(uuid, user)
    rev = artifacts.revision(doc, revision)
    version = rev.get("version") or next(i for i, item in enumerate(doc["revisions"], 1) if item["uuid"] == revision)
    return content_response(rev, download, version=version, view=view)


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
    chosen = body.model_fields_set & {"expires_at", "audience", "emails"}
    link = public_page_access.normalize(body.expires_at, body.audience, body.emails) if chosen else None
    saved = await run(artifacts.publish_separate if body.separate_link else artifacts.publish, doc, body.revision)
    if not saved:
        raise HTTPException(404, "Page not found")
    if link is not None:
        if body.separate_link:
            await run(public_page_access.apply_version, saved, body.revision, link)
        else:
            await run(public_page_access.apply_main, saved, link)
        saved = await run(artifacts.get, uuid)
    return artifacts.metadata(saved, True)


@router.delete("/{uuid}/publication", response_model=None)
async def unpublish(uuid: str, revision: str | None = Query(default=None, min_length=1, max_length=64), user: User = Depends(get_current_user)) -> dict[str, object]:
    doc = await authorized(uuid, user, manage=True)
    if revision is not None:
        await run(artifacts.unpublish_separate, doc, revision)
    else:
        await run(artifacts.unpublish, doc)
        await run(public_page_access.clear_main, doc)
    return {"ok": True}


@router.delete("/{uuid}", response_model=None)
async def delete_artifact(uuid: str, user: User = Depends(get_current_user)) -> dict[str, object]:
    from datetime import datetime, timezone
    await authorized(uuid, user, manage=True)
    await run(lambda db: db.html_artifacts.update_one({"uuid": uuid, "user_id": user.user_id}, {"$set": {
        "deleted_at": datetime.now(timezone.utc), "public_token": None, "published_revision": None, "publications": [], "revisions": [],
    }}))
    return {"ok": True}



@router.post("/{uuid}/text-edits", response_model=None)
@limiter.limit("30/minute")
async def save_text_edits(request: Request, uuid: str, body: PageTextEditsRequest,
                          user: User = Depends(get_current_user)) -> dict:
    """Save the owner's in-place text changes as a new version (Edit text).

    No AI and no HTML: the changed blocks are found in the saved HTML and only
    their text changes. Like any save, the published link is untouched.
    """
    from app.services import page_text_edits

    doc = await authorized(uuid, user, manage=True)
    if doc["latest_revision"] != body.base_revision:
        raise HTTPException(409, "This page changed. Reload it and make your edits on the latest version.")
    current = artifacts.revision(doc, body.base_revision)
    html, notes = page_text_edits.apply(current["html"], [
        page_text_edits.TextEdit(tag=e.tag.lower(), index=e.index, original=e.original, text=e.text) for e in body.edits
    ])
    # Keep what the page was built from (Living Pages), not checks of the old text.
    previous = {k: v for k, v in (current.get("source") or {}).items() if k not in {"figure_check", "template_check"}}
    source = {**previous, "kind": "text_edit", "edited_revision": body.base_revision}
    # The owner's library name, as Edit HTML saves it: a revision's own title
    # would undo a rename (revise sets the page title).
    title = doc.get("title") or current["title"]
    saved = await run(artifacts.revise, doc, title, html, body.base_revision, source)
    version = len(saved["revisions"])
    return {**artifacts.metadata(saved, True), "version": version, "notes": notes}
