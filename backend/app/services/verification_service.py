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
from app.models.system_config import SystemConfig
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
    # Look up by uuid string for knowledge_base and search_set; ObjectId for others
    if item_kind == "knowledge_base":
        obj = await KnowledgeBase.find_one(KnowledgeBase.uuid == item_id)
        if not obj:
            raise ValueError("Item not found")
        obj_id = obj.id
    elif item_kind == "search_set":
        # Search sets may be referenced by UUID or ObjectId
        try:
            obj_id = PydanticObjectId(item_id)
            obj = await SearchSet.get(obj_id)
        except Exception:
            obj = await SearchSet.find_one(SearchSet.uuid == item_id)
        if not obj:
            raise ValueError("Item not found")
        obj_id = obj.id
    else:
        obj_id = PydanticObjectId(item_id)
        obj = await Workflow.get(obj_id)
        if not obj:
            raise ValueError("Item not found")

    # Check for existing pending request (returned items can be resubmitted)
    existing = await VerificationRequest.find_one(
        VerificationRequest.item_id == obj_id,
        {"status": {"$in": [VerificationStatus.SUBMITTED.value, VerificationStatus.IN_REVIEW.value]}},
    )
    if existing:
        raise ValueError("A verification request is already pending for this item")

    # Fetch latest validation for quality gate checks
    from app.services.quality_service import get_latest_validation, compute_quality_tier

    item_ref = str(getattr(obj, 'uuid', '')) if item_kind == "search_set" and hasattr(obj, 'uuid') else str(obj_id)
    latest = await get_latest_validation(item_kind, item_ref)

    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    gates = qc.get("verification_gates", {})

    # Quality gate: require validation before submission
    if gates.get("require_validation") and not latest:
        raise ValueError("This item must be validated before submitting for verification. Run validation first.")

    # Enforce minimum sample size thresholds
    if latest:
        result_snap = latest.get("result_snapshot", {})
        min_tc = gates.get("min_test_cases", 0)
        min_runs = gates.get("min_runs", 0)
        min_score_gate = gates.get("min_score", 0)

        num_tc = len(result_snap.get("test_cases", result_snap.get("sources", [])))
        num_runs_val = result_snap.get("num_runs", 1)
        val_score = latest.get("score", 0)

        issues = []
        if min_tc > 0 and num_tc < min_tc:
            issues.append(f"Validation used {num_tc} test case(s), minimum is {min_tc}")
        if min_runs > 0 and num_runs_val < min_runs:
            issues.append(f"Validation used {num_runs_val} run(s), minimum is {min_runs}")
        if min_score_gate > 0 and val_score < min_score_gate:
            issues.append(f"Quality score is {val_score:.0f}, minimum is {min_score_gate}")
        if issues:
            raise ValueError("Submission requirements not met: " + "; ".join(issues))

    validation_snapshot = latest.get("result_snapshot") if latest else None
    validation_score = latest.get("score") if latest else None
    validation_tier = compute_quality_tier(validation_score, qc) if validation_score is not None else None

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
        validation_snapshot=validation_snapshot,
        validation_score=validation_score,
        validation_tier=validation_tier,
    )
    await req.insert()
    return await _request_to_dict(req)


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
        d = await _request_to_dict(req)
        # Attach item name
        d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
        results.append(d)
    return results


async def get_request(request_uuid: str) -> dict | None:
    """Get a single verification request by UUID."""
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return None
    d = await _request_to_dict(req)
    d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
    return d


