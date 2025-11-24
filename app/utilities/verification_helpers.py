"""Helpers for working with verified objects and examiner permissions."""

from __future__ import annotations

from typing import Optional, Tuple

from flask_login import AnonymousUserMixin

from app.models import (
    SearchSet,
    SearchSetItem,
    VerificationRequest,
    VerificationStatus,
    Workflow,
)


def _kind_and_identifier_for_obj(obj) -> Tuple[Optional[str], Optional[str]]:
    """Return the verification kind/identifier pair for a supported object."""
    if isinstance(obj, Workflow):
        return "workflow", str(obj.id)
    if isinstance(obj, SearchSet):
        return "searchset", obj.uuid
    if isinstance(obj, SearchSetItem):
        search_type = (obj.searchtype or "").lower()
        if search_type == "prompt":
            return "prompt", str(obj.id)
        if search_type == "formatter":
            return "formatter", str(obj.id)
    return None, None


def is_obj_verified(obj) -> bool:
    """Return True when the object has been verified."""
    if obj is None:
        return False

    if hasattr(obj, "verified"):
        return bool(getattr(obj, "verified", False))

    kind, identifier = _kind_and_identifier_for_obj(obj)
    if not kind or not identifier:
        return False

    return (
        VerificationRequest.objects(
            item_kind=kind,
            item_identifier=identifier,
            status=VerificationStatus.APPROVED,
        ).first()
        is not None
    )


def user_can_modify_verified(user, obj) -> bool:
    """
    Return True when the provided user may change the object.

    Non-examiners are blocked when the object is verified.
    """
    if obj is None:
        return False

    if not is_obj_verified(obj):
        return True

    if user is None:
        return False

    if isinstance(user, AnonymousUserMixin):
        return False

    return bool(getattr(user, "is_examiner", False))
