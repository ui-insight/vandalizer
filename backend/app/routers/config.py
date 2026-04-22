"""Config API routes  - model listing, user config, theme, and automation stats."""

import asyncio
import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.activity import ActivityEvent
from app.models.automation import Automation
from app.models.certification import CertificationProgress
from app.models.chat import ChatConversation
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
    ActiveAlertItem,
    ModelInfo,
    OnboardingStatusResponse,
    RecentActivityItem,
    ThemeConfigResponse,
    UpdateThemeConfigRequest,
    UpdateUserConfigRequest,
    UserConfigResponse,
)
from app.services.config_service import (
    get_llm_model_by_name,
    get_llm_models,
    reconcile_user_model_config,
)
from app.services import workflow_service

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
            speed=m.get("speed", ""),
            tier=m.get("tier", ""),
            privacy=m.get("privacy", ""),
            supports_structured=m.get("supports_structured", True),
            context_window=m.get("context_window", 128000),
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
            speed=m.get("speed", ""),
            tier=m.get("tier", ""),
            privacy=m.get("privacy", ""),
            supports_structured=m.get("supports_structured", True),
            context_window=m.get("context_window", 128000),
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
            speed=m.get("speed", ""),
            tier=m.get("tier", ""),
            privacy=m.get("privacy", ""),
            supports_structured=m.get("supports_structured", True),
            context_window=m.get("context_window", 128000),
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
async def get_theme():
    """Public endpoint  - returns brand theme so the landing page can render it."""
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
# Feature flags
# ---------------------------------------------------------------------------


@router.get("/features")
async def get_features(user: User = Depends(get_current_user)):
    """Return feature flags for the current deployment."""
    config = await SystemConfig.get_config()
    return {
        "m365_enabled": config.is_m365_enabled(),
    }


# ---------------------------------------------------------------------------
# Onboarding status
# ---------------------------------------------------------------------------


def _compute_maturity_stage(
    *,
    doc_count: int,
    extraction_run_count: int,
    workflows: list,
    has_enabled_automation: bool,
    is_certified: bool,
) -> str:
    """Determine user maturity stage for progressive guidance."""
    if is_certified or has_enabled_automation:
        return "architect"
    if workflows:
        return "builder"
    if extraction_run_count >= 3:
        return "practitioner"
    if doc_count > 0:
        return "explorer"
    return "newcomer"


def _generate_daily_guidance(
    *,
    recent_activity: list,
    active_alerts: list,
    maturity_stage: str,
    has_only_onboarding_docs: bool,
    doc_count: int,
) -> str | None:
    """Synthesize alerts + activity + maturity into a single actionable sentence."""
    # Post-demo: bridge to real work
    if has_only_onboarding_docs:
        return (
            "You've seen Vandalizer in action with a sample proposal. "
            "Upload one of your own documents and I'll help you build a custom template for it."
        )

    # Critical alerts take priority
    critical = [a for a in active_alerts if getattr(a, "severity", "") == "critical"]
    if critical:
        return f"Your {critical[0].item_name} has a critical quality issue — want me to diagnose it?"

    # Warning alerts
    warnings = [a for a in active_alerts if getattr(a, "severity", "") == "warning"]
    if warnings:
        return f"Your {warnings[0].item_name} flagged a quality warning — want me to take a look?"

    # Failed recent activity
    failed = [a for a in recent_activity if getattr(a, "status", "") == "failed"]
    if failed:
        title = getattr(failed[0], "title", "activity") or "activity"
        return f'Your "{title}" run failed — want me to help figure out what went wrong?'

    # Running activity
    running = [a for a in recent_activity if getattr(a, "status", "") == "running"]
    if running:
        title = getattr(running[0], "title", "activity") or "activity"
        return f'Your "{title}" is still running — I can check on it when you\'re ready.'

    # Maturity-driven nudge for users with no pressing items
    if maturity_stage == "newcomer" and doc_count == 0:
        return "Upload your first document and I'll help you get value from it immediately."
    if maturity_stage == "explorer" and doc_count > 0:
        return "You have documents ready — want me to run an extraction template on them?"

    # Recent success — offer next step
    completed = [a for a in recent_activity if getattr(a, "status", "") == "completed"]
    if completed:
        title = getattr(completed[0], "title", "") or "activity"
        return f'Your latest "{title}" completed successfully — ready to continue?'

    return None


