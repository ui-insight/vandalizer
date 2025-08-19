# admin_routes.py (or wherever your Flask routes live)
from datetime import datetime, timedelta

from flask import Blueprint, abort, render_template, request
from flask_login import current_user

from app.models import (
    Feedback,
    SearchSet,
    SearchSetItem,
    SmartDocument,
    Space,
    User,
    Workflow,
    WorkflowResult,
)

admin = Blueprint("admin", __name__)


def parse_date(s: str, default: datetime) -> datetime:
    try:
        # Accept YYYY-MM-DD or ISO-like
        return datetime.fromisoformat(s.strip())
    except Exception:
        return default


def get_admin_user():
    # Require admin
    u = (
        User.objects(user_id=str(current_user.id)).first()
        if hasattr(current_user, "id")
        else None
    )
    if not u or not u.is_admin:
        abort(403)
    return u


@admin.route("/usage", methods=["GET"])
# @login_required
def usage_dashboard():
    # get_admin_user()

    # Date range (defaults: last 30 days)
    end_default = datetime.now()
    start_default = end_default - timedelta(days=30)
    start = parse_date(request.args.get("start", ""), start_default)
    end = parse_date(request.args.get("end", ""), end_default)

    # Optional filters
    user_id = request.args.get("user_id", "").strip() or None
    space_id = request.args.get("space_id", "").strip() or None

    # Build base filters
    doc_q = SmartDocument.objects(created_at__gte=start, created_at__lte=end)
    wf_q = Workflow.objects(created_at__gte=start, created_at__lte=end)
    wfr_q = WorkflowResult.objects(start_time__gte=start, start_time__lte=end)
    fb_q = Feedback.objects(created_at__gte=start, created_at__lte=end)
    ss_q = SearchSet.objects(created_at__gte=start, created_at__lte=end)

    if user_id:
        doc_q = doc_q.filter(user_id=user_id)
        wf_q = wf_q.filter(user_id=user_id)
        fb_q = fb_q.filter(user_id=user_id)
        ss_q = ss_q.filter(user_id=user_id)
        wfr_q = wfr_q  # WorkflowResult has session_id, not user_id; skip narrowing unless you store it in steps_output

    if space_id:
        doc_q = doc_q.filter(space=space_id)
        wf_q = wf_q.filter(space=space_id)
        ss_q = ss_q.filter(space=space_id)

    # === High-level KPIs ===
    kpi = {
        "total_users": User.objects.count(),
        "total_spaces": Space.objects.count(),
        "total_documents": SmartDocument.objects.count(),
        "total_workflows": Workflow.objects.count(),
        "total_results": WorkflowResult.objects.count(),
    }

    # === In-range metrics ===
    in_range = {
        "docs_count": doc_q.count(),
        "docs_processing": doc_q.filter(processing=True).count(),
        "docs_validating": doc_q.filter(validating=True).count(),
        "docs_invalid": doc_q.filter(valid=False).count(),
        "workflows_count": wf_q.count(),
        "workflow_results_count": wfr_q.count(),
        "feedback_count": fb_q.count(),
        "feedback_positive": fb_q.filter(feedback="positive").count(),
        "feedback_negative": fb_q.filter(feedback="negative").count(),
        "search_sets_count": ss_q.count(),
        "search_items_count": SearchSetItem.objects(
            searchset__in=[s.uuid for s in ss_q.only("uuid")]
        ).count(),
    }

    # === Top users by uploads (in range) ===
    pipeline_users = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}}},
        *([{"$match": {"user_id": user_id}}] if user_id else []),
        *([{"$match": {"space": space_id}}] if space_id else []),
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_users = list(SmartDocument.objects.aggregate(*pipeline_users))

    # === Top spaces by uploads (in range) ===
    pipeline_spaces = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}}},
        *([{"$match": {"user_id": user_id}}] if user_id else []),
        *([{"$match": {"space": space_id}}] if space_id else []),
        {"$group": {"_id": "$space", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_spaces = list(SmartDocument.objects.aggregate(*pipeline_spaces))

    # === Result status breakdown (in range) ===
    results_by_status = (
        wfr_q.only("status")
        .as_pymongo()
        .aggregate(
            [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
        )
    )
    results_by_status = list(results_by_status)

    # === Recent Activity (last 25 of each) ===
    recent_docs = doc_q.order_by("-created_at").limit(25)
    recent_results = wfr_q.order_by("-start_time").limit(25)
    recent_feedback = fb_q.order_by("-created_at").limit(25)

    # For select options
    all_users = User.objects.only("user_id").order_by("user_id")
    all_spaces = Space.objects.only("uuid", "title").order_by("title")

    return render_template(
        "admin/usage.html",
        kpi=kpi,
        in_range=in_range,
        start=start,
        end=end,
        user_id=user_id or "",
        space_id=space_id or "",
        top_users=top_users,
        top_spaces=top_spaces,
        results_by_status=results_by_status,
        recent_docs=recent_docs,
        recent_results=recent_results,
        recent_feedback=recent_feedback,
        all_users=all_users,
        all_spaces=all_spaces,
    )
