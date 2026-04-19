"""Verification session API routes.

The chat agent creates a VerificationSession when it proposes turning an
extraction into a test case. The user reviews each extracted value in the
document viewer; the viewer PATCHes field statuses back here. When every
field is resolved, POST /finalize persists an ExtractionTestCase using the
user-approved (or user-corrected) values.
"""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.extraction_test_case import ExtractionTestCase
from app.models.user import User
from app.models.verification_session import VerificationSession

router = APIRouter()


class FieldPatch(BaseModel):
    status: str  # "approved" | "corrected" | "skipped" | "pending"
    expected: Optional[str] = None


class FinalizeRequest(BaseModel):
    label: Optional[str] = None


def _session_response(s: VerificationSession) -> dict:
    return {
        "uuid": s.uuid,
        "search_set_uuid": s.search_set_uuid,
        "document_uuid": s.document_uuid,
        "document_title": s.document_title,
        "label": s.label,
        "status": s.status,
        "test_case_uuid": s.test_case_uuid,
        "fields": [
            {
                "key": f.key,
                "extracted": f.extracted,
                "expected": f.expected,
                "status": f.status,
            }
            for f in s.fields
        ],
        "all_resolved": s.all_resolved(),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


async def _get_owned(uuid: str, user: User) -> VerificationSession:
    s = await VerificationSession.find_one(VerificationSession.uuid == uuid)
    if not s:
        raise HTTPException(status_code=404, detail="Verification session not found")
    if s.user_id != user.user_id:
        # Allow access when the session is scoped to the user's current team.
        if not (s.team_id and user.current_team and s.team_id == user.current_team):
            raise HTTPException(status_code=403, detail="Not authorized")
    return s


@router.get("/{uuid}")
async def get_session(uuid: str, user: User = Depends(get_current_user)) -> dict:
    s = await _get_owned(uuid, user)
    return _session_response(s)


@router.patch("/{uuid}/fields/{key}")
async def update_field(
    uuid: str,
    key: str,
    patch: FieldPatch,
    user: User = Depends(get_current_user),
) -> dict:
    """Approve, correct, or skip a single extracted field."""
    s = await _get_owned(uuid, user)
    if s.status != "pending":
        raise HTTPException(status_code=400, detail=f"Session is {s.status}")

    if patch.status not in ("approved", "corrected", "skipped", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")

    matched = False
    for f in s.fields:
        if f.key == key:
            f.status = patch.status
            if patch.status == "corrected":
                if patch.expected is None:
                    raise HTTPException(
                        status_code=400,
                        detail="expected value required when status=corrected",
                    )
                f.expected = patch.expected
            elif patch.status == "approved":
                f.expected = f.extracted
            elif patch.status == "skipped":
                f.expected = None
            matched = True
            break
    if not matched:
        raise HTTPException(status_code=404, detail=f"Field '{key}' not in session")

    s.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await s.save()
    return _session_response(s)


@router.post("/{uuid}/finalize")
async def finalize_session(
    uuid: str,
    body: FinalizeRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Lock the session in as an ExtractionTestCase.

    Only fields with status "approved" or "corrected" become part of the
    test case's expected_values. "Skipped" fields are dropped (the user
    couldn't confirm them from the document, so no ground truth).
    """
    s = await _get_owned(uuid, user)
    if s.status != "pending":
        raise HTTPException(status_code=400, detail=f"Session is {s.status}")
    if not s.all_resolved():
        raise HTTPException(
            status_code=400,
            detail="Cannot finalize: some fields are still pending review",
        )

    expected_values: dict[str, str] = {}
    for f in s.fields:
        if f.status in ("approved", "corrected") and f.expected is not None:
            expected_values[f.key] = f.expected

    label = body.label or s.label or s.document_title or s.document_uuid
    tc = ExtractionTestCase(
        search_set_uuid=s.search_set_uuid,
        label=label,
        source_type="document",
        document_uuid=s.document_uuid,
        expected_values=expected_values,
        user_id=user.user_id,
    )
    await tc.insert()

    s.status = "completed"
    s.test_case_uuid = tc.uuid
    s.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await s.save()

    return {
        "session": _session_response(s),
        "test_case": {
            "uuid": tc.uuid,
            "label": tc.label,
            "search_set_uuid": tc.search_set_uuid,
            "expected_values": tc.expected_values,
        },
    }


@router.post("/{uuid}/cancel")
async def cancel_session(uuid: str, user: User = Depends(get_current_user)) -> dict:
    s = await _get_owned(uuid, user)
    if s.status != "pending":
        raise HTTPException(status_code=400, detail=f"Session is {s.status}")
    s.status = "cancelled"
    s.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await s.save()
    return _session_response(s)
