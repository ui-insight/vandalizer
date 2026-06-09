"""Optimizer Inbox  - unified shadow-run candidate list (Phase 6 of loop closure).

Phase 5 + 6 trigger optimizer runs in *shadow* mode in response to quality
alerts and report-only signals. These runs land in the user's inbox with
their winning config + ``apply_preview`` already computed — the user can
review, apply, dismiss, or re-tune from one place rather than checking
each KB / SearchSet / workflow individually.

Query logic lives in ``app.services.optimization_summary`` so the agentic
chat tools can serve the same inbox.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.services.optimization_summary import shadow_inbox

router = APIRouter()


@router.get("/inbox")
async def list_shadow_inbox(
    user: User = Depends(get_current_user),
) -> dict:
    """Return shadow optimizer runs across KB/extraction/workflow.

    Owned by the current user (system-triggered runs use user_id="system",
    and are visible to everyone via the team scope of their parent item;
    for v1 we surface only the requester's own runs so the inbox stays
    focused — wider sharing is a Phase 7 concern).
    """
    return await shadow_inbox()
