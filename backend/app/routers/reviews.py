"""Review (workflow approval) endpoints — user-facing replacement for /api/approvals.

Approvals are work assigned to specific reviewers, not platform administration,
so this router exposes them under /api/reviews and authorizes against the
assigned reviewer / workflow manager — not the global admin flag.
"""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.approval import (
    ApprovalRequest,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from app.models.document import SmartDocument
from app.models.user import User
from app.models.workflow import Workflow, WorkflowResult
from app.services import access_control, audit_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------


class ApproveRequestBody(BaseModel):
    comments: str = ""
    edited_artifact: Optional[dict] = None  # reviewer's edits, if any


class RejectRequestBody(BaseModel):
    comments: str = ""


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _approval_summary(a: ApprovalRequest) -> dict:
    """Compact shape used by list views."""
    return {
        "uuid": a.uuid,
        "workflow_id": str(a.workflow_id),
        "workflow_name": a.workflow_name,
        "step_name": a.step_name,
        "status": a.status,
        "assigned_to_user_ids": a.assigned_to_user_ids,
        "assignee_role": a.assignee_role,
        "requester_user_id": a.requester_user_id,
        "team_id": a.team_id,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "decision_at": a.decision_at.isoformat() if a.decision_at else None,
        "escalated_at": a.escalated_at.isoformat() if a.escalated_at else None,
    }


async def _approval_full(a: ApprovalRequest) -> dict:
    """Detail shape: includes context, artifact, and source-doc metadata."""
    summary = _approval_summary(a)

    # Source documents (titles for the reviewer to know what they're reviewing)
    source_docs: list[dict] = []
    if a.source_doc_uuids:
        docs = await SmartDocument.find(
            {"uuid": {"$in": a.source_doc_uuids}},
        ).to_list()
        source_docs = [
            {"uuid": d.uuid, "title": d.title or d.filename or d.uuid}
            for d in docs
        ]

    # Requester display name
    requester = None
    if a.requester_user_id:
        u = await User.find_one(User.user_id == a.requester_user_id)
        if u:
            requester = {"user_id": u.user_id, "name": u.name, "email": u.email}

    return {
        **summary,
        "step_index": a.step_index,
        "review_instructions": a.review_instructions,
        "artifact_kind": a.artifact_kind,
        "data_for_review": a.data_for_review,
        "edited_artifact": a.edited_artifact,
        "timeout_action": a.timeout_action,
        "escalation_user_ids": a.escalation_user_ids,
        "reviewer_user_id": a.reviewer_user_id,
        "reviewer_comments": a.reviewer_comments,
        "expired_at": a.expired_at.isoformat() if a.expired_at else None,
        "source_docs": source_docs,
        "requester": requester,
    }


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def _can_view_approval(approval: ApprovalRequest, user: User) -> bool:
    """User can see this review if assigned, or if they manage the workflow."""
    if user.user_id in (approval.assigned_to_user_ids or []):
        return True
    if user.user_id == approval.requester_user_id:
        return True
    # Workflow manage rights (covers team admins on team-scoped workflows)
    workflow = await access_control.get_authorized_workflow(
        str(approval.workflow_id), user, manage=True,
    )
    if workflow is not None:
        return True
    # Global admins keep visibility for support/debugging
    return bool(getattr(user, "is_admin", False))


async def _can_decide_approval(approval: ApprovalRequest, user: User) -> bool:
    """Only assigned reviewers (or workflow managers) can approve/reject."""
    if user.user_id in (approval.assigned_to_user_ids or []):
        return True
    workflow = await access_control.get_authorized_workflow(
        str(approval.workflow_id), user, manage=True,
    )
    return workflow is not None


# ---------------------------------------------------------------------------
# List endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_my_reviews(
    status: Optional[str] = Query(None, description="pending | approved | rejected | expired | all"),
    user: User = Depends(get_current_user),
):
    """Reviews assigned to the current user."""
    query: dict = {"assigned_to_user_ids": user.user_id}
    if status and status != "all":
        query["status"] = status
    else:
        # Default: show pending only on the inbox
        if status is None:
            query["status"] = STATUS_PENDING

    approvals = (
        await ApprovalRequest.find(query)
        .sort(-ApprovalRequest.created_at)
        .to_list()
    )
    return {"reviews": [_approval_summary(a) for a in approvals]}


