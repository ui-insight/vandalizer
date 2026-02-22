"""Config API routes  - model listing, user config, theme, and automation stats."""

import asyncio
import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.automation import Automation
from app.models.document import SmartDocument
from app.models.knowledge import KnowledgeBase
from app.models.library import LibraryItem
from app.models.search_set import SearchSet
from app.models.system_config import SystemConfig
from app.models.team import TeamMembership
from app.models.user import User
from app.models.user_config import UserModelConfig
from app.models.workflow import Workflow, WorkflowResult
from app.schemas.config import (
    ModelInfo,
    OnboardingStatusResponse,
    ThemeConfigResponse,
    UpdateThemeConfigRequest,
    UpdateUserConfigRequest,
    UserConfigResponse,
)
from app.services.config_service import (
    get_llm_model_by_name,
    get_llm_models,
    reconcile_user_model_config,
    resolve_model_name,
)

router = APIRouter()


@router.get("/models", response_model=list[ModelInfo])
async def get_models(user: User = Depends(get_current_user)):
    models = await get_llm_models()
    return [
        ModelInfo(
            name=m.get("name", ""),
            tag=m.get("tag", ""),
            external=m.get("external", False),
            thinking=m.get("thinking", False),
        )
        for m in models
        if isinstance(m, dict)
    ]


@router.get("/user", response_model=UserConfigResponse)
async def get_user_config(user: User = Depends(get_current_user)):
    user_config, models, _ = await reconcile_user_model_config(
        user.user_id, create_if_missing=True
    )
    model_infos = [
        ModelInfo(
            name=m.get("name", ""),
            tag=m.get("tag", ""),
            external=m.get("external", False),
            thinking=m.get("thinking", False),
        )
        for m in models
        if isinstance(m, dict)
    ]
    # Return the tag so the frontend can match the correct dropdown item
    stored = user_config.name if user_config else ""
    matched = await get_llm_model_by_name(stored)
    display_model = matched.get("tag", stored) if matched else stored
    return UserConfigResponse(
        model=display_model,
        temperature=user_config.temperature if user_config else 0.7,
        top_p=user_config.top_p if user_config else 0.9,
        available_models=model_infos,
    )


@router.put("/user", response_model=UserConfigResponse)
async def update_user_config(req: UpdateUserConfigRequest, user: User = Depends(get_current_user)):
    user_config, models, _ = await reconcile_user_model_config(
        user.user_id, create_if_missing=True
    )
    if not user_config:
        user_config = UserModelConfig(
            user_id=user.user_id,
            name=req.model or "",
            available_models=models,
        )
        await user_config.insert()

    if req.model is not None:
        # Store the tag as-is; resolve_model_name handles tag→name at LLM call time
        user_config.name = req.model
    if req.temperature is not None:
        user_config.temperature = req.temperature
    if req.top_p is not None:
        user_config.top_p = req.top_p
    await user_config.save()

    model_infos = [
        ModelInfo(
            name=m.get("name", ""),
            tag=m.get("tag", ""),
            external=m.get("external", False),
            thinking=m.get("thinking", False),
        )
        for m in models
        if isinstance(m, dict)
    ]
    # Return the tag for frontend matching
    matched = await get_llm_model_by_name(user_config.name)
    display_model = matched.get("tag", user_config.name) if matched else user_config.name
    return UserConfigResponse(
        model=display_model,
        temperature=user_config.temperature,
        top_p=user_config.top_p,
        available_models=model_infos,
    )


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


@router.get("/theme", response_model=ThemeConfigResponse)
async def get_theme(user: User = Depends(get_current_user)):
    config = await SystemConfig.get_config()
    return ThemeConfigResponse(
        highlight_color=config.highlight_color,
        ui_radius=config.ui_radius,
    )


@router.put("/theme", response_model=ThemeConfigResponse)
async def update_theme(req: UpdateThemeConfigRequest, user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    config = await SystemConfig.get_config()
    if req.highlight_color is not None:
        config.highlight_color = req.highlight_color
    if req.ui_radius is not None:
        config.ui_radius = req.ui_radius
    config.updated_at = datetime.datetime.now(datetime.timezone.utc)
    config.updated_by = user.user_id
    await config.save()
    return ThemeConfigResponse(
        highlight_color=config.highlight_color,
        ui_radius=config.ui_radius,
    )


# ---------------------------------------------------------------------------
# Onboarding status
# ---------------------------------------------------------------------------


@router.get("/onboarding-status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(user: User = Depends(get_current_user)):
    uid = user.user_id

    (
        doc_count,
        workflows,
        ss_count,
        library_items,
        membership_count,
        automations,
        knowledge_bases,
    ) = await asyncio.gather(
        SmartDocument.find(SmartDocument.user_id == uid).count(),
        Workflow.find(Workflow.user_id == uid).to_list(),
        SearchSet.find(SearchSet.user_id == uid).count(),
        LibraryItem.find(LibraryItem.added_by_user_id == uid).to_list(),
        TeamMembership.find(TeamMembership.user_id == uid).count(),
        Automation.find(Automation.user_id == uid).to_list(),
        KnowledgeBase.find(KnowledgeBase.user_id == uid).to_list(),
    )

    return OnboardingStatusResponse(
        has_documents=doc_count > 0,
        has_workflows=len(workflows) > 0,
        has_run_workflow=any(getattr(w, "num_executions", 0) > 0 for w in workflows),
        has_extraction_sets=ss_count > 0,
        has_library_items=len(library_items) > 0,
        has_pinned_item=any(getattr(i, "pinned", False) for i in library_items),
        has_favorited_item=any(getattr(i, "favorited", False) for i in library_items),
        has_team_members=membership_count > 1,
        has_automations=len(automations) > 0,
        has_enabled_automation=any(getattr(a, "enabled", False) for a in automations),
        has_knowledge_base=len(knowledge_bases) > 0,
        has_ready_knowledge_base=any(getattr(kb, "status", "") == "ready" for kb in knowledge_bases),
    )


# ---------------------------------------------------------------------------
# Automation stats
# ---------------------------------------------------------------------------


@router.get("/automation-stats")
async def get_automation_stats(user: User = Depends(get_current_user)):
    all_workflows = await Workflow.find().to_list()
    total = len(all_workflows)

    passive = [
        w for w in all_workflows
        if w.input_config.get("folder_watch", {}).get("enabled")
    ]
    passive_count = len(passive)

    watched_folders = set()
    for w in passive:
        for f in w.input_config.get("folder_watch", {}).get("folders", []):
            watched_folders.add(f)

    # Recent runs (last 7 days)
    week_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    recent_results = await WorkflowResult.find(
        WorkflowResult.start_time >= week_ago,
    ).to_list()

    today_start = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_results = [r for r in recent_results if r.start_time >= today_start]

    return {
        "total_workflows": total,
        "passive_workflows": passive_count,
        "watched_folders": len(watched_folders),
        "runs_today": len(today_results),
        "runs_today_success": len([r for r in today_results if r.status == "completed"]),
        "runs_today_failed": len([r for r in today_results if r.status in ("error", "failed")]),
        "runs_this_week": len(recent_results),
        "recent_runs": [
            {
                "id": str(r.id),
                "workflow_id": str(r.workflow) if r.workflow else None,
                "status": r.status,
                "trigger_type": r.trigger_type or "manual",
                "is_passive": r.is_passive,
                "started_at": r.start_time.isoformat() if r.start_time else None,
                "steps_completed": r.num_steps_completed,
                "steps_total": r.num_steps_total,
            }
            for r in sorted(recent_results, key=lambda x: x.start_time, reverse=True)[:20]
        ],
    }
