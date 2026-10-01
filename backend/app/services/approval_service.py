"""Approval lifecycle service.

Handles:
- Resolving assignee role (specific_users / workflow_owner / team_admins) → user IDs.
- Detecting the kind of artifact under review so the UI can render it nicely.
- Async timeout sweeper that fires the configured timeout_action on expired
  pending approvals (run via Celery beat).
"""

from __future__ import annotations

import datetime
import logging
from typing import Iterable, Optional

from beanie import PydanticObjectId

from app.models.approval import (
    ARTIFACT_DOCUMENT_RENDER,
    ARTIFACT_EXTRACTION_TABLE,
    ARTIFACT_JSON,
    ARTIFACT_MARKDOWN,
    ARTIFACT_TEXT,
    ARTIFACT_UNKNOWN,
    ASSIGNEE_SPECIFIC_USERS,
    ASSIGNEE_TEAM_ADMINS,
    ASSIGNEE_WORKFLOW_OWNER,
    ApprovalRequest,
    STATUS_APPROVED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_REJECTED,
    TIMEOUT_APPROVE,
    TIMEOUT_ESCALATE,
    TIMEOUT_NONE,
    TIMEOUT_REJECT,
)
from app.models.team import TeamMembership
from app.models.workflow import Workflow, WorkflowResult

logger = logging.getLogger(__name__)