async def update_status(
    request_uuid: str,
    new_status: str,
    reviewer_user_id: str,
    reviewer_notes: str | None = None,
    organization_ids: list[str] | None = None,
    collection_ids: list[str] | None = None,
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

    # If returned, store guidance for the submitter
    if new_status == VerificationStatus.RETURNED.value:
        req.return_guidance = reviewer_notes
        await req.save()

    # Notify the submitter of status changes
    await _notify_submitter(req, new_status, reviewer_notes)

    # If approved, mark the library item as verified
    if new_status == VerificationStatus.APPROVED.value:
        if req.item_kind == "knowledge_base":
            await _mark_kb_verified(req.item_id)
        else:
            await _mark_item_verified(req.item_id, req.item_kind)

        # Assign org visibility if provided
        if organization_ids is not None:
            await update_item_metadata(
                item_kind=req.item_kind,
                item_id=str(req.item_id),
                user_id=reviewer_user_id,
                organization_ids=organization_ids,
            )

        # Add to collections if provided
        if collection_ids:
            for cid in collection_ids:
                await add_to_collection(cid, str(req.item_id))

    return await _request_to_dict(req)


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
        d = await _request_to_dict(req)
        d["item_name"] = await _get_item_name(req.item_kind, req.item_id)
        results.append(d)
    return results


async def get_reviewer_rubric(request_uuid: str) -> dict | None:
    """Generate a structured reviewer rubric/checklist for a verification request.

    Returns a checklist of items the reviewer should verify, pre-populated
    with automated checks where possible.
    """
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return None

    from app.services.quality_service import get_latest_validation, check_verification_readiness

    item_ref = str(req.item_id)
    # For search sets, use uuid
    if req.item_kind == "search_set":
        ss = await SearchSet.find_one(SearchSet.id == req.item_id)
        if ss:
            item_ref = ss.uuid

    readiness = await check_verification_readiness(req.item_kind, item_ref)
    latest = await get_latest_validation(req.item_kind, item_ref)

    result = latest.get("result_snapshot", {}) if latest else {}
    score = latest.get("score") if latest else None
    num_tc = len(result.get("test_cases", result.get("sources", [])))
    num_runs = result.get("num_runs", 0)

    checklist = []

    # Automated checks
    checklist.append({
        "category": "validation",
        "item": "Validation has been run",
        "status": "pass" if latest else "fail",
        "automated": True,
        "detail": f"Score: {score:.0f}" if score else "No validation found",
    })

    checklist.append({
        "category": "validation",
        "item": f"Minimum test cases (\u22653)",
        "status": "pass" if num_tc >= 3 else "warning",
        "automated": True,
        "detail": f"{num_tc} test case(s) used",
    })

    checklist.append({
        "category": "validation",
        "item": f"Minimum runs per test case (\u22653)",
        "status": "pass" if num_runs >= 3 else "warning",
        "automated": True,
        "detail": f"{num_runs} run(s) per test case",
    })

    # Check challenging fields
    challenging = result.get("challenging_fields", [])
    checklist.append({
        "category": "quality",
        "item": "No challenging fields (all fields \u226590% accuracy & consistency)",
        "status": "pass" if not challenging else "warning",
        "automated": True,
        "detail": f"{len(challenging)} field(s) below threshold" if challenging else "All fields performing well",
    })

    # Check cross-field rules
    cf_score = result.get("cross_field_score")
    if cf_score is not None:
        checklist.append({
            "category": "quality",
            "item": "Cross-field validation passing",
            "status": "pass" if cf_score >= 0.9 else "warning",
            "automated": True,
            "detail": f"{cf_score * 100:.0f}% cross-field compliance",
        })

    # Manual checks for the reviewer
    checklist.append({
        "category": "review",
        "item": "Test cases use representative, diverse source documents",
        "status": "pending",
        "automated": False,
        "detail": "Reviewer should verify test cases cover typical document variations",
    })

    checklist.append({
        "category": "review",
        "item": "Expected values in test cases are correct",
        "status": "pending",
        "automated": False,
        "detail": "Reviewer should spot-check expected values against source documents",
    })

    checklist.append({
        "category": "review",
        "item": "Extraction fields are well-defined and unambiguous",
        "status": "pending",
        "automated": False,
        "detail": "Reviewer should check that field names and descriptions are clear",
    })

    checklist.append({
        "category": "review",
        "item": "Submission metadata is complete",
        "status": "pass" if req.summary and req.description else "warning",
        "automated": True,
        "detail": "Summary and description provided" if req.summary and req.description else "Missing summary or description",
    })

    return {
        "request_uuid": request_uuid,
        "readiness": readiness,
        "checklist": checklist,
        "automated_pass_count": sum(1 for c in checklist if c["automated"] and c["status"] == "pass"),
        "automated_total": sum(1 for c in checklist if c["automated"]),
        "manual_pending_count": sum(1 for c in checklist if not c["automated"] and c["status"] == "pending"),
    }


async def check_auto_approve(request_uuid: str) -> dict:
    """Check if a verification request qualifies for auto-approval based on config thresholds.

    Returns dict with 'auto_approve': bool and 'reason': str.
    """
    req = await VerificationRequest.find_one(VerificationRequest.uuid == request_uuid)
    if not req:
        return {"auto_approve": False, "reason": "Request not found"}

    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    auto_cfg = qc.get("auto_approve", {})

    if not auto_cfg.get("enabled", False):
        return {"auto_approve": False, "reason": "Auto-approve is not enabled"}

    min_score = auto_cfg.get("min_score", 95)
    min_test_cases = auto_cfg.get("min_test_cases", 5)
    min_runs = auto_cfg.get("min_runs", 3)

    if not req.validation_score or req.validation_score < min_score:
        return {"auto_approve": False, "reason": f"Score {req.validation_score or 0:.0f} < {min_score} threshold"}

    snap = req.validation_snapshot or {}
    num_tc = len(snap.get("test_cases", snap.get("sources", [])))
    num_runs_val = snap.get("num_runs", 1)

    if num_tc < min_test_cases:
        return {"auto_approve": False, "reason": f"{num_tc} test cases < {min_test_cases} minimum"}

    if num_runs_val < min_runs:
        return {"auto_approve": False, "reason": f"{num_runs_val} runs < {min_runs} minimum"}

    return {"auto_approve": True, "reason": f"Score {req.validation_score:.0f} with {num_tc} test cases and {num_runs_val} runs meets auto-approve thresholds"}


# ---------------------------------------------------------------------------
# Verified Catalog
# ---------------------------------------------------------------------------


async def list_verified_items(
    kind_filter: str | None = None,
    search: str | None = None,
    user_org_ancestry: list[str] | None = None,
    quality_tier: str | None = None,
    tag: str | None = None,
    collection_id: str | None = None,
    sort: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """List verified library items with filtering, sorting, and pagination.

    Returns {"items": [...], "total": int} so the frontend can paginate.
    """
    # If filtering by collection, resolve the item_ids in that collection first
    collection_item_ids: set[str] | None = None
    if collection_id:
        col = await VerifiedCollection.get(PydanticObjectId(collection_id))
        if col:
            collection_item_ids = set(col.item_ids)
        else:
            return {"items": [], "total": 0}

    query: dict = {"verified": True}
    if kind_filter:
        query["kind"] = kind_filter
    if tag:
        query["tags"] = tag

    items = await LibraryItem.find(query).sort("-created_at").to_list()

    # Deduplicate by (item_id, kind) — keep the first (newest) entry
    seen: set[tuple[str, str]] = set()
    deduped_items = []
    for item in items:
        key = (str(item.item_id), item.kind.value)
        if key not in seen:
            seen.add(key)
            deduped_items.append(item)
    items = deduped_items

    # Collection filter: keep only items whose item_id is in the collection
    if collection_item_ids is not None:
        items = [i for i in items if str(i.item_id) in collection_item_ids]

    # --- Batch-fetch names for all items to avoid N+1 queries ---
    wf_ids = [i.item_id for i in items if i.kind == LibraryItemKind.WORKFLOW]
    ss_ids = [i.item_id for i in items if i.kind == LibraryItemKind.SEARCH_SET]
    kb_ids = [i.item_id for i in items if i.kind == LibraryItemKind.KNOWLEDGE_BASE]

    name_map: dict[str, str] = {}
    if wf_ids:
        wfs = await Workflow.find({"_id": {"$in": wf_ids}}).to_list()
        for wf in wfs:
            name_map[str(wf.id)] = wf.name
    if ss_ids:
        ssets = await SearchSet.find({"_id": {"$in": ss_ids}}).to_list()
        for ss in ssets:
            name_map[str(ss.id)] = ss.title
    if kb_ids:
        kbs = await KnowledgeBase.find({"_id": {"$in": kb_ids}}).to_list()
        for kb in kbs:
            name_map[str(kb.id)] = kb.title

    # --- Batch-fetch all metadata ---
    all_meta = await VerifiedItemMetadata.find_all().to_list()
    meta_map: dict[tuple[str, str], VerifiedItemMetadata] = {}
    for m in all_meta:
        meta_map[(m.item_kind, m.item_id)] = m

    # --- Batch-fetch KB metrics ---
    kb_map: dict[str, KnowledgeBase] = {}
    if kb_ids:
        kb_docs = await KnowledgeBase.find({"_id": {"$in": kb_ids}}).to_list()
        for kb in kb_docs:
            kb_map[str(kb.id)] = kb

    # --- Build result entries (applying search and org filters) ---
    search_lower = search.lower() if search else None
    results = []
    for item in items:
        item_id_str = str(item.item_id)
        name = name_map.get(item_id_str, "Unknown")
        meta = meta_map.get((item.kind.value, item_id_str))

        # Search: match against name, display_name, description, and tags
        if search_lower:
            searchable = " ".join(filter(None, [
                name.lower(),
                (meta.display_name or "").lower() if meta else "",
                (meta.description or "").lower() if meta else "",
                " ".join(t.lower() for t in item.tags),
            ]))
            if search_lower not in searchable:
                continue

        # Org visibility
        item_org_ids = meta.organization_ids if meta else []
        if user_org_ancestry is not None and item_org_ids:
            if not set(item_org_ids) & set(user_org_ancestry):
                continue

        # Quality tier filter
        item_tier = meta.quality_tier if meta else None
        if quality_tier and item_tier != quality_tier:
            continue

        entry = {
            "id": str(item.id),
            "item_id": item_id_str,
            "kind": item.kind.value,
            "name": name,
            "tags": item.tags,
            "verified": item.verified,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "display_name": meta.display_name if meta else None,
            "description": meta.description if meta else None,
            "markdown": meta.markdown if meta else None,
            "organization_ids": item_org_ids,
            "quality_score": meta.quality_score if meta else None,
            "quality_tier": item_tier,
            "quality_grade": meta.quality_grade if meta else None,
            "last_validated_at": meta.last_validated_at.isoformat() if meta and meta.last_validated_at else None,
            "validation_run_count": meta.validation_run_count if meta else 0,
        }

        # KB-specific metrics (from batch)
        if item.kind == LibraryItemKind.KNOWLEDGE_BASE:
            kb = kb_map.get(item_id_str)
            if kb:
                entry["total_sources"] = kb.total_sources
                entry["total_chunks"] = kb.total_chunks
                entry["sources_ready"] = kb.sources_ready
                entry["kb_status"] = kb.status
                entry["source_uuid"] = kb.uuid

        results.append(entry)

    # --- Sort ---
    if sort == "quality":
        tier_order = {"gold": 0, "silver": 1, "bronze": 2}
        results.sort(key=lambda e: (tier_order.get(e.get("quality_tier") or "", 99), -(e.get("quality_score") or 0)))
    elif sort == "name":
        results.sort(key=lambda e: (e.get("display_name") or e.get("name") or "").lower())
    elif sort == "validations":
        results.sort(key=lambda e: -(e.get("validation_run_count") or 0))
    # default: already sorted by created_at desc from the DB query

    total = len(results)
    paginated = results[skip : skip + limit]
    return {"items": paginated, "total": total}


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
        "organization_ids": meta.organization_ids,
        "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
        "updated_by_user_id": meta.updated_by_user_id,
        "quality_score": meta.quality_score,
        "quality_tier": meta.quality_tier,
        "quality_grade": meta.quality_grade,
        "last_validated_at": meta.last_validated_at.isoformat() if meta.last_validated_at else None,
        "validation_run_count": meta.validation_run_count,
    }


async def update_item_metadata(
    item_kind: str,
    item_id: str,
    user_id: str,
    display_name: str | None = None,
    description: str | None = None,
    markdown: str | None = None,
    organization_ids: list[str] | None = None,
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
        if organization_ids is not None:
            meta.organization_ids = organization_ids
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
            organization_ids=organization_ids or [],
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
        "organization_ids": meta.organization_ids,
        "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
        "updated_by_user_id": meta.updated_by_user_id,
    }


async def unverify_item(item_id: str, item_kind: str) -> dict:
    """Remove verified status from a library item and remove from verified library."""
    from app.services.library_service import get_or_create_verified_library

    obj_id = PydanticObjectId(item_id)
    if item_kind == "workflow":
        wf = await Workflow.get(obj_id)
        if wf:
            wf.verified = False
            await wf.save()
    elif item_kind == "search_set":
        ss = await SearchSet.get(obj_id)
        if ss:
            ss.verified = False
            await ss.save()
    elif item_kind == "knowledge_base":
        kb = await KnowledgeBase.get(obj_id)
        if kb:
            kb.verified = False
            await kb.save()

    items = await LibraryItem.find(
        LibraryItem.item_id == obj_id,
        LibraryItem.kind == LibraryItemKind(item_kind),
    ).to_list()
    for item in items:
        item.verified = False
        await item.save()

    # Remove from the global verified library
    verified_lib = await get_or_create_verified_library()
    verified_items = await LibraryItem.find(
        {"_id": {"$in": verified_lib.items}},
        LibraryItem.item_id == obj_id,
        LibraryItem.kind == LibraryItemKind(item_kind),
    ).to_list()
    for vi in verified_items:
        verified_lib.items = [i for i in verified_lib.items if i != vi.id]
        await vi.delete()
    if verified_items:
        verified_lib.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await verified_lib.save()

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
    featured: bool | None = None,
) -> dict:
    """Create a new verified collection."""
    now = datetime.datetime.now(datetime.timezone.utc)
    col = VerifiedCollection(
        title=title,
        description=description,
        featured=featured or False,
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
    featured: bool | None = None,
) -> dict | None:
    """Update a collection's title, description, and/or featured status."""
    col = await VerifiedCollection.get(PydanticObjectId(collection_id))
    if not col:
        return None
    if title is not None:
        col.title = title
    if description is not None:
        col.description = description
    if featured is not None:
        col.featured = featured
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
    """List all users with examiner status (includes admins)."""
    users = await User.find(
        {"$or": [{"is_examiner": True}, {"is_admin": True}]}
    ).to_list()
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "email": u.email,
            "is_examiner": u.is_examiner or u.is_admin,
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
    """Set verified=True on a KnowledgeBase and add to the verified library."""
    from app.services.library_service import get_or_create_verified_library

    kb = await KnowledgeBase.get(item_id)
    if not kb:
        return
    kb.verified = True
    await kb.save()

    # Add a verified LibraryItem to the global verified library
    verified_lib = await get_or_create_verified_library()
    verified_item_ids = set(verified_lib.items) if verified_lib.items else set()

    existing_in_verified = await LibraryItem.find(
        {"_id": {"$in": list(verified_item_ids)}},
        {"item_id": item_id, "kind": "knowledge_base"},
    ).to_list() if verified_item_ids else []

    if not existing_in_verified:
        now = datetime.datetime.now(datetime.timezone.utc)
        new_item = LibraryItem(
            item_id=item_id,
            kind=LibraryItemKind.KNOWLEDGE_BASE,
            added_by_user_id="system",
            verified=True,
            tags=[],
            created_at=now,
        )
        await new_item.insert()
        verified_lib.items.append(new_item.id)
        verified_lib.updated_at = now
        await verified_lib.save()


