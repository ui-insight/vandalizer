"""Tests for app.services.verification_service — submit, review, approve, reject, collections, examiners."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

MODULE = "app.services.verification_service"
_FAKE_COL_OID = str(ObjectId())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obj(obj_id="obj-id-123", uuid="obj-uuid-456", verified=False, name="Test Obj", title="Test Title"):
    """Generic DB object mock (Workflow, SearchSet, KnowledgeBase)."""
    o = MagicMock()
    o.id = obj_id
    o.uuid = uuid
    o.verified = verified
    o.name = name
    o.title = title
    o.save = AsyncMock()
    o.insert = AsyncMock()
    o.delete = AsyncMock()
    return o


def _make_verification_request(
    uuid="req-uuid",
    item_kind="workflow",
    item_id="obj-id-123",
    status="submitted",
    submitter_user_id="alice",
    submitter_name="Alice",
    submitter_org=None,
    submitter_role=None,
    summary="A summary",
    description="A description",
    category=None,
    reviewer_user_id=None,
    reviewer_notes=None,
    validation_snapshot=None,
    validation_score=None,
    validation_tier=None,
    return_guidance=None,
    submitted_at=None,
    reviewed_at=None,
    item_version_hash=None,
    run_instructions=None,
    evaluation_notes=None,
    known_limitations=None,
    example_inputs=None,
    expected_outputs=None,
    dependencies=None,
    intended_use_tags=None,
    test_files=None,
):
    r = MagicMock()
    r.id = "req-oid"
    r.uuid = uuid
    r.item_kind = item_kind
    r.item_id = item_id
    r.status = status
    r.submitter_user_id = submitter_user_id
    r.submitter_name = submitter_name
    r.submitter_org = submitter_org
    r.submitter_role = submitter_role
    r.summary = summary
    r.description = description
    r.category = category
    r.reviewer_user_id = reviewer_user_id
    r.reviewer_notes = reviewer_notes
    r.validation_snapshot = validation_snapshot
    r.validation_score = validation_score
    r.validation_tier = validation_tier
    r.return_guidance = return_guidance
    r.submitted_at = submitted_at or datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    r.reviewed_at = reviewed_at
    r.item_version_hash = item_version_hash
    r.run_instructions = run_instructions
    r.evaluation_notes = evaluation_notes
    r.known_limitations = known_limitations
    r.example_inputs = example_inputs or []
    r.expected_outputs = expected_outputs or []
    r.dependencies = dependencies or []
    r.intended_use_tags = intended_use_tags or []
    r.test_files = test_files or []
    r.save = AsyncMock()
    r.insert = AsyncMock()
    r.delete = AsyncMock()
    return r


def _make_collection(
    col_id=_FAKE_COL_OID,
    title="My Collection",
    description="Desc",
    featured=False,
    item_ids=None,
    created_by_user_id="alice",
    promo_image_url=None,
):
    c = MagicMock()
    c.id = col_id
    c.title = title
    c.description = description
    c.featured = featured
    c.item_ids = item_ids if item_ids is not None else []
    c.created_by_user_id = created_by_user_id
    c.promo_image_url = promo_image_url
    c.created_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    c.updated_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    c.save = AsyncMock()
    c.insert = AsyncMock()
    c.delete = AsyncMock()
    return c


def _make_user(user_id="alice", name="Alice", email="alice@example.com", is_examiner=False, is_admin=False):
    u = MagicMock()
    u.user_id = user_id
    u.name = name
    u.email = email
    u.is_examiner = is_examiner
    u.is_admin = is_admin
    u.save = AsyncMock()
    return u


def _make_meta(
    item_kind="workflow",
    item_id="obj-id-123",
    display_name="Display",
    description="Desc",
    markdown=None,
    organization_ids=None,
    quality_score=None,
    quality_tier=None,
    quality_grade=None,
    last_validated_at=None,
    validation_run_count=0,
    updated_at=None,
    updated_by_user_id=None,
):
    m = MagicMock()
    m.id = "meta-oid"
    m.item_kind = item_kind
    m.item_id = item_id
    m.display_name = display_name
    m.description = description
    m.markdown = markdown
    m.organization_ids = organization_ids or []
    m.quality_score = quality_score
    m.quality_tier = quality_tier
    m.quality_grade = quality_grade
    m.last_validated_at = last_validated_at
    m.validation_run_count = validation_run_count
    m.updated_at = updated_at or datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    m.updated_by_user_id = updated_by_user_id
    m.save = AsyncMock()
    m.insert = AsyncMock()
    return m


def _make_sys_config(quality_config=None):
    cfg = MagicMock()
    cfg.get_quality_config.return_value = quality_config or {}
    return cfg


def _chain_query(*items):
    """Create a mock that supports chained .sort().limit().to_list() returning items."""
    chain = MagicMock()
    chain.sort.return_value = chain
    chain.limit.return_value = chain
    chain.to_list = AsyncMock(return_value=list(items))
    return chain


# ---------------------------------------------------------------------------
# _request_to_dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.SearchSet", new_callable=MagicMock)
async def test_request_to_dict_workflow(mock_ss):
    """_request_to_dict returns a proper dict for a workflow request (no item_uuid)."""
    from app.services.verification_service import _request_to_dict

    req = _make_verification_request(item_kind="workflow")
    result = await _request_to_dict(req)

    assert result["uuid"] == "req-uuid"
    assert result["item_kind"] == "workflow"
    assert result["status"] == "submitted"
    assert result["submitter_user_id"] == "alice"
    assert result["item_uuid"] is None


@pytest.mark.asyncio
@patch(f"{MODULE}.SearchSet")
async def test_request_to_dict_search_set(mock_ss):
    """_request_to_dict resolves item_uuid for a search_set."""
    from app.services.verification_service import _request_to_dict

    ss_obj = _make_obj(uuid="ss-uuid-789")
    mock_ss.get = AsyncMock(return_value=ss_obj)

    req = _make_verification_request(item_kind="search_set")
    result = await _request_to_dict(req)

    assert result["item_uuid"] == "ss-uuid-789"


@pytest.mark.asyncio
@patch(f"{MODULE}.KnowledgeBase")
@patch(f"{MODULE}.SearchSet")
async def test_request_to_dict_knowledge_base(mock_ss, mock_kb):
    """_request_to_dict resolves item_uuid for a knowledge_base."""
    from app.services.verification_service import _request_to_dict

    kb_obj = _make_obj(uuid="kb-uuid-789")
    mock_kb.get = AsyncMock(return_value=kb_obj)

    req = _make_verification_request(item_kind="knowledge_base")
    result = await _request_to_dict(req)

    assert result["item_uuid"] == "kb-uuid-789"


# ---------------------------------------------------------------------------
# _collection_to_dict
# ---------------------------------------------------------------------------


def test_collection_to_dict():
    """_collection_to_dict converts a VerifiedCollection to a dict."""
    from app.services.verification_service import _collection_to_dict

    col = _make_collection(item_ids=["item-1", "item-2"])
    result = _collection_to_dict(col)

    assert result["id"] == _FAKE_COL_OID
    assert result["title"] == "My Collection"
    assert result["item_ids"] == ["item-1", "item-2"]
    assert result["featured"] is False
    assert result["created_at"] is not None


# ---------------------------------------------------------------------------
# _get_item_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.Workflow")
async def test_get_item_name_workflow(mock_wf):
    from app.services.verification_service import _get_item_name

    wf = _make_obj(name="My Workflow")
    mock_wf.get = AsyncMock(return_value=wf)

    result = await _get_item_name("workflow", "oid-1")
    assert result == "My Workflow"


@pytest.mark.asyncio
@patch(f"{MODULE}.Workflow")
async def test_get_item_name_workflow_not_found(mock_wf):
    from app.services.verification_service import _get_item_name

    mock_wf.get = AsyncMock(return_value=None)
    result = await _get_item_name("workflow", "oid-1")
    assert result == "Unknown workflow"


@pytest.mark.asyncio
@patch(f"{MODULE}.KnowledgeBase")
async def test_get_item_name_knowledge_base(mock_kb):
    from app.services.verification_service import _get_item_name

    kb = _make_obj(title="My KB")
    mock_kb.get = AsyncMock(return_value=kb)

    result = await _get_item_name("knowledge_base", "oid-1")
    assert result == "My KB"


@pytest.mark.asyncio
@patch(f"{MODULE}.SearchSet")
async def test_get_item_name_search_set(mock_ss):
    from app.services.verification_service import _get_item_name

    ss = _make_obj(title="My Search Set")
    mock_ss.get = AsyncMock(return_value=ss)

    result = await _get_item_name("search_set", "oid-1")
    assert result == "My Search Set"


@pytest.mark.asyncio
@patch(f"{MODULE}.SearchSet")
async def test_get_item_name_unknown_kind_not_found(mock_ss):
    from app.services.verification_service import _get_item_name

    mock_ss.get = AsyncMock(return_value=None)
    result = await _get_item_name("other_kind", "oid-1")
    assert result == "Unknown extraction"


# ---------------------------------------------------------------------------
# get_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="Test Item")
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock)
@patch(f"{MODULE}.VerificationRequest")
async def test_get_request_found(mock_vr, mock_to_dict, mock_name):
    from app.services.verification_service import get_request

    req = _make_verification_request()
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_to_dict.return_value = {"uuid": "req-uuid", "item_kind": "workflow"}

    result = await get_request("req-uuid")
    assert result is not None
    assert result["item_name"] == "Test Item"


@pytest.mark.asyncio
@patch(f"{MODULE}.VerificationRequest")
async def test_get_request_not_found(mock_vr):
    from app.services.verification_service import get_request

    mock_vr.find_one = AsyncMock(return_value=None)
    result = await get_request("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# list_queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="Item Name")
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "r1"})
@patch(f"{MODULE}.VerificationRequest")
async def test_list_queue_no_filter(mock_vr, mock_to_dict, mock_name):
    from app.services.verification_service import list_queue

    req = _make_verification_request()
    chain = _chain_query(req)
    mock_vr.find.return_value = chain

    result = await list_queue()
    assert len(result) == 1
    assert result[0]["item_name"] == "Item Name"
    # Should use default filter (submitted + in_review)
    call_args = mock_vr.find.call_args[0][0]
    assert "$in" in call_args["status"]


@pytest.mark.asyncio
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="Item Name")
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "r1"})
@patch(f"{MODULE}.VerificationRequest")
async def test_list_queue_with_status_filter(mock_vr, mock_to_dict, mock_name):
    from app.services.verification_service import list_queue

    chain = _chain_query(_make_verification_request())
    mock_vr.find.return_value = chain

    await list_queue(status_filter="approved")
    call_args = mock_vr.find.call_args[0][0]
    assert call_args["status"] == "approved"


# ---------------------------------------------------------------------------
# my_requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="My Item")
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "r1"})
@patch(f"{MODULE}.VerificationRequest")
async def test_my_requests(mock_vr, mock_to_dict, mock_name):
    from app.services.verification_service import my_requests

    chain = _chain_query(_make_verification_request())
    mock_vr.find.return_value = chain

    result = await my_requests("alice")
    assert len(result) == 1
    assert result[0]["item_name"] == "My Item"


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.add_to_collection", new_callable=AsyncMock)
@patch(f"{MODULE}.update_item_metadata", new_callable=AsyncMock)
@patch(f"{MODULE}._mark_item_verified", new_callable=AsyncMock)
@patch(f"{MODULE}._notify_submitter", new_callable=AsyncMock)
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "req-uuid", "status": "approved"})
@patch(f"{MODULE}.VerificationRequest")
async def test_update_status_approved(mock_vr, mock_to_dict, mock_notify, mock_mark, mock_meta, mock_add_col):
    from app.services.verification_service import update_status

    req = _make_verification_request(item_kind="workflow")
    mock_vr.find_one = AsyncMock(return_value=req)

    result = await update_status(
        "req-uuid", "approved", "bob",
        reviewer_notes="Looks good",
        organization_ids=["org-1"],
        collection_ids=["col-1"],
    )

    assert result is not None
    assert req.status == "approved"
    assert req.reviewer_user_id == "bob"
    assert req.reviewer_notes == "Looks good"
    req.save.assert_awaited()
    mock_mark.assert_awaited_once_with(req.item_id, "workflow")
    mock_meta.assert_awaited_once()
    mock_add_col.assert_awaited_once_with("col-1", str(req.item_id))
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}._notify_submitter", new_callable=AsyncMock)
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "req-uuid", "status": "returned"})
@patch(f"{MODULE}.VerificationRequest")
async def test_update_status_returned_stores_guidance(mock_vr, mock_to_dict, mock_notify):
    from app.services.verification_service import update_status

    req = _make_verification_request()
    mock_vr.find_one = AsyncMock(return_value=req)

    await update_status("req-uuid", "returned", "bob", reviewer_notes="Fix field X")

    assert req.return_guidance == "Fix field X"
    # save() called at least twice: once for status, once for guidance
    assert req.save.await_count >= 2


@pytest.mark.asyncio
@patch(f"{MODULE}.VerificationRequest")
async def test_update_status_not_found(mock_vr):
    from app.services.verification_service import update_status

    mock_vr.find_one = AsyncMock(return_value=None)
    result = await update_status(str(ObjectId()), "approved", "bob")
    assert result is None


@pytest.mark.asyncio
@patch(f"{MODULE}._mark_kb_verified", new_callable=AsyncMock)
@patch(f"{MODULE}._notify_submitter", new_callable=AsyncMock)
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "req-uuid", "status": "approved"})
@patch(f"{MODULE}.VerificationRequest")
async def test_update_status_approved_kb(mock_vr, mock_to_dict, mock_notify, mock_mark_kb):
    from app.services.verification_service import update_status

    req = _make_verification_request(item_kind="knowledge_base")
    mock_vr.find_one = AsyncMock(return_value=req)

    await update_status("req-uuid", "approved", "bob")
    mock_mark_kb.assert_awaited_once_with(req.item_id)


@pytest.mark.asyncio
@patch(f"{MODULE}._notify_submitter", new_callable=AsyncMock)
@patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "req-uuid", "status": "rejected"})
@patch(f"{MODULE}.VerificationRequest")
async def test_update_status_rejected_no_mark(mock_vr, mock_to_dict, mock_notify):
    """Rejected status should NOT call _mark_item_verified."""
    from app.services.verification_service import update_status

    req = _make_verification_request()
    mock_vr.find_one = AsyncMock(return_value=req)

    with patch(f"{MODULE}._mark_item_verified", new_callable=AsyncMock) as mock_mark:
        await update_status("req-uuid", "rejected", "bob")
        mock_mark.assert_not_awaited()


# ---------------------------------------------------------------------------
# check_auto_approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_not_found(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    mock_vr.find_one = AsyncMock(return_value=None)
    result = await check_auto_approve(str(ObjectId()))
    assert result["auto_approve"] is False
    assert "not found" in result["reason"].lower()


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_disabled(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    req = _make_verification_request(validation_score=100)
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_sc.get_config = AsyncMock(return_value=_make_sys_config({"auto_approve": {"enabled": False}}))

    result = await check_auto_approve("req-uuid")
    assert result["auto_approve"] is False
    assert "not enabled" in result["reason"].lower()


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_score_too_low(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    req = _make_verification_request(validation_score=80)
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_sc.get_config = AsyncMock(return_value=_make_sys_config({
        "auto_approve": {"enabled": True, "min_score": 95, "min_test_cases": 5, "min_runs": 3}
    }))

    result = await check_auto_approve("req-uuid")
    assert result["auto_approve"] is False
    assert "80" in result["reason"]


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_not_enough_test_cases(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    req = _make_verification_request(
        validation_score=98,
        validation_snapshot={"test_cases": [1, 2], "num_runs": 5},
    )
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_sc.get_config = AsyncMock(return_value=_make_sys_config({
        "auto_approve": {"enabled": True, "min_score": 95, "min_test_cases": 5, "min_runs": 3}
    }))

    result = await check_auto_approve("req-uuid")
    assert result["auto_approve"] is False
    assert "test cases" in result["reason"].lower()


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_not_enough_runs(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    req = _make_verification_request(
        validation_score=98,
        validation_snapshot={"test_cases": [1, 2, 3, 4, 5], "num_runs": 1},
    )
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_sc.get_config = AsyncMock(return_value=_make_sys_config({
        "auto_approve": {"enabled": True, "min_score": 95, "min_test_cases": 5, "min_runs": 3}
    }))

    result = await check_auto_approve("req-uuid")
    assert result["auto_approve"] is False
    assert "runs" in result["reason"].lower()


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_passes(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    req = _make_verification_request(
        validation_score=98,
        validation_snapshot={"test_cases": [1, 2, 3, 4, 5], "num_runs": 5},
    )
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_sc.get_config = AsyncMock(return_value=_make_sys_config({
        "auto_approve": {"enabled": True, "min_score": 95, "min_test_cases": 5, "min_runs": 3}
    }))

    result = await check_auto_approve("req-uuid")
    assert result["auto_approve"] is True
    assert "meets auto-approve" in result["reason"].lower()


@pytest.mark.asyncio
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.VerificationRequest")
async def test_check_auto_approve_no_score(mock_vr, mock_sc):
    from app.services.verification_service import check_auto_approve

    req = _make_verification_request(validation_score=None)
    mock_vr.find_one = AsyncMock(return_value=req)
    mock_sc.get_config = AsyncMock(return_value=_make_sys_config({
        "auto_approve": {"enabled": True, "min_score": 95}
    }))

    result = await check_auto_approve("req-uuid")
    assert result["auto_approve"] is False


# ---------------------------------------------------------------------------
# get_item_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedItemMetadata")
async def test_get_item_metadata_found(mock_vim):
    from app.services.verification_service import get_item_metadata

    meta = _make_meta(display_name="Nice Name", quality_score=92.5, quality_tier="gold")
    mock_vim.find_one = AsyncMock(return_value=meta)

    result = await get_item_metadata("workflow", "obj-id-123")
    assert result is not None
    assert result["display_name"] == "Nice Name"
    assert result["quality_score"] == 92.5
    assert result["quality_tier"] == "gold"
    assert result["id"] == "meta-oid"


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedItemMetadata")
async def test_get_item_metadata_not_found(mock_vim):
    from app.services.verification_service import get_item_metadata

    mock_vim.find_one = AsyncMock(return_value=None)
    result = await get_item_metadata("workflow", str(ObjectId()))
    assert result is None


# ---------------------------------------------------------------------------
# update_item_metadata — upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedItemMetadata")
async def test_update_item_metadata_existing(mock_vim_cls):
    from app.services.verification_service import update_item_metadata

    meta = _make_meta()
    mock_vim_cls.find_one = AsyncMock(return_value=meta)

    result = await update_item_metadata(
        "workflow", "obj-id-123", "bob",
        display_name="New Name",
        description="New Desc",
        organization_ids=["org-1"],
    )

    assert meta.display_name == "New Name"
    assert meta.description == "New Desc"
    assert meta.organization_ids == ["org-1"]
    meta.save.assert_awaited_once()
    assert result["display_name"] == "New Name"


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedItemMetadata")
async def test_update_item_metadata_new(mock_vim_cls):
    from app.services.verification_service import update_item_metadata

    mock_vim_cls.find_one = AsyncMock(return_value=None)

    # Mock constructor: return a mock that has .insert() and the right fields
    created_meta = _make_meta(display_name="Fresh", description="New item desc")
    # Use return_value so find_one (set above) is preserved and constructor call returns created_meta
    mock_vim_cls.return_value = created_meta

    result = await update_item_metadata(
        "workflow", "new-id", "alice",
        display_name="Fresh",
        description="New item desc",
    )
    created_meta.insert.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedItemMetadata")
async def test_update_item_metadata_partial_update(mock_vim_cls):
    """Only provided fields should be updated."""
    from app.services.verification_service import update_item_metadata

    meta = _make_meta(display_name="Old Name", description="Old Desc", markdown="# Old")
    mock_vim_cls.find_one = AsyncMock(return_value=meta)

    # Only update display_name — description and markdown should be untouched
    await update_item_metadata("workflow", "obj-id-123", "bob", display_name="New Name")

    assert meta.display_name == "New Name"
    assert meta.description == "Old Desc"
    assert meta.markdown == "# Old"


# ---------------------------------------------------------------------------
# Collections CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_create_collection(mock_col_cls):
    from app.services.verification_service import create_collection

    col = _make_collection()
    mock_col_cls.return_value = col

    result = await create_collection("Test Col", "alice", description="Desc", featured=True)
    col.insert.assert_awaited_once()
    assert result["title"] == "My Collection"


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_list_collections(mock_col_cls):
    from app.services.verification_service import list_collections

    c1 = _make_collection(title="Col 1")
    c2 = _make_collection(title="Col 2")
    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=[c1, c2])
    find_all_chain = MagicMock()
    find_all_chain.sort.return_value = chain
    mock_col_cls.find_all.return_value = find_all_chain

    result = await list_collections()
    assert len(result) == 2


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_update_collection_found(mock_col_cls):
    from app.services.verification_service import update_collection

    col = _make_collection()
    mock_col_cls.get = AsyncMock(return_value=col)

    result = await update_collection(_FAKE_COL_OID, title="Updated", featured=True)
    assert result is not None
    assert col.title == "Updated"
    assert col.featured is True
    col.save.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_update_collection_not_found(mock_col_cls):
    from app.services.verification_service import update_collection

    mock_col_cls.get = AsyncMock(return_value=None)
    result = await update_collection(str(ObjectId()))
    assert result is None


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_delete_collection_found(mock_col_cls):
    from app.services.verification_service import delete_collection

    col = _make_collection()
    mock_col_cls.get = AsyncMock(return_value=col)

    result = await delete_collection(_FAKE_COL_OID)
    assert result is True
    col.delete.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_delete_collection_not_found(mock_col_cls):
    from app.services.verification_service import delete_collection

    mock_col_cls.get = AsyncMock(return_value=None)
    result = await delete_collection(str(ObjectId()))
    assert result is False


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_add_to_collection(mock_col_cls):
    from app.services.verification_service import add_to_collection

    col = _make_collection(item_ids=["existing-1"])
    mock_col_cls.get = AsyncMock(return_value=col)

    result = await add_to_collection(_FAKE_COL_OID, "new-item")
    assert "new-item" in col.item_ids
    col.save.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_add_to_collection_already_present(mock_col_cls):
    from app.services.verification_service import add_to_collection

    col = _make_collection(item_ids=["item-1"])
    mock_col_cls.get = AsyncMock(return_value=col)

    await add_to_collection(_FAKE_COL_OID, "item-1")
    # Should not duplicate — save not called since item already in list
    col.save.assert_not_awaited()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_add_to_collection_not_found(mock_col_cls):
    from app.services.verification_service import add_to_collection

    mock_col_cls.get = AsyncMock(return_value=None)
    result = await add_to_collection(str(ObjectId()), "item-1")
    assert result is None


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_remove_from_collection(mock_col_cls):
    from app.services.verification_service import remove_from_collection

    col = _make_collection(item_ids=["item-1", "item-2"])
    mock_col_cls.get = AsyncMock(return_value=col)

    result = await remove_from_collection(_FAKE_COL_OID, "item-1")
    assert "item-1" not in col.item_ids
    assert "item-2" in col.item_ids
    col.save.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_remove_from_collection_not_found(mock_col_cls):
    from app.services.verification_service import remove_from_collection

    mock_col_cls.get = AsyncMock(return_value=None)
    result = await remove_from_collection(str(ObjectId()), "item-1")
    assert result is None


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedCollection")
async def test_remove_from_collection_item_not_present(mock_col_cls):
    from app.services.verification_service import remove_from_collection

    col = _make_collection(item_ids=["item-2"])
    mock_col_cls.get = AsyncMock(return_value=col)

    result = await remove_from_collection(_FAKE_COL_OID, "item-1")
    # Should not error, save not called since nothing changed
    col.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# Examiner management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.User")
async def test_list_examiners(mock_user_cls):
    from app.services.verification_service import list_examiners

    u1 = _make_user(user_id="alice", is_examiner=True)
    u2 = _make_user(user_id="bob", is_admin=True)
    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=[u1, u2])
    mock_user_cls.find.return_value = chain

    result = await list_examiners()
    assert len(result) == 2
    assert result[0]["user_id"] == "alice"
    assert result[1]["is_examiner"] is True  # bob is admin so is_examiner returns True


@pytest.mark.asyncio
@patch(f"{MODULE}.User")
async def test_set_examiner_grant(mock_user_cls):
    from app.services.verification_service import set_examiner

    user = _make_user(user_id="alice", is_examiner=False)
    mock_user_cls.find_one = AsyncMock(return_value=user)

    result = await set_examiner("alice", True)
    assert user.is_examiner is True
    user.save.assert_awaited_once()
    assert result["user_id"] == "alice"


@pytest.mark.asyncio
@patch(f"{MODULE}.User")
async def test_set_examiner_revoke(mock_user_cls):
    from app.services.verification_service import set_examiner

    user = _make_user(user_id="alice", is_examiner=True)
    mock_user_cls.find_one = AsyncMock(return_value=user)

    result = await set_examiner("alice", False)
    assert user.is_examiner is False


@pytest.mark.asyncio
@patch(f"{MODULE}.User")
async def test_set_examiner_user_not_found(mock_user_cls):
    from app.services.verification_service import set_examiner

    mock_user_cls.find_one = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="User not found"):
        await set_examiner("ghost", True)


@pytest.mark.asyncio
@patch(f"{MODULE}.User")
async def test_search_users(mock_user_cls):
    from app.services.verification_service import search_users

    u1 = _make_user(user_id="alice", is_examiner=False)
    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=[u1])
    limit_chain = MagicMock()
    limit_chain.limit.return_value = chain
    mock_user_cls.find.return_value = limit_chain

    result = await search_users("ali")
    assert len(result) == 1
    assert result[0]["user_id"] == "alice"


# ---------------------------------------------------------------------------
# submit_for_verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.VerificationRequest")
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.Workflow")
async def test_submit_for_verification_workflow_happy_path(mock_wf_cls, mock_sc, mock_vr_cls):
    from app.services.verification_service import submit_for_verification

    wf = _make_obj()
    mock_wf_cls.get = AsyncMock(return_value=wf)

    # No existing pending request
    mock_vr_cls.find_one = AsyncMock(return_value=None)

    # Quality service mocks
    with patch("app.services.quality_service.get_latest_validation", new_callable=AsyncMock, return_value=None) as mock_glv, \
         patch("app.services.quality_service.compute_quality_tier", return_value=None):
        sys_cfg = _make_sys_config({"verification_gates": {}})
        mock_sc.get_config = AsyncMock(return_value=sys_cfg)

        # Mock VerificationRequest constructor
        created_req = _make_verification_request()
        mock_vr_cls.return_value = created_req

        # Mock _request_to_dict
        with patch(f"{MODULE}._request_to_dict", new_callable=AsyncMock, return_value={"uuid": "req-uuid"}):
            result = await submit_for_verification(
                item_kind="workflow",
                item_id="507f1f77bcf86cd799439011",
                user_id="alice",
                submitter_name="Alice",
                summary="Test submission",
            )

        assert result["uuid"] == "req-uuid"
        created_req.insert.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.VerificationRequest")
@patch(f"{MODULE}.Workflow")
async def test_submit_for_verification_already_pending(mock_wf_cls, mock_vr_cls):
    from app.services.verification_service import submit_for_verification

    wf = _make_obj()
    mock_wf_cls.get = AsyncMock(return_value=wf)

    # Existing pending request found
    existing = _make_verification_request()
    mock_vr_cls.find_one = AsyncMock(return_value=existing)

    with pytest.raises(ValueError, match="already pending"):
        await submit_for_verification(
            item_kind="workflow",
            item_id="507f1f77bcf86cd799439011",
            user_id="alice",
        )


@pytest.mark.asyncio
@patch(f"{MODULE}.Workflow")
async def test_submit_for_verification_item_not_found(mock_wf_cls):
    from app.services.verification_service import submit_for_verification

    mock_wf_cls.get = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Item not found"):
        await submit_for_verification(
            item_kind="workflow",
            item_id="507f1f77bcf86cd799439011",
            user_id="alice",
        )


@pytest.mark.asyncio
@patch(f"{MODULE}.VerificationRequest")
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.Workflow")
async def test_submit_for_verification_gate_requires_validation(mock_wf_cls, mock_sc, mock_vr_cls):
    from app.services.verification_service import submit_for_verification

    wf = _make_obj()
    mock_wf_cls.get = AsyncMock(return_value=wf)
    mock_vr_cls.find_one = AsyncMock(return_value=None)

    sys_cfg = _make_sys_config({"verification_gates": {"require_validation": True}})
    mock_sc.get_config = AsyncMock(return_value=sys_cfg)

    with patch("app.services.quality_service.get_latest_validation", new_callable=AsyncMock, return_value=None), \
         patch("app.services.quality_service.compute_quality_tier", return_value=None):
        with pytest.raises(ValueError, match="must be validated"):
            await submit_for_verification(
                item_kind="workflow",
                item_id="507f1f77bcf86cd799439011",
                user_id="alice",
            )


@pytest.mark.asyncio
@patch(f"{MODULE}.VerificationRequest")
@patch(f"{MODULE}.SystemConfig")
@patch(f"{MODULE}.Workflow")
async def test_submit_for_verification_gate_min_score_fails(mock_wf_cls, mock_sc, mock_vr_cls):
    from app.services.verification_service import submit_for_verification

    wf = _make_obj()
    mock_wf_cls.get = AsyncMock(return_value=wf)
    mock_vr_cls.find_one = AsyncMock(return_value=None)

    sys_cfg = _make_sys_config({"verification_gates": {"min_score": 90}})
    mock_sc.get_config = AsyncMock(return_value=sys_cfg)

    latest = {
        "result_snapshot": {"test_cases": [1, 2, 3], "num_runs": 5},
        "score": 70,
    }

    with patch("app.services.quality_service.get_latest_validation", new_callable=AsyncMock, return_value=latest), \
         patch("app.services.quality_service.compute_quality_tier", return_value="bronze"):
        with pytest.raises(ValueError, match="Quality score is 70"):
            await submit_for_verification(
                item_kind="workflow",
                item_id="507f1f77bcf86cd799439011",
                user_id="alice",
            )


# ---------------------------------------------------------------------------
# check_and_flag_stale_verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}.VerifiedItemMetadata")
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="My Workflow")
@patch(f"{MODULE}.Workflow")
async def test_check_and_flag_stale_verified_workflow(mock_wf_cls, mock_name, mock_meta_cls):
    from app.services.verification_service import check_and_flag_stale_verification

    wf = _make_obj(verified=True)
    mock_wf_cls.get = AsyncMock(return_value=wf)

    meta = _make_meta(last_validated_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
    mock_meta_cls.find_one = AsyncMock(return_value=meta)

    with patch("app.models.quality_alert.QualityAlert") as mock_qa_cls:
        mock_alert = MagicMock()
        mock_alert.insert = AsyncMock()
        mock_qa_cls.return_value = mock_alert

        result = await check_and_flag_stale_verification("workflow", "507f1f77bcf86cd799439011")

    assert result is True
    assert meta.last_validated_at is None
    meta.save.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.Workflow")
async def test_check_and_flag_stale_not_verified(mock_wf_cls):
    from app.services.verification_service import check_and_flag_stale_verification

    wf = _make_obj(verified=False)
    mock_wf_cls.get = AsyncMock(return_value=wf)

    result = await check_and_flag_stale_verification("workflow", "507f1f77bcf86cd799439011")
    assert result is False


@pytest.mark.asyncio
@patch(f"{MODULE}.Workflow")
async def test_check_and_flag_stale_item_not_found(mock_wf_cls):
    from app.services.verification_service import check_and_flag_stale_verification

    mock_wf_cls.get = AsyncMock(return_value=None)
    result = await check_and_flag_stale_verification("workflow", "507f1f77bcf86cd799439011")
    assert result is False


@pytest.mark.asyncio
async def test_check_and_flag_stale_unknown_kind():
    from app.services.verification_service import check_and_flag_stale_verification

    result = await check_and_flag_stale_verification("unknown_kind", "507f1f77bcf86cd799439011")
    assert result is False


# ---------------------------------------------------------------------------
# _notify_submitter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="Test Item")
async def test_notify_submitter_approved(mock_name):
    from app.services.verification_service import _notify_submitter

    req = _make_verification_request()

    with patch("app.services.notification_service.create_notification", new_callable=AsyncMock) as mock_create:
        await _notify_submitter(req, "approved", "Looks good")

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["kind"] == "verification_approved"
        assert "approved" in call_kwargs["title"].lower()


@pytest.mark.asyncio
@patch(f"{MODULE}._get_item_name", new_callable=AsyncMock, return_value="Test Item")
async def test_notify_submitter_unknown_status_no_op(mock_name):
    from app.services.verification_service import _notify_submitter

    req = _make_verification_request()

    with patch("app.services.notification_service.create_notification", new_callable=AsyncMock) as mock_create:
        await _notify_submitter(req, "some_unknown_status", None)

        mock_create.assert_not_awaited()
