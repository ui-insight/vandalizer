"""Owner-scoped quality notices and evidence for the workspace home."""
from typing import Literal

from bson.errors import InvalidId
from fastapi import HTTPException
from pydantic import BaseModel

from app.models.quality_alert import QualityAlert
from app.models.search_set import SearchSet
from app.models.workflow import Workflow
from app.models.user import User
from app.schemas.config import ActiveAlertItem


def alert_item(alert: QualityAlert) -> ActiveAlertItem:
    return ActiveAlertItem(
        uuid=alert.uuid, message=alert.message, severity=alert.severity,
        item_name=alert.item_name, item_kind=alert.item_kind, item_id=alert.item_id,
        alert_type=alert.alert_type, previous_score=alert.previous_score,
        current_score=alert.current_score, created_at=alert.created_at,
        review_state="acknowledged" if alert.acknowledged else alert.review_state,
    )


async def owned_alert(uuid: str, user: User) -> QualityAlert:
    alert = await QualityAlert.find_one({"uuid": uuid})
    if alert is None:
        raise HTTPException(404, "Quality notice not found")
    if alert.item_kind == "search_set":
        item = await SearchSet.find_one({"uuid": alert.item_id, "user_id": user.user_id})
    elif alert.item_kind == "workflow":
        from beanie import PydanticObjectId
        try:
            oid = PydanticObjectId(alert.item_id)
        except (ValueError, TypeError, InvalidId):
            raise HTTPException(404, "Quality notice not found")
        item = await Workflow.find_one({"_id": oid, "user_id": user.user_id})
    elif alert.item_kind == "knowledge_base":
        from app.models.knowledge import KnowledgeBase
        item = await KnowledgeBase.find_one({"uuid": alert.item_id, "user_id": user.user_id})
    else:
        item = None
    if item is None:
        raise HTTPException(404, "Quality notice not found")
    return alert


class ReviewAlertRequest(BaseModel):
    state: Literal["new", "in_review", "acknowledged"]