async def _mark_item_verified(item_id: PydanticObjectId, item_kind: str) -> None:
    """Mark the underlying item as verified and add to the verified library."""
    from app.services.library_service import get_or_create_verified_library

    # Mark verified on the underlying object (workflow / search_set)
    if item_kind == "workflow":
        wf = await Workflow.get(item_id)
        if wf:
            wf.verified = True
            await wf.save()
    elif item_kind == "search_set":
        ss = await SearchSet.get(item_id)
        if ss:
            ss.verified = True
            await ss.save()

    # Add a verified LibraryItem to the global verified library (if not already present)
    verified_lib = await get_or_create_verified_library()
    verified_item_ids = set(verified_lib.items) if verified_lib.items else set()

    # Check if this item is already in the verified library
    existing_in_verified = await LibraryItem.find(
        {"_id": {"$in": list(verified_item_ids)}},
        {"item_id": item_id, "kind": item_kind},
    ).to_list() if verified_item_ids else []

    if not existing_in_verified:
        now = datetime.datetime.now(datetime.timezone.utc)
        new_item = LibraryItem(
            item_id=item_id,
            kind=LibraryItemKind(item_kind),
            added_by_user_id="system",
            verified=True,
            tags=[],
            created_at=now,
        )
        await new_item.insert()
        verified_lib.items.append(new_item.id)
        verified_lib.updated_at = now
        await verified_lib.save()


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


