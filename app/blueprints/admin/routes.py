# admin_routes.py (or wherever your Flask routes live)
import json
import secrets
from datetime import datetime, time, timedelta, timezone
from devtools import debug

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    flash,
)
from flask_login import current_user, login_required

from app.models import (
    ActivityEvent,
    DailyUsageAggregate,
    Space,
    SystemConfig,
    Team,
    TeamInvite,
    TeamMembership,
    User,
)
from app import load_user

admin = Blueprint("admin", __name__)


def day_bounds(start_dt: datetime, end_dt: datetime) -> tuple[datetime, datetime]:
    """
    Return UTC day-bounded datetimes [start_of_start_day, start_of_day_after_end].
    
    Returns timezone-aware UTC datetimes for proper comparison with stored dates.
    """
    # Get date portion and create timezone-aware UTC datetimes
    start_floor = datetime.combine(start_dt.date(), time.min, tzinfo=timezone.utc)
    end_exclusive = datetime.combine(end_dt.date(), time.min, tzinfo=timezone.utc) + timedelta(days=1)
    return start_floor, end_exclusive


def parse_date(s: str, default: datetime) -> datetime:
    """Parse ISO date string, returning timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(s.strip())
        # If parsed datetime is naive, make it UTC-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        # Make sure default is also timezone-aware
        if default.tzinfo is None:
            return default.replace(tzinfo=timezone.utc)
        return default



def get_admin_user():
    u = (
        User.objects(user_id=str(current_user.get_id())).first()
    )
    if not u or not u.is_admin:
        abort(403)
    return u


def _agg_cursor(
    scope: str, start: datetime, end: datetime, *, user_id=None, team_id=None
):
    # Pull the appropriate rollups
    q = DailyUsageAggregate.objects(
        date__gte=start.date(), date__lte=end.date(), scope=scope
    )
    if scope == "user" and user_id:
        q = q.filter(user_id=user_id)
    if scope == "team" and team_id:
        q = q.filter(team_id=team_id)
    return q


def _sum_int(q, attr):
    return sum(getattr(r, attr, 0) or 0 for r in q)


@admin.route("/usage", methods=["GET"])
def usage_dashboard():
    # --- Permission & Scope Logic ---
    user = current_user
    
    # Check regular admin
    is_sys_admin = user.is_admin
    # Check team admin (owner or admin of current team)
    is_team_admin = user.is_owner_current_team or user.is_admin_current_team
    
    if not (is_sys_admin or is_team_admin):
        abort(403)
        
    # Determine the forced scope constraints
    forced_team_id = None
    if not is_sys_admin:
        # If not system admin, MUST be scoped to current team
        if user.current_team:
            forced_team_id = user.current_team_uuid
        else:
            # edge case: team admin but no current team? should not happen if is_owner_current_team is true
            abort(403)

    # Resolve filters
    req_user_id = (request.args.get("user_id") or "").strip() or None
    req_team_id = (request.args.get("team_id") or "").strip() or None
    req_space_id = (request.args.get("space_id") or "").strip() or None

    # Apply constraints
    if forced_team_id:
        # Force the team ID. Ignore request arg if it tries to break out.
        team_id = forced_team_id
        # Allow user_id filtering ONLY if that user is in the team (optional check, but good for hygiene)
        # For now, we trust the DB query to filter by both team_id + user_id, 
        # so if the user isn't in the team, result is empty (safe).
        user_id = req_user_id
    else:
        # System admin can filter as they please
        team_id = req_team_id
        user_id = req_user_id
        
    space_id = req_space_id

    # Parse dates
    print("DEBUG: entering date parsing")
    end_default = datetime.now(timezone.utc)
    start_default = end_default - timedelta(days=30)
    start = parse_date(request.args.get("start", ""), start_default)
    end = parse_date(request.args.get("end", ""), end_default)

    # Normalize to start/end of day for consistency
    start_floor, end_exclusive = day_bounds(start, end)

    # Which scope to read rollups from?
    scope = "global"
    if user_id:
        scope = "user"
    elif team_id:
        scope = "team"

    rollups = _agg_cursor(scope, start, end, user_id=user_id, team_id=team_id)

    # Fetch context objects for display
    context_team = None
    context_user = None
    if team_id:
        context_team = Team.objects(uuid=team_id).first()
    if user_id:
        context_user = User.objects(user_id=user_id).first()

    
    # === Chart Data Preparation (Time Series) ===
    # We want a list of days in the range, and for each day, the metrics.
    # _agg_cursor returns a MongoEngine QuerySet. We can iterate it.
    
    # 1. Create a map of date -> aggregate object
    agg_map = {}
    for r in rollups:
        # r.date is a date object (or datetime)
        d_str = r.date.strftime("%Y-%m-%d")
        agg_map[d_str] = r

    # 2. Iterate through all days in range to fill gaps with zeros
    chart_dates = []
    chart_wfs = []
    chart_tokens = []
    chart_convs = []
    
    curr = start_floor
    while curr < end_exclusive:
        d_str = curr.strftime("%Y-%m-%d")
        chart_dates.append(d_str)
        
        row = agg_map.get(d_str)
        if row:
            chart_wfs.append(row.workflows_completed or 0)
            chart_tokens.append((row.tokens_input or 0) + (row.tokens_output or 0))
            chart_convs.append(row.conversations or 0)
        else:
            chart_wfs.append(0)
            chart_tokens.append(0)
            chart_convs.append(0)
            
        curr += timedelta(days=1)
        
    chart_data = {
        "dates": chart_dates,
        "workflows": chart_wfs,
        "tokens": chart_tokens,
        "conversations": chart_convs
    }

    # === KPIs (from rollups) ===
    conversations = _sum_int(rollups, "conversations")
    debug(f"Conversations: {conversations}")
    searches = _sum_int(rollups, "searches")
    wf_started = _sum_int(rollups, "workflows_started")
    wf_completed = _sum_int(rollups, "workflows_completed")
    wf_failed = _sum_int(rollups, "workflows_failed")
    tokens_in = _sum_int(rollups, "tokens_input")
    tokens_out = _sum_int(rollups, "tokens_output")
    conv_msgs = _sum_int(rollups, "conversation_messages")
    total_wf_duration_ms = _sum_int(rollups, "workflow_duration_ms")
    avg_wf_ms = (total_wf_duration_ms / wf_completed) if wf_completed else 0

    # === Active users/teams (from ActivityEvent with CONSISTENT date filtering) ===
    # Use the SAME date range as aggregates
    ev_match = {
        "started_at": {"$gte": start_floor, "$lt": end_exclusive}
    }
    if user_id:
        ev_match["user_id"] = user_id
    if team_id:
        ev_match["team_id"] = team_id
    if space_id:
        ev_match["space"] = space_id

    # Single aggregation to get distinct users and teams efficiently
    active_counts_pipeline = [
        {"$match": ev_match},
        {
            "$group": {
                "_id": None,
                "users": {"$addToSet": "$user_id"},
                "teams": {"$addToSet": "$team_id"},
            }
        },
    ]
    
    active_counts = list(ActivityEvent._get_collection().aggregate(active_counts_pipeline))
    
    if active_counts:
        users_set = active_counts[0].get("users", [])
        teams_set = active_counts[0].get("teams", [])
        # Filter out None/empty values
        active_users = len([u for u in users_set if u])
        active_teams = len([t for t in teams_set if t])
    else:
        active_users = 0
        active_teams = 0
    
    debug(f"Active users: {active_users}, Active teams: {active_teams}")

    # === Status breakdown for workflow runs (from events) ===
    wf_status_pipeline = [
        {
            "$match": {
                "type": "workflow_run",
                "started_at": {"$gte": start_floor, "$lt": end_exclusive},
                **({"user_id": user_id} if user_id else {}),
                **({"team_id": team_id} if team_id else {}),
                **({"space": space_id} if space_id else {}),
            }
        },
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results_by_status = list(
        ActivityEvent._get_collection().aggregate(wf_status_pipeline)
    )

    # === ActivityEvent Match Base ===
    base_match = {
        "started_at": {"$gte": start_floor, "$lt": end_exclusive},
    }
    if user_id:
        base_match["user_id"] = user_id
    if team_id:
        base_match["team_id"] = team_id
    if space_id:
        base_match["space"] = space_id

    # === Top users / teams by workflows completed ===
    # If filtered to a team, we MUST use ActivityEvent for top users, 
    # because DailyUsageAggregate(scope='user') is global per user, not per team.
    if team_id:
        # Team-scoped user stats
        top_users_pipeline = [
            {"$match": base_match | {"type": "workflow_run", "status": "completed"}},
            {"$group": {"_id": "$user_id", "completed": {"$sum": 1}}},
            {"$sort": {"completed": -1}},
            {"$limit": 10},
        ]
        top_users = list(ActivityEvent._get_collection().aggregate(top_users_pipeline))
    else:
        # Global stats (cheaper via lookups)
        top_users_pipeline = [
            {
                "$match": {
                    "scope": "user",
                    "date": {"$gte": start_floor, "$lt": end_exclusive},
                }
            },
            {"$group": {"_id": "$user_id", "completed": {"$sum": "$workflows_completed"}}},
            {"$sort": {"completed": -1}},
            {"$limit": 10},
        ]
        top_users = list(DailyUsageAggregate._get_collection().aggregate(top_users_pipeline))

    # Top Teams
    # If team_id is set, this list will just be that one team (or empty)
    if team_id:
        top_teams_pipeline = [
            {"$match": base_match | {"type": "workflow_run", "status": "completed"}},
            {"$group": {"_id": "$team_id", "completed": {"$sum": 1}}},
            {"$sort": {"completed": -1}},
            {"$limit": 10},
        ]
        top_teams = list(ActivityEvent._get_collection().aggregate(top_teams_pipeline))
    else:
        top_teams_pipeline = [
            {
                "$match": {
                    "scope": "team",
                    "date": {"$gte": start_floor, "$lt": end_exclusive},
                }
            },
            {"$group": {"_id": "$team_id", "completed": {"$sum": "$workflows_completed"}}},
            {"$sort": {"completed": -1}},
            {"$limit": 10},
        ]
        top_teams = list(DailyUsageAggregate._get_collection().aggregate(top_teams_pipeline))
    # Enrich top teams with names
    if top_teams:
        t_ids = [t["_id"] for t in top_teams]
        t_map = {t.uuid: t.name for t in Team.objects(uuid__in=t_ids)}
        for t in top_teams:
            t["name"] = t_map.get(t["_id"], t["_id"])


    # === Top Workflows (ActivityEvent aggregation) ===
    # Group by 'safe_workflow_name' (or workflow_id if preferred, but name is safer display)
    top_workflows_pipeline = [
        {"$match": base_match | {"type": "workflow_run", "status": "completed"}},
        {"$group": {"_id": "$meta_summary.workflow_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_workflows = list(ActivityEvent._get_collection().aggregate(top_workflows_pipeline))

    # === Top Tasks/Search Sets (ActivityEvent aggregation) ===
    # Group by search_set_uuid
    top_tasks_pipeline = [
        {"$match": base_match | {"type": "search_set_run", "status": "completed"}},
        {"$group": {"_id": "$search_set_uuid", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_tasks = list(ActivityEvent._get_collection().aggregate(top_tasks_pipeline))
    
    # Enrich tasks with titles
    if top_tasks:
        task_uuids = [t["_id"] for t in top_tasks if t["_id"]]
        # We need to import SearchSet locally or at top
        from app.models import SearchSet
        ts_map = {s.uuid: s.title for s in SearchSet.objects(uuid__in=task_uuids)}
        for t in top_tasks:
            t["title"] = ts_map.get(t["_id"], t["_id"] or "Unknown Task")

    # === Recent activity (unified stream) ===
    ev_q = ActivityEvent.objects(
        started_at__gte=start_floor, 
        started_at__lt=end_exclusive
    )
    if user_id:
        ev_q = ev_q.filter(user_id=user_id)
    if team_id:
        ev_q = ev_q.filter(team_id=team_id)
    if space_id:
        ev_q = ev_q.filter(space=space_id)
    
    recent_events = ev_q.order_by("-started_at").limit(50)

    # Selects
    # Selects
    if is_sys_admin:
        all_users = sorted([u for u in ActivityEvent.objects.distinct("user_id") if u is not None])
        all_teams = Team.objects.order_by("name")
        all_spaces = Space.objects.only("uuid", "title").order_by("title")
    else:
        # Non-admin: Scope to own team
        if user.current_team:
            all_teams = [user.current_team]
            # Only users active in this team
            all_users = sorted([u for u in ActivityEvent.objects(team_id=user.current_team_uuid).distinct("user_id") if u is not None])
        else:
            all_teams = []
            all_users = []
        all_spaces = []

    kpi = {
        "conversations": conversations,
        "searches": searches,
        "wf_started": wf_started,
        "wf_completed": wf_completed,
        "wf_failed": wf_failed,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "avg_wf_ms": int(avg_wf_ms),
        "active_users": active_users,
        "active_teams": active_teams,
    }
    debug(kpi)

    return render_template(
        "admin/usage.html",
        start=start,
        end=end,
        user_id=user_id or "",
        team_id=team_id or "",
        space_id=space_id or "",
        kpi=kpi,
        results_by_status=results_by_status,
        top_users=top_users,
        top_teams=top_teams,
        recent_events=recent_events,
        all_users=all_users,
        all_teams=all_teams,
        all_spaces=all_spaces,
        is_sys_admin=is_sys_admin,
        chart_data=chart_data,
        context_team=context_team,
        context_user=context_user,
        top_workflows=top_workflows,
        top_tasks=top_tasks,
    )

@admin.route("/teams", methods=["GET"])
@login_required
def admin_teams():
    user = current_user
    if not user.is_admin:
        abort(403)
        
    # Default to last 30 days
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    start_floor, end_exclusive = day_bounds(start, end)

    # Aggregate usage by team
    pipeline = [
        {
            "$match": {
                "scope": "team",
                "date": {"$gte": start_floor, "$lt": end_exclusive},
            }
        },
        {
            "$group": {
                "_id": "$team_id",
                "workflows": {"$sum": "$workflows_completed"},
                "tokens": {"$sum": {"$add": ["$tokens_input", "$tokens_output"]}},
                "conversations": {"$sum": "$conversations"},
                "avg_duration_sum": {"$sum": "$workflow_duration_ms"},
            }
        },
        {"$sort": {"tokens": -1}}, # Default sort by biggest spenders
    ]
    
    usage_stats = list(DailyUsageAggregate._get_collection().aggregate(pipeline))
    
    # Enrich with team names
    data = []
    # Fetch all needed teams in one go (or lazily if list is huge, but here it's fine)
    team_ids = [s["_id"] for s in usage_stats if s["_id"]]
    teams_map = {t.uuid: t for t in Team.objects(uuid__in=team_ids)}
    
    # Also get active users count per team in Period
    # This is a bit expensive but useful
    active_users_pipeline = [
        {
             "$match": {
                "started_at": {"$gte": start_floor, "$lt": end_exclusive},
                "team_id": {"$in": team_ids},
            }
        },
        {
            "$group": {
                "_id": "$team_id",
                "users": {"$addToSet": "$user_id"}
            }
        }
    ]
    active_counts = {
        str(r["_id"]): len(r["users"]) 
        for r in ActivityEvent._get_collection().aggregate(active_users_pipeline)
    }

    max_tokens = 0
    for stat in usage_stats:
        tid = str(stat["_id"])
        team = teams_map.get(tid)
        if not team:
            continue
            
        wfs = stat.get("workflows", 0)
        tokens = stat.get("tokens", 0)
        if tokens > max_tokens:
            max_tokens = tokens
            
        duration_sum = stat.get("avg_duration_sum", 0)
        avg_ms = 0
        if wfs > 0:
            avg_ms = duration_sum / wfs
            
        data.append({
            "team": team,
            "workflows": wfs,
            "tokens": tokens,
            "conversations": stat.get("conversations", 0),
            "active_users": active_counts.get(tid, 0),
            "avg_latency": int(avg_ms)
        })
        
    return render_template(
        "admin/teams.html", 
        teams_data=data, 
        max_tokens=max_tokens,
        start=start,
        end=end
    )


@admin.route("/users", methods=["GET"])
def admin_users():
    """List users with analytics metrics."""
    user = load_user()
    if not user.is_admin:
        abort(403)
        
    # Default to last 30 days
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    start_floor, end_exclusive = day_bounds(start, end)
    
    # Aggregate usage by user (global scope aggregation)
    # We want to know their TOTAL usage across all teams/personal
    pipeline = [
        {
            "$match": {
                "scope": "user",
                "date": {"$gte": start_floor, "$lt": end_exclusive},
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "workflows": {"$sum": "$workflows_completed"},
                "tokens": {"$sum": {"$add": ["$tokens_input", "$tokens_output"]}},
                "last_active": {"$max": "$date"},
            }
        },
        {"$sort": {"tokens": -1}}, # Default sort by whale status
        {"$limit": 100} # Top 100 users
    ]
    
    user_stats = list(DailyUsageAggregate._get_collection().aggregate(pipeline))
    
    # Enrich with user details
    user_ids = [s["_id"] for s in user_stats if s["_id"]]
    users_map = {u.user_id: u for u in User.objects(user_id__in=user_ids)}
    
    data = []
    max_tokens = 0
    
    for stat in user_stats:
        uid = stat["_id"]
        u_obj = users_map.get(uid)
        
        # Determine "Primary Team" (where they did the most work)
        # We can run a sub-aggregation or just look at their current team
        # For performance, let's just show their current team name if available
        primary_team_name = "—"
        if u_obj and u_obj.current_team:
            # We would need to fetch the team name, potentially expensive loop.
            # Ideally User object has cached team name or we trust ID.
            # Let's skip heavy logic and just check if we have it loaded or use generic.
            pass

        tokens = stat.get("tokens", 0)
        if tokens > max_tokens:
            max_tokens = tokens
            
        data.append({
            "user": u_obj, # Might be None if user deleted but metrics remain
            "user_id": uid,
            "workflows": stat.get("workflows", 0),
            "tokens": tokens,
            "last_active": stat.get("last_active")
        })

    return render_template(
        "admin/users.html",
        users_data=data,
        max_tokens=max_tokens,
        start=start,
        end=end,
        is_admin=True
    )


@admin.route("/workflows", methods=["GET"])
def admin_workflows():
    """List recent workflows."""
    user = load_user()
    if not user.is_admin:
        abort(403)
        
    status_filter = request.args.get("status")
    
    # We use ActivityEvent for this listing as it's the unified stream
    query = ActivityEvent.objects(type="workflow_run")
    
    if status_filter:
        query = query.filter(status=status_filter)
        
    # Pagination
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    total_events = query.count()
    events = query.order_by("-started_at").skip(offset).limit(per_page)
    
    return render_template(
        "admin/workflows.html",
        events=events,
        page=page,
        total_pages=(total_events + per_page - 1) // per_page,
        status_filter=status_filter,
        is_admin=True
    )

@admin.route("/config", methods=["GET"])
@login_required
def admin_config():
    """System configuration page."""
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    return render_template("admin/config.html", config=config)


@admin.route("/config/update", methods=["POST"])
@login_required
def admin_config_update():
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    # Update fields
    config.ocr_endpoint = request.form.get("ocr_endpoint", "").strip()
    config.llm_endpoint = request.form.get("llm_endpoint", "").strip()
    config.highlight_color = request.form.get("highlight_color", "#eab308").strip()
    config.ui_radius = request.form.get("ui_radius", "12px").strip()
    
    config.updated_at = datetime.now()
    config.updated_by = user.email or user.name
    config.save()
    
    flash("System configuration updated.")
    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/update_methods", methods=["POST"])
@login_required
def admin_config_auth_methods():
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    methods = []
    if request.form.get("auth_password"):
        methods.append("password")
    if request.form.get("auth_oauth"):
        methods.append("oauth")
        
    config.auth_methods = methods
    config.save()
    
    flash("Authentication methods updated.")
    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/add_provider", methods=["POST"])
@login_required
def admin_config_add_provider():
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    p_type = request.form.get("provider_type")
    
    # Common fields
    new_provider = {
        "provider": p_type,
        "enabled": True,
        "display_name": request.form.get("display_name", f"Sign in with {p_type}"),
        "client_id": request.form.get("client_id", "").strip(),
        "client_secret": request.form.get("client_secret", "").strip(),
        "redirect_uri": request.form.get("redirect_uri", "").strip(),
    }
    
    # Type-specific fields
    if p_type == "azure":
        new_provider["tenant_id"] = request.form.get("tenant_id", "").strip()
    elif p_type == "saml":
        new_provider["metadata_url"] = request.form.get("metadata_url", "").strip()
        new_provider["entity_id"] = request.form.get("entity_id", "").strip()
    elif p_type == "custom":
        new_provider["authorization_endpoint"] = request.form.get("authorization_endpoint", "").strip()
        new_provider["token_endpoint"] = request.form.get("token_endpoint", "").strip()
        new_provider["userinfo_endpoint"] = request.form.get("userinfo_endpoint", "").strip()

    config.oauth_providers.append(new_provider)
    config.save()
    
    flash("OAuth provider added.")
    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/update_provider/<int:index>", methods=["POST"])
@login_required
def admin_config_update_provider(index):
    user = current_user
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    if 0 <= index < len(config.oauth_providers):
        provider = dict(config.oauth_providers[index])
        provider_type = provider.get("provider")

        provider["display_name"] = request.form.get(
            "display_name", provider.get("display_name", "")
        ).strip()
        provider["client_id"] = request.form.get(
            "client_id", provider.get("client_id", "")
        ).strip()
        provider["redirect_uri"] = request.form.get(
            "redirect_uri", provider.get("redirect_uri", "")
        ).strip()

        client_secret = request.form.get("client_secret", "").strip()
        if client_secret:
            provider["client_secret"] = client_secret

        if provider_type == "azure":
            provider["tenant_id"] = request.form.get(
                "tenant_id", provider.get("tenant_id", "")
            ).strip()
        elif provider_type == "saml":
            provider["metadata_url"] = request.form.get(
                "metadata_url", provider.get("metadata_url", "")
            ).strip()
            provider["entity_id"] = request.form.get(
                "entity_id", provider.get("entity_id", "")
            ).strip()
        elif provider_type == "custom":
            provider["authorization_endpoint"] = request.form.get(
                "authorization_endpoint",
                provider.get("authorization_endpoint", ""),
            ).strip()
            provider["token_endpoint"] = request.form.get(
                "token_endpoint", provider.get("token_endpoint", "")
            ).strip()
            provider["userinfo_endpoint"] = request.form.get(
                "userinfo_endpoint", provider.get("userinfo_endpoint", "")
            ).strip()

        config.oauth_providers[index] = provider
        config.save()
        flash("OAuth provider updated.")
    else:
        flash("Invalid provider index.")

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/toggle_provider/<int:index>", methods=["POST"])
@login_required
def admin_config_toggle_provider(index):
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    if 0 <= index < len(config.oauth_providers):
        # Toggle boolean
        current = config.oauth_providers[index].get("enabled", True)
        config.oauth_providers[index]["enabled"] = not current
        config.save()
        flash("Provider status updated.")
    else:
        flash("Invalid provider index.")
        
    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/remove_provider/<int:index>", methods=["POST"])
@login_required
def admin_config_remove_provider(index):
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    if 0 <= index < len(config.oauth_providers):
        config.oauth_providers.pop(index)
        config.save()
        flash("Provider removed.")
    else:
        flash("Invalid provider index.")
        
    return redirect(url_for("admin.admin_config"))


@admin.route("/config/add_model", methods=["POST"])
@login_required
def admin_config_add_model():
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    new_model = {
        "name": request.form.get("model_name", "").strip(),
        "tag": request.form.get("model_tag", "").strip(),
        "external": bool(request.form.get("model_external")),
        "thinking": bool(request.form.get("model_thinking")),
        "endpoint": request.form.get("model_endpoint", "").strip(),
        "api_protocol": request.form.get("model_api_protocol", "").strip()
    }
    
    if new_model["name"]:
        config.available_models.append(new_model)
        config.save()
        flash("Model added.")
    else:
        flash("Model name required.")
        
    return redirect(url_for("admin.admin_config"))


@admin.route("/config/remove_model/<int:index>", methods=["POST"])
@login_required
def admin_config_remove_model(index):
    user = current_user
    if not user.is_admin:
        abort(403)
        
    config = SystemConfig.get_config()
    
    if 0 <= index < len(config.available_models):
        config.available_models.pop(index)
        config.save()
        flash("Model removed.")
    else:
        flash("Invalid model index.")
        
    return redirect(url_for("admin.admin_config"))