async def update_pending_approval(
    approval: ApprovalRequest, changes: dict, *, allow_expired: bool = False,
) -> bool:
    """Claim a pending transition before dispatching any of its side effects.

    Assignment and deadline are part of the comparison so a stale reviewer or
    timeout sweep cannot overwrite a reassignment, extension, or other decision.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    deadline = approval.expires_at
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=datetime.timezone.utc)
    if not allow_expired and deadline and deadline <= now:
        return False
    result = await ApprovalRequest.get_motor_collection().update_one(
        {
            "_id": approval.id,
            "status": STATUS_PENDING,
            "assigned_to_user_ids": approval.assigned_to_user_ids,
            "expires_at": approval.expires_at,
        },
        {"$set": changes},
    )
    if result.modified_count != 1:
        return False
    for key, value in changes.items():
        setattr(approval, key, value)
    return True


# ---------------------------------------------------------------------------
# Assignee resolution
# ---------------------------------------------------------------------------


async def resolve_assignees(
    role: str,
    workflow: Workflow,
    explicit_user_ids: Optional[Iterable[str]] = None,
) -> list[str]:
    """Convert an `assignee_role` into a concrete list of reviewer user IDs.

    Resolution happens at pause time so changes to team membership after the
    workflow was authored are picked up automatically.
    """
    if role == ASSIGNEE_SPECIFIC_USERS:
        return list(explicit_user_ids or [])

    if role == ASSIGNEE_WORKFLOW_OWNER:
        return [workflow.user_id] if workflow.user_id else []

    if role == ASSIGNEE_TEAM_ADMINS:
        if not workflow.team_id:
            # Fall back to the workflow owner if the workflow isn't team-scoped.
            return [workflow.user_id] if workflow.user_id else []
        try:
            team_oid = PydanticObjectId(workflow.team_id)
        except Exception:
            return [workflow.user_id] if workflow.user_id else []
        memberships = await TeamMembership.find(
            TeamMembership.team == team_oid,
        ).to_list()
        admins = [m.user_id for m in memberships if m.role in ("owner", "admin")]
        return admins or ([workflow.user_id] if workflow.user_id else [])

    # Unknown role — be safe and fall back to workflow owner
    logger.warning("Unknown assignee_role %r — defaulting to workflow owner", role)
    return [workflow.user_id] if workflow.user_id else []


def resolve_assignees_sync(db, role: str, workflow_doc: dict, explicit_user_ids: list[str]) -> list[str]:
    """Sync variant for use inside Celery tasks (pymongo handle).

    Mirrors `resolve_assignees` but uses sync pymongo so the Celery worker
    doesn't have to spin up an event loop.
    """
    from bson import ObjectId

    user_id = workflow_doc.get("user_id")
    team_id = workflow_doc.get("team_id")

    if role == ASSIGNEE_SPECIFIC_USERS:
        return list(explicit_user_ids or [])

    if role == ASSIGNEE_WORKFLOW_OWNER:
        return [user_id] if user_id else []

    if role == ASSIGNEE_TEAM_ADMINS:
        if not team_id:
            return [user_id] if user_id else []
        try:
            team_oid = ObjectId(team_id)
        except Exception:
            return [user_id] if user_id else []
        memberships = list(db.team_membership.find({"team": team_oid}))
        admins = [m.get("user_id") for m in memberships if m.get("role") in ("owner", "admin")]
        admins = [a for a in admins if a]
        return admins or ([user_id] if user_id else [])

    logger.warning("Unknown assignee_role %r — defaulting to workflow owner", role)
    return [user_id] if user_id else []


# ---------------------------------------------------------------------------
# Artifact kind detection
# ---------------------------------------------------------------------------


def detect_artifact_kind(value) -> str:
    """Best-effort guess at the renderer to use on the review screen.

    The output of the previous step can be almost anything. We try to identify
    common shapes the workflow engine produces so the reviewer sees a useful
    rendering (table, document preview, markdown) rather than raw JSON.
    """
    if value is None:
        return ARTIFACT_UNKNOWN

    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("#", "- ", "* ", "**", "> ")) or "\n##" in value:
            return ARTIFACT_MARKDOWN
        return ARTIFACT_TEXT

    if isinstance(value, dict):
        # A document-render task emits {"type": "file_download", ...}
        if value.get("type") == "file_download":
            return ARTIFACT_DOCUMENT_RENDER
        # An extraction node emits {"<key>": "<value>", ...} of strings
        if value and all(isinstance(v, (str, int, float, type(None))) for v in value.values()):
            return ARTIFACT_EXTRACTION_TABLE
        return ARTIFACT_JSON

    if isinstance(value, list):
        # A list of dicts that look like extraction rows
        if value and all(isinstance(item, dict) for item in value):
            sample = value[0]
            if all(isinstance(v, (str, int, float, type(None))) for v in sample.values()):
                return ARTIFACT_EXTRACTION_TABLE
        return ARTIFACT_JSON

    return ARTIFACT_UNKNOWN


# ---------------------------------------------------------------------------
# Timeout sweeper (called from Celery beat)
# ---------------------------------------------------------------------------


async def end_approval_wait(
    workflow_result_id: PydanticObjectId,
    *,
    approval_uuid: str | None = None,
    error: str = "",
) -> None:
    """Take a run's activity out of its approval wait, closing it if it ended.

    ``_pause_for_approval`` stamps ``meta_summary.pending_review_uuid`` on the
    ActivityEvent while a run waits on a reviewer, and the stale reaper skips
    rows carrying it. So every path that ends the wait has to clear it — and a
    rejected or expired review ends the *run*, which the activity never learned
    about: it was left at "running" and only the reaper ever closed it. Passing
    ``error`` closes the row too, so the rail agrees with the WorkflowResult.

    Two things make a batch different, and both are handled here.

    A batch shares one ActivityEvent across every document
    (``run_workflow_batch`` hands the same ``activity_id`` to all of them), and
    ``_pause_for_approval`` overwrites ``workflow_result`` on each pause. So
    matching on ``workflow_result`` finds the row only for whichever document
    paused last, and misses entirely for the others — leaving the marker in
    place, and with it a row the reaper will never touch. Matching on the
    approval's own uuid finds exactly the row that is waiting on *this* review,
    for a batch and a single run alike.

    And one document's rejection is not the batch's failure. Where several runs
    share a row, the wait is ended without closing it, so the documents still
    running keep their row; the ``WorkflowResult`` for the rejected one is
    already marked by the caller.

    Never raises: a review decision must not fail because a bookkeeping write
    on the activity did.
    """
    from app.models.activity import ActivityEvent, ActivityStatus

    now = datetime.datetime.now(datetime.timezone.utc)
    update: dict = {"$unset": {"meta_summary.pending_review_uuid": ""}}
    set_ops: dict = {"last_updated_at": now}

    try:
        shared_with_a_batch = await _is_batch_run(workflow_result_id)
    except Exception:  # pragma: no cover - defensive
        shared_with_a_batch = False

    if error and not shared_with_a_batch:
        set_ops.update({
            "status": ActivityStatus.FAILED.value,
            "finished_at": now,
            "error": error,
        })
    update["$set"] = set_ops

    # Prefer the approval's own uuid; fall back to the run for callers that
    # have no approval in hand.
    query: dict = (
        {"meta_summary.pending_review_uuid": approval_uuid}
        if approval_uuid
        else {"workflow_result": workflow_result_id}
    )

    try:
        await ActivityEvent.get_motor_collection().update_one(query, update)
    except Exception:
        logger.exception(
            "Could not end approval wait on activity for result %s", workflow_result_id,
        )


async def _is_batch_run(workflow_result_id: PydanticObjectId) -> bool:
    """True when this run is one document of a batch sharing an activity row."""
    from app.models.workflow import WorkflowResult

    result = await WorkflowResult.get(workflow_result_id)
    return bool(result and result.batch_id)


async def expire_overdue_approvals() -> dict:
    """Find pending approvals past their expires_at and apply timeout_action.

    Returns a counts dict so the periodic task can log progress.
    """
    from app.services.audit_service import log_event
    from app.services import notification_service
    from app.celery_app import celery

    now = datetime.datetime.now(datetime.timezone.utc)
    overdue = await ApprovalRequest.find(
        ApprovalRequest.status == STATUS_PENDING,
        ApprovalRequest.expires_at != None,  # noqa: E711
        ApprovalRequest.expires_at < now,
    ).to_list()

    counts = {"approved": 0, "rejected": 0, "escalated": 0, "expired": 0, "skipped": 0}
    for approval in overdue:
        action = approval.timeout_action or TIMEOUT_NONE

        if action == TIMEOUT_APPROVE:
            changes = {"status": STATUS_APPROVED, "decision_at": now, "reviewer_comments": "Auto-approved on timeout"}
        elif action == TIMEOUT_REJECT:
            changes = {"status": STATUS_REJECTED, "decision_at": now, "reviewer_comments": "Auto-rejected on timeout"}
        elif action == TIMEOUT_ESCALATE:
            changes = {
                "status": STATUS_PENDING, "escalated_at": now,
                "assigned_to_user_ids": list(set(approval.assigned_to_user_ids + approval.escalation_user_ids)),
                "expires_at": now + datetime.timedelta(days=2), "timeout_action": TIMEOUT_NONE,
            }
        elif action == TIMEOUT_NONE:
            changes = {"status": STATUS_EXPIRED, "expired_at": now}
        else:
            counts["skipped"] += 1
            logger.warning("Unknown timeout_action %r on approval %s", action, approval.uuid)
            continue
        if not await update_pending_approval(approval, changes, allow_expired=True):
            counts["skipped"] += 1
            continue

        if action == TIMEOUT_APPROVE:
            celery.send_task(
                "tasks.workflow.resume_after_approval",
                kwargs={"approval_uuid": approval.uuid},
                queue="workflows",
            )
            counts["approved"] += 1
            await log_event(
                action="workflow.approval_timeout_approved",
                actor_user_id="system",
                resource_type="approval",
                resource_id=approval.uuid,
                detail={"workflow_result_id": str(approval.workflow_result_id)},
            )

        elif action == TIMEOUT_REJECT:
            result = await WorkflowResult.get(approval.workflow_result_id)
            if result:
                result.status = "failed"
                result.current_step_detail = "Auto-rejected: review deadline passed"
                await result.save()
            await end_approval_wait(
                approval.workflow_result_id,
                approval_uuid=approval.uuid,
                error="Auto-rejected: review deadline passed.",
            )
            counts["rejected"] += 1
            await log_event(
                action="workflow.approval_timeout_rejected",
                actor_user_id="system",
                resource_type="approval",
                resource_id=approval.uuid,
                detail={"workflow_result_id": str(approval.workflow_result_id)},
            )

        elif action == TIMEOUT_ESCALATE:
            for uid in approval.escalation_user_ids:
                await notification_service.create_notification(
                    user_id=uid,
                    kind="approval_escalated",
                    title=f"Escalated: {approval.workflow_name or 'Workflow'}",
                    body=(
                        f"An approval for step \"{approval.step_name}\" was not "
                        "actioned in time and has been escalated to you."
                    ),
                    link=f"/reviews/{approval.uuid}",
                    item_kind="approval",
                    item_id=approval.uuid,
                )
            counts["escalated"] += 1
            await log_event(
                action="workflow.approval_escalated",
                actor_user_id="system",
                resource_type="approval",
                resource_id=approval.uuid,
                detail={"escalated_to": approval.escalation_user_ids},
            )

        elif action == TIMEOUT_NONE:
            # Just mark expired — workflow stays paused; humans must act.
            # The activity, though, has to stop reading as in-flight: no one can
            # decide an expired review, so the run is not going to move on its
            # own and the rail would spin on it indefinitely.
            await end_approval_wait(
                approval.workflow_result_id,
                approval_uuid=approval.uuid,
                error="Review deadline passed with no decision — run is still paused.",
            )
            counts["expired"] += 1

    if any(counts.values()):
        logger.info("Approval timeout sweep: %s", counts)
    return counts