async def _request_to_dict(req: VerificationRequest) -> dict:
    # Resolve item_uuid for search_set and knowledge_base items
    item_uuid = None
    if req.item_kind == "search_set":
        ss = await SearchSet.get(req.item_id)
        if ss and hasattr(ss, "uuid"):
            item_uuid = ss.uuid
    elif req.item_kind == "knowledge_base":
        kb = await KnowledgeBase.get(req.item_id)
        if kb:
            item_uuid = kb.uuid

    return {
        "id": str(req.id),
        "uuid": req.uuid,
        "item_kind": req.item_kind,
        "item_id": str(req.item_id),
        "item_uuid": item_uuid,
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
        "validation_snapshot": req.validation_snapshot,
        "validation_score": req.validation_score,
        "validation_tier": req.validation_tier,
        "return_guidance": req.return_guidance,
    }


def _collection_to_dict(col: VerifiedCollection) -> dict:
    return {
        "id": str(col.id),
        "title": col.title,
        "description": col.description,
        "promo_image_url": col.promo_image_url,
        "featured": col.featured,
        "item_ids": col.item_ids,
        "created_by_user_id": col.created_by_user_id,
        "created_at": col.created_at.isoformat() if col.created_at else None,
        "updated_at": col.updated_at.isoformat() if col.updated_at else None,
    }


