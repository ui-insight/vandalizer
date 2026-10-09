"""API routes for trial feedback prompts."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.services import feedback_prompt_service as svc

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_demo_user(user: User) -> User:
    if not user.is_demo_user:
        raise HTTPException(status_code=403, detail="Only available for trial users")
    return user


def _require_admin(user: User) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ------------------------------------------------------------------
# Demo user endpoints
# ------------------------------------------------------------------


@router.get("/pending")
async def get_pending_prompt(user: User = Depends(get_current_user)):
    """Return the next eligible feedback prompt for this demo user, or null."""
    if not user.is_demo_user:
        return {"prompt": None}

    # Build onboarding status inline (reuse the same queries as config router)
    from app.models.document import SmartDocument
    from app.models.workflow import Workflow
    from app.models.search_set import SearchSet
    from app.models.library import LibraryItem
    from app.models.team import TeamMembership
    from app.models.automation import Automation
    from app.models.knowledge import KnowledgeBase
    from app.models.chat import ChatConversation
    from app.services.certification_versions.readers import has_earned_certification

    uid = user.user_id
    (
        doc_count,
        workflows,
        ss_count,
        library_items,
        membership_count,
        automations,
        knowledge_bases,
        doc_chat_count,
        is_certified,
    ) = await asyncio.gather(
        SmartDocument.find(SmartDocument.user_id == uid).count(),
        Workflow.find(Workflow.user_id == uid).to_list(),
        SearchSet.find(SearchSet.user_id == uid).count(),
        LibraryItem.find(LibraryItem.added_by_user_id == uid).to_list(),
        TeamMembership.find(TeamMembership.user_id == uid).count(),
        Automation.find(Automation.user_id == uid).to_list(),
        KnowledgeBase.find(KnowledgeBase.user_id == uid).to_list(),
        ChatConversation.find({
            "user_id": uid,
            "messages": {"$ne": []},
            "$or": [
                {"file_attachments": {"$ne": []}},
                {"url_attachments": {"$ne": []}},
            ],
        }).count(),
        has_earned_certification(uid),
    )

    onboarding = {
        "has_documents": doc_count > 0,
        "has_workflows": len(workflows) > 0,
        "has_run_workflow": any(getattr(w, "num_executions", 0) > 0 for w in workflows),
        "has_extraction_sets": ss_count > 0,
        "has_library_items": len(library_items) > 0,
        "has_pinned_item": any(getattr(i, "pinned", False) for i in library_items),
        "has_favorited_item": any(getattr(i, "favorited", False) for i in library_items),
        "has_team_members": membership_count > 1,
        "has_automations": len(automations) > 0,
        "has_enabled_automation": any(getattr(a, "enabled", False) for a in automations),
        "has_knowledge_base": len(knowledge_bases) > 0,
        "has_ready_knowledge_base": any(getattr(kb, "status", "") == "ready" for kb in knowledge_bases),
        "has_chatted_with_docs": doc_chat_count > 0,
        "is_certified": is_certified,
    }

    prompt = await svc.evaluate_eligible_prompt(user, onboarding)
    return {"prompt": prompt}


@router.post("/{slug}/show")
async def show_prompt(slug: str, user: User = Depends(get_current_user)):
    """Create a support ticket for this prompt and mark it shown."""
    _require_demo_user(user)
    result = await svc.show_prompt(user, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


@router.post("/{slug}/dismiss")
async def dismiss_prompt(slug: str, user: User = Depends(get_current_user)):
    """Dismiss a feedback prompt so it won't be shown again."""
    _require_demo_user(user)
    ok = await svc.dismiss_prompt(user, slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"ok": True}


# ------------------------------------------------------------------
# Admin endpoints
# ------------------------------------------------------------------


@router.get("/admin/overview")
async def admin_overview(user: User = Depends(get_current_user)):
    """Per-prompt stats for the admin dashboard."""
    _require_admin(user)
    return await svc.get_admin_overview()


class UpdatePromptRequest(BaseModel):
    question_text: str | None = None
    subject: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    trigger_rules: dict | None = None


@router.put("/admin/{slug}")
async def admin_update_prompt(
    slug: str,
    req: UpdatePromptRequest,
    user: User = Depends(get_current_user),
):
    """Update a feedback prompt's configuration."""
    _require_admin(user)
    updates = req.model_dump(exclude_none=True)
    result = await svc.admin_update_prompt(slug, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result
