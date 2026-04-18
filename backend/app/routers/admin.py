"""Admin API routes  - usage stats, leaderboards, system config management."""

import datetime
import math
import re
from typing import Optional

from bson import ObjectId as BsonObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.models.activity import ActivityEvent
from app.models.audit_log import AdminAuditLog
from app.models.system_config import SystemConfig
from app.services.llm_service import clear_agent_caches, get_agent_model
from app.utils.encryption import decrypt_value, encrypt_value
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.models.document import SmartDocument

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_admin(user: User) -> User:
    """Raise 403 if the user is not an admin or staff member."""
    if not (user.is_admin or user.is_staff):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _require_superadmin(user: User) -> User:
    """Raise 403 if the user is not a full admin (staff cannot access)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _sanitize_providers(providers: list[dict]) -> list[dict]:
    """Replace client_secret values with '***' in OAuth provider dicts."""
    sanitized = []
    for p in providers:
        p_copy = dict(p)
        secret = p_copy.get("client_secret", "")
        if secret:
            # Decrypt to check if a real value exists, then mask it
            p_copy["client_secret"] = "***" if decrypt_value(secret) else ""
        sanitized.append(p_copy)
    return sanitized


def _sanitize_models(models: list[dict]) -> list[dict]:
    """Replace api_key values with '***' in model config dicts."""
    sanitized = []
    for m in models:
        m_copy = dict(m)
        key = m_copy.get("api_key", "")
        if key:
            # Decrypt to check if a real value exists, then mask it
            m_copy["api_key"] = "***" if decrypt_value(key) else ""
        sanitized.append(m_copy)
    return sanitized


async def _audit(user: User, action: str, detail: str, payload: dict | None = None) -> None:
    """Fire-and-forget audit log entry for state-changing admin actions."""
    entry = AdminAuditLog(user_id=user.user_id, action=action, detail=detail, payload=payload)
    await entry.insert()


async def _require_admin_or_team_admin(user: User) -> tuple[User, str | None]:
    """Allow global admins (no scope) or team admins/owners (scoped to current team).

    Returns (user, team_id) where team_id is None for global admins or the
    stringified team ObjectId for team admins.
    """
    if user.is_admin or user.is_staff:
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


async def _get_team_by_identifier(team_id: str) -> Team | None:
    """Resolve a team from either its Mongo ObjectId string or UUID."""
    if len(team_id) == 24:
        try:
            team = await Team.find_one({"_id": BsonObjectId(team_id)})
            if team:
                return team
        except Exception:
            pass
    return await Team.find_one({"uuid": team_id})


def _team_scope_identifiers(team: Team | None, *, fallback: str | None = None) -> list[str]:
    """Return all known identifiers that may appear on team-scoped resources."""
    identifiers: set[str] = set()
    if fallback:
        identifiers.add(fallback)
    if team:
        if getattr(team, "uuid", None):
            identifiers.add(team.uuid)
        if getattr(team, "id", None):
            identifiers.add(str(team.id))
    return sorted(identifiers)


async def _resolve_team_scope(team_id: str | None) -> tuple[Team | None, list[str]]:
    """Resolve a team plus every identifier that may be stored on scoped records."""
    if not team_id:
        return None, []
    team = await _get_team_by_identifier(team_id)
    return team, _team_scope_identifiers(team, fallback=team_id)


def _can_view_platform_role_flags(team_scope: str | None) -> bool:
    """Only global admins should see installation-wide role flags in analytics views."""
    return team_scope is None


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
    is_admin: bool = False
    is_staff: bool = False
    is_examiner: bool = False
    tokens_total: int = 0
    workflows_run: int = 0
    conversations: int = 0
    last_active: Optional[datetime.datetime] = None


class TeamLeaderboardItem(BaseModel):
    team_id: str
    name: str
    uuid: str
    tokens_total: int = 0
    workflows_completed: int = 0
    active_users: int = 0
    member_count: int = 0
    avg_latency_ms: Optional[float] = None


class WorkflowEventItem(BaseModel):
    id: str
    status: str
    title: Optional[str] = None
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    started_at: Optional[datetime.datetime] = None
    finished_at: Optional[datetime.datetime] = None
    duration_ms: Optional[int] = None
    tokens_in: int = 0
    tokens_out: int = 0
    steps_completed: int = 0
    steps_total: int = 0
    error: Optional[str] = None


class WorkflowSummaryStats(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    running: int = 0
    success_rate: float = 0.0
    avg_duration_ms: Optional[float] = None
    total_tokens: int = 0


class PaginatedWorkflowResponse(BaseModel):
    items: list[WorkflowEventItem]
    total: int
    page: int
    pages: int
    summary: Optional[WorkflowSummaryStats] = None


class ConfigUpdateRequest(BaseModel):
    extraction_config: Optional[dict] = None
    quality_config: Optional[dict] = None
    ocr_endpoint: Optional[str] = None
    ocr_api_key: Optional[str] = None
    llm_endpoint: Optional[str] = None
    default_team_id: Optional[str] = None
    support_contacts: Optional[list[dict]] = None


class AdminTeamItem(BaseModel):
    team_id: str
    uuid: str
    name: str
    owner_user_id: str
    member_count: int
    is_default: bool


class AdminCreateTeamRequest(BaseModel):
    name: str


class AdminAddUserRequest(BaseModel):
    user_id: str
    role: str = "member"


class IsolatedUserItem(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None


class ModelAddRequest(BaseModel):
    name: str
    tag: str
    external: bool = False
    thinking: bool = False
    endpoint: Optional[str] = ""
    api_protocol: Optional[str] = ""
    api_key: Optional[str] = ""
    speed: Optional[str] = ""
    tier: Optional[str] = ""
    privacy: Optional[str] = ""
    supports_structured: bool = True
    multimodal: bool = False
    supports_pdf: bool = False
    context_window: int = 128000


class OAuthProviderRequest(BaseModel):
    provider: str
    display_name: str
    client_id: str
    client_secret: str
    redirect_uri: Optional[str] = None
    enabled: bool = True
    tenant_id: Optional[str] = None
    metadata_url: Optional[str] = None
    entity_id: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None


class AuthMethodsRequest(BaseModel):
    methods: list[str]


class TimeseriesDayItem(BaseModel):
    date: str  # YYYY-MM-DD
    conversations: int = 0
    search_runs: int = 0
    workflows_started: int = 0
    workflows_completed: int = 0
    workflows_failed: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    active_users: int = 0


class TimeseriesResponse(BaseModel):
    days: list[TimeseriesDayItem]
    previous_period: UsageStatsResponse


class TeamDetailMember(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    role: str = "member"
    tokens_total: int = 0
    workflows_run: int = 0
    conversations: int = 0
    last_active: Optional[datetime.datetime] = None


class TeamDetailResponse(BaseModel):
    team_id: str
    name: str
    uuid: str
    tokens_in: int = 0
    tokens_out: int = 0
    workflows_started: int = 0
    workflows_completed: int = 0
    workflows_failed: int = 0
    conversations: int = 0
    active_users: int = 0
    document_count: int = 0
    timeseries: list[TimeseriesDayItem] = []
    previous_period: UsageStatsResponse = Field(default_factory=UsageStatsResponse)
    members: list[TeamDetailMember] = []
    recent_workflows: list[WorkflowEventItem] = []


class UserDetailResponse(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False
    is_staff: bool = False
    is_examiner: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    workflows_started: int = 0
    workflows_completed: int = 0
    workflows_failed: int = 0
    conversations: int = 0
    document_count: int = 0
    timeseries: list[TimeseriesDayItem] = []
    previous_period: UsageStatsResponse = Field(default_factory=UsageStatsResponse)
    recent_workflows: list[WorkflowEventItem] = []


# ---------------------------------------------------------------------------
# 1. GET /usage  - Usage stats dashboard
# ---------------------------------------------------------------------------

@router.get("/usage", response_model=UsageStatsResponse)
async def usage_stats(
    days: int = Query(default=30, ge=1),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    query_filter: dict = {"started_at": {"$gte": cutoff}}
    if team_scope:
        _, team_scope_ids = await _resolve_team_scope(team_scope)
        query_filter["team_id"] = {"$in": team_scope_ids}
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
# 1b. GET /usage/timeseries  - Daily breakdown for charts + previous period
# ---------------------------------------------------------------------------

@router.get("/usage/timeseries", response_model=TimeseriesResponse)
async def usage_timeseries(
    days: int = Query(default=30, ge=1),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=days)
    prev_cutoff = cutoff - datetime.timedelta(days=days)

    query_filter: dict = {"started_at": {"$gte": prev_cutoff}}
    if team_scope:
        _, team_scope_ids = await _resolve_team_scope(team_scope)
        query_filter["team_id"] = {"$in": team_scope_ids}
    events = await ActivityEvent.find(query_filter).to_list()

    # Build daily buckets for current period
    daily: dict[str, dict] = {}
    for i in range(days):
        d = (cutoff + datetime.timedelta(days=i + 1)).strftime("%Y-%m-%d")
        daily[d] = {
            "conversations": 0, "search_runs": 0,
            "workflows_started": 0, "workflows_completed": 0, "workflows_failed": 0,
            "tokens_in": 0, "tokens_out": 0, "user_ids": set(),
        }

    # Previous period aggregates
    prev = {
        "conversations": 0, "search_runs": 0,
        "workflows_started": 0, "workflows_completed": 0, "workflows_failed": 0,
        "tokens_in": 0, "tokens_out": 0, "user_ids": set(), "team_ids": set(),
    }

    for ev in events:
        ts = ev.started_at
        if not ts:
            continue
        day_str = ts.strftime("%Y-%m-%d")

        if ts >= cutoff:
            bucket = daily.get(day_str)
            if bucket:
                if ev.type == "conversation":
                    bucket["conversations"] += 1
                elif ev.type == "search_set_run":
                    bucket["search_runs"] += 1
                elif ev.type == "workflow_run":
                    bucket["workflows_started"] += 1
                    if ev.status == "completed":
                        bucket["workflows_completed"] += 1
                    elif ev.status == "failed":
                        bucket["workflows_failed"] += 1
                bucket["tokens_in"] += ev.tokens_input or 0
                bucket["tokens_out"] += ev.tokens_output or 0
                bucket["user_ids"].add(ev.user_id)
        else:
            # Previous period
            if ev.type == "conversation":
                prev["conversations"] += 1
            elif ev.type == "search_set_run":
                prev["search_runs"] += 1
            elif ev.type == "workflow_run":
                prev["workflows_started"] += 1
                if ev.status == "completed":
                    prev["workflows_completed"] += 1
                elif ev.status == "failed":
                    prev["workflows_failed"] += 1
            prev["tokens_in"] += ev.tokens_input or 0
            prev["tokens_out"] += ev.tokens_output or 0
            prev["user_ids"].add(ev.user_id)
            if ev.team_id:
                prev["team_ids"].add(ev.team_id)

    day_items = []
    for d_str in sorted(daily.keys()):
        b = daily[d_str]
        day_items.append(TimeseriesDayItem(
            date=d_str,
            conversations=b["conversations"],
            search_runs=b["search_runs"],
            workflows_started=b["workflows_started"],
            workflows_completed=b["workflows_completed"],
            workflows_failed=b["workflows_failed"],
            tokens_in=b["tokens_in"],
            tokens_out=b["tokens_out"],
            active_users=len(b["user_ids"]),
        ))

    previous_period = UsageStatsResponse(
        conversations=prev["conversations"],
        search_runs=prev["search_runs"],
        workflows_started=prev["workflows_started"],
        workflows_completed=prev["workflows_completed"],
        workflows_failed=prev["workflows_failed"],
        tokens_in=prev["tokens_in"],
        tokens_out=prev["tokens_out"],
        active_users=len(prev["user_ids"]),
        active_teams=len(prev["team_ids"]),
    )

    return TimeseriesResponse(days=day_items, previous_period=previous_period)


# ---------------------------------------------------------------------------
# 2. GET /users  - User leaderboard
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserLeaderboardItem])
async def user_leaderboard(
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)
    show_platform_role_flags = _can_view_platform_role_flags(team_scope)

    query_filter: dict = {}
    scoped_team: Team | None = None
    if team_scope:
        scoped_team, team_scope_ids = await _resolve_team_scope(team_scope)
        query_filter["team_id"] = {"$in": team_scope_ids}
    events = await ActivityEvent.find(query_filter).to_list()

    # Aggregate per user
    user_agg: dict[str, dict] = {}
    for ev in events:
        uid = ev.user_id
        if uid not in user_agg:
            user_agg[uid] = {"tokens_total": 0, "workflows_run": 0, "conversations": 0, "last_active": None}
        agg = user_agg[uid]
        agg["tokens_total"] += (ev.tokens_input or 0) + (ev.tokens_output or 0)
        if ev.type == "workflow_run":
            agg["workflows_run"] += 1
        elif ev.type == "conversation":
            agg["conversations"] += 1
        ts = ev.started_at
        if ts and (agg["last_active"] is None or ts > agg["last_active"]):
            agg["last_active"] = ts

    # Fetch user records — scope to team members when team-scoped
    if team_scope:
        if not scoped_team:
            return []
        team_memberships = await TeamMembership.find(
            TeamMembership.team == scoped_team.id
        ).to_list()
        team_user_ids = [m.user_id for m in team_memberships]
        all_users = await User.find({"user_id": {"$in": team_user_ids}}).to_list()
    else:
        all_users = await User.find().limit(10000).to_list()
    user_map = {u.user_id: u for u in all_users}

    # Build result list — include ALL users, not just those with activity
    result: list[UserLeaderboardItem] = []
    seen_uids: set[str] = set()
    for uid, agg in user_agg.items():
        seen_uids.add(uid)
        u = user_map.get(uid)
        result.append(
            UserLeaderboardItem(
                user_id=uid,
                name=u.name if u else None,
                email=u.email if u else None,
                is_admin=(u.is_admin if u and show_platform_role_flags else False),
                is_staff=(
                    getattr(u, "is_staff", False)
                    if u and show_platform_role_flags
                    else False
                ),
                is_examiner=(
                    getattr(u, "is_examiner", False)
                    if u and show_platform_role_flags
                    else False
                ),
                tokens_total=agg["tokens_total"],
                workflows_run=agg["workflows_run"],
                conversations=agg["conversations"],
                last_active=agg["last_active"],
            )
        )

    # Include users with no activity events (e.g. new demo users)
    for u in all_users:
        if u.user_id not in seen_uids:
            result.append(
                UserLeaderboardItem(
                    user_id=u.user_id,
                    name=u.name,
                    email=u.email,
                    is_admin=(u.is_admin if show_platform_role_flags else False),
                    is_staff=(
                        getattr(u, "is_staff", False)
                        if show_platform_role_flags
                        else False
                    ),
                    is_examiner=(
                        getattr(u, "is_examiner", False)
                        if show_platform_role_flags
                        else False
                    ),
                )
            )

    # Sort by tokens desc
    result.sort(key=lambda x: x.tokens_total, reverse=True)
    return result


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
        _, team_scope_ids = await _resolve_team_scope(team_scope)
        query_filter["team_id"] = {"$in": team_scope_ids}
    events = await ActivityEvent.find(query_filter).to_list()

    all_teams = await Team.find().limit(10000).to_list()
    team_lookup: dict[str, Team] = {}
    for team in all_teams:
        team_lookup[str(team.id)] = team
        if getattr(team, "uuid", None):
            team_lookup[team.uuid] = team

    # Aggregate per canonical team id so mixed UUID/ObjectId activity history rolls up together.
    team_agg: dict[str, dict] = {}
    for ev in events:
        raw_tid = ev.team_id
        if not raw_tid:
            continue
        team = team_lookup.get(raw_tid)
        tid = str(team.id) if team else raw_tid
        if tid not in team_agg:
            team_agg[tid] = {
                "tokens_total": 0,
                "workflows_completed": 0,
                "user_ids": set(),
                "latencies": [],
                "team": team,
            }
        agg = team_agg[tid]
        if team and not agg.get("team"):
            agg["team"] = team
        agg["tokens_total"] += (ev.tokens_input or 0) + (ev.tokens_output or 0)
        agg["user_ids"].add(ev.user_id)
        if ev.type == "workflow_run" and ev.status == "completed":
            agg["workflows_completed"] += 1
            if ev.started_at and ev.finished_at:
                delta_ms = int((ev.finished_at - ev.started_at).total_seconds() * 1000)
                agg["latencies"].append(delta_ms)

    # Fetch member counts per team
    all_memberships = await TeamMembership.find().limit(50000).to_list()
    member_counts: dict[str, int] = {}
    for m in all_memberships:
        tid_str = str(m.team) if m.team else ""
        member_counts[tid_str] = member_counts.get(tid_str, 0) + 1

    result: list[TeamLeaderboardItem] = []
    for tid, agg in team_agg.items():
        t = agg.get("team") or team_lookup.get(tid)
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
                member_count=member_counts.get(tid, 0),
                avg_latency_ms=avg_lat,
            )
        )

    result.sort(key=lambda x: x.tokens_total, reverse=True)
    return result


# ---------------------------------------------------------------------------
# 3b. GET /teams/{team_id}/detail  - Team drill-down
# ---------------------------------------------------------------------------

@router.get("/teams/{team_id}/detail", response_model=TeamDetailResponse)
async def team_detail(
    team_id: str,
    days: int = Query(default=30, ge=1),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    # Fetch team record
    team = await _get_team_by_identifier(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team_scope_ids = _team_scope_identifiers(team, fallback=team_id)

    # Team admins can only see their own team, regardless of whether the route
    # uses the team's UUID or ObjectId-style identifier.
    if team_scope:
        _, caller_scope_ids = await _resolve_team_scope(team_scope)
        if not set(team_scope_ids) & set(caller_scope_ids):
            raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=days)
    prev_cutoff = cutoff - datetime.timedelta(days=days)

    events = await ActivityEvent.find(
        {"team_id": {"$in": team_scope_ids}, "started_at": {"$gte": prev_cutoff}}
    ).to_list()

    # Split current vs previous period
    cur_events = [e for e in events if e.started_at and e.started_at >= cutoff]
    prev_events = [e for e in events if e.started_at and e.started_at < cutoff]

    # KPIs
    conversations = sum(1 for e in cur_events if e.type == "conversation")
    workflows_started = sum(1 for e in cur_events if e.type == "workflow_run")
    workflows_completed = sum(1 for e in cur_events if e.type == "workflow_run" and e.status == "completed")
    workflows_failed = sum(1 for e in cur_events if e.type == "workflow_run" and e.status == "failed")
    tokens_in = sum(e.tokens_input or 0 for e in cur_events)
    tokens_out = sum(e.tokens_output or 0 for e in cur_events)
    user_ids = {e.user_id for e in cur_events}

    # Previous period KPIs
    prev_convos = sum(1 for e in prev_events if e.type == "conversation")
    prev_wf_started = sum(1 for e in prev_events if e.type == "workflow_run")
    prev_wf_completed = sum(1 for e in prev_events if e.type == "workflow_run" and e.status == "completed")
    prev_wf_failed = sum(1 for e in prev_events if e.type == "workflow_run" and e.status == "failed")
    prev_tokens_in = sum(e.tokens_input or 0 for e in prev_events)
    prev_tokens_out = sum(e.tokens_output or 0 for e in prev_events)
    prev_users = {e.user_id for e in prev_events}

    previous_period = UsageStatsResponse(
        conversations=prev_convos,
        workflows_started=prev_wf_started,
        workflows_completed=prev_wf_completed,
        workflows_failed=prev_wf_failed,
        tokens_in=prev_tokens_in,
        tokens_out=prev_tokens_out,
        active_users=len(prev_users),
    )

    # Timeseries
    daily: dict[str, dict] = {}
    for i in range(days):
        d = (cutoff + datetime.timedelta(days=i + 1)).strftime("%Y-%m-%d")
        daily[d] = {
            "conversations": 0, "search_runs": 0,
            "workflows_started": 0, "workflows_completed": 0, "workflows_failed": 0,
            "tokens_in": 0, "tokens_out": 0, "user_ids": set(),
        }
    for ev in cur_events:
        ts = ev.started_at
        if not ts:
            continue
        day_str = ts.strftime("%Y-%m-%d")
        bucket = daily.get(day_str)
        if bucket:
            if ev.type == "conversation":
                bucket["conversations"] += 1
            elif ev.type == "search_set_run":
                bucket["search_runs"] += 1
            elif ev.type == "workflow_run":
                bucket["workflows_started"] += 1
                if ev.status == "completed":
                    bucket["workflows_completed"] += 1
                elif ev.status == "failed":
                    bucket["workflows_failed"] += 1
            bucket["tokens_in"] += ev.tokens_input or 0
            bucket["tokens_out"] += ev.tokens_output or 0
            bucket["user_ids"].add(ev.user_id)

    timeseries = [
        TimeseriesDayItem(
            date=d, conversations=b["conversations"], search_runs=b["search_runs"],
            workflows_started=b["workflows_started"], workflows_completed=b["workflows_completed"],
            workflows_failed=b["workflows_failed"], tokens_in=b["tokens_in"],
            tokens_out=b["tokens_out"], active_users=len(b["user_ids"]),
        )
        for d, b in sorted(daily.items())
    ]

    # Members
    memberships = await TeamMembership.find(
        TeamMembership.team == team.id
    ).to_list()
    member_user_ids = [m.user_id for m in memberships]
    member_role_map = {m.user_id: m.role for m in memberships}

    all_users = await User.find({"user_id": {"$in": member_user_ids}}).to_list() if member_user_ids else []
    user_map = {u.user_id: u for u in all_users}

    # Per-member stats from current events
    member_agg: dict[str, dict] = {uid: {"tokens_total": 0, "workflows_run": 0, "conversations": 0, "last_active": None} for uid in member_user_ids}
    for ev in cur_events:
        agg = member_agg.get(ev.user_id)
        if not agg:
            continue
        agg["tokens_total"] += (ev.tokens_input or 0) + (ev.tokens_output or 0)
        if ev.type == "workflow_run":
            agg["workflows_run"] += 1
        elif ev.type == "conversation":
            agg["conversations"] += 1
        ts = ev.started_at
        if ts and (agg["last_active"] is None or ts > agg["last_active"]):
            agg["last_active"] = ts

    members = []
    for uid in member_user_ids:
        u = user_map.get(uid)
        agg = member_agg[uid]
        members.append(TeamDetailMember(
            user_id=uid,
            name=u.name if u else None,
            email=u.email if u else None,
            role=member_role_map.get(uid, "member"),
            tokens_total=agg["tokens_total"],
            workflows_run=agg["workflows_run"],
            conversations=agg["conversations"],
            last_active=agg["last_active"],
        ))
    members.sort(key=lambda m: m.tokens_total, reverse=True)

    # Document count
    doc_count = await SmartDocument.find(
        {"team_id": {"$in": team_scope_ids}}
    ).count()

    # Recent workflows
    recent_wf_events = await ActivityEvent.find(
        {"team_id": {"$in": team_scope_ids}, "type": "workflow_run"}
    ).sort(-ActivityEvent.started_at).limit(20).to_list()

    recent_workflows = []
    for ev in recent_wf_events:
        duration = None
        if ev.started_at and ev.finished_at:
            duration = int((ev.finished_at - ev.started_at).total_seconds() * 1000)
        u = user_map.get(ev.user_id)
        recent_workflows.append(WorkflowEventItem(
            id=str(ev.id), status=ev.status, title=ev.title,
            user_id=ev.user_id, user_name=u.name if u else None,
            user_email=u.email if u else None,
            team_id=ev.team_id, team_name=team.name,
            started_at=ev.started_at, finished_at=ev.finished_at,
            duration_ms=duration, tokens_in=ev.tokens_input or 0,
            tokens_out=ev.tokens_output or 0,
            steps_completed=ev.steps_completed or 0,
            steps_total=ev.steps_total or 0, error=ev.error,
        ))

    return TeamDetailResponse(
        team_id=team_id, name=team.name, uuid=team.uuid,
        tokens_in=tokens_in, tokens_out=tokens_out,
        workflows_started=workflows_started,
        workflows_completed=workflows_completed,
        workflows_failed=workflows_failed,
        conversations=conversations,
        active_users=len(user_ids),
        document_count=doc_count,
        timeseries=timeseries,
        previous_period=previous_period,
        members=members,
        recent_workflows=recent_workflows,
    )


# ---------------------------------------------------------------------------
# 3c. GET /users/{user_id}/detail  - User drill-down
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}/detail", response_model=UserDetailResponse)
async def user_detail(
    user_id: str,
    days: int = Query(default=30, ge=1),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)
    show_platform_role_flags = _can_view_platform_role_flags(team_scope)
    scoped_team: Team | None = None
    team_scope_ids: list[str] = []

    # Team admins: verify the target user is a member of their team
    if team_scope:
        scoped_team, team_scope_ids = await _resolve_team_scope(team_scope)
        if not scoped_team:
            raise HTTPException(status_code=403, detail="Admin access required")
        membership = await TeamMembership.find_one(
            TeamMembership.team == scoped_team.id,
            TeamMembership.user_id == user_id,
        )
        if not membership:
            raise HTTPException(status_code=403, detail="User not in your team")

    # Fetch user record
    target_user = await User.find_one(User.user_id == user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=days)
    prev_cutoff = cutoff - datetime.timedelta(days=days)

    query_filter: dict = {"user_id": user_id, "started_at": {"$gte": prev_cutoff}}
    if team_scope:
        query_filter["team_id"] = {"$in": team_scope_ids}
    events = await ActivityEvent.find(query_filter).to_list()

    cur_events = [e for e in events if e.started_at and e.started_at >= cutoff]
    prev_events = [e for e in events if e.started_at and e.started_at < cutoff]

    # KPIs
    conversations = sum(1 for e in cur_events if e.type == "conversation")
    workflows_started = sum(1 for e in cur_events if e.type == "workflow_run")
    workflows_completed = sum(1 for e in cur_events if e.type == "workflow_run" and e.status == "completed")
    workflows_failed = sum(1 for e in cur_events if e.type == "workflow_run" and e.status == "failed")
    tokens_in = sum(e.tokens_input or 0 for e in cur_events)
    tokens_out = sum(e.tokens_output or 0 for e in cur_events)

    # Previous period
    prev_convos = sum(1 for e in prev_events if e.type == "conversation")
    prev_wf_started = sum(1 for e in prev_events if e.type == "workflow_run")
    prev_wf_completed = sum(1 for e in prev_events if e.type == "workflow_run" and e.status == "completed")
    prev_wf_failed = sum(1 for e in prev_events if e.type == "workflow_run" and e.status == "failed")
    prev_tokens_in = sum(e.tokens_input or 0 for e in prev_events)
    prev_tokens_out = sum(e.tokens_output or 0 for e in prev_events)

    previous_period = UsageStatsResponse(
        conversations=prev_convos,
        workflows_started=prev_wf_started,
        workflows_completed=prev_wf_completed,
        workflows_failed=prev_wf_failed,
        tokens_in=prev_tokens_in,
        tokens_out=prev_tokens_out,
    )

    # Timeseries
    daily: dict[str, dict] = {}
    for i in range(days):
        d = (cutoff + datetime.timedelta(days=i + 1)).strftime("%Y-%m-%d")
        daily[d] = {
            "conversations": 0, "search_runs": 0,
            "workflows_started": 0, "workflows_completed": 0, "workflows_failed": 0,
            "tokens_in": 0, "tokens_out": 0, "user_ids": set(),
        }
    for ev in cur_events:
        ts = ev.started_at
        if not ts:
            continue
        day_str = ts.strftime("%Y-%m-%d")
        bucket = daily.get(day_str)
        if bucket:
            if ev.type == "conversation":
                bucket["conversations"] += 1
            elif ev.type == "search_set_run":
                bucket["search_runs"] += 1
            elif ev.type == "workflow_run":
                bucket["workflows_started"] += 1
                if ev.status == "completed":
                    bucket["workflows_completed"] += 1
                elif ev.status == "failed":
                    bucket["workflows_failed"] += 1
            bucket["tokens_in"] += ev.tokens_input or 0
            bucket["tokens_out"] += ev.tokens_output or 0

    timeseries = [
        TimeseriesDayItem(
            date=d, conversations=b["conversations"], search_runs=b["search_runs"],
            workflows_started=b["workflows_started"], workflows_completed=b["workflows_completed"],
            workflows_failed=b["workflows_failed"], tokens_in=b["tokens_in"],
            tokens_out=b["tokens_out"], active_users=0,
        )
        for d, b in sorted(daily.items())
    ]

    # Document count
    doc_query: dict = {"user_id": user_id}
    if team_scope:
        doc_query["team_id"] = {"$in": team_scope_ids}
    doc_count = await SmartDocument.find(doc_query).count()

    # Recent workflows
    wf_filter: dict = {"user_id": user_id, "type": "workflow_run"}
    if team_scope:
        wf_filter["team_id"] = {"$in": team_scope_ids}
    recent_wf_events = await ActivityEvent.find(wf_filter).sort(
        -ActivityEvent.started_at
    ).limit(20).to_list()

    recent_workflows = []
    for ev in recent_wf_events:
        duration = None
        if ev.started_at and ev.finished_at:
            duration = int((ev.finished_at - ev.started_at).total_seconds() * 1000)
        recent_workflows.append(WorkflowEventItem(
            id=str(ev.id), status=ev.status, title=ev.title,
            user_id=ev.user_id, user_name=target_user.name,
            user_email=target_user.email,
            team_id=ev.team_id, started_at=ev.started_at,
            finished_at=ev.finished_at, duration_ms=duration,
            tokens_in=ev.tokens_input or 0, tokens_out=ev.tokens_output or 0,
            steps_completed=ev.steps_completed or 0,
            steps_total=ev.steps_total or 0, error=ev.error,
        ))

    return UserDetailResponse(
        user_id=user_id, name=target_user.name, email=target_user.email,
        is_admin=target_user.is_admin if show_platform_role_flags else False,
        is_staff=(
            getattr(target_user, "is_staff", False)
            if show_platform_role_flags
            else False
        ),
        is_examiner=(
            getattr(target_user, "is_examiner", False)
            if show_platform_role_flags
            else False
        ),
        tokens_in=tokens_in, tokens_out=tokens_out,
        workflows_started=workflows_started,
        workflows_completed=workflows_completed,
        workflows_failed=workflows_failed,
        conversations=conversations,
        document_count=doc_count,
        timeseries=timeseries,
        previous_period=previous_period,
        recent_workflows=recent_workflows,
    )


# ---------------------------------------------------------------------------
# 3c. PUT /users/{user_id}/roles  - Update platform roles
# ---------------------------------------------------------------------------


class UpdateRolesRequest(BaseModel):
    is_admin: Optional[bool] = None
    is_staff: Optional[bool] = None
    is_examiner: Optional[bool] = None


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    body: UpdateRolesRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    target = await User.find_one(User.user_id == user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if body.is_admin is not None:
        target.is_admin = body.is_admin
    if body.is_staff is not None:
        target.is_staff = body.is_staff
    if body.is_examiner is not None:
        target.is_examiner = body.is_examiner
    await target.save()

    await _audit(
        user, "update_user_roles",
        f"Updated roles for {user_id}: admin={target.is_admin}, staff={target.is_staff}, examiner={target.is_examiner}",
    )

    return {"ok": True}


# ---------------------------------------------------------------------------
# 4. GET /workflows  - Paginated workflow events
# ---------------------------------------------------------------------------

@router.get("/workflows", response_model=PaginatedWorkflowResponse)
async def workflow_events(
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    _, team_scope = await _require_admin_or_team_admin(user)

    query_filter: dict = {"type": "workflow_run"}
    if team_scope:
        _, team_scope_ids = await _resolve_team_scope(team_scope)
        query_filter["team_id"] = {"$in": team_scope_ids}
    if status:
        query_filter["status"] = status
    if search:
        query_filter["title"] = {"$regex": re.escape(search), "$options": "i"}

    total = await ActivityEvent.find(query_filter).count()
    pages = max(1, math.ceil(total / per_page))
    skip = (page - 1) * per_page

    events = await ActivityEvent.find(query_filter).sort(
        -ActivityEvent.started_at
    ).skip(skip).limit(per_page).to_list()

    # Resolve user and team names
    user_ids = list({ev.user_id for ev in events})
    team_ids = list({ev.team_id for ev in events if ev.team_id})
    all_users = await User.find({"user_id": {"$in": user_ids}}).to_list() if user_ids else []
    user_map = {u.user_id: u for u in all_users}
    object_id_team_ids = [BsonObjectId(t) for t in team_ids if len(t) == 24]
    uuid_team_ids = [t for t in team_ids if len(t) != 24]
    team_map: dict[str, Team] = {}
    if object_id_team_ids or uuid_team_ids:
        team_query: dict[str, dict[str, list]] = {"$or": []}
        if object_id_team_ids:
            team_query["$or"].append({"_id": {"$in": object_id_team_ids}})
        if uuid_team_ids:
            team_query["$or"].append({"uuid": {"$in": uuid_team_ids}})
        all_teams = await Team.find(team_query).to_list()
        for team in all_teams:
            team_map[str(team.id)] = team
            if getattr(team, "uuid", None):
                team_map[team.uuid] = team

    items: list[WorkflowEventItem] = []
    for ev in events:
        duration = None
        if ev.started_at and ev.finished_at:
            duration = int((ev.finished_at - ev.started_at).total_seconds() * 1000)
        u = user_map.get(ev.user_id)
        t = team_map.get(ev.team_id) if ev.team_id else None
        items.append(
            WorkflowEventItem(
                id=str(ev.id),
                status=ev.status,
                title=ev.title,
                user_id=ev.user_id,
                user_name=u.name if u else None,
                user_email=u.email if u else None,
                team_id=ev.team_id,
                team_name=t.name if t else None,
                started_at=ev.started_at,
                finished_at=ev.finished_at,
                duration_ms=duration,
                tokens_in=ev.tokens_input or 0,
                tokens_out=ev.tokens_output or 0,
                steps_completed=ev.steps_completed or 0,
                steps_total=ev.steps_total or 0,
                error=ev.error,
            )
        )

    # Compute summary stats across all matching workflows (not just this page)
    summary_filter: dict = {"type": "workflow_run"}
    if team_scope:
        _, team_scope_ids = await _resolve_team_scope(team_scope)
        summary_filter["team_id"] = {"$in": team_scope_ids}
    if search:
        summary_filter["title"] = {"$regex": re.escape(search), "$options": "i"}
    all_wf_events = await ActivityEvent.find(summary_filter).to_list()
    completed_count = sum(1 for e in all_wf_events if e.status == "completed")
    failed_count = sum(1 for e in all_wf_events if e.status == "failed")
    running_count = sum(1 for e in all_wf_events if e.status in ("running", "queued"))
    total_wf = len(all_wf_events)
    durations = []
    total_tokens = 0
    for e in all_wf_events:
        total_tokens += (e.tokens_input or 0) + (e.tokens_output or 0)
        if e.started_at and e.finished_at:
            durations.append(int((e.finished_at - e.started_at).total_seconds() * 1000))
    avg_dur = sum(durations) / len(durations) if durations else None
    success_rate = (completed_count / total_wf * 100) if total_wf > 0 else 0.0

    summary = WorkflowSummaryStats(
        total=total_wf,
        completed=completed_count,
        failed=failed_count,
        running=running_count,
        success_rate=round(success_rate, 1),
        avg_duration_ms=avg_dur,
        total_tokens=total_tokens,
    )

    return PaginatedWorkflowResponse(
        items=items,
        total=total,
        page=page,
        pages=pages,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 5. GET /config  - Full system config
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config(
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    return {
        "extraction_config": cfg.get_extraction_config(),
        "quality_config": cfg.get_quality_config(),
        "auth_methods": cfg.auth_methods,
        "oauth_providers": _sanitize_providers(cfg.oauth_providers),
        "available_models": _sanitize_models(cfg.available_models),
        "ocr_endpoint": cfg.ocr_endpoint,
        "ocr_api_key": "***" if decrypt_value(cfg.ocr_api_key) else "",
        "llm_endpoint": cfg.llm_endpoint,
        "highlight_color": cfg.highlight_color,
        "ui_radius": cfg.ui_radius,
        "default_team_id": cfg.default_team_id or "",
        "support_contacts": cfg.support_contacts,
        "m365_config": _sanitize_m365_config(cfg.get_m365_config()),
    }


# ---------------------------------------------------------------------------
# 6. PUT /config  - Update system config
# ---------------------------------------------------------------------------

@router.put("/config")
async def update_config(
    body: ConfigUpdateRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()

    if body.extraction_config is not None:
        cfg.extraction_config = body.extraction_config
    if body.quality_config is not None:
        cfg.quality_config = body.quality_config
    if body.ocr_endpoint is not None:
        cfg.ocr_endpoint = body.ocr_endpoint
    if body.ocr_api_key is not None and body.ocr_api_key != "***":
        cfg.ocr_api_key = encrypt_value(body.ocr_api_key)
    if body.llm_endpoint is not None:
        cfg.llm_endpoint = body.llm_endpoint
    if body.default_team_id is not None:
        cfg.default_team_id = body.default_team_id or None
    if body.support_contacts is not None:
        cfg.support_contacts = body.support_contacts

    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    clear_agent_caches()
    await _audit(user, "update_config", "Updated system configuration")

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 7. POST /config/models  - Add a model
# ---------------------------------------------------------------------------

@router.post("/config/models")
async def add_model(
    body: ModelAddRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    cfg.available_models.append(
        {
            "name": body.name,
            "tag": body.tag,
            "external": body.external,
            "thinking": body.thinking,
            "endpoint": body.endpoint or "",
            "api_protocol": body.api_protocol or "",
            "api_key": encrypt_value(body.api_key or ""),
            "speed": body.speed or "",
            "tier": body.tier or "",
            "privacy": body.privacy or "",
            "supports_structured": body.supports_structured,
            "multimodal": body.multimodal,
            "supports_pdf": body.supports_pdf,
            "context_window": body.context_window,
        }
    )
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    clear_agent_caches()
    await _audit(user, "add_model", f"Added model: {body.name} ({body.tag})")

    return {"status": "ok", "models": _sanitize_models(cfg.available_models)}


# ---------------------------------------------------------------------------
# 7b. PUT /config/models/{index}  - Update an existing model
# ---------------------------------------------------------------------------

@router.put("/config/models/{index}")
async def update_model(
    index: int,
    body: ModelAddRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.available_models):
        raise HTTPException(status_code=404, detail="Model index out of range")

    # If the client sends '***', preserve the existing (encrypted) key
    new_api_key = body.api_key or ""
    if new_api_key == "***":
        new_api_key = cfg.available_models[index].get("api_key", "")
    else:
        new_api_key = encrypt_value(new_api_key)

    cfg.available_models[index] = {
        "name": body.name,
        "tag": body.tag,
        "external": body.external,
        "thinking": body.thinking,
        "endpoint": body.endpoint or "",
        "api_protocol": body.api_protocol or "",
        "api_key": new_api_key,
        "speed": body.speed or "",
        "tier": body.tier or "",
        "privacy": body.privacy or "",
        "supports_structured": body.supports_structured,
        "multimodal": body.multimodal,
        "supports_pdf": body.supports_pdf,
        "context_window": body.context_window,
    }
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    clear_agent_caches()
    await _audit(user, "update_model", f"Updated model at index {index}: {body.tag}")

    return {"status": "ok", "models": _sanitize_models(cfg.available_models)}


# ---------------------------------------------------------------------------
# 8. DELETE /config/models/{index}  - Remove a model by index
# ---------------------------------------------------------------------------

@router.delete("/config/models/{index}")
async def delete_model(
    index: int,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.available_models):
        raise HTTPException(status_code=404, detail="Model index out of range")

    removed = cfg.available_models.pop(index)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    clear_agent_caches()
    await _audit(user, "delete_model", f"Deleted model at index {index}: {removed.get('tag', '?')}")

    return {"status": "ok", "removed": removed, "models": cfg.available_models}


# ---------------------------------------------------------------------------
# 9. POST /config/auth/providers  - Add OAuth provider
# ---------------------------------------------------------------------------

@router.post("/config/auth/providers")
async def add_oauth_provider(
    body: OAuthProviderRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    provider_dict = body.model_dump(exclude_none=True)
    provider_dict["enabled"] = True
    if provider_dict.get("client_secret"):
        provider_dict["client_secret"] = encrypt_value(provider_dict["client_secret"])
    cfg.oauth_providers.append(provider_dict)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    await _audit(user, "add_oauth_provider", f"Added OAuth provider: {body.provider}")

    return {"status": "ok", "providers": _sanitize_providers(cfg.oauth_providers)}


# ---------------------------------------------------------------------------
# 10. PUT /config/auth/providers/{index}  - Update OAuth provider
# ---------------------------------------------------------------------------

@router.put("/config/auth/providers/{index}")
async def update_oauth_provider(
    index: int,
    body: OAuthProviderRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.oauth_providers):
        raise HTTPException(status_code=404, detail="Provider index out of range")

    provider_dict = body.model_dump(exclude_none=True)
    # If the client sends '***', preserve the existing (encrypted) secret
    if provider_dict.get("client_secret") == "***":
        provider_dict["client_secret"] = cfg.oauth_providers[index].get("client_secret", "")
    elif provider_dict.get("client_secret"):
        provider_dict["client_secret"] = encrypt_value(provider_dict["client_secret"])
    cfg.oauth_providers[index] = provider_dict
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    await _audit(user, "update_oauth_provider", f"Updated OAuth provider at index {index}: {body.provider}")

    return {"status": "ok", "providers": _sanitize_providers(cfg.oauth_providers)}


# ---------------------------------------------------------------------------
# 11. DELETE /config/auth/providers/{index}  - Remove OAuth provider
# ---------------------------------------------------------------------------

@router.delete("/config/auth/providers/{index}")
async def delete_oauth_provider(
    index: int,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.oauth_providers):
        raise HTTPException(status_code=404, detail="Provider index out of range")

    removed = cfg.oauth_providers.pop(index)
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    await _audit(user, "delete_oauth_provider", f"Deleted OAuth provider at index {index}: {removed.get('provider', '?')}")

    return {"status": "ok", "removed": removed, "providers": cfg.oauth_providers}


# ---------------------------------------------------------------------------
# 12. PUT /config/auth/methods  - Update auth methods
# ---------------------------------------------------------------------------

@router.put("/config/auth/methods")
async def update_auth_methods(
    body: AuthMethodsRequest,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    cfg.auth_methods = body.methods
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    await _audit(user, "update_auth_methods", f"Updated auth methods: {body.methods}")

    return {"status": "ok", "auth_methods": cfg.auth_methods}


# ---------------------------------------------------------------------------
# 12b. GET/PUT /config/m365  - M365 integration config
# ---------------------------------------------------------------------------


def _sanitize_m365_config(cfg: dict) -> dict:
    """Mask the client_secret for safe display."""
    out = {**cfg}
    secret = out.get("client_secret", "")
    if secret and secret != "***":
        out["client_secret"] = "***"
    return out


@router.get("/config/m365")
async def get_m365_config(
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)
    cfg = await SystemConfig.get_config()
    return _sanitize_m365_config(cfg.get_m365_config())


@router.put("/config/m365")
async def update_m365_config(
    body: dict,
    user: User = Depends(get_current_user),
):
    await _require_superadmin(user)
    cfg = await SystemConfig.get_config()
    current = cfg.get_m365_config()

    if "enabled" in body:
        current["enabled"] = bool(body["enabled"])
    if "client_id" in body:
        current["client_id"] = body["client_id"]
    if "tenant_id" in body:
        current["tenant_id"] = body["tenant_id"]
    if "client_secret" in body and body["client_secret"] != "***":
        current["client_secret"] = encrypt_value(body["client_secret"])

    cfg.m365_config = current
    cfg.updated_at = datetime.datetime.now(datetime.timezone.utc)
    cfg.updated_by = user.user_id
    await cfg.save()
    await _audit(user, "update_m365_config", "Updated M365 integration configuration")

    return _sanitize_m365_config(cfg.get_m365_config())


# ---------------------------------------------------------------------------
# 13. GET /quality/summary  - Quality dashboard summary
# ---------------------------------------------------------------------------

@router.get("/quality/summary")
async def quality_summary(user: User = Depends(get_current_user)):
    await _require_admin(user)
    from app.services.quality_service import get_quality_summary
    return await get_quality_summary()


# ---------------------------------------------------------------------------
# 14. GET /quality/timeline  - Quality timeline for charts
# ---------------------------------------------------------------------------

@router.get("/quality/timeline")
async def quality_timeline(
    days: int = 90,
    item_kind: str | None = None,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    from app.services.quality_service import get_quality_timeline
    return {"timeline": await get_quality_timeline(days, item_kind)}


# ---------------------------------------------------------------------------
# 15. POST /quality/regression-suite  - Run regression on all verified items
# ---------------------------------------------------------------------------

@router.post("/quality/regression-suite")
async def regression_suite(
    model: str | None = None,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    await _audit(user, "run_regression_suite", f"Ran regression suite (model={model})")
    from app.services.quality_service import run_regression_suite
    return await run_regression_suite(user.user_id, model)


# ---------------------------------------------------------------------------
# 16. Quality Alerts (Phase 3)
# ---------------------------------------------------------------------------

@router.get("/quality/alerts")
async def get_quality_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    acknowledged: bool = Query(default=False),
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    from app.models.quality_alert import QualityAlert

    query = QualityAlert.find(QualityAlert.acknowledged == acknowledged)
    alerts = await query.sort("-created_at").limit(limit).to_list()
    return {
        "alerts": [
            {
                "uuid": a.uuid,
                "alert_type": a.alert_type,
                "item_kind": a.item_kind,
                "item_id": a.item_id,
                "item_name": a.item_name,
                "severity": a.severity,
                "message": a.message,
                "previous_score": a.previous_score,
                "current_score": a.current_score,
                "previous_tier": a.previous_tier,
                "current_tier": a.current_tier,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ]
    }


@router.post("/quality/alerts/{uuid}/acknowledge")
async def acknowledge_alert(
    uuid: str,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    from app.models.quality_alert import QualityAlert

    alert = await QualityAlert.find_one(QualityAlert.uuid == uuid)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    alert.acknowledged_by = user.user_id
    alert.acknowledged_at = datetime.datetime.now(datetime.timezone.utc)
    await alert.save()
    await _audit(user, "acknowledge_alert", f"Acknowledged quality alert: {uuid}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 17. Per-Item Quality (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/quality/items")
async def quality_items(
    sort: str = Query(default="score"),
    order: str = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    from app.services.quality_service import get_quality_items
    return {"items": await get_quality_items(sort, order, limit)}


@router.get("/quality/items/{item_kind}/{item_id}")
async def quality_item_detail(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    from app.services.quality_service import get_quality_item_detail
    return await get_quality_item_detail(item_kind, item_id)


# ---------------------------------------------------------------------------
# 18. Quality Contract (Phase 6)
# ---------------------------------------------------------------------------

@router.get("/quality/contract/{item_kind}/{item_id}")
async def quality_contract(
    item_kind: str,
    item_id: str,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)
    from app.services.quality_service import get_quality_contract_status
    return await get_quality_contract_status(item_kind, item_id)


# ---------------------------------------------------------------------------
# 19. GET /admin/teams/all  - All teams (admin management view)
# ---------------------------------------------------------------------------

@router.get("/teams/all", response_model=list[AdminTeamItem])
async def admin_list_all_teams(user: User = Depends(get_current_user)):
    await _require_admin(user)

    cfg = await SystemConfig.get_config()
    all_teams = await Team.find().limit(10000).to_list()
    all_memberships = await TeamMembership.find().limit(100000).to_list()

    member_counts: dict[str, int] = {}
    for m in all_memberships:
        key = str(m.team)
        member_counts[key] = member_counts.get(key, 0) + 1

    return [
        AdminTeamItem(
            team_id=str(t.id),
            uuid=t.uuid,
            name=t.name,
            owner_user_id=t.owner_user_id,
            member_count=member_counts.get(str(t.id), 0),
            is_default=(cfg.default_team_id == t.uuid),
        )
        for t in all_teams
    ]


# ---------------------------------------------------------------------------
# 20. POST /admin/teams/create  - Create a team (admin)
# ---------------------------------------------------------------------------

@router.post("/teams/create", response_model=AdminTeamItem)
async def admin_create_team(
    body: AdminCreateTeamRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    from app.services import team_service

    team = await team_service.create_team(body.name, user.user_id)
    await _audit(user, "admin_create_team", f"Created team: {body.name}")

    return AdminTeamItem(
        team_id=str(team.id),
        uuid=team.uuid,
        name=team.name,
        owner_user_id=team.owner_user_id,
        member_count=1,
        is_default=False,
    )


# ---------------------------------------------------------------------------
# 21. POST /admin/teams/{team_uuid}/members  - Add user to team (no invite)
# ---------------------------------------------------------------------------

@router.post("/teams/{team_uuid}/members")
async def admin_add_user_to_team(
    team_uuid: str,
    body: AdminAddUserRequest,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    target = await User.find_one(User.user_id == body.user_id)
    if not target:
        target = await User.find_one(User.email == body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == target.user_id,
    )
    if existing:
        existing.role = body.role
        await existing.save()
    else:
        await TeamMembership(team=team.id, user_id=target.user_id, role=body.role).insert()

    await _audit(user, "admin_add_team_member", f"Added {target.user_id} to team {team.name} as {body.role}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 22. DELETE /admin/teams/{team_uuid}/members/{user_id}  - Remove user
# ---------------------------------------------------------------------------

@router.delete("/teams/{team_uuid}/members/{user_id}")
async def admin_remove_user_from_team(
    team_uuid: str,
    user_id: str,
    user: User = Depends(get_current_user),
):
    await _require_admin(user)

    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    membership = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == user_id,
    )
    if not membership:
        raise HTTPException(status_code=404, detail="User not in team")

    await membership.delete()

    # If this was their current_team, clear it
    target = await User.find_one(User.user_id == user_id)
    if target and target.current_team == team.id:
        target.current_team = None
        await target.save()

    await _audit(user, "admin_remove_team_member", f"Removed {user_id} from team {team.name}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 23. GET /admin/users/isolated  - Users with no shared team
# ---------------------------------------------------------------------------

@router.get("/users/isolated", response_model=list[IsolatedUserItem])
async def isolated_users(user: User = Depends(get_current_user)):
    await _require_admin(user)

    all_memberships = await TeamMembership.find().limit(100000).to_list()

    # Count memberships per user and members per team
    user_team_ids: dict[str, set] = {}
    team_member_counts: dict[str, int] = {}
    for m in all_memberships:
        tid = str(m.team)
        user_team_ids.setdefault(m.user_id, set()).add(tid)
        team_member_counts[tid] = team_member_counts.get(tid, 0) + 1

    # Isolated = all their teams have exactly 1 member (just themselves)
    isolated_ids = [
        uid for uid, team_ids in user_team_ids.items()
        if all(team_member_counts.get(tid, 1) == 1 for tid in team_ids)
    ]

    if not isolated_ids:
        return []

    users = await User.find({"user_id": {"$in": isolated_ids}}).to_list()
    return [
        IsolatedUserItem(user_id=u.user_id, name=u.name, email=u.email)
        for u in users
    ]


# ---------------------------------------------------------------------------
# 24. Retention Dashboard
# ---------------------------------------------------------------------------

@router.get("/retention/dashboard")
async def retention_dashboard(user: User = Depends(get_current_user)):
    """Get retention policy status and document counts by classification."""
    await _require_admin(user)

    config = await SystemConfig.get_config()
    retention_config = config.get_retention_config()
    classification_config = config.get_classification_config()

    # Count documents by classification
    pipeline = [
        {"$match": {"soft_deleted": {"$ne": True}}},
        {"$group": {"_id": "$classification", "count": {"$sum": 1}}},
    ]
    counts_raw = await SmartDocument.aggregate(pipeline).to_list()
    counts = {item["_id"] or "unclassified": item["count"] for item in counts_raw}

    # Count pending deletions
    pending = await SmartDocument.find(
        SmartDocument.scheduled_deletion_at != None,  # noqa: E711
        SmartDocument.soft_deleted != True,  # noqa: E712
    ).count()

    # Count soft-deleted
    soft_deleted = await SmartDocument.find(SmartDocument.soft_deleted == True).count()  # noqa: E712

    # Count holds
    holds = await SmartDocument.find(SmartDocument.retention_hold == True).count()  # noqa: E712

    return {
        "retention_config": retention_config,
        "classification_config": classification_config,
        "document_counts": counts,
        "pending_deletions": pending,
        "soft_deleted": soft_deleted,
        "retention_holds": holds,
    }


@router.put("/retention/config")
async def update_retention_config(user: User = Depends(get_current_user)):
    """Update retention configuration."""
    await _require_admin(user)
    # This endpoint is defined but config updates go through the existing config endpoints
    return {"detail": "Use PUT /api/config to update retention_config"}


# ---------------------------------------------------------------------------
# 25. Classification Dashboard
# ---------------------------------------------------------------------------

@router.get("/classification/dashboard")
async def classification_dashboard(user: User = Depends(get_current_user)):
    """Get classification status overview."""
    await _require_admin(user)

    config = await SystemConfig.get_config()
    classification_config = config.get_classification_config()

    pipeline = [
        {"$match": {"soft_deleted": {"$ne": True}}},
        {"$group": {"_id": "$classification", "count": {"$sum": 1}}},
    ]
    counts_raw = await SmartDocument.aggregate(pipeline).to_list()
    counts = {item["_id"] or "unclassified": item["count"] for item in counts_raw}

    # Recent classifications
    recent = await SmartDocument.find(
        SmartDocument.classified_at != None,  # noqa: E711
    ).sort(-SmartDocument.classified_at).limit(10).to_list()

    recent_list = [
        {
            "uuid": doc.uuid,
            "title": doc.title,
            "classification": doc.classification,
            "confidence": doc.classification_confidence,
            "classified_at": doc.classified_at.isoformat() if doc.classified_at else None,
            "classified_by": doc.classified_by,
        }
        for doc in recent
    ]

    return {
        "config": classification_config,
        "counts": counts,
        "recent_classifications": recent_list,
    }


# ---------------------------------------------------------------------------
# Test connectivity endpoints
# ---------------------------------------------------------------------------


@router.post("/config/test-ocr")
async def test_ocr(user: User = Depends(get_current_user)):
    """Test OCR endpoint connectivity by sending a small health-check request."""
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    if not cfg.ocr_endpoint:
        raise HTTPException(status_code=400, detail="OCR endpoint not configured")

    import httpx

    headers: dict[str, str] = {}
    api_key = decrypt_value(cfg.ocr_api_key) if cfg.ocr_api_key else ""
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(cfg.ocr_endpoint, headers=headers)
            return {
                "status": "ok",
                "status_code": resp.status_code,
                "message": f"OCR endpoint responded with {resp.status_code}",
            }
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Could not connect to OCR endpoint")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OCR endpoint timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OCR test failed: {e}")


@router.post("/config/test-model/{index}")
async def test_model(index: int, user: User = Depends(get_current_user)):
    """Test an LLM model by sending a minimal completion request."""
    await _require_superadmin(user)

    cfg = await SystemConfig.get_config()
    if index < 0 or index >= len(cfg.available_models):
        raise HTTPException(status_code=404, detail="Model not found")

    model_cfg = cfg.available_models[index]
    model_name = model_cfg.get("name", "")

    try:
        from pydantic_ai import Agent

        model = get_agent_model(model_name)
        agent = Agent(model, system_prompt="Reply with exactly: ok")
        result = await agent.run("Say ok")
        return {
            "status": "ok",
            "model": model_name,
            "message": f"Model responded: {result.output[:100]}",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model test failed: {e}")
