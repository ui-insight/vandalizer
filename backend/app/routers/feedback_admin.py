"""Admin read surface for positive feedback — the "What's Working" feed.

Positive signal used to be write-only: chat thumbs-up, high extraction star
ratings, and (now) ProductFeedback all landed in Mongo and were never read by a
human. This router is the read side that gives that signal a home. It unifies
three sources into one reverse-chronological feed plus a small stats rollup, so
support agents can finally see what users love — the mirror image of the
thumbs-down path that already drives KB optimization.

Support users / admins only, mirroring ``/api/support/stats``.
"""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.feedback import ChatFeedback, ExtractionQualityRecord, ProductFeedback
from app.models.user import User
from app.services import support_service

router = APIRouter()

# A star rating at or above this counts as positive signal for the feed.
POSITIVE_STAR_THRESHOLD = 4


async def _require_support(user: User) -> None:
    if not await support_service.is_support_user(user):
        raise HTTPException(status_code=403, detail="Not authorized")


def _item(source: str, sentiment: str, message: Optional[str], feature: Optional[str],
          user_id: Optional[str], created_at: datetime.datetime) -> dict:
    return {
        "source": source,
        "sentiment": sentiment,
        "message": message,
        "feature": feature,
        "user_id": user_id,
        "created_at": created_at.isoformat() if created_at else None,
        "_sort": created_at or datetime.datetime.min,
    }


@router.get("/positive")
async def list_positive_feedback(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = Query(None, description="chat | extraction | product"),
):
    """Unified reverse-chronological feed of positive feedback across sources.

    - chat: thumbs-up ChatFeedback that carries a comment (bare up-votes have
      no words to show, so they inflate stats, not the feed).
    - extraction: ExtractionQualityRecord at or above the star threshold.
    - product: every ProductFeedback (already positive/idea by construction).
    """
    await _require_support(user)

    # Over-fetch per source, merge, then trim — a per-source limit can't know
    # the global chronological cut-off ahead of the merge.
    items: list[dict] = []

    if source in (None, "chat"):
        chats = await (
            ChatFeedback.find(ChatFeedback.rating == "up")
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )
        for c in chats:
            if c.comment and c.comment.strip():
                items.append(_item("chat", "positive", c.comment, "chat",
                                   c.user_id, c.created_at))

    if source in (None, "extraction"):
        extractions = await (
            ExtractionQualityRecord.find(
                ExtractionQualityRecord.star_rating >= POSITIVE_STAR_THRESHOLD
            )
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )
        for e in extractions:
            label = f"{e.star_rating}★ — {e.pdf_title}"
            msg = f"{label}: {e.comment}" if (e.comment and e.comment.strip()) else label
            items.append(_item("extraction", "positive", msg, "extraction",
                               e.user_id, e.created_at))

    if source in (None, "product"):
        products = await (
            ProductFeedback.find()
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )
        for p in products:
            items.append(_item("product", p.sentiment, p.message, p.feature,
                               p.user_id, p.created_at))

    items.sort(key=lambda i: i["_sort"], reverse=True)
    trimmed = items[:limit]
    for i in trimmed:
        i.pop("_sort", None)
    return {"items": trimmed, "count": len(trimmed)}


@router.get("/stats")
async def positive_feedback_stats(user: User = Depends(get_current_user)):
    """Rollup for the 'What's Working' header: how much positive signal there
    is, where it comes from, and the chat thumbs-up rate (the one sentiment
    metric we already trend elsewhere)."""
    await _require_support(user)

    week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    chat_up = await ChatFeedback.find(ChatFeedback.rating == "up").count()
    chat_down = await ChatFeedback.find(ChatFeedback.rating == "down").count()
    extraction_positive = await ExtractionQualityRecord.find(
        ExtractionQualityRecord.star_rating >= POSITIVE_STAR_THRESHOLD
    ).count()
    product_total = await ProductFeedback.find().count()

    product_week = await ProductFeedback.find(
        ProductFeedback.created_at >= week_ago
    ).count()
    chat_up_week = await ChatFeedback.find(
        ChatFeedback.rating == "up", ChatFeedback.created_at >= week_ago
    ).count()

    total_chat = chat_up + chat_down
    thumbs_up_rate = round(chat_up / total_chat, 3) if total_chat else None

    return {
        "by_source": {
            "chat": chat_up,
            "extraction": extraction_positive,
            "product": product_total,
        },
        "thumbs_up_rate": thumbs_up_rate,
        "positive_last_7_days": product_week + chat_up_week,
    }