def _generate_since_last_visit(
    *,
    last_login_at: datetime.datetime | None,
    recent_activity: list,
    active_alerts: list,
) -> str | None:
    """Summarize what happened since the user was last here."""
    if not last_login_at:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - last_login_at
    if delta.total_seconds() < 3600:  # Less than 1 hour — not meaningful
        return None

    # Count events since last visit
    completed_since = 0
    failed_since = 0
    for ev in recent_activity:
        ev_time = getattr(ev, "last_updated_at", None)
        if ev_time and ev_time > last_login_at:
            status = getattr(ev, "status", "")
            if status == "completed":
                completed_since += 1
            elif status == "failed":
                failed_since += 1

    new_alerts = sum(
        1 for a in active_alerts
        if getattr(a, "created_at", None) and a.created_at > last_login_at
    )

    parts: list[str] = []

    # Format time away
    hours = delta.total_seconds() / 3600
    if hours < 24:
        time_str = f"{int(hours)} hour{'s' if int(hours) != 1 else ''}"
    else:
        days = int(hours / 24)
        time_str = f"{days} day{'s' if days != 1 else ''}"

    if completed_since == 0 and failed_since == 0 and new_alerts == 0:
        return None

    parts.append(f"Since you were last here ({time_str} ago):")
    if completed_since > 0:
        parts.append(f"{completed_since} run{'s' if completed_since != 1 else ''} completed successfully")
    if failed_since > 0:
        parts.append(f"{failed_since} run{'s' if failed_since != 1 else ''} failed")
    if new_alerts > 0:
        parts.append(f"{new_alerts} quality alert{'s' if new_alerts != 1 else ''} raised")

    return " — ".join(parts) if len(parts) > 1 else None


def _generate_action_pills(
    *,
    doc_count: int,
    onboarding_doc_count: int,
    search_sets: list,
    workflows: list,
    knowledge_bases: list,
    has_chatted_with_docs: bool,
    quality_map: dict[str, float],
    last_activity_title: str | None = None,
    maturity_stage: str = "newcomer",
) -> list[str]:
    """Generate up to 4 personalised, action-oriented suggestion pills."""
    pills: list[str] = []

    # 0. Post-demo: user has only the onboarding sample, no user-uploaded docs
    has_only_sample = doc_count > 0 and doc_count == onboarding_doc_count
    if has_only_sample:
        pills.append("Ask me anything about the sample NSF proposal")
        pills.append("Upload your own documents to get started")
        return pills[:4]

    # Continue where you left off — returning users with real content
    if last_activity_title and doc_count > 0:
        pills.append(f"Pick up where I left off: {last_activity_title}")

    ready_kbs = [kb for kb in knowledge_bases if getattr(kb, "status", "") == "ready"]

    # 1. Run extraction on latest docs
    if doc_count > 0 and search_sets:
        top_ss = search_sets[0]
        label = top_ss.title
        score = quality_map.get(top_ss.uuid)
        if score is not None:
            label += f" ({round(score)}% validated)"
        pills.append(f"Run {label} on your latest documents")

    # 2. Query a ready knowledge base
    if ready_kbs:
        pills.append(f"Ask your {ready_kbs[0].title} knowledge base a question")

    # 3. Run a workflow
    if workflows and doc_count > 0:
        pills.append(f"Run {workflows[0].name} on your documents")

    # 4. Build extraction template from docs
    if doc_count > 0 and not search_sets:
        pills.append("Build an extraction template from your documents")

    # 5. Turn extraction set into workflow
    if search_sets and not workflows:
        pills.append(f"Turn {search_sets[0].title} into a repeatable workflow")

    # 6. Chat with docs
    if doc_count > 0 and not has_chatted_with_docs:
        pills.append("Select a document and ask me about it")

    # 7. Empty workspace
    if doc_count == 0:
        pills.append("Upload your first document to get started")

    # 8. Maturity-aware escalation pills (fill remaining slots)
    if len(pills) < 4:
        if maturity_stage == "explorer" and search_sets:
            pills.append(f"Check quality score for {search_sets[0].title}")
        elif maturity_stage == "practitioner" and search_sets and not workflows:
            pills.append(f"Chain {search_sets[0].title} into a repeatable workflow")
        elif maturity_stage == "builder":
            pills.append("Set up a folder watch to automate your workflow")
        elif maturity_stage == "architect":
            low_quality = [ss for ss in search_sets if quality_map.get(ss.uuid, 100) < 80]
            if low_quality:
                pills.append(f"Tune {low_quality[0].title} to improve extraction accuracy")

    return pills[:4]


