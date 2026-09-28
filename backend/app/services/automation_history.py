"""Bounded history pages across persisted workflow and extraction events."""
import datetime

from bson import ObjectId

from app.models.passive import ExtractionTriggerEvent, WorkflowTriggerEvent


def _utc(value: datetime.datetime) -> datetime.datetime:
    return value.replace(tzinfo=datetime.timezone.utc) if value.tzinfo is None else value.astimezone(datetime.timezone.utc)


async def list_runs(automation_id: str, limit: int, before: datetime.datetime | None = None, before_id: str | None = None) -> dict:
    rows = []
    for model, field, action_type in (
        (WorkflowTriggerEvent, "trigger_context.automation_id", "workflow"),
        (ExtractionTriggerEvent, "automation_id", "extraction"),
    ):
        query: dict = {field: automation_id}
        if before is not None and before_id is not None:
            query["$or"] = [
                {"created_at": {"$lt": before}},
                {"created_at": before, "_id": {"$lt": ObjectId(before_id)}},
            ]
        # Existing compound indexes cover scope + created_at + _id. Exclude
        # potentially large outputs; the authorized detail endpoint loads them.
        pipeline = [
            {"$match": query},
            {"$sort": {"created_at": -1, "_id": -1}},
            {"$limit": limit + 1},
            {"$project": {"_id": 1, "status": 1, "created_at": 1, "started_at": 1, "completed_at": 1, "error": 1}},
        ]
        for event in await model.aggregate(pipeline).to_list():
            rows.append({
                "trigger_event_id": str(event["_id"]),
                "action_type": action_type,
                "status": event["status"],
                "created_at": _utc(event["created_at"]).isoformat(),
                "started_at": _utc(event["started_at"]).isoformat() if event.get("started_at") else None,
                "completed_at": _utc(event["completed_at"]).isoformat() if event.get("completed_at") else None,
                "error": event.get("error"),
            })
    rows.sort(key=lambda row: (row["created_at"], row["trigger_event_id"]), reverse=True)
    page = rows[:limit]
    last = page[-1] if len(rows) > limit else None
    return {
        "items": page,
        "next_cursor": {"before": last["created_at"], "before_id": last["trigger_event_id"]} if last else None,
    }
