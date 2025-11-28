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
)
from flask_login import current_user

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
    # get_admin_user()  # enable when ready

    end_default = datetime.now(timezone.utc)  # Make timezone-aware
    start_default = end_default - timedelta(days=30)
    start = parse_date(request.args.get("start", ""), start_default)
    end = parse_date(request.args.get("end", ""), end_default)

    user_id = (request.args.get("user_id") or "").strip() or None
    team_id = (request.args.get("team_id") or "").strip() or None
    space_id = (request.args.get("space_id") or "").strip() or None

    # Normalize to start/end of day for consistency
    start_floor, end_exclusive = day_bounds(start, end)

    # Which scope to read rollups from?
    scope = "global"
    if user_id:
        scope = "user"
    elif team_id:
        scope = "team"

    rollups = _agg_cursor(scope, start, end, user_id=user_id, team_id=team_id)

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

    # === Top users / teams by workflows completed ===
    # Note: Don't call .date() - MongoDB needs datetime objects
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
    top_users = list(
        DailyUsageAggregate._get_collection().aggregate(top_users_pipeline)
    )

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
    top_teams = list(
        DailyUsageAggregate._get_collection().aggregate(top_teams_pipeline)
    )

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
    all_users = sorted([u for u in ActivityEvent.objects.distinct("user_id") if u is not None])
    all_teams = Team.objects.order_by("name")
    all_spaces = Space.objects.only("uuid", "title").order_by("title")

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
    )

@admin.route("/teams", methods=["GET"])
def admin_teams():
    user = load_user()
    if not user.is_admin:
        abort(403)
    teams = Team.objects.order_by("name")
    data = []
    for t in teams:
        members = TeamMembership.objects(team=t)
        invites = TeamInvite.objects(team=t, accepted=False)
        data.append({"team": t, "members": members, "invites": invites})
    return render_template(
        "admin/teams.html", teams=data, is_admin=True, current_user_name=user.name
    )


@admin.route("/teams/create", methods=["POST"])
def admin_teams_create():
    user = load_user()
    if not user.is_admin:
        abort(403)
    name = request.form.get("name", "").strip()
    owner_user_id = request.form.get("owner_user_id", "").strip()
    if not name or not owner_user_id:
        return jsonify({"error": "name and owner_user_id required"}), 400
    t = Team(
        uuid=secrets.token_urlsafe(12), name=name, owner_user_id=owner_user_id
    ).save()
    TeamMembership(team=t, user_id=owner_user_id, role="owner").save()
    return redirect(url_for("admin.admin_teams"))


@admin.route("/teams/invite", methods=["POST"])
def admin_teams_invite():
    user = load_user()
    if not user.is_admin:
        abort(403)
    team_id = request.form.get("team_id")
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "member")
    team = Team.objects(id=team_id).first()
    if not team:
        return jsonify({"error": "Team not found"}), 404
    token = secrets.token_urlsafe(24)
    TeamInvite(
        team=team, email=email, role=role, invited_by_user_id=user.user_id, token=token
    ).save()

    # TODO: send mail
    return redirect(url_for("admin.admin_teams"))


