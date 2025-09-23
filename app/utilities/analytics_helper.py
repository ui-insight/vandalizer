import logging
from datetime import datetime, timezone

from app.models import (
    ActivityEvent,
    ActivityStatus,
    ActivityType,
    DailyUsageAggregate,
    Workflow,
    WorkflowResult,
)


def _safe_duration_ms(ev) -> int | None:
    try:
        return ev.duration_ms
    except Exception as e:
        # Log once at warn; don't crash analytics
        logger = logging.getLogger(__name__)
        logger.warning("duration_ms failed for event %s: %s", getattr(ev, "id", "?"), e)
        return None


def _incs_for(ev):
    dur = _safe_duration_ms(ev)
    return {
        "tokens_input": getattr(ev, "tokens_input", 0) or 0,
        "tokens_output": getattr(ev, "tokens_output", 0) or 0,
        "requests": 1,
        "errors": 1 if getattr(ev, "had_error", False) else 0,
        "duration_ms": dur or 0,  # record 0 if unknown instead of crashing
    }


def recent_activity_for_feed(
    user_id: str | None = None, team_id: str | None = None, limit: int = 100
):
    q = ActivityEvent.objects
    print(f"Activites for {user_id} {team_id}")
    if user_id:
        q = q(user_id=user_id)
    return q.order_by("-started_at").limit(limit)


def activity_start(
    *,
    type: ActivityType,
    user_id: str,
    title: str | None = None,
    team_id: str | None = None,
    space: str | None = None,
    conversation_id: str | None = None,
    search_set_uuid: str | None = None,
    workflow: Workflow | None = None,
    workflow_result: WorkflowResult | None = None,
    steps_total: int = 0,
    meta_summary: dict | None = None,
    tags: list[str] | None = None,
) -> ActivityEvent:
    ev = ActivityEvent(
        type=type.value,
        title=title,
        status=ActivityStatus.RUNNING.value,
        user_id=user_id,
        team_id=team_id,
        space=space,
        conversation_id=conversation_id,
        search_set_uuid=search_set_uuid,
        workflow=workflow,
        workflow_result=workflow_result,
        steps_total=steps_total,
        meta_summary=meta_summary or {},
        tags=tags or [],
    )
    ev.save()
    return ev


def activity_progress(
    ev: ActivityEvent,
    *,
    steps_completed: int | None = None,
    message_count_inc: int = 0,
    documents_touched_inc: int = 0,
    tokens_in_inc: int = 0,
    tokens_out_inc: int = 0,
    meta_updates: dict | None = None,
):
    if steps_completed is not None:
        ev.steps_completed = steps_completed
    if message_count_inc:
        ev.message_count += message_count_inc
    if documents_touched_inc:
        ev.documents_touched += documents_touched_inc
    if tokens_in_inc:
        ev.tokens_input += tokens_in_inc
    if tokens_out_inc:
        ev.tokens_output += tokens_out_inc
    if meta_updates:
        ev.meta_summary.update(meta_updates)
    ev.save()


def activity_finish(
    ev: ActivityEvent,
    *,
    status: ActivityStatus = ActivityStatus.COMPLETED,
    error: str | None = None,
):
    ev.status = status.value
    ev.finished_at = datetime.now(timezone.utc)
    if error:
        ev.error = error[:2000]
    ev.save()
    # Also push to daily aggregates (see below)
    rollup_event_to_daily_aggregates(ev)


def _agg_key(ev: ActivityEvent):
    day = ev.finished_at.date() if ev.finished_at else datetime.now(timezone.utc).date()
    # emit 3 scopes to support user, team, and global dashboards
    keys = [{"date": day, "scope": "global"}]
    if ev.user_id:
        keys.append({"date": day, "scope": "user", "user_id": ev.user_id})
    if ev.team_id:
        keys.append({"date": day, "scope": "team", "team_id": ev.team_id})
    return keys


def _incs_for(ev: ActivityEvent) -> dict:
    inc = {
        "tokens_input": ev.tokens_input or 0,
        "tokens_output": ev.tokens_output or 0,
        "documents_touched": ev.documents_touched or 0,
        "conversation_messages": ev.message_count or 0,
    }
    if ev.type == ActivityType.CONVERSATION.value:
        inc["conversations"] = 1
    elif ev.type == ActivityType.SEARCH_SET_RUN.value:
        inc["searches"] = 1
    elif ev.type == ActivityType.WORKFLOW_RUN.value:
        inc["workflows_started"] = 1
        if ev.status == ActivityStatus.COMPLETED.value:
            inc["workflows_completed"] = 1
            if ev.duration_ms:
                inc["workflow_duration_ms"] = ev.duration_ms
        elif ev.status == ActivityStatus.FAILED.value:
            inc["workflows_failed"] = 1
    return inc


def rollup_event_to_daily_aggregates(ev: ActivityEvent):
    for key in _agg_key(ev):
        doc = DailyUsageAggregate.objects(**key).modify(
            upsert=True,
            new=True,
            set__updated_at=datetime.now(timezone.utc),
            inc__tokens_input=_incs_for(ev).get("tokens_input", 0),
            inc__tokens_output=_incs_for(ev).get("tokens_output", 0),
            inc__documents_touched=_incs_for(ev).get("documents_touched", 0),
            inc__conversation_messages=_incs_for(ev).get("conversation_messages", 0),
            inc__conversations=_incs_for(ev).get("conversations", 0),
            inc__searches=_incs_for(ev).get("searches", 0),
            inc__workflows_started=_incs_for(ev).get("workflows_started", 0),
            inc__workflows_completed=_incs_for(ev).get("workflows_completed", 0),
            inc__workflows_failed=_incs_for(ev).get("workflows_failed", 0),
            inc__workflow_duration_ms=_incs_for(ev).get("workflow_duration_ms", 0),
        )
        # ensure created_at on first upsert
        if not doc.created_at:
            doc.update(set__created_at=datetime.now(timezone.utc))
