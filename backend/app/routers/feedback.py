"""Feedback API routes  - extraction quality ratings."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from app.dependencies import get_current_user
from app.models.user import User
from app.models.feedback import ChatFeedback, ExtractionQualityRecord

router = APIRouter()


class SubmitRatingRequest(BaseModel):
    pdf_title: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    result_json: Optional[dict] = None
    search_set_uuid: Optional[str] = None


@router.post("/submit_rating")
async def submit_rating(req: SubmitRatingRequest, user: User = Depends(get_current_user)):
    import json
    record = ExtractionQualityRecord(
        pdf_title=req.pdf_title,
        star_rating=req.rating,
        comment=req.comment,
        result_json=json.dumps(req.result_json) if req.result_json else None,
        user_id=user.user_id,
        search_set_uuid=req.search_set_uuid,
    )
    await record.insert()
    return {"complete": True}


class ChatFeedbackRequest(BaseModel):
    conversation_uuid: Optional[str] = None
    message_index: Optional[int] = None
    rating: str  # "up" or "down"
    comment: Optional[str] = None
    # When the rated message came from a KB-backed answer, the chat surface
    # supplies the KB uuid so Phase-5 feedback aggregation can attribute the
    # rating to that KB. Optional — non-RAG ratings don't carry it.
    kb_uuid: Optional[str] = None


# Phase 5: a single user's thumbs-down rate over the last ``THUMBS_DOWN_WINDOW``
# events for a KB. When the rate exceeds the threshold we enqueue a shadow
# KB autovalidate run so the feedback signal becomes input to the optimizer
# instead of dying in this collection.
THUMBS_DOWN_WINDOW = 10
THUMBS_DOWN_THRESHOLD = 0.4   # >= 4 of last 10 = trigger
THUMBS_DOWN_MIN_SAMPLES = 4   # need at least this many ratings before triggering


async def _maybe_trigger_kb_shadow_run(kb_uuid: str, user_id: str) -> None:
    """Inspect the last N ratings for this KB; if down-rate is elevated, fire
    a shadow KB autovalidate run via optimizer_signal_service. Best-effort —
    never raised into the caller (a feedback POST must always succeed)."""
    try:
        recent = await (
            ChatFeedback.find(ChatFeedback.kb_uuid == kb_uuid)
            .sort("-created_at")
            .limit(THUMBS_DOWN_WINDOW)
            .to_list()
        )
        if len(recent) < THUMBS_DOWN_MIN_SAMPLES:
            return
        downs = sum(1 for r in recent if r.rating == "down")
        rate = downs / len(recent)
        if rate < THUMBS_DOWN_THRESHOLD:
            return
        from app.services import optimizer_signal_service
        await optimizer_signal_service.enqueue_kb_shadow_run(
            kb_uuid=kb_uuid,
            user_id=user_id,
            trigger="chat_feedback_threshold",
            trigger_detail={
                "window": len(recent), "downs": downs, "rate": round(rate, 3),
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Shadow-run trigger failed for kb=%s", kb_uuid, exc_info=True,
        )


@router.post("/chat")
async def submit_chat_feedback(req: ChatFeedbackRequest, user: User = Depends(get_current_user)):
    record = ChatFeedback(
        conversation_uuid=req.conversation_uuid,
        message_index=req.message_index,
        rating=req.rating,
        comment=req.comment,
        kb_uuid=req.kb_uuid,
        user_id=user.user_id,
    )
    await record.insert()
    # Only down-ratings against a known KB can trigger a shadow run.
    if req.rating == "down" and req.kb_uuid:
        await _maybe_trigger_kb_shadow_run(req.kb_uuid, user.user_id)
    return {"complete": True}
