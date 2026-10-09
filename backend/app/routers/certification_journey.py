from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import PyMongoError

from app.dependencies import get_current_user
from app.models.user import User
from app.rate_limit import limiter
from app.services.certification_versions.journey_events import JourneyEventRequest, JourneyEventConflict, record

router = APIRouter()


@router.post('/journey-events')
@limiter.limit('120/minute')
async def record_journey_event(request: Request, payload: JourneyEventRequest, user: User = Depends(get_current_user)):
    try:
        return await record(user.user_id, payload)
    except JourneyEventConflict:
        raise HTTPException(status_code=409, detail='The journey observation could not be recorded.') from None
    except PyMongoError:
        raise HTTPException(status_code=503, detail='Journey observations are temporarily unavailable.') from None