async def _notify_submitter(
    req: VerificationRequest,
    new_status: str,
    reviewer_notes: str | None,
) -> None:
    """Send a notification to the submitter when their request status changes."""
    from app.services import notification_service

    item_name = await _get_item_name(req.item_kind, req.item_id)

    status_config = {
        VerificationStatus.APPROVED.value: {
            "kind": "verification_approved",
            "title": f'"{item_name}" has been approved',
            "body": reviewer_notes or "Your submission has been verified and added to the catalog.",
        },
        VerificationStatus.REJECTED.value: {
            "kind": "verification_rejected",
            "title": f'"{item_name}" was not approved',
            "body": reviewer_notes or "Your submission did not meet verification requirements.",
        },
        VerificationStatus.RETURNED.value: {
            "kind": "verification_returned",
            "title": f'"{item_name}" needs revision',
            "body": reviewer_notes or "Your submission has been returned with feedback.",
        },
        VerificationStatus.IN_REVIEW.value: {
            "kind": "verification_in_review",
            "title": f'"{item_name}" is under review',
            "body": "An examiner has started reviewing your submission.",
        },
    }

    cfg = status_config.get(new_status)
    if not cfg:
        return

    await notification_service.create_notification(
        user_id=req.submitter_user_id,
        kind=cfg["kind"],
        title=cfg["title"],
        body=cfg["body"],
        link=f"/library?tab=verification",
        item_kind=req.item_kind,
        item_id=str(req.item_id),
        item_name=item_name,
        request_uuid=req.uuid,
    )