@router.get("/onboarding-status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(user: User = Depends(get_current_user)):
    uid = user.user_id

    (
        doc_count,
        onboarding_doc_count,
        workflows,
        search_sets,
        library_items,
        membership_count,
        automations,
        knowledge_bases,
        doc_chat_count,
        conversation_count,
        cert_progress,
        recent_activities,
        extraction_run_count,
    ) = await asyncio.gather(
        SmartDocument.find(SmartDocument.user_id == uid).count(),
        SmartDocument.find(
            SmartDocument.user_id == uid,
            SmartDocument.is_onboarding_sample == True,  # noqa: E712
        ).count(),
        Workflow.find(Workflow.user_id == uid).to_list(),
        SearchSet.find(SearchSet.user_id == uid).to_list(),
        LibraryItem.find(LibraryItem.added_by_user_id == uid).to_list(),
        TeamMembership.find(TeamMembership.user_id == uid).count(),
        Automation.find(Automation.user_id == uid).to_list(),
        KnowledgeBase.find(KnowledgeBase.user_id == uid).to_list(),
        # Conversations with at least one file or URL attachment + messages
        ChatConversation.find({
            "user_id": uid,
            "messages": {"$ne": []},
            "$or": [
                {"file_attachments": {"$ne": []}},
                {"url_attachments": {"$ne": []}},
            ],
        }).count(),
        # Any conversations at all
        ChatConversation.find(ChatConversation.user_id == uid).count(),
        CertificationProgress.find_one(CertificationProgress.user_id == uid),
        # Recent activities for workspace briefing + "continue where you left off" pill
        ActivityEvent.find(
            {"user_id": uid, "status": {"$in": ["completed", "failed", "running"]}}
        ).sort("-last_updated_at").limit(3).to_list(),
        # Completed extraction runs — drives maturity stage progression
        ActivityEvent.find(
            {"user_id": uid, "type": "search_set_run", "status": "completed"}
        ).count(),
    )

    # Fetch quality scores + alerts for extraction sets
    quality_map: dict[str, float] = {}
    quality_alerts: list = []
    if search_sets:
        from app.models.quality_alert import QualityAlert
        from app.models.validation_run import ValidationRun

        ss_uuids = [ss.uuid for ss in search_sets]
        vr_list, quality_alerts = await asyncio.gather(
            ValidationRun.find(
                {"item_kind": "search_set", "item_id": {"$in": ss_uuids}}
            ).sort("-created_at").to_list(),
            QualityAlert.find(
                {"item_kind": "search_set", "item_id": {"$in": ss_uuids}, "acknowledged": {"$ne": True}}
            ).sort("-created_at").limit(3).to_list(),
        )
        for vr in vr_list:
            if vr.item_id not in quality_map and vr.accuracy is not None:
                quality_map[vr.item_id] = round(vr.accuracy * 100)

    last_activity_title = recent_activities[0].title if recent_activities else None

    is_certified = bool(cert_progress and cert_progress.certified)
    has_enabled_automation = any(getattr(a, "enabled", False) for a in automations)

    maturity_stage = _compute_maturity_stage(
        doc_count=doc_count,
        extraction_run_count=extraction_run_count,
        workflows=workflows,
        has_enabled_automation=has_enabled_automation,
        is_certified=is_certified,
    )

    pills = _generate_action_pills(
        doc_count=doc_count,
        onboarding_doc_count=onboarding_doc_count,
        search_sets=search_sets,
        workflows=workflows,
        knowledge_bases=knowledge_bases,
        has_chatted_with_docs=doc_chat_count > 0,
        quality_map=quality_map,
        last_activity_title=last_activity_title,
        maturity_stage=maturity_stage,
    )

    # Format recent activity for frontend briefing
    from app.services.chat_service import _relative_time

    recent_activity_items = [
        RecentActivityItem(
            type=ev.type,
            title=ev.title or "Activity",
            relative_time=_relative_time(ev.last_updated_at) if ev.last_updated_at else "",
            status=ev.status,
        )
        for ev in recent_activities[:3]
    ]

    alert_items = [
        ActiveAlertItem(
            message=alert.message,
            severity=alert.severity,
            item_name=alert.item_name,
        )
        for alert in quality_alerts
    ]

    # Unprocessed doc count: simple heuristic — all docs are unprocessed if
    # user has never run an extraction
    unprocessed = doc_count if (doc_count > 0 and extraction_run_count == 0) else 0

    has_only_sample = doc_count > 0 and doc_count == onboarding_doc_count

    daily_guidance = _generate_daily_guidance(
        recent_activity=recent_activities,
        active_alerts=quality_alerts,
        maturity_stage=maturity_stage,
        has_only_onboarding_docs=has_only_sample,
        doc_count=doc_count,
    )

    since_last_visit = _generate_since_last_visit(
        last_login_at=user.last_login_at,
        recent_activity=recent_activities,
        active_alerts=quality_alerts,
    )

    # Update last_login_at for future delta computation (fire-and-forget)
    user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
    asyncio.ensure_future(user.save())

    return OnboardingStatusResponse(
        has_documents=doc_count > 0,
        has_workflows=len(workflows) > 0,
        has_run_workflow=any(getattr(w, "num_executions", 0) > 0 for w in workflows),
        has_extraction_sets=len(search_sets) > 0,
        has_library_items=len(library_items) > 0,
        has_pinned_item=any(getattr(i, "pinned", False) for i in library_items),
        has_favorited_item=any(getattr(i, "favorited", False) for i in library_items),
        has_team_members=membership_count > 1,
        has_automations=len(automations) > 0,
        has_enabled_automation=has_enabled_automation,
        has_knowledge_base=len(knowledge_bases) > 0,
        has_ready_knowledge_base=any(getattr(kb, "status", "") == "ready" for kb in knowledge_bases),
        has_chatted_with_docs=doc_chat_count > 0,
        has_conversations=conversation_count > 0,
        first_session_completed=user.first_session_completed,
        is_certified=is_certified,
        suggestion_pills=pills,
        has_only_onboarding_docs=(doc_count > 0 and doc_count == onboarding_doc_count),
        top_extraction_set_name=search_sets[0].title if search_sets else None,
        top_workflow_name=workflows[0].name if workflows else None,
        recent_activity=recent_activity_items,
        active_alerts=alert_items,
        maturity_stage=maturity_stage,
        unprocessed_doc_count=unprocessed,
        daily_guidance=daily_guidance,
        since_last_visit=since_last_visit,
    )


@router.post("/first-session-complete", status_code=204)
async def mark_first_session_complete(user: User = Depends(get_current_user)):
    """Mark the first-session onboarding as completed so it won't show again."""
    if not user.first_session_completed:
        user.first_session_completed = True
        await user.save()


# ---------------------------------------------------------------------------
# Automation stats
# ---------------------------------------------------------------------------


@router.get("/automation-stats")
async def get_automation_stats(user: User = Depends(get_current_user)):
    visible_workflows = await workflow_service.list_workflows(
        user=user,
        skip=0,
        limit=5000,
    )
    total = len(visible_workflows)

    passive = [
        w for w in visible_workflows
        if w.input_config.get("folder_watch", {}).get("enabled")
    ]
    passive_count = len(passive)

    watched_folders = set()
    for w in passive:
        for f in w.input_config.get("folder_watch", {}).get("folders", []):
            watched_folders.add(f)

    # Recent runs (last 7 days)
    week_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    workflow_ids = [wf.id for wf in visible_workflows if getattr(wf, "id", None)]
    if workflow_ids:
        recent_results = await WorkflowResult.find({
            "workflow": {"$in": workflow_ids},
            "start_time": {"$gte": week_ago},
        }).limit(10000).to_list()
    else:
        recent_results = []

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
