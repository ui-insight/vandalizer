# admin_routes.py (or wherever your Flask routes live)
import secrets
from datetime import datetime, time, timedelta, timezone
from devtools import debug
import asyncio
import logging

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    send_file,
    Response,
)
from flask_login import current_user

from app.models import (
    ActivityEvent,
    DailyUsageAggregate,
    Space,
    Team,
    TeamInvite,
    TeamMembership,
    User,
    UserModelConfig
)
from app import load_user
from app.utilities.markdown_helpers import generate_pdf_from_html
from app.utilities.agents import create_chat_agent
from app.utilities.config import settings

admin = Blueprint("admin", __name__)


logger = logging.getLogger(__name__)


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


@admin.route("/usage/download", methods=["GET"])
def download_usage_report():
    """Generate and download a PDF report of usage statistics."""
    # get_admin_user()  # enable when ready
    
    end_default = datetime.now(timezone.utc)
    start_default = end_default - timedelta(days=30)
    start = parse_date(request.args.get("start", ""), start_default)
    end = parse_date(request.args.get("end", ""), end_default)

    user_id = (request.args.get("user_id") or "").strip() or None
    team_id = (request.args.get("team_id") or "").strip() or None
    space_id = (request.args.get("space_id") or "").strip() or None

    start_floor, end_exclusive = day_bounds(start, end)

    # Determine scope
    scope = "global"
    if user_id:
        scope = "user"
    elif team_id:
        scope = "team"

    rollups = _agg_cursor(scope, start, end, user_id=user_id, team_id=team_id)

    # Calculate KPIs
    conversations = _sum_int(rollups, "conversations")
    searches = _sum_int(rollups, "searches")
    wf_started = _sum_int(rollups, "workflows_started")
    wf_completed = _sum_int(rollups, "workflows_completed")
    wf_failed = _sum_int(rollups, "workflows_failed")
    tokens_in = _sum_int(rollups, "tokens_input")
    tokens_out = _sum_int(rollups, "tokens_output")
    total_wf_duration_ms = _sum_int(rollups, "workflow_duration_ms")
    avg_wf_ms = (total_wf_duration_ms / wf_completed) if wf_completed else 0

    # Get active users/teams
    ev_match = {"started_at": {"$gte": start_floor, "$lt": end_exclusive}}
    if user_id:
        ev_match["user_id"] = user_id
    if team_id:
        ev_match["team_id"] = team_id
    if space_id:
        ev_match["space"] = space_id

    active_counts_pipeline = [
        {"$match": ev_match},
        {"$group": {"_id": None, "users": {"$addToSet": "$user_id"}, "teams": {"$addToSet": "$team_id"}}},
    ]
    active_counts = list(ActivityEvent._get_collection().aggregate(active_counts_pipeline))
    
    if active_counts:
        users_set = active_counts[0].get("users", [])
        teams_set = active_counts[0].get("teams", [])
        active_users = len([u for u in users_set if u])
        active_teams = len([t for t in teams_set if t])
    else:
        active_users = 0
        active_teams = 0

    # Get status breakdown
    wf_status_pipeline = [
        {"$match": {"type": "workflow_run", "started_at": {"$gte": start_floor, "$lt": end_exclusive}, **({"user_id": user_id} if user_id else {}), **({"team_id": team_id} if team_id else {}), **({"space": space_id} if space_id else {})}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results_by_status = list(ActivityEvent._get_collection().aggregate(wf_status_pipeline))

    # Get top users/teams
    top_users_pipeline = [
        {"$match": {"scope": "user", "date": {"$gte": start_floor, "$lt": end_exclusive}}},
        {"$group": {"_id": "$user_id", "completed": {"$sum": "$workflows_completed"}}},
        {"$sort": {"completed": -1}},
        {"$limit": 10},
    ]
    top_users = list(DailyUsageAggregate._get_collection().aggregate(top_users_pipeline))

    top_teams_pipeline = [
        {"$match": {"scope": "team", "date": {"$gte": start_floor, "$lt": end_exclusive}}},
        {"$group": {"_id": "$team_id", "completed": {"$sum": "$workflows_completed"}}},
        {"$sort": {"completed": -1}},
        {"$limit": 10},
    ]
    top_teams = list(DailyUsageAggregate._get_collection().aggregate(top_teams_pipeline))

    # Get recent events
    ev_q = ActivityEvent.objects(started_at__gte=start_floor, started_at__lt=end_exclusive)
    if user_id:
        ev_q = ev_q.filter(user_id=user_id)
    if team_id:
        ev_q = ev_q.filter(team_id=team_id)
    if space_id:
        ev_q = ev_q.filter(space=space_id)
    recent_events = list(ev_q.order_by("-started_at").limit(20))

    # Build report data structure
    report_data = {
        "period": f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        "filters": {
            "user": user_id or "All",
            "team": team_id or "All",
            "space": space_id or "All",
        },
        "kpis": {
            "conversations": conversations,
            "searches": searches,
            "workflows_started": wf_started,
            "workflows_completed": wf_completed,
            "workflows_failed": wf_failed,
            "tokens_input": f"{tokens_in:,}",
            "tokens_output": f"{tokens_out:,}",
            "avg_workflow_duration_ms": int(avg_wf_ms),
            "active_users": active_users,
            "active_teams": active_teams,
        },
        "workflow_status": [{"status": r["_id"], "count": r["count"]} for r in results_by_status],
        "top_users": [{"user_id": u["_id"], "completed": u["completed"]} for u in top_users],
        "top_teams": [{"team_id": t["_id"], "completed": t["completed"]} for t in top_teams],
        "recent_activity": [
            {
                "type": ev.type,
                "started_at": ev.started_at.strftime('%Y-%m-%d %H:%M'),
                "status": ev.status,
                "user_id": ev.user_id,
                "team_id": ev.team_id or "",
                "details": _format_event_details(ev),
            }
            for ev in recent_events
        ],
    }

    # Create prompt for LLM with strict CSS requirements
    prompt = f"""Create a professional, well-formatted HTML report for the following usage analytics data.

CRITICAL CSS REQUIREMENTS (for PDF generation):
- DO NOT use CSS variables (no var(--anything))
- Use ONLY hex color codes (e.g., #2563eb, #f1f5f9)
- Use ONLY inline CSS or <style> tags with concrete values
- Avoid complex CSS features (no grid, no flexbox for critical layout)
- Use simple tables for layout if needed
- All colors must be in #RRGGBB or #RGB format

Design requirements:
- A header with the report title "Usage & Activity Report"
- The date range: {report_data['period']}
- Filter information: User={report_data['filters']['user']}, Team={report_data['filters']['team']}, Space={report_data['filters']['space']}
- KPI cards showing key metrics in a simple layout (use tables if needed)
- Tables for workflow status breakdown, top users, and top teams
- A section for recent activity
- Use professional colors with HEX codes, proper spacing, and make it print-friendly
- Simple, clean design that works well for PDF generation

Here's the data:

KEY METRICS:
- Conversations: {report_data['kpis']['conversations']}
- Searches: {report_data['kpis']['searches']}
- Workflows Started: {report_data['kpis']['workflows_started']}
- Workflows Completed: {report_data['kpis']['workflows_completed']}
- Workflows Failed: {report_data['kpis']['workflows_failed']}
- Tokens Input: {report_data['kpis']['tokens_input']}
- Tokens Output: {report_data['kpis']['tokens_output']}
- Avg Workflow Duration: {report_data['kpis']['avg_workflow_duration_ms']} ms
- Active Users: {report_data['kpis']['active_users']}
- Active Teams: {report_data['kpis']['active_teams']}

WORKFLOW STATUS:
{report_data['workflow_status'] if report_data['workflow_status'] else 'No workflow activity'}

TOP USERS:
{report_data['top_users'] if report_data['top_users'] else 'No user data'}

TOP TEAMS:
{report_data['top_teams'] if report_data['top_teams'] else 'No team data'}

RECENT ACTIVITY (last 20):
{report_data['recent_activity'] if report_data['recent_activity'] else 'No recent activity'}

Generate a complete HTML document with inline CSS. Use simple table-based layouts where needed. Make it professional and readable."""

    # Get model config
    user = load_user()
    model_config = UserModelConfig.objects(user_id=user.get_id()).first()
    model = model_config.name if model_config else settings.base_model

    # Generate HTML using LLM
    chat_agent = create_chat_agent(model)
    formatted_html = asyncio.run(chat_agent.run(prompt))
    formatted_html = formatted_html.output.strip("`").strip()
    
    # Remove markdown code fences if present
    if formatted_html.startswith("html"):
        formatted_html = formatted_html[4:].strip()
    
    debug("Generated HTML length:", len(formatted_html))
    debug("First 500 chars:", formatted_html[:500])

    try:
        # Generate PDF
        pdf_buffer = generate_pdf_from_html(formatted_html)
        
        # Generate filename
        filename = f"usage_report_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        debug(f"PDF generation error: {e}")
        # Return the HTML for debugging
        return Response(formatted_html, mimetype="text/html")


def _format_event_details(ev: ActivityEvent) -> str:
    """Format event details for the report."""
    if ev.type == "workflow_run":
        workflow_name = "(workflow)"
        if ev.meta_summary and ev.meta_summary.get("workflow_name"):
            workflow_name = ev.meta_summary["workflow_name"]
        elif ev.workflow:
            workflow_name = ev.workflow.name
        return f"{workflow_name} — Steps {ev.steps_completed or 0}/{ev.steps_total or 0}"
    elif ev.type == "search_set_run":
        if ev.meta_summary:
            return ev.meta_summary.get("search_set_title", "")
        return ev.search_set_uuid or ""
    elif ev.type == "conversation":
        model = ev.meta_summary.get("model", "") if ev.meta_summary else ""
        return f"{model} · {ev.message_count or 0} msgs"
    return ""