async def check_and_flag_stale_verification(item_kind: str, item_id: str) -> bool:
    """Check if a verified item was modified and flag it as stale.

    Called from workflow/extraction update endpoints. Returns True if the item
    was verified and is now flagged stale.
    """
    from beanie import PydanticObjectId

    obj_id = PydanticObjectId(item_id)

    # Check if the underlying item is verified
    if item_kind == "workflow":
        obj = await Workflow.get(obj_id)
        if not obj or not obj.verified:
            return False
    elif item_kind == "search_set":
        obj = await SearchSet.get(obj_id)
        if not obj or not obj.verified:
            return False
    elif item_kind == "knowledge_base":
        obj = await KnowledgeBase.get(obj_id)
        if not obj or not obj.verified:
            return False
    else:
        return False

    # Create a quality alert for the stale verification
    from app.models.quality_alert import QualityAlert

    item_name = await _get_item_name(item_kind, obj_id)

    await QualityAlert(
        alert_type="config_changed",
        item_kind=item_kind,
        item_id=str(obj_id),
        item_name=item_name,
        severity="warning",
        message=f'Verified item "{item_name}" was modified. Re-validation recommended.',
    ).insert()

    # Mark verified item metadata as stale by clearing last_validated_at
    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == str(obj_id),
    )
    if meta:
        meta.last_validated_at = None
        meta.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await meta.save()

    return True
