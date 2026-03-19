"""Approval request endpoints for workflow review gates."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.approval import ApprovalRequest
from app.models.user import User
from app.models.workflow import WorkflowResult
from app.services import access_control
from app.services import audit_service

router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    comments: str = ""


def _approval_to_dict(a: ApprovalRequest) -> dict:
    return {
        "uuid": a.uuid,
        "workflow_result_id": str(a.workflow_result_id),
        "workflow_id": str(a.workflow_id),
        "step_index": a.step_index,
        "step_name": a.step_name,
        "data_for_review": a.data_for_review,
        "review_instructions": a.review_instructions,
        "status": a.status,
        "assigned_to_user_ids": a.assigned_to_user_ids,
        "reviewer_user_id": a.reviewer_user_id,
        "reviewer_comments": a.reviewer_comments,
        "decision_at": a.decision_at.isoformat() if a.decision_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _can_access_approval(approval: ApprovalRequest, user: User) -> bool:
    if user.is_admin:
        return True
    if user.user_id in (approval.assigned_to_user_ids or []):
        return True
    workflow = await access_control.get_authorized_workflow(
        str(approval.workflow_id),
        user,
        manage=True,
    )
    return workflow is not None


@router.get("/")
async def list_approvals(
    status: Optional[str] = "pending",
    user: User = Depends(get_current_user),
):
    """List approval requests, optionally filtered by status."""
    filters = {}
    if status:
        filters["status"] = status

    approvals = await ApprovalRequest.find(
        filters
    ).sort(-ApprovalRequest.created_at).to_list()
    if not user.is_admin:
        approvals = [a for a in approvals if await _can_access_approval(a, user)]

    return {"approvals": [_approval_to_dict(a) for a in approvals]}


@router.get("/count")
async def approval_count(user: User = Depends(get_current_user)):
    """Get count of pending approvals for badge display."""
    approvals = await ApprovalRequest.find(ApprovalRequest.status == "pending").to_list()
    if not user.is_admin:
        approvals = [a for a in approvals if await _can_access_approval(a, user)]
    return {"count": len(approvals)}


@router.get("/{approval_uuid}")
async def get_approval(approval_uuid: str, user: User = Depends(get_current_user)):
    approval = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval_uuid)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if not await _can_access_approval(approval, user):
        raise HTTPException(status_code=404, detail="Approval request not found")
    return _approval_to_dict(approval)


@router.post("/{approval_uuid}/approve")
async def approve_request(
    approval_uuid: str,
    body: ApprovalDecisionRequest,
    user: User = Depends(get_current_user),
):
    """Approve a pending request and resume the workflow."""
    approval = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval_uuid)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve: status is {approval.status}")

    if not await _can_access_approval(approval, user):
        raise HTTPException(status_code=403, detail="Not authorized to review this approval")

    approval.status = "approved"
    approval.reviewer_user_id = user.user_id
    approval.reviewer_comments = body.comments
    approval.decision_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await approval.save()

    # Resume workflow
    from app.celery_app import celery
    celery.send_task(
        "tasks.workflow.resume_after_approval",
        kwargs={"approval_uuid": approval_uuid},
        queue="workflows",
    )

    await audit_service.log_event(
        action="workflow.approve",
        actor_user_id=user.user_id,
        resource_type="approval",
        resource_id=approval_uuid,
        detail={"workflow_result_id": str(approval.workflow_result_id), "comments": body.comments},
    )

    return {"detail": "Approved, workflow resuming"}


@router.post("/{approval_uuid}/reject")
async def reject_request(
    approval_uuid: str,
    body: ApprovalDecisionRequest,
    user: User = Depends(get_current_user),
):
    """Reject a pending request and fail the workflow."""
    approval = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval_uuid)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot reject: status is {approval.status}")

    if not await _can_access_approval(approval, user):
        raise HTTPException(status_code=403, detail="Not authorized to review this approval")

    approval.status = "rejected"
    approval.reviewer_user_id = user.user_id
    approval.reviewer_comments = body.comments
    approval.decision_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await approval.save()

    # Mark workflow as failed
    result = await WorkflowResult.get(approval.workflow_result_id)
    if result:
        result.status = "failed"
        result.current_step_detail = f"Rejected by reviewer: {body.comments}"
        await result.save()

    await audit_service.log_event(
        action="workflow.reject",
        actor_user_id=user.user_id,
        resource_type="approval",
        resource_id=approval_uuid,
        detail={"workflow_result_id": str(approval.workflow_result_id), "comments": body.comments},
    )

    return {"detail": "Rejected, workflow failed"}