@admin.route("/config", methods=["GET"])
def admin_config():
    """System configuration page - only accessible to system administrators."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()
    return render_template(
        "admin/config.html",
        config=config,
        is_admin=True,
        current_user_name=user.name
    )


@admin.route("/config/update", methods=["POST"])
def admin_config_update():
    """Update system configuration - only accessible to system administrators."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    # Update OCR endpoint
    ocr_endpoint = request.form.get("ocr_endpoint", "").strip()
    if ocr_endpoint:
        config.ocr_endpoint = ocr_endpoint

    # Update LLM endpoint
    llm_endpoint = request.form.get("llm_endpoint", "").strip()
    if llm_endpoint:
        config.llm_endpoint = llm_endpoint

    # Update highlight color
    highlight_color = request.form.get("highlight_color", "").strip()
    if highlight_color:
        config.highlight_color = highlight_color

    # Update UI radius
    ui_radius = request.form.get("ui_radius", "").strip()
    if ui_radius:
        if ui_radius.isdigit():
            ui_radius = f"{ui_radius}px"
        elif ui_radius.replace(".", "", 1).isdigit() and not ui_radius.endswith("px"):
            ui_radius = f"{ui_radius}px"
        config.ui_radius = ui_radius

    # Update available models from JSON
    models_json = request.form.get("models_json", "").strip()
    if models_json:
        try:
            models = json.loads(models_json)
            config.available_models = models
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON for models"}), 400

    # Update metadata
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by = user.user_id
    config.save()

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/add_model", methods=["POST"])
def admin_config_add_model():
    """Add a new model to the configuration."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    model_name = request.form.get("model_name", "").strip()
    model_tag = request.form.get("model_tag", "").strip()
    model_external = request.form.get("model_external") == "on"

    if not model_name or not model_tag:
        return jsonify({"error": "Model name and tag are required"}), 400

    # Add new model
    new_model = {
        "name": model_name,
        "tag": model_tag,
        "external": model_external
    }

    if not config.available_models:
        config.available_models = []

    config.available_models.append(new_model)
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by = user.user_id
    config.save()

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/remove_model/<int:index>", methods=["POST"])
def admin_config_remove_model(index):
    """Remove a model from the configuration."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    if 0 <= index < len(config.available_models):
        config.available_models.pop(index)
        config.updated_at = datetime.now(timezone.utc)
        config.updated_by = user.user_id
        config.save()

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/update_methods", methods=["POST"])
def admin_config_update_auth_methods():
    """Update enabled authentication methods."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    # Get selected auth methods from checkboxes
    password_enabled = request.form.get("auth_password") == "on"
    oauth_enabled = request.form.get("auth_oauth") == "on"

    auth_methods = []
    if password_enabled:
        auth_methods.append("password")
    if oauth_enabled:
        auth_methods.append("oauth")

    # Ensure at least one method is enabled
    if not auth_methods:
        return jsonify({"error": "At least one authentication method must be enabled"}), 400

    config.auth_methods = auth_methods
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by = user.user_id
    config.save()

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/add_provider", methods=["POST"])
def admin_config_add_oauth_provider():
    """Add a new OAuth/SAML provider."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    provider_type = request.form.get("provider_type", "").strip()
    display_name = request.form.get("display_name", "").strip()
    client_id = request.form.get("client_id", "").strip()
    client_secret = request.form.get("client_secret", "").strip()
    redirect_uri = request.form.get("redirect_uri", "").strip()

    if not all([provider_type, display_name, client_id, redirect_uri]):
        return jsonify({"error": "Provider type, display name, client ID, and redirect URI are required"}), 400

    new_provider = {
        "provider": provider_type,
        "enabled": True,
        "display_name": display_name,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }

    # Add provider-specific fields
    if provider_type == "azure":
        tenant_id = request.form.get("tenant_id", "").strip()
        if tenant_id:
            new_provider["tenant_id"] = tenant_id
        # Azure well-known endpoints
        new_provider["authority"] = f"https://login.microsoftonline.com/{tenant_id}" if tenant_id else ""

    elif provider_type == "saml":
        metadata_url = request.form.get("metadata_url", "").strip()
        entity_id = request.form.get("entity_id", "").strip()
        if metadata_url:
            new_provider["metadata_url"] = metadata_url
        if entity_id:
            new_provider["entity_id"] = entity_id

    else:
        # Custom OAuth provider
        authorization_endpoint = request.form.get("authorization_endpoint", "").strip()
        token_endpoint = request.form.get("token_endpoint", "").strip()
        userinfo_endpoint = request.form.get("userinfo_endpoint", "").strip()

        if authorization_endpoint:
            new_provider["authorization_endpoint"] = authorization_endpoint
        if token_endpoint:
            new_provider["token_endpoint"] = token_endpoint
        if userinfo_endpoint:
            new_provider["userinfo_endpoint"] = userinfo_endpoint

    if not config.oauth_providers:
        config.oauth_providers = []

    config.oauth_providers.append(new_provider)
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by = user.user_id
    config.save()

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/remove_provider/<int:index>", methods=["POST"])
def admin_config_remove_oauth_provider(index):
    """Remove an OAuth/SAML provider."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    if 0 <= index < len(config.oauth_providers):
        config.oauth_providers.pop(index)
        config.updated_at = datetime.now(timezone.utc)
        config.updated_by = user.user_id
        config.save()

    return redirect(url_for("admin.admin_config"))


@admin.route("/config/auth/toggle_provider/<int:index>", methods=["POST"])
def admin_config_toggle_oauth_provider(index):
    """Toggle OAuth/SAML provider enabled status."""
    user = load_user()
    if not user.is_admin:
        abort(403)

    config = SystemConfig.get_config()

    if 0 <= index < len(config.oauth_providers):
        config.oauth_providers[index]["enabled"] = not config.oauth_providers[index].get("enabled", True)
        config.updated_at = datetime.now(timezone.utc)
        config.updated_by = user.user_id
        config.save()

    return redirect(url_for("admin.admin_config"))
