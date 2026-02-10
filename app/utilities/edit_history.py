from __future__ import annotations

from typing import Any, Dict, Optional

from app.models import EditHistoryEntry, User


def _user_display_name(user: User | None) -> tuple[str | None, str | None]:
    if not user:
        return None, None
    user_id = getattr(user, "user_id", None)
    user_name = user.name or user.email or user_id
    return user_id, user_name


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_changes(fields: Dict[str, tuple[Any, Any]]) -> dict[str, dict[str, str]]:
    changes: dict[str, dict[str, str]] = {}
    for field, (before, after) in fields.items():
        if before != after:
            changes[field] = {
                "before": _stringify(before),
                "after": _stringify(after),
            }
    return changes


def log_edit_history(
    *,
    kind: str,
    obj_id: str,
    user: User | None,
    action: str,
    changes: Optional[dict[str, dict[str, str]]] = None,
) -> EditHistoryEntry | None:
    normalized_changes = changes or {}
    if action == "update" and not normalized_changes:
        return None
    user_id, user_name = _user_display_name(user)
    return EditHistoryEntry(
        obj_kind=kind,
        obj_id=obj_id,
        action=action,
        user_id=user_id,
        user_name=user_name,
        changes=normalized_changes,
    ).save()


def history_for(kind: str, obj_id: str, limit: int = 20) -> list[EditHistoryEntry]:
    return list(
        EditHistoryEntry.objects(obj_kind=kind, obj_id=obj_id)
        .order_by("-created_at")
        .limit(limit)
    )
