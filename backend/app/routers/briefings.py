"""Morning Briefing API routes — fetch today's briefing and mark it opened."""

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.services import briefing_service

router = APIRouter()


def _serialize(briefing) -> dict:
    return {
        "date": briefing.date.isoformat(),
        "items": [item.model_dump() for item in briefing.items],
        "primer_padded": briefing.primer_padded,
        "opened_at": briefing.opened_at.isoformat() if briefing.opened_at else None,
        "sent_via_email": briefing.sent_via_email,
    }


@router.get("/today")
async def get_today_briefing(user: User = Depends(get_current_user)):
    """Fetch today's briefing for the current user. Idempotent — computes if missing."""
    briefing = await briefing_service.get_or_create_today_briefing(user)
    return _serialize(briefing)


@router.post("/today/open")
async def mark_today_opened(user: User = Depends(get_current_user)):
    """Mark today's briefing as opened. Drives streak tracking."""
    briefing = await briefing_service.get_or_create_today_briefing(user)
    await briefing_service.mark_briefing_opened(briefing, user)
    return _serialize(briefing)
