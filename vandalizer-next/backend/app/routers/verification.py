"""Verification queue API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.services import verification_service as svc
from app.services import group_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SubmitRequest(BaseModel):
    item_kind: str  # "workflow", "search_set", or "knowledge_base"
    item_id: str
    submitter_name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    submitter_org: Optional[str] = None
    submitter_role: Optional[str] = None
    item_version_hash: Optional[str] = None
    run_instructions: Optional[str] = None
    evaluation_notes: Optional[str] = None
    known_limitations: Optional[str] = None
    example_inputs: Optional[list[str]] = None
    expected_outputs: Optional[list[str]] = None
    dependencies: Optional[list[str]] = None
    intended_use_tags: Optional[list[str]] = None
    test_files: Optional[list[dict]] = None


class UpdateStatusRequest(BaseModel):
    status: str  # "approved", "rejected", "in_review"
    reviewer_notes: Optional[str] = None


class MetadataUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    markdown: Optional[str] = None
    group_ids: Optional[list[str]] = None


class CreateCollectionRequest(BaseModel):
    title: str
    description: Optional[str] = None


class UpdateCollectionRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class AddToCollectionRequest(BaseModel):
    item_id: str


class SetExaminerRequest(BaseModel):
    user_id: str
    is_examiner: bool


# ---------------------------------------------------------------------------
# Submission & Queue
# ---------------------------------------------------------------------------


@router.post("/submit")
async def submit_for_verification(
    req: SubmitRequest,
    user: User = Depends(get_current_user),
):
    try:
        result = await svc.submit_for_verification(
            item_kind=req.item_kind,
            item_id=req.item_id,
            user_id=user.user_id,
            submitter_name=req.submitter_name,
            summary=req.summary,
            description=req.description,
            category=req.category,
            submitter_org=req.submitter_org,
            submitter_role=req.submitter_role,
            item_version_hash=req.item_version_hash,
            run_instructions=req.run_instructions,
            evaluation_notes=req.evaluation_notes,
            known_limitations=req.known_limitations,
            example_inputs=req.example_inputs,
            expected_outputs=req.expected_outputs,
            dependencies=req.dependencies,
            intended_use_tags=req.intended_use_tags,
            test_files=req.test_files,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/queue")
async def list_queue(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    requests = await svc.list_queue(status_filter=status, limit=limit)
    return {"requests": requests}


@router.get("/mine")
async def my_requests(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    requests = await svc.my_requests(user.user_id, limit=limit)
    return {"requests": requests}


# ---------------------------------------------------------------------------
# Verified Catalog
# ---------------------------------------------------------------------------


@router.get("/verified")
async def list_verified_items(
    kind: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    # Admins/examiners see all items unfiltered (Catalog view)
    if user.is_admin or user.is_examiner:
        user_group_uuids = None
    else:
        user_group_uuids = await group_service.get_user_group_uuids(user.user_id)
    items = await svc.list_verified_items(
        kind_filter=kind, search=search, user_group_uuids=user_group_uuids,
    )
    return {"items": items}


@router.get("/verified/{item_kind}/{item_id}/metadata")
async def get_item_metadata(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    meta = await svc.get_item_metadata(item_kind, item_id)
    return meta or {}


@router.put("/verified/{item_kind}/{item_id}/metadata")
async def update_item_metadata(
    item_kind: str,
    item_id: str,
    req: MetadataUpdateRequest,
    user: User = Depends(get_current_user),
):
    result = await svc.update_item_metadata(
        item_kind=item_kind,
        item_id=item_id,
        user_id=user.user_id,
        display_name=req.display_name,
        description=req.description,
        markdown=req.markdown,
        group_ids=req.group_ids,
    )
    return result


@router.post("/verified/{item_kind}/{item_id}/unverify")
async def unverify_item(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    result = await svc.unverify_item(item_id, item_kind)
    return result


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


@router.get("/collections")
async def list_collections(
    user: User = Depends(get_current_user),
):
    collections = await svc.list_collections()
    return {"collections": collections}


@router.post("/collections")
async def create_collection(
    req: CreateCollectionRequest,
    user: User = Depends(get_current_user),
):
    result = await svc.create_collection(
        title=req.title,
        description=req.description,
        user_id=user.user_id,
    )
    return result


@router.patch("/collections/{collection_id}")
async def update_collection(
    collection_id: str,
    req: UpdateCollectionRequest,
    user: User = Depends(get_current_user),
):
    result = await svc.update_collection(
        collection_id=collection_id,
        title=req.title,
        description=req.description,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: User = Depends(get_current_user),
):
    ok = await svc.delete_collection(collection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"ok": True}


@router.post("/collections/{collection_id}/items")
async def add_to_collection(
    collection_id: str,
    req: AddToCollectionRequest,
    user: User = Depends(get_current_user),
):
    result = await svc.add_to_collection(collection_id, req.item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.delete("/collections/{collection_id}/items/{item_id}")
async def remove_from_collection(
    collection_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    result = await svc.remove_from_collection(collection_id, item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


# ---------------------------------------------------------------------------
# Group management (admin/examiner)
# ---------------------------------------------------------------------------


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddGroupMemberRequest(BaseModel):
    user_id: str


@router.get("/groups")
async def list_groups(user: User = Depends(get_current_user)):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    groups = await group_service.list_groups()
    return {"groups": groups}


@router.post("/groups")
async def create_group(req: CreateGroupRequest, user: User = Depends(get_current_user)):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    result = await group_service.create_group(
        name=req.name, user_id=user.user_id, description=req.description,
    )
    return result


@router.patch("/groups/{group_uuid}")
async def update_group(
    group_uuid: str,
    req: UpdateGroupRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    result = await group_service.update_group(
        group_uuid, name=req.name, description=req.description,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Group not found")
    return result


@router.delete("/groups/{group_uuid}")
async def delete_group(group_uuid: str, user: User = Depends(get_current_user)):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    ok = await group_service.delete_group(group_uuid)
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"ok": True}


@router.get("/groups/search-users")
async def search_users_for_groups(
    q: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    users = await group_service.search_users(q)
    return {"users": users}


@router.get("/groups/{group_uuid}/members")
async def list_group_members(group_uuid: str, user: User = Depends(get_current_user)):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    members = await group_service.list_group_members(group_uuid)
    return {"members": members}


@router.post("/groups/{group_uuid}/members")
async def add_group_member(
    group_uuid: str,
    req: AddGroupMemberRequest,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    ok = await group_service.add_user_to_group(group_uuid, req.user_id, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"ok": True}


@router.delete("/groups/{group_uuid}/members/{member_user_id}")
async def remove_group_member(
    group_uuid: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
):
    if not (user.is_admin or user.is_examiner):
        raise HTTPException(status_code=403, detail="Admin or examiner access required")
    ok = await group_service.remove_user_from_group(group_uuid, member_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Group or member not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Examiner management (admin only)
# ---------------------------------------------------------------------------


@router.get("/examiners")
async def list_examiners(
    user: User = Depends(get_current_user),
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    examiners = await svc.list_examiners()
    return {"examiners": examiners}


@router.post("/examiners")
async def set_examiner(
    req: SetExaminerRequest,
    user: User = Depends(get_current_user),
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        result = await svc.set_examiner(req.user_id, req.is_examiner)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/examiners/search")
async def search_users_for_examiner(
    q: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    users = await svc.search_users(q)
    return {"users": users}


# ---------------------------------------------------------------------------
# Individual request (keep at bottom to avoid path conflicts)
# ---------------------------------------------------------------------------


@router.get("/{request_uuid}")
async def get_request(
    request_uuid: str,
    user: User = Depends(get_current_user),
):
    result = await svc.get_request(request_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Verification request not found")
    return result


@router.patch("/{request_uuid}/status")
async def update_status(
    request_uuid: str,
    req: UpdateStatusRequest,
    user: User = Depends(get_current_user),
):
    result = await svc.update_status(
        request_uuid=request_uuid,
        new_status=req.status,
        reviewer_user_id=user.user_id,
        reviewer_notes=req.reviewer_notes,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Verification request not found")
    return result
