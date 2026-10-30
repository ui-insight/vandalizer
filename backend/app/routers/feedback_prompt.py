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


@router.get("/pending", response_model=None)
async def get_pending_prompt(user: User = Depends(get_current_user)) -> dict[str, object]:
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
    doc_count_task = asyncio.create_task(SmartDocument.find(SmartDocument.user_id == uid).count())
    workflows_task = asyncio.create_task(Workflow.find(Workflow.user_id == uid).to_list())
    ss_count_task = asyncio.create_task(SearchSet.find(SearchSet.user_id == uid).count())
    library_items_task = asyncio.create_task(LibraryItem.find(LibraryItem.added_by_user_id == uid).to_list())
    membership_count_task = asyncio.create_task(TeamMembership.find(TeamMembership.user_id == uid).count())
    automations_task = asyncio.create_task(Automation.find(Automation.user_id == uid).to_list())
    knowledge_bases_task = asyncio.create_task(KnowledgeBase.find(KnowledgeBase.user_id == uid).to_list())
    doc_chat_count_task = asyncio.create_task(ChatConversation.find({
        'user_id': uid, 'messages': {'$ne': []},
        '$or': [{'file_attachments': {'$ne': []}}, {'url_attachments': {'$ne': []}}],
    }).count())
    is_certified_task = asyncio.create_task(has_earned_certification(uid))
    await asyncio.gather(
        doc_count_task, workflows_task, ss_count_task, library_items_task,
        membership_count_task, automations_task, knowledge_bases_task,
        doc_chat_count_task, is_certified_task,
    )
    doc_count = doc_count_task.result()
    workflows = workflows_task.result()
    ss_count = ss_count_task.result()
    library_items = library_items_task.result()
    membership_count = membership_count_task.result()
    automations = automations_task.result()
    knowledge_bases = knowledge_bases_task.result()
    doc_chat_count = doc_chat_count_task.result()
    is_certified = is_certified_task.result()

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


@router.post("/{slug}/show", response_model=None)
async def show_prompt(slug: str, user: User = Depends(get_current_user)) -> dict:
    """Create a support ticket for this prompt and mark it shown."""
    _require_demo_user(user)
    result = await svc.show_prompt(user, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


@router.post("/{slug}/dismiss", response_model=None)
async def dismiss_prompt(slug: str, user: User = Depends(get_current_user)) -> dict[str, object]:
    """Dismiss a feedback prompt so it won't be shown again."""
    _require_demo_user(user)
    ok = await svc.dismiss_prompt(user, slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"ok": True}


# ------------------------------------------------------------------
# Admin endpoints
# ------------------------------------------------------------------


@router.get("/admin/overview", response_model=None)
async def admin_overview(user: User = Depends(get_current_user)) -> list[dict]:
    """Per-prompt stats for the admin dashboard."""
    _require_admin(user)
    return await svc.get_admin_overview()


class UpdatePromptRequest(BaseModel):
    question_text: str | None = None
    subject: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    trigger_rules: dict | None = None


@router.put("/admin/{slug}", response_model=None)
async def admin_update_prompt(
    slug: str,
    req: UpdatePromptRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Update a feedback prompt's configuration."""
    _require_admin(user)
    updates = req.model_dump(exclude_none=True)
    result = await svc.admin_update_prompt(slug, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result
