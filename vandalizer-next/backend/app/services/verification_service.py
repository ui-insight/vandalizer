"""Verification queue service  - submit, review, approve, reject."""

import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
from app.models.user import User
from app.models.verification import (
    VerificationRequest,
    VerificationStatus,
    VerifiedCollection,
    VerifiedItemMetadata,
)
from app.models.knowledge import KnowledgeBase
from app.models.workflow import Workflow
from app.models.search_set import SearchSet


async def submit_for_verification(
    item_kind: str,
    item_id: str,
    user_id: str,
    submitter_name: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    category: str | None = None,
    submitter_org: str | None = None,
    submitter_role: str | None = None,
    item_version_hash: str | None = None,
    run_instructions: str | None = None,
    evaluation_notes: str | None = None,
    known_limitations: str | None = None,
    example_inputs: list[str] | None = None,
    expected_outputs: list[str] | None = None,
    dependencies: list[str] | None = None,
    intended_use_tags: list[str] | None = None,
    test_files: list[dict] | None = None,
) -> dict:
    """Create a verification request for a library item."""
    # For knowledge bases, look up by uuid string; for others, by ObjectId
    if item_kind == "knowledge_base":
        obj = await KnowledgeBase.find_one(KnowledgeBase.uuid == item_id)
        if not obj:
            raise ValueError("Item not found")
        obj_id = obj.id
    else:
        obj_id = PydanticObjectId(item_id)
        if item_kind == "workflow":
            obj = await Workflow.get(obj_id)
        else:
            obj = await SearchSet.get(obj_id)
        if not obj:
            raise ValueError("Item not found")

    # Check for existing pending request
    existing = await VerificationRequest.find_one(
        VerificationRequest.item_id == obj_id,
        VerificationRequest.status.is_in([  # type: ignore[attr-defined]
            VerificationStatus.SUBMITTED.value,
            VerificationStatus.IN_REVIEW.value,
        ]),
    )
    if existing:
        raise ValueError("A verification request is already pending for this item")

    req = VerificationRequest(
        item_kind=item_kind,
        item_id=obj_id,
        submitter_user_id=user_id,
        submitter_name=submitter_name,
        summary=summary,
        description=description,
        category=category,
        submitter_org=submitter_org,
        submitter_role=submitter_role,
        item_version_hash=item_version_hash,
        run_instructions=run_instructions,
        evaluation_notes=evaluation_notes,
        known_limitations=known_limitations,
        example_inputs=example_inputs or [],
        expected_outputs=expected_outputs or [],
        dependencies=dependencies or [],
        intended_use_tags=intended_use_tags or [],
        test_files=test_files or [],
    )
    await req.insert()
    return _request_to_dict(req)


