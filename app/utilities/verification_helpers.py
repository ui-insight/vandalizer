"""Helpers for working with verified objects and examiner permissions."""

from __future__ import annotations
from devtools import debug

from typing import Optional, Tuple

from flask_login import AnonymousUserMixin

import hashlib
import json
import datetime
from app.models import (
    Workflow, VerificationRequest, VerificationStatus, 
    Library, LibraryItem, LibraryScope
)

from app.models import (
    SearchSet,
    SearchSetItem,
    VerificationRequest,
    VerificationStatus,
    Workflow,
)


def _kind_and_identifier_for_obj(obj) -> Tuple[Optional[str], Optional[str]]:
    """Return the verification kind/identifier pair for a supported object."""
    if isinstance(obj, Workflow):
        return "workflow", str(obj.id)
    if isinstance(obj, SearchSet):
        return "searchset", obj.uuid
    if isinstance(obj, SearchSetItem):
        search_type = (obj.searchtype or "").lower()
        if search_type == "prompt":
            return "prompt", str(obj.id)
        if search_type == "formatter":
            return "formatter", str(obj.id)
    return None, None


def is_obj_verified(obj) -> bool:
    """Return True when the object has been verified."""
    if obj is None:
        return False

    if hasattr(obj, "verified"):
        return bool(getattr(obj, "verified", False))

    kind, identifier = _kind_and_identifier_for_obj(obj)
    if not kind or not identifier:
        return False

    return (
        VerificationRequest.objects(
            item_kind=kind,
            item_identifier=identifier,
            status=VerificationStatus.APPROVED,
        ).first()
        is not None
    )


def user_can_modify_verified(user, obj) -> bool:
    """
    Return True when the provided user may change the object.

    Non-examiners are blocked when the object is verified.
    """
    if obj is None:
        return False

    if not is_obj_verified(obj):
        return True

    if user is None:
        return False

    if isinstance(user, AnonymousUserMixin):
        return False

    return bool(getattr(user, "is_examiner", False))


def calculate_workflow_hash(workflow: Workflow) -> str:
    # (Hash calculation logic remains the same)
    data_to_hash = {
        "steps": [json.loads(step.to_json()) for step in workflow.steps],
        "attachments": [str(att.id) for att in workflow.attachments],
        "name": workflow.name
    }
    dump = json.dumps(data_to_hash, sort_keys=True)
    return hashlib.sha256(dump.encode()).hexdigest()

def process_verification_approval(request_uuid: str, approver_user_id: str):
    """
    The atomic logic to finalize verification.
    """
    try:
        req = VerificationRequest.objects(uuid=request_uuid).first()
        
        # === FIX STARTS HERE ===
        # Allow 'IN_REVIEW' because the admin route sets this status 
        # right before dispatching the Celery task.
        allowed_statuses = [VerificationStatus.SUBMITTED, VerificationStatus.IN_REVIEW]
        
        if not req or req.status not in allowed_statuses:
            current_status = req.status.value if req and req.status else "None"
            return {"success": False, "error": f"Invalid request state: {current_status}"}
        # === FIX ENDS HERE ===

        # 1. Fetch the actual Workflow
        workflow = Workflow.objects(id=req.item_identifier).first()
        if not workflow:
            return {"success": False, "error": "Workflow no longer exists"}

        # 2. Check Integrity
        current_hash = calculate_workflow_hash(workflow)
        # Handle cases where item_version_hash might be None (legacy data)
        if req.item_version_hash and current_hash != req.item_version_hash:
            req.status = VerificationStatus.REJECTED
            req.evaluation_notes = "Hash mismatch: Workflow was modified after submission."
            req.save()
            return {"success": False, "error": "Hash mismatch - Workflow modified during review"}

        # 3. Update Request Status to APPROVED
        req.status = VerificationStatus.APPROVED
        req.updated_at = datetime.datetime.now(datetime.timezone.utc)
        req.save()

        # 4. Update Workflow Status
        workflow.verified = True
        workflow.save()

        # 5. Add to Global Verified Library
        verified_lib = Library.objects(scope=LibraryScope.VERIFIED).first()
        if not verified_lib:
            verified_lib = Library(
                scope=LibraryScope.VERIFIED, 
                title="Global Verified Library"
            ).save()

        existing_item = LibraryItem.objects(
            obj=workflow, 
            kind='workflow', 
            verified=True
        ).first()

        if not existing_item:
            item = LibraryItem(
                obj=workflow,
                kind='workflow',
                added_by_user_id=req.submitter_user_id,
                verified=True,
                verified_at=datetime.datetime.now(datetime.timezone.utc),
                verified_by_user_id=approver_user_id,
                note=req.summary
            ).save()
            verified_lib.update(push__items=item)
        
        return {"success": True}

    except Exception as e:
        print(f"Verification Logic Error: {e}")
        return {"success": False, "error": str(e)}
