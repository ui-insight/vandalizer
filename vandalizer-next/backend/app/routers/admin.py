"""Admin API routes  - usage stats, leaderboards, system config management."""

import datetime
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.models.activity import ActivityEvent
from app.models.system_config import SystemConfig
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.models.workflow import Workflow, WorkflowResult

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_admin(user: User) -> User:
    """Raise 403 if the user is not an admin."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _require_admin_or_team_admin(user: User) -> tuple[User, str | None]:
    """Allow global admins (no scope) or team admins/owners (scoped to current team).

    Returns (user, team_id) where team_id is None for global admins or the
    stringified team ObjectId for team admins.
    """
    if user.is_admin:
        return user, None

    if not user.current_team:
        raise HTTPException(status_code=403, detail="Admin access required")

    membership = await TeamMembership.find_one(
        TeamMembership.team == user.current_team,
        TeamMembership.user_id == user.user_id,
    )
    if not membership or membership.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    return user, str(user.current_team)


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class UsageStatsResponse(BaseModel):
    conversations: int = 0
    search_runs: int = 0
    workflows_started: int = 0
    workflows_completed: int = 0
    workflows_failed: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    active_users: int = 0
    active_teams: int = 0


class UserLeaderboardItem(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    tokens_total: int = 0
    workflows_run: int = 0
    last_active: Optional[datetime.datetime] = None


class TeamLeaderboardItem(BaseModel):
    team_id: str
    name: str
    uuid: str
    tokens_total: int = 0
    workflows_completed: int = 0
    active_users: int = 0
    avg_latency_ms: Optional[float] = None


class WorkflowEventItem(BaseModel):
    id: str
    status: str
    title: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    started_at: Optional[datetime.datetime] = None
    finished_at: Optional[datetime.datetime] = None
    duration_ms: Optional[int] = None
    tokens_in: int = 0
    tokens_out: int = 0
    steps_completed: int = 0
    steps_total: int = 0


class PaginatedWorkflowResponse(BaseModel):
    items: list[WorkflowEventItem]
    total: int
    page: int
    pages: int


class ConfigUpdateRequest(BaseModel):
    extraction_config: Optional[dict] = None
    ocr_endpoint: Optional[str] = None
    llm_endpoint: Optional[str] = None


class ModelAddRequest(BaseModel):
    name: str
    tag: str
    external: bool = False
    thinking: bool = False
    endpoint: Optional[str] = ""
    api_protocol: Optional[str] = ""
    api_key: Optional[str] = ""


class OAuthProviderRequest(BaseModel):
    provider: str
    display_name: str
    client_id: str
    client_secret: str
    redirect_uri: str
    tenant_id: Optional[str] = None
    metadata_url: Optional[str] = None
    entity_id: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None


class AuthMethodsRequest(BaseModel):
    methods: list[str]


# ---------------------------------------------------------------------------
# 1. GET /usage  - Usage stats dashboard
# ---------------------------------------------------------------------------

@router.get("/usage", response_model=UsageStatsResponse)
async def usage_stats(
    days: int = Query(default=30, ge=1),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    query_filter: dict = {"started_at": {"$gte": cutoff}}
    if team_scope:
        query_filter["team_id"] = team_scope
    events = await ActivityEvent.find(query_filter).to_list()

    conversations = 0
    search_runs = 0
    workflows_started = 0
    workflows_completed = 0
    workflows_failed = 0
    tokens_in = 0
    tokens_out = 0
    user_ids: set[str] = set()
    team_ids: set[str] = set()

    for ev in events:
        if ev.type == "conversation":
            conversations += 1
        elif ev.type == "search_set_run":
            search_runs += 1
        elif ev.type == "workflow_run":
            workflows_started += 1
            if ev.status == "completed":
                workflows_completed += 1
            elif ev.status == "failed":
                workflows_failed += 1

        tokens_in += ev.tokens_input or 0
        tokens_out += ev.tokens_output or 0
        user_ids.add(ev.user_id)
        if ev.team_id:
            team_ids.add(ev.team_id)

    return UsageStatsResponse(
        conversations=conversations,
        search_runs=search_runs,
        workflows_started=workflows_started,
        workflows_completed=workflows_completed,
        workflows_failed=workflows_failed,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        active_users=len(user_ids),
        active_teams=len(team_ids),
    )


# ---------------------------------------------------------------------------
# 2. GET /users  - User leaderboard
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserLeaderboardItem])
async def user_leaderboard(
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    query_filter: dict = {}
    if team_scope:
        query_filter["team_id"] = team_scope
    events = await ActivityEvent.find(query_filter).to_list()

    # Aggregate per user
    user_agg: dict[str, dict] = {}
    for ev in events:
        uid = ev.user_id
        if uid not in user_agg:
            user_agg[uid] = {"tokens_total": 0, "workflows_run": 0, "last_active": None}
        agg = user_agg[uid]
        agg["tokens_total"] += (ev.tokens_input or 0) + (ev.tokens_output or 0)
        if ev.type == "workflow_run":
            agg["workflows_run"] += 1
        ts = ev.started_at
        if ts and (agg["last_active"] is None or ts > agg["last_active"]):
            agg["last_active"] = ts

    # Fetch user records
    all_users = await User.find().to_list()
    user_map = {u.user_id: u for u in all_users}

    # Build result list
    result: list[UserLeaderboardItem] = []
    for uid, agg in user_agg.items():
        u = user_map.get(uid)
        result.append(
            UserLeaderboardItem(
                user_id=uid,
                name=u.name if u else None,
                email=u.email if u else None,
                tokens_total=agg["tokens_total"],
                workflows_run=agg["workflows_run"],
                last_active=agg["last_active"],
            )
        )

    # Sort by tokens desc, take top 100
    result.sort(key=lambda x: x.tokens_total, reverse=True)
    return result[:100]


# ---------------------------------------------------------------------------
# 3. GET /teams  - Team leaderboard
# ---------------------------------------------------------------------------

@router.get("/teams", response_model=list[TeamLeaderboardItem])
async def team_leaderboard(
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    query_filter: dict = {}
    if team_scope:
        query_filter["team_id"] = team_scope
    events = await ActivityEvent.find(query_filter).to_list()

    # Aggregate per team
    team_agg: dict[str, dict] = {}
    for ev in events:
        tid = ev.team_id
        if not tid:
            continue
        if tid not in team_agg:
            team_agg[tid] = {
                "tokens_total": 0,
                "workflows_completed": 0,
                "user_ids": set(),
                "latencies": [],
            }
        agg = team_agg[tid]
        agg["tokens_total"] += (ev.tokens_input or 0) + (ev.tokens_output or 0)
        agg["user_ids"].add(ev.user_id)
        if ev.type == "workflow_run" and ev.status == "completed":
            agg["workflows_completed"] += 1
            if ev.started_at and ev.finished_at:
                delta_ms = int((ev.finished_at - ev.started_at).total_seconds() * 1000)
                agg["latencies"].append(delta_ms)

    # Fetch team records  - map by str(id)
    all_teams = await Team.find().to_list()
    team_map = {str(t.id): t for t in all_teams}

    result: list[TeamLeaderboardItem] = []
    for tid, agg in team_agg.items():
        t = team_map.get(tid)
        avg_lat = None
        if agg["latencies"]:
            avg_lat = sum(agg["latencies"]) / len(agg["latencies"])
        result.append(
            TeamLeaderboardItem(
                team_id=tid,
                name=t.name if t else "Unknown",
                uuid=t.uuid if t else tid,
                tokens_total=agg["tokens_total"],
                workflows_completed=agg["workflows_completed"],
                active_users=len(agg["user_ids"]),
                avg_latency_ms=avg_lat,
            )
        )

    result.sort(key=lambda x: x.tokens_total, reverse=True)
    return result


# ---------------------------------------------------------------------------
# 4. GET /workflows  - Paginated workflow events
# ---------------------------------------------------------------------------

@router.get("/workflows", response_model=PaginatedWorkflowResponse)
async def workflow_events(
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    query_filter: dict = {"type": "workflow_run"}
    if team_scope:
        query_filter["team_id"] = team_scope
    if status:
        query_filter["status"] = status

    total = await ActivityEvent.find(query_filter).count()
    pages = max(1, math.ceil(total / per_page))
    skip = (page - 1) * per_page

    events = await ActivityEvent.find(query_filter).sort(
        -ActivityEvent.started_at
    ).skip(skip).limit(per_page).to_list()

    items: list[WorkflowEventItem] = []
    for ev in events:
        duration = None
        if ev.started_at and ev.finished_at:
            duration = int((ev.finished_at - ev.started_at).total_seconds() * 1000)
        items.append(
            WorkflowEventItem(
                id=str(ev.id),
                status=ev.status,
                title=ev.title,
                user_id=ev.user_id,
                team_id=ev.team_id,
                started_at=ev.started_at,
                finished_at=ev.finished_at,
                duration_ms=duration,
                tokens_in=ev.tokens_input or 0,
                tokens_out=ev.tokens_output or 0,
                steps_completed=ev.steps_completed or 0,
                steps_total=ev.steps_total or 0,
            )
        )

    return PaginatedWorkflowResponse(
        items=items,
        total=total,
        page=page,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# 5. GET /config  - Full system config
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config(
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    return {
        "extraction_config": cfg.get_extraction_config(),
        "auth_methods": cfg.auth_methods,
        "oauth_providers": cfg.oauth_providers,
        "available_models": cfg.available_models,
        "ocr_endpoint": cfg.ocr_endpoint,
        "llm_endpoint": cfg.llm_endpoint,
        "highlight_color": cfg.highlight_color,
        "ui_radius": cfg.ui_radius,
    }


# ---------------------------------------------------------------------------
# 6. PUT /config  - Update system config
# ---------------------------------------------------------------------------

@router.put("/config")
async def update_config(
    body: ConfigUpdateRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()

    if body.extraction_config is not None:
        cfg.extraction_config = body.extraction_config
    if body.ocr_endpoint is not None:
        cfg.ocr_endpoint = body.ocr_endpoint
    if body.llm_endpoint is not None:
        cfg.llm_endpoint = body.llm_endpoint

    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 7. POST /config/models  - Add a model
# ---------------------------------------------------------------------------

@router.post("/config/models")
async def add_model(
    body: ModelAddRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    cfg.available_models.append(
        {
            "name": body.name,
            "tag": body.tag,
            "external": body.external,
            "thinking": body.thinking,
            "endpoint": body.endpoint or "",
            "api_protocol": body.api_protocol or "",
            "api_key": body.api_key or "",
        }
    )
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "models": cfg.available_models}


# ---------------------------------------------------------------------------
# 7b. PUT /config/models/{index}  - Update an existing model
# ---------------------------------------------------------------------------

@router.put("/config/models/{index}")
async def update_model(
    index: int,
    body: ModelAddRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.available_models):
        raise HTTPException(status_code=404, detail="Model index out of range")

    cfg.available_models[index] = {
        "name": body.name,
        "tag": body.tag,
        "external": body.external,
        "thinking": body.thinking,
        "endpoint": body.endpoint or "",
        "api_protocol": body.api_protocol or "",
        "api_key": body.api_key or "",
    }
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "models": cfg.available_models}


# ---------------------------------------------------------------------------
# 8. DELETE /config/models/{index}  - Remove a model by index
# ---------------------------------------------------------------------------

@router.delete("/config/models/{index}")
async def delete_model(
    index: int,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.available_models):
        raise HTTPException(status_code=404, detail="Model index out of range")

    removed = cfg.available_models.pop(index)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "removed": removed, "models": cfg.available_models}


# ---------------------------------------------------------------------------
# 9. POST /config/auth/providers  - Add OAuth provider
# ---------------------------------------------------------------------------

@router.post("/config/auth/providers")
async def add_oauth_provider(
    body: OAuthProviderRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    provider_dict = body.model_dump(exclude_none=True)
    cfg.oauth_providers.append(provider_dict)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "providers": cfg.oauth_providers}


# ---------------------------------------------------------------------------
# 10. PUT /config/auth/providers/{index}  - Update OAuth provider
# ---------------------------------------------------------------------------

@router.put("/config/auth/providers/{index}")
async def update_oauth_provider(
    index: int,
    body: OAuthProviderRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.oauth_providers):
        raise HTTPException(status_code=404, detail="Provider index out of range")

    cfg.oauth_providers[index] = body.model_dump(exclude_none=True)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "providers": cfg.oauth_providers}


# ---------------------------------------------------------------------------
# 11. DELETE /config/auth/providers/{index}  - Remove OAuth provider
# ---------------------------------------------------------------------------

@router.delete("/config/auth/providers/{index}")
async def delete_oauth_provider(
    index: int,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.oauth_providers):
        raise HTTPException(status_code=404, detail="Provider index out of range")

    removed = cfg.oauth_providers.pop(index)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "removed": removed, "providers": cfg.oauth_providers}


# ---------------------------------------------------------------------------
# 12. PUT /config/auth/methods  - Update auth methods
# ---------------------------------------------------------------------------

@router.put("/config/auth/methods")
async def update_auth_methods(
    body: AuthMethodsRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    cfg.auth_methods = body.methods
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()

    return {"status": "ok", "auth_methods": cfg.auth_methods}