@router.get("/team")
async def list_team_reviews(
    team_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    """All pending approvals on workflows owned by a team the user manages.

    Defaults to the user's current_team. Returns 403 if the user isn't a team
    manager (owner/admin) of the requested team.
    """
    target_team = team_id or (str(user.current_team) if user.current_team else None)
    if not target_team:
        return {"reviews": []}

    team_access = await access_control.get_team_access_context(user)
    if not access_control.can_manage_team(target_team, team_access):
        raise HTTPException(status_code=403, detail="Not authorized for this team")

    query: dict = {"team_id": target_team}
    if status and status != "all":
        query["status"] = status
    else:
        query["status"] = STATUS_PENDING

    approvals = (
        await ApprovalRequest.find(query)
        .sort(-ApprovalRequest.created_at)
        .to_list()
    )
    return {"reviews": [_approval_summary(a) for a in approvals]}


@router.get("/count")
async def my_review_count(user: User = Depends(get_current_user)):
    """Pending count for the bell badge."""
    count = await ApprovalRequest.find(
        ApprovalRequest.status == STATUS_PENDING,
        {"assigned_to_user_ids": user.user_id},
    ).count()
    return {"count": count}


# ---------------------------------------------------------------------------
# Detail + decision endpoints
# ---------------------------------------------------------------------------


@router.get("/{approval_uuid}")
async def get_review(approval_uuid: str, user: User = Depends(get_current_user)):
    approval = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval_uuid)
    if not approval:
        raise HTTPException(status_code=404, detail="Review not found")
    if not await _can_view_approval(approval, user):
        raise HTTPException(status_code=404, detail="Review not found")
    return await _approval_full(approval)


@router.post("/{approval_uuid}/approve")
async def approve_review(
    approval_uuid: str,
    body: ApproveRequestBody,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    approval = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval_uuid)
    if not approval:
        raise HTTPException(status_code=404, detail="Review not found")
    if approval.status != STATUS_PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot approve: status is {approval.status}")
    if not await _can_decide_approval(approval, user):
        raise HTTPException(status_code=403, detail="Not authorized to decide this review")

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    approval.status = STATUS_APPROVED
    approval.reviewer_user_id = user.user_id
    approval.reviewer_comments = body.comments
    approval.decision_at = now
    if body.edited_artifact is not None:
        approval.edited_artifact = body.edited_artifact
    await approval.save()

    # Resume the workflow
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
        detail={
            "workflow_result_id": str(approval.workflow_result_id),
            "comments": body.comments,
            "edited": body.edited_artifact is not None,
        },
    )

    await _notify_owner(approval, "approved", user, settings)
    return {"detail": "Approved, workflow resuming"}


@router.post("/{approval_uuid}/reject")
async def reject_review(
    approval_uuid: str,
    body: RejectRequestBody,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    approval = await ApprovalRequest.find_one(ApprovalRequest.uuid == approval_uuid)
    if not approval:
        raise HTTPException(status_code=404, detail="Review not found")
    if approval.status != STATUS_PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot reject: status is {approval.status}")
    if not await _can_decide_approval(approval, user):
        raise HTTPException(status_code=403, detail="Not authorized to decide this review")

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    approval.status = STATUS_REJECTED
    approval.reviewer_user_id = user.user_id
    approval.reviewer_comments = body.comments
    approval.decision_at = now
    await approval.save()

    # Mark workflow result failed
    result = await WorkflowResult.get(approval.workflow_result_id)
    if result:
        result.status = "failed"
        result.current_step_detail = f"Rejected by reviewer: {body.comments}" if body.comments else "Rejected by reviewer"
        await result.save()

    await audit_service.log_event(
        action="workflow.reject",
        actor_user_id=user.user_id,
        resource_type="approval",
        resource_id=approval_uuid,
        detail={"workflow_result_id": str(approval.workflow_result_id), "comments": body.comments},
    )

    await _notify_owner(approval, "rejected", user, settings)
    return {"detail": "Rejected, workflow failed"}


# ---------------------------------------------------------------------------
# Owner notification on resolution
# ---------------------------------------------------------------------------


async def _notify_owner(
    approval: ApprovalRequest, decision: str, reviewer: User, settings: Settings,
) -> None:
    from app.services.notification_service import create_notification
    from app.services.email_service import approval_resolved_email, send_email

    workflow = await Workflow.get(approval.workflow_id)
    workflow_name = workflow.name if workflow else (approval.workflow_name or "Workflow")
    owner_user_id = workflow.user_id if workflow else approval.requester_user_id
    if not owner_user_id:
        return

    await create_notification(
        user_id=owner_user_id,
        kind=f"approval_{decision}",
        title=f"Workflow {decision}: {workflow_name}",
        body=f"{reviewer.name or reviewer.user_id} {decision} the approval."
             + (f" Comments: {approval.reviewer_comments}" if approval.reviewer_comments else ""),
        link=f"/reviews/{approval.uuid}",
        item_kind="approval",
        item_id=approval.uuid,
    )

    owner = await User.find_one(User.user_id == owner_user_id)
    if owner and owner.email:
        subject, html = approval_resolved_email(
            owner_name=owner.name or owner.user_id,
            workflow_name=workflow_name,
            decision=decision,
            reviewer_name=reviewer.name or reviewer.user_id,
            comments=approval.reviewer_comments,
            frontend_url=settings.frontend_url,
        )
        await send_email(owner.email, subject, html, settings, email_type="approval_resolved")
