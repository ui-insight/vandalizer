"""Notification API routes."""

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user
from app.models.user import User
from app.services import notification_service as svc

router = APIRouter()


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    notifications = await svc.list_notifications(user.user_id, unread_only=unread_only, limit=limit)
    count = await svc.unread_count(user.user_id)
    return {"notifications": notifications, "unread_count": count}


@router.get("/count")
async def get_unread_count(user: User = Depends(get_current_user)):
    count = await svc.unread_count(user.user_id)
    return {"unread_count": count}


@router.post("/{notification_uuid}/read")
async def mark_read(
    notification_uuid: str,
    user: User = Depends(get_current_user),
):
    ok = await svc.mark_read(user.user_id, notification_uuid)
    return {"ok": ok}


@router.post("/read-item/{item_kind}/{item_id}")
async def mark_read_for_item(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    count = await svc.mark_read_for_item(user.user_id, item_kind, item_id)
    return {"ok": True, "marked_count": count}


@router.post("/read-all")
async def mark_all_read(user: User = Depends(get_current_user)):
    count = await svc.mark_all_read(user.user_id)
    return {"ok": True, "marked_count": count}