async def list_queue(
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List verification requests (for reviewers)."""
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    else:
        query["status"] = {"$in": [
            VerificationStatus.SUBMITTED.value,
            VerificationStatus.IN_REVIEW.value,
        ]}

    requests = await VerificationRequest.find(query).sort("-submitted_at").limit(limit).to_list()
    results = []
    for req in requests:
        d = _request_to_dict(req)
        # Attach item name
        d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
        results.append(d)
    return results


async def get_request(request_uuid: str) -> dict | None:
    """Get a single verification request by UUID."""
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return None
    d = _request_to_dict(req)
    d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
    return d


async def update_status(
    request_uuid: str,
    new_status: str,
    reviewer_user_id: str,
    reviewer_notes: str | None = None,
) -> dict | None:
    """Approve or reject a verification request."""
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    req.status = new_status
    req.reviewer_user_id = reviewer_user_id
    req.reviewer_notes = reviewer_notes
    req.reviewed_at = now
    await req.save()

    # If approved, mark the library item as verified
    if new_status == VerificationStatus.APPROVED.value:
        if req.item_kind == "knowledge_base":
            await _mark_kb_verified(req.item_id)
        else:
            await _mark_item_verified(req.item_id, req.item_kind)

    return _request_to_dict(req)


async def my_requests(user_id: str, limit: int = 50) -> list[dict]:
    """List a user's own verification requests."""
    requests = (
        await VerificationRequest.find(VerificationRequest.submitter_user_id == user_id)
        .sort("-submitted_at")
        .limit(limit)
        .to_list()
    )
    results = []
    for req in requests:
        d = _request_to_dict(req)
        d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
        results.append(d)
    return results


# ---------------------------------------------------------------------------
# Verified Catalog
# ---------------------------------------------------------------------------


async def list_verified_items(
    kind_filter: str | None = None,
    search: str | None = None,
    user_group_uuids: list[str] | None = None,
) -> list[dict]:
    """List all verified library items, optionally filtered by kind, search, and groups."""
    query: dict = {"verified": True}
    if kind_filter:
        query["kind"] = kind_filter

    items = await LibraryItem.find(query).sort("-created_at").to_list()

    results = []
    for item in items:
        name = await _get_item_name(item.kind.value, item.item_id)
        if search and search.lower() not in name.lower():
            continue

        # Fetch metadata overlay if it exists
        meta = await VerifiedItemMetadata.find_one(
            VerifiedItemMetadata.item_kind == item.kind.value,
            VerifiedItemMetadata.item_id == str(item.item_id),
        )

        # Group filtering: if item has groups and user doesn't match, skip
        meta_group_ids = meta.group_ids if meta else []
        if user_group_uuids is not None and meta_group_ids:
            if not set(meta_group_ids) & set(user_group_uuids):
                continue

        results.append({
            "id": str(item.id),
            "item_id": str(item.item_id),
            "kind": item.kind.value,
            "name": name,
            "tags": item.tags,
            "verified": item.verified,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "display_name": meta.display_name if meta else None,
            "description": meta.description if meta else None,
            "markdown": meta.markdown if meta else None,
            "group_ids": meta_group_ids,
        })
    return results


async def get_item_metadata(item_kind: str, item_id: str) -> dict | None:
    """Get metadata for a verified item."""
    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    if not meta:
        return None
    return {
        "id": str(meta.id),
        "item_kind": meta.item_kind,
        "item_id": meta.item_id,
        "display_name": meta.display_name,
        "description": meta.description,
        "markdown": meta.markdown,
        "group_ids": meta.group_ids,
        "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
        "updated_by_user_id": meta.updated_by_user_id,
    }


async def update_item_metadata(
    item_kind: str,
    item_id: str,
    user_id: str,
    display_name: str | None = None,
    description: str | None = None,
    markdown: str | None = None,
    group_ids: list[str] | None = None,
) -> dict:
    """Upsert metadata for a verified item."""
    now = datetime.datetime.now(datetime.timezone.utc)
    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    if meta:
        if display_name is not None:
            meta.display_name = display_name
        if description is not None:
            meta.description = description
        if markdown is not None:
            meta.markdown = markdown
        if group_ids is not None:
            meta.group_ids = group_ids
        meta.updated_at = now
        meta.updated_by_user_id = user_id
        await meta.save()
    else:
        meta = VerifiedItemMetadata(
            item_kind=item_kind,
            item_id=item_id,
            display_name=display_name,
            description=description,
            markdown=markdown,
            group_ids=group_ids or [],
            updated_at=now,
            updated_by_user_id=user_id,
        )
        await meta.insert()

    return {
        "id": str(meta.id),
        "item_kind": meta.item_kind,
        "item_id": meta.item_id,
        "display_name": meta.display_name,
        "description": meta.description,
        "markdown": meta.markdown,
        "group_ids": meta.group_ids,
        "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
        "updated_by_user_id": meta.updated_by_user_id,
    }


async def unverify_item(item_id: str, item_kind: str) -> dict:
    """Remove verified status from a library item."""
    obj_id = PydanticObjectId(item_id)
    items = await LibraryItem.find(
        LibraryItem.item_id == obj_id,
        LibraryItem.kind == LibraryItemKind(item_kind),
    ).to_list()
    for item in items:
        item.verified = False
        await item.save()
    return {"ok": True, "unverified_count": len(items)}


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


async def list_collections() -> list[dict]:
    """List all verified collections."""
    collections = await VerifiedCollection.find_all().sort("-updated_at").to_list()
    return [_collection_to_dict(c) for c in collections]


async def create_collection(
    title: str,
    user_id: str,
    description: str | None = None,
) -> dict:
    """Create a new verified collection."""
    now = datetime.datetime.now(datetime.timezone.utc)
    col = VerifiedCollection(
        title=title,
        description=description,
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    await col.insert()
    return _collection_to_dict(col)


async def update_collection(
    collection_id: str,
    title: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update a collection's title/description."""
    col = await VerifiedCollection.get(PydanticObjectId(collection_id))
    if not col:
        return None
    if title is not None:
        col.title = title
    if description is not None:
        col.description = description
    col.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await col.save()
    return _collection_to_dict(col)


async def delete_collection(collection_id: str) -> bool:
    """Delete a collection."""
    col = await VerifiedCollection.get(PydanticObjectId(collection_id))
    if not col:
        return False
    await col.delete()
    return True


async def add_to_collection(collection_id: str, item_id: str) -> dict | None:
    """Add an item to a collection."""
    col = await VerifiedCollection.get(PydanticObjectId(collection_id))
    if not col:
        return None
    if item_id not in col.item_ids:
        col.item_ids.append(item_id)
        col.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await col.save()
    return _collection_to_dict(col)


async def remove_from_collection(collection_id: str, item_id: str) -> dict | None:
    """Remove an item from a collection."""
    col = await VerifiedCollection.get(PydanticObjectId(collection_id))
    if not col:
        return None
    if item_id in col.item_ids:
        col.item_ids.remove(item_id)
        col.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await col.save()
    return _collection_to_dict(col)


# ---------------------------------------------------------------------------
# Examiner management
# ---------------------------------------------------------------------------


async def list_examiners() -> list[dict]:
    """List all users with examiner status."""
    users = await User.find(User.is_examiner == True).to_list()  # noqa: E712
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "email": u.email,
            "is_examiner": u.is_examiner,
        }
        for u in users
    ]


async def set_examiner(user_id: str, is_examiner: bool) -> dict:
    """Grant or revoke examiner status on a user."""
    user = await User.find_one(User.user_id == user_id)
    if not user:
        raise ValueError("User not found")
    user.is_examiner = is_examiner
    await user.save()
    return {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
        "is_examiner": user.is_examiner,
    }


async def search_users(query: str, limit: int = 20) -> list[dict]:
    """Search users by name or email for examiner management."""
    import re
    regex = re.compile(re.escape(query), re.IGNORECASE)
    users = await User.find(
        {"$or": [{"name": {"$regex": regex}}, {"email": {"$regex": regex}}]}
    ).limit(limit).to_list()
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "email": u.email,
            "is_examiner": u.is_examiner,
        }
        for u in users
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _mark_kb_verified(item_id: PydanticObjectId) -> None:
    """Set verified=True on a KnowledgeBase by its MongoDB _id."""
    kb = await KnowledgeBase.get(item_id)
    if kb:
        kb.verified = True
        await kb.save()


