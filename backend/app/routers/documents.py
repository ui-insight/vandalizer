import re

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.document import SmartDocument
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.services import document_service

router = APIRouter()


@router.get("/list")
async def list_documents(
    space: str,
    folder: str | None = None,
    team_uuid: str | None = None,
    user: User = Depends(get_current_user),
):
    # Use provided team_uuid, or fall back to user's current team
    if not team_uuid and user.current_team:
        team = await Team.get(user.current_team)
        if team:
            team_uuid = team.uuid

    # Validate that the user is a member of the requested team
    if team_uuid:
        team = await Team.find_one(Team.uuid == team_uuid)
        if team:
            membership = await TeamMembership.find_one(
                TeamMembership.team == team.id,
                TeamMembership.user_id == user.user_id,
            )
            if not membership:
                raise HTTPException(status_code=403, detail="Not a member of this team")

    return await document_service.list_contents(
        space, folder, user_id=user.user_id, team_uuid=team_uuid
    )


@router.get("/search")
async def search_documents(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Search documents by title or content text. Returns recent docs when q is empty."""
    if not q.strip():
        results = await SmartDocument.find(
            {"user_id": user.user_id},
        ).sort(-SmartDocument.created_at).limit(limit).to_list()
    else:
        regex = re.compile(re.escape(q), re.IGNORECASE)
        results = await SmartDocument.find(
            {
                "$or": [
                    {"title": {"$regex": regex.pattern, "$options": "i"}},
                    {"raw_text": {"$regex": regex.pattern, "$options": "i"}},
                ],
                "user_id": user.user_id,
            }
        ).sort(-SmartDocument.created_at).limit(limit).to_list()

    items = []
    for doc in results:
        # Extract snippet around match in raw_text
        snippet = ""
        if q.strip() and doc.raw_text:
            rgx = re.compile(re.escape(q), re.IGNORECASE)
            match = rgx.search(doc.raw_text)
            if match:
                start = max(0, match.start() - 80)
                end = min(len(doc.raw_text), match.end() + 80)
                snippet = ("..." if start > 0 else "") + doc.raw_text[start:end] + ("..." if end < len(doc.raw_text) else "")

        items.append({
            "uuid": doc.uuid,
            "title": doc.title,
            "extension": doc.extension,
            "snippet": snippet,
            "num_pages": doc.num_pages,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            "processing": doc.processing,
            "valid": doc.valid,
            "task_status": doc.task_status,
            "folder": doc.folder,
            "token_count": doc.token_count,
        })

    return {"items": items, "total": len(items)}


@router.get("/poll_status")
async def poll_status(
    docid: str,
    user: User = Depends(get_current_user),
):
    result = await document_service.poll_status(docid)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result
