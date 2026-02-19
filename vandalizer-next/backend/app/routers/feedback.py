"""Feedback API routes — extraction quality ratings."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from app.dependencies import get_current_user
from app.models.user import User
from app.models.feedback import ExtractionQualityRecord

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