async def _mark_item_verified(item_id: PydanticObjectId, item_kind: str) -> None:
    """Set verified=True on all LibraryItem records pointing to this object."""
    items = await LibraryItem.find(
        LibraryItem.item_id == item_id,
        LibraryItem.kind == LibraryItemKind(item_kind),
    ).to_list()
    for item in items:
        item.verified = True
        await item.save()


async def _get_item_name(item_kind: str, item_id: PydanticObjectId) -> str:
    if item_kind == "workflow":
        wf = await Workflow.get(item_id)
        return wf.name if wf else "Unknown workflow"
    elif item_kind == "knowledge_base":
        kb = await KnowledgeBase.get(item_id)
        return kb.title if kb else "Unknown knowledge base"
    else:
        ss = await SearchSet.get(item_id)
        return ss.title if ss else "Unknown extraction"


def _request_to_dict(req: VerificationRequest) -> dict:
    return {
        "id": str(req.id),
        "uuid": req.uuid,
        "item_kind": req.item_kind,
        "item_id": str(req.item_id),
        "status": req.status,
        "submitter_user_id": req.submitter_user_id,
        "submitter_name": req.submitter_name,
        "submitter_org": req.submitter_org,
        "submitter_role": req.submitter_role,
        "summary": req.summary,
        "description": req.description,
        "category": req.category,
        "item_version_hash": req.item_version_hash,
        "run_instructions": req.run_instructions,
        "evaluation_notes": req.evaluation_notes,
        "known_limitations": req.known_limitations,
        "example_inputs": req.example_inputs,
        "expected_outputs": req.expected_outputs,
        "dependencies": req.dependencies,
        "intended_use_tags": req.intended_use_tags,
        "test_files": req.test_files,
        "reviewer_user_id": req.reviewer_user_id,
        "reviewer_notes": req.reviewer_notes,
        "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }


def _collection_to_dict(col: VerifiedCollection) -> dict:
    return {
        "id": str(col.id),
        "title": col.title,
        "description": col.description,
        "promo_image_url": col.promo_image_url,
        "item_ids": col.item_ids,
        "created_by_user_id": col.created_by_user_id,
        "created_at": col.created_at.isoformat() if col.created_at else None,
        "updated_at": col.updated_at.isoformat() if col.updated_at else None,
    }
